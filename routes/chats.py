import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import database

router = APIRouter()


class CreateChat(BaseModel):
    doc_context: str = "all"
    persona_id: str | None = None


class SendMessage(BaseModel):
    message: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_chat(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "doc_context": row["doc_context"],
        "persona_id": row["persona_id"] if "persona_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "archived_at": row["archived_at"] if "archived_at" in row.keys() else None,
    }


def _format_message(row) -> dict:
    sources = []
    if row["sources"]:
        try:
            sources = json.loads(row["sources"])
        except Exception:
            pass
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "role": row["role"],
        "content": row["content"],
        "sources": sources,
        "created_at": row["created_at"],
    }


def _build_system_prompt(settings: dict) -> str:
    lang = settings.get("response_language", "English")
    length = settings.get("response_length", "balanced")
    return (
        f"You are AI Blueprint, a helpful document assistant.\n"
        f"Always respond in {lang}, regardless of the language the documents are written in.\n"
        f"Base your answers only on the provided document context.\n"
        f"If the answer is not found in the documents, say so clearly in {lang}.\n"
        f"Response length preference: {length}."
    )


def _apply_persona_prompt(prompt: str, persona: dict | None) -> str:
    if not persona:
        return prompt
    constraints = persona.get("constraints") or []
    parts = [
        prompt,
        "\nPersona:",
        f"Name: {persona.get('name', '')}",
        f"Instructions: {persona.get('system_prompt', '')}",
        "Write the final answer in natural prose or markdown. Do not output JSON unless the user explicitly asks for JSON.",
    ]
    if constraints:
        parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in constraints))
    return "\n".join(parts)


def _build_general_system_prompt(settings: dict) -> str:
    lang = settings.get("response_language", "English")
    length = settings.get("response_length", "balanced")
    return (
        f"You are AI Blueprint, a helpful assistant.\n"
        f"Always respond in {lang}.\n"
        f"Answer the user's question directly without using uploaded document context.\n"
        f"Response length preference: {length}."
    )


def _get_persona(persona_id: str | None) -> dict | None:
    if not persona_id:
        return None
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM personas WHERE id = ? AND is_enabled = 1", (persona_id,)).fetchone()
    conn.close()
    if not row:
        return None
    def parse(value, fallback):
        if not value:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "system_prompt": row["system_prompt"],
        "constraints": parse(row["constraints_json"], []),
        "output_format": parse(row["output_format_json"], {}),
        "tags": parse(row["tags_json"], []),
    }


@router.get("/chats")
async def list_chats():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM chats WHERE archived_at IS NULL ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [_format_chat(r) for r in rows]


@router.post("/chats")
async def create_chat(body: CreateChat):
    chat_id = str(uuid.uuid4())
    now = _now()
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO chats (id, title, doc_context, persona_id, thread_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, None, body.doc_context, body.persona_id, None, now, now),
    )
    conn.commit()
    conn.close()
    return {"id": chat_id, "title": None, "doc_context": body.doc_context, "persona_id": body.persona_id, "created_at": now, "updated_at": now}


@router.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    rows = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)).fetchall()
    conn.close()
    return [_format_message(r) for r in rows]


@router.post("/chats/{chat_id}/message")
async def send_message(chat_id: str, body: SendMessage):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()

    user_msg_id = str(uuid.uuid4())
    now = _now()
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO messages (id, chat_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_msg_id, chat_id, "user", body.message, "[]", now),
    )
    # Set chat title from first message
    if not chat["title"]:
        title = body.message[:60]
        conn.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?", (title, now, chat_id))
    else:
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    conn.commit()
    conn.close()

    settings = database.get_all_settings()
    for k in database.API_KEY_FIELDS:
        settings[k] = database.get_setting(k)

    # Auto-detect language
    if settings.get("auto_detect_language") == "true":
        settings["response_language"] = _detect_language(body.message)

    provider_name = settings.get("rag_provider", "openai")
    doc_context = chat["doc_context"]
    use_documents = doc_context != "none"
    doc_ids = None if doc_context in ("all", "none") else [d.strip() for d in doc_context.split(",") if d.strip()]
    persona = _get_persona(chat["persona_id"] if "persona_id" in chat.keys() else None)

    return StreamingResponse(
        _stream(chat_id, chat, body.message, settings, provider_name, doc_ids, use_documents, persona),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _detect_language(text: str) -> str:
    # Simple heuristic: check for common non-ASCII chars
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii > len(text) * 0.3:
        return "auto"  # Fall back to English if we can't detect
    return "English"


def _openai_vector_stores(client):
    if hasattr(client, "vector_stores"):
        return client.vector_stores
    if hasattr(client, "beta") and hasattr(client.beta, "vector_stores"):
        return client.beta.vector_stores
    raise RuntimeError(
        "This OpenAI SDK does not expose vector stores. Upgrade with: pip install -U openai"
    )


async def _stream(
    chat_id: str,
    chat,
    message: str,
    settings: dict,
    provider_name: str,
    doc_ids: list[str] | None,
    use_documents: bool,
    persona: dict | None,
) -> AsyncGenerator[str, None]:
    collected_content = []
    collected_sources = []

    try:
        if not use_documents:
            async for event in _stream_general(message, settings, persona):
                yield event
                data = _parse_sse(event)
                if data and data.get("type") == "token":
                    collected_content.append(data.get("content", ""))
        elif provider_name == "openai":
            async for event in _stream_openai(chat, message, settings, persona):
                yield event
                data = _parse_sse(event)
                if data:
                    if data.get("type") == "token":
                        collected_content.append(data.get("content", ""))
                    elif data.get("type") == "source":
                        collected_sources.append(data)
        else:
            async for event in _stream_local(message, settings, doc_ids, persona):
                yield event
                data = _parse_sse(event)
                if data:
                    if data.get("type") == "token":
                        collected_content.append(data.get("content", ""))
                    elif data.get("type") == "source":
                        collected_sources.append(data)
    except Exception as e:
        err_event = f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'
        yield err_event

    # Save assistant message
    full_content = "".join(collected_content)
    if full_content:
        now = _now()
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), chat_id, "assistant", full_content, json.dumps(collected_sources), now),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        conn.commit()
        conn.close()

    yield f'data: {json.dumps({"type": "done"})}\n\n'


async def _stream_general(message: str, settings: dict, persona: dict | None) -> AsyncGenerator[str, None]:
    system_prompt = _apply_persona_prompt(_build_general_system_prompt(settings), persona)
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    if llm_provider == "ollama":
        async for token in _stream_ollama(system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "anthropic":
        anthropic_key = settings.get("anthropic_api_key", "")
        if not anthropic_key:
            yield f'data: {json.dumps({"type": "error", "content": "Anthropic API key not configured."})}\n\n'
            return
        async for token in _stream_anthropic(anthropic_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "groq":
        groq_key = settings.get("groq_api_key", "")
        if not groq_key:
            yield f'data: {json.dumps({"type": "error", "content": "Groq API key not configured."})}\n\n'
            return
        async for token in _stream_groq(groq_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    else:
        openai_key = settings.get("openai_api_key", "")
        if not openai_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenAI API key not configured. Go to Settings → API Keys."})}\n\n'
            return
        async for token in _stream_openai_chat(openai_key, system_prompt, message, model, temperature, max_tokens):
            yield token


def _parse_sse(event: str) -> dict | None:
    if event.startswith("data: "):
        try:
            return json.loads(event[6:])
        except Exception:
            pass
    return None


async def _stream_openai(chat, message: str, settings: dict, persona: dict | None) -> AsyncGenerator[str, None]:
    import openai

    key = settings.get("openai_api_key", "")
    if not key:
        yield f'data: {json.dumps({"type": "error", "content": "OpenAI API key not configured. Go to Settings → API Keys."})}\n\n'
        return

    client = openai.AsyncOpenAI(api_key=key)
    try:
        vector_stores = _openai_vector_stores(client)
    except RuntimeError as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'
        return

    # Ensure vector store and assistant
    vs_id = settings.get("vector_store_id", "")
    asst_id = settings.get("assistant_id", "")

    if not vs_id:
        try:
            vs = await vector_stores.create(name="AI Blueprint")
            vs_id = vs.id
            database.set_setting("vector_store_id", vs_id)
            settings["vector_store_id"] = vs_id
        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "content": f"Failed to create vector store: {e}"})}\n\n'
            return

    if not asst_id:
        try:
            model = settings.get("chat_model", "gpt-4o")
            asst = await client.beta.assistants.create(
                name="AI Blueprint Assistant",
                model=model,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [vs_id]}},
            )
            asst_id = asst.id
            database.set_setting("assistant_id", asst_id)
            settings["assistant_id"] = asst_id
        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "content": f"Failed to create assistant: {e}"})}\n\n'
            return

    # Get or create thread
    chat_id = chat["id"]
    thread_id = chat["thread_id"]
    if not thread_id:
        try:
            thread = await client.beta.threads.create()
            thread_id = thread.id
            conn = database.get_connection()
            conn.execute("UPDATE chats SET thread_id = ? WHERE id = ?", (thread_id, chat_id))
            conn.commit()
            conn.close()
        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "content": f"Failed to create thread: {e}"})}\n\n'
            return

    # Add message to thread
    try:
        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message,
        )
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": f"Failed to send message: {e}"})}\n\n'
        return

    system_prompt = _apply_persona_prompt(_build_system_prompt(settings), persona)
    top_k = int(settings.get("top_k", 5))
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    try:
        model = settings.get("chat_model", "gpt-4o")
        await client.beta.assistants.update(
            asst_id,
            model=model,
            tools=[{"type": "file_search", "file_search": {"max_num_results": top_k}}],
        )
    except Exception:
        pass

    seen_sources = set()
    try:
        async with client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=asst_id,
            additional_instructions=system_prompt,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        ) as stream:
            async for text_delta in stream.text_deltas:
                yield f'data: {json.dumps({"type": "token", "content": text_delta})}\n\n'

            # Extract citations from final messages
            try:
                final_msgs = await stream.get_final_messages()
                for msg in final_msgs:
                    if msg.role != "assistant":
                        continue
                    for block in (msg.content or []):
                        if hasattr(block, "text") and hasattr(block.text, "annotations"):
                            for ann in block.text.annotations:
                                if ann.type == "file_citation":
                                    fid = ann.file_citation.file_id
                                    if fid in seen_sources:
                                        continue
                                    seen_sources.add(fid)
                                    conn = database.get_connection()
                                    row = conn.execute(
                                        "SELECT original_name FROM documents WHERE openai_file_id = ?", (fid,)
                                    ).fetchone()
                                    conn.close()
                                    fname = row["original_name"] if row else fid
                                    src = {"type": "source", "filename": fname, "page": None, "excerpt": ""}
                                    yield f'data: {json.dumps(src)}\n\n'
            except Exception:
                pass
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_local(message: str, settings: dict, doc_ids: list[str] | None, persona: dict | None) -> AsyncGenerator[str, None]:
    from rag.llamaindex_rag import LlamaIndexRag

    provider = LlamaIndexRag()
    top_k = int(settings.get("top_k", 5))
    threshold = float(settings.get("similarity_threshold", 0.72))

    try:
        chunks = await provider.retrieve(message, doc_ids, top_k, threshold)
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": f"Retrieval failed: {e}"})}\n\n'
        return

    if not chunks:
        context = "No relevant document sections found."
    else:
        context = "\n\n---\n\n".join(
            f"[Source: {c['source']}]\n{c['content']}" for c in chunks
        )

    system_prompt = _apply_persona_prompt(_build_system_prompt(settings), persona)
    llm_provider = settings.get("local_llm_provider", "openai")
    full_message = f"Document context:\n{context}\n\nQuestion: {message}"
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    if llm_provider == "ollama":
        async for token in _stream_ollama(system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "anthropic":
        anthropic_key = settings.get("anthropic_api_key", "")
        if not anthropic_key:
            yield f'data: {json.dumps({"type": "error", "content": "Anthropic API key not configured."})}\n\n'
            return
        async for token in _stream_anthropic(anthropic_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "groq":
        groq_key = settings.get("groq_api_key", "")
        if not groq_key:
            yield f'data: {json.dumps({"type": "error", "content": "Groq API key not configured."})}\n\n'
            return
        async for token in _stream_groq(groq_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    else:
        openai_key = settings.get("openai_api_key", "")
        if not openai_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenAI API key not configured. Go to Settings → API Keys."})}\n\n'
            return
        async for token in _stream_openai_chat(openai_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token

    # Emit sources
    for chunk in chunks:
        src = {
            "type": "source",
            "filename": chunk["source"],
            "page": chunk.get("page"),
            "excerpt": chunk["content"][:200],
        }
        yield f'data: {json.dumps(src)}\n\n'


async def _stream_openai_chat(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import openai
    client = openai.AsyncOpenAI(api_key=key)
    try:
        async with await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield f'data: {json.dumps({"type": "token", "content": delta})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_groq(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=key)
        groq_model = model if "llama" in model.lower() or "mixtral" in model.lower() else "llama-3.1-8b-instant"
        stream = await client.chat.completions.create(
            model=groq_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield f'data: {json.dumps({"type": "token", "content": delta})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_anthropic(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model or "claude-3-5-sonnet-latest",
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except Exception:
                        continue
                    if data.get("type") == "content_block_delta":
                        text = data.get("delta", {}).get("text", "")
                        if text:
                            yield f'data: {json.dumps({"type": "token", "content": text})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_ollama(
    system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import httpx
    ollama_model = model if model else "llama3"
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Check Ollama is reachable
            try:
                await client.get("http://localhost:11434")
            except Exception:
                yield f'data: {json.dumps({"type": "error", "content": "Ollama is not running. Start it with: ollama serve"})}\n\n'
                return

            async with client.stream(
                "POST",
                "http://localhost:11434/api/chat",
                json={
                    "model": ollama_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": True,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield f'data: {json.dumps({"type": "token", "content": content})}\n\n'
                    except Exception:
                        pass
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/chats/{chat_id}/archive")
async def archive_chat(chat_id: str):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    now = _now()
    conn.execute("UPDATE chats SET archived_at = ?, updated_at = ? WHERE id = ?", (now, now, chat_id))
    conn.commit()
    conn.close()
    return {"ok": True}
