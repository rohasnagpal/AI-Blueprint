import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

import database
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.models import (
    BlueprintInstance,
    BlueprintMember,
    DocumentLink,
    KnowledgeChunk,
    KnowledgeDocument,
    Matter,
    SessionToken,
    User,
    Workspace,
    WorkspaceMember,
)
from app.core.security import hash_session_token
from webtools import format_search_context, web_search

router = APIRouter()


class CreateChat(BaseModel):
    doc_context: str = "none"
    persona_id: str | None = None
    v2_workspace_id: str | None = None
    v2_matter_id: str | None = None
    v2_blueprint_id: str | None = None
    v2_document_ids: list[str] | None = None


class SendMessage(BaseModel):
    message: str
    web_search: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_chat(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "doc_context": row["doc_context"],
        "persona_id": row["persona_id"] if "persona_id" in row.keys() else None,
        "v2_workspace_id": row["v2_workspace_id"] if "v2_workspace_id" in row.keys() else None,
        "v2_matter_id": row["v2_matter_id"] if "v2_matter_id" in row.keys() else None,
        "v2_blueprint_id": row["v2_blueprint_id"] if "v2_blueprint_id" in row.keys() else None,
        "v2_document_ids": _parse_json(row["v2_document_ids"], []) if "v2_document_ids" in row.keys() else [],
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


def _parse_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


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


def _get_v2_user(request: Request) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    with SessionLocal() as db:
        row = db.execute(
            select(SessionToken, User)
            .join(User, User.id == SessionToken.user_id)
            .where(SessionToken.token_hash == hash_session_token(token))
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        session, user = row
        if session.revoked_at or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        db.expunge(user)
        return user


def _optional_v2_user(request: Request) -> User | None:
    try:
        return _get_v2_user(request)
    except HTTPException:
        return None


def _user_can_access_v2_scope(user: User | None, scope: dict | None) -> bool:
    if not scope:
        return True
    if not user:
        return False
    with SessionLocal() as db:
        membership = db.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.workspace_id == scope["workspace_id"], WorkspaceMember.user_id == user.id)
        ).first()
        if not membership:
            return False
        _workspace_member, workspace = membership
        if workspace.deleted_at:
            return False
        if scope.get("blueprint_id"):
            blueprint_member = db.execute(
                select(BlueprintMember)
                .join(BlueprintInstance, BlueprintInstance.id == BlueprintMember.blueprint_id)
                .where(
                    BlueprintInstance.workspace_id == scope["workspace_id"],
                    BlueprintInstance.id == scope["blueprint_id"],
                    BlueprintMember.user_id == user.id,
                )
            ).scalar_one_or_none()
            return bool(blueprint_member)
    return True


def _require_v2_chat_access(request: Request, chat) -> None:
    scope = _v2_scope_from_chat(chat)
    if not scope:
        return
    user = _get_v2_user(request)
    if not _user_can_access_v2_scope(user, scope):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat access denied")


def _validate_v2_chat_scope(request: Request, body: CreateChat) -> dict | None:
    if not body.v2_workspace_id:
        return None
    user = _get_v2_user(request)
    document_ids = [doc_id for doc_id in (body.v2_document_ids or []) if doc_id]
    with SessionLocal() as db:
        membership = db.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.workspace_id == body.v2_workspace_id, WorkspaceMember.user_id == user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
        _workspace_member, workspace = membership
        if workspace.deleted_at:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if body.v2_matter_id:
            matter = db.execute(
                select(Matter).where(Matter.workspace_id == body.v2_workspace_id, Matter.id == body.v2_matter_id)
            ).scalar_one_or_none()
            if not matter:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
        if body.v2_blueprint_id:
            blueprint_row = db.execute(
                select(BlueprintInstance, BlueprintMember)
                .join(BlueprintMember, BlueprintMember.blueprint_id == BlueprintInstance.id)
                .where(
                    BlueprintInstance.workspace_id == body.v2_workspace_id,
                    BlueprintInstance.id == body.v2_blueprint_id,
                    BlueprintMember.user_id == user.id,
                )
            ).first()
            if not blueprint_row:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint access denied")
            blueprint, _blueprint_member = blueprint_row
            if not body.v2_matter_id and blueprint.matter_id:
                body.v2_matter_id = blueprint.matter_id
        if document_ids:
            count = db.execute(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.workspace_id == body.v2_workspace_id,
                    KnowledgeDocument.id.in_(document_ids),
                )
            ).all()
            if len(count) != len(set(document_ids)):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {
        "workspace_id": body.v2_workspace_id,
        "matter_id": body.v2_matter_id,
        "blueprint_id": body.v2_blueprint_id,
        "document_ids": document_ids,
    }


def _v2_scope_from_chat(chat) -> dict | None:
    workspace_id = chat["v2_workspace_id"] if "v2_workspace_id" in chat.keys() else None
    if not workspace_id:
        return None
    return {
        "workspace_id": workspace_id,
        "matter_id": chat["v2_matter_id"] if "v2_matter_id" in chat.keys() else None,
        "blueprint_id": chat["v2_blueprint_id"] if "v2_blueprint_id" in chat.keys() else None,
        "document_ids": _parse_json(chat["v2_document_ids"], []) if "v2_document_ids" in chat.keys() else [],
    }


@router.get("/chats")
async def list_chats(request: Request):
    user = _optional_v2_user(request)
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM chats WHERE archived_at IS NULL ORDER BY updated_at DESC").fetchall()
    conn.close()
    rows = [r for r in rows if _user_can_access_v2_scope(user, _v2_scope_from_chat(r))]
    return [_format_chat(r) for r in rows]


@router.post("/chats")
async def create_chat(body: CreateChat, request: Request):
    v2_scope = _validate_v2_chat_scope(request, body)
    chat_id = str(uuid.uuid4())
    now = _now()
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO chats (
            id, title, doc_context, persona_id, thread_id,
            v2_workspace_id, v2_matter_id, v2_blueprint_id, v2_document_ids,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat_id,
            None,
            body.doc_context,
            body.persona_id,
            None,
            v2_scope["workspace_id"] if v2_scope else None,
            v2_scope["matter_id"] if v2_scope else None,
            v2_scope["blueprint_id"] if v2_scope else None,
            json.dumps(v2_scope["document_ids"]) if v2_scope else "[]",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "id": chat_id,
        "title": None,
        "doc_context": body.doc_context,
        "persona_id": body.persona_id,
        "v2_workspace_id": v2_scope["workspace_id"] if v2_scope else None,
        "v2_matter_id": v2_scope["matter_id"] if v2_scope else None,
        "v2_blueprint_id": v2_scope["blueprint_id"] if v2_scope else None,
        "v2_document_ids": v2_scope["document_ids"] if v2_scope else [],
        "created_at": now,
        "updated_at": now,
    }


@router.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str, request: Request):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()
    _require_v2_chat_access(request, chat)
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)).fetchall()
    conn.close()
    return [_format_message(r) for r in rows]


@router.post("/chats/{chat_id}/message")
async def send_message(chat_id: str, body: SendMessage, request: Request):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()
    _require_v2_chat_access(request, chat)

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
    v2_scope = _v2_scope_from_chat(chat)

    return StreamingResponse(
        _stream(chat_id, chat, body.message, settings, provider_name, doc_ids, use_documents, persona, body.web_search, v2_scope),
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


async def _ensure_openai_indexed_documents(rows) -> tuple[list[str], list[str]]:
    from rag.openai_rag import OpenAIRag

    indexed_file_ids = []
    failed_names = []
    provider = OpenAIRag()

    for row in rows:
        if row["openai_file_id"]:
            indexed_file_ids.append(row["openai_file_id"])
            continue

        upload_path = Path("uploads") / row["filename"]
        if not upload_path.exists():
            failed_names.append(f"{row['original_name']} (uploaded file missing)")
            continue

        try:
            meta = await provider.ingest(str(upload_path), row["id"], row["original_name"])
            openai_file_id = meta.get("openai_file_id")
            if not openai_file_id:
                failed_names.append(row["original_name"])
                continue

            conn = database.get_connection()
            updates = ["openai_file_id = ?"]
            params = [openai_file_id]
            if "page_count" in meta:
                updates.append("page_count = ?")
                params.append(meta["page_count"])
            params.append(row["id"])
            conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            conn.close()
            indexed_file_ids.append(openai_file_id)
        except Exception as e:
            failed_names.append(f"{row['original_name']} ({e})")

    return indexed_file_ids, failed_names


async def _stream(
    chat_id: str,
    chat,
    message: str,
    settings: dict,
    provider_name: str,
    doc_ids: list[str] | None,
    use_documents: bool,
    persona: dict | None,
    use_web_search: bool,
    v2_scope: dict | None = None,
) -> AsyncGenerator[str, None]:
    collected_content = []
    collected_sources = []
    web_results = []

    try:
        if use_web_search:
            try:
                web_results = await web_search(message)
                for result in web_results:
                    src = {
                        "type": "source",
                        "kind": "web",
                        "filename": result.get("title") or result.get("url"),
                        "url": result.get("url"),
                        "excerpt": result.get("snippet", ""),
                    }
                    collected_sources.append(src)
                    yield f"data: {json.dumps(src)}\n\n"
            except Exception as e:
                yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'
                web_results = []
        if not use_documents:
            async for event in _stream_general(message, settings, persona, web_results):
                yield event
                data = _parse_sse(event)
                if data and data.get("type") == "token":
                    collected_content.append(data.get("content", ""))
        elif v2_scope:
            async for event in _stream_v2_documents(message, settings, v2_scope, persona, web_results):
                yield event
                data = _parse_sse(event)
                if data:
                    if data.get("type") == "token":
                        collected_content.append(data.get("content", ""))
                    elif data.get("type") == "source":
                        collected_sources.append(data)
        elif provider_name == "openai":
            async for event in _stream_openai(chat, message, settings, doc_ids, persona, web_results):
                yield event
                data = _parse_sse(event)
                if data:
                    if data.get("type") == "token":
                        collected_content.append(data.get("content", ""))
                    elif data.get("type") == "source":
                        collected_sources.append(data)
        else:
            async for event in _stream_local(message, settings, doc_ids, persona, web_results):
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


async def _stream_general(message: str, settings: dict, persona: dict | None, web_results: list[dict] | None = None) -> AsyncGenerator[str, None]:
    system_prompt = _apply_persona_prompt(_build_general_system_prompt(settings), persona)
    if web_results:
        system_prompt += "\nUse the provided web search results when relevant and cite source titles or URLs in the answer."
        message = f"Web search results:\n{format_search_context(web_results)}\n\nQuestion: {message}"
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    if llm_provider == "ollama":
        async for token in _stream_ollama(system_prompt, message, model, temperature, max_tokens, settings):
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


def _score_chunk(query_terms: set[str], text: str) -> int:
    lower = text.lower()
    return sum(1 for term in query_terms if term in lower)


def _v2_scope_name(scope: dict) -> str:
    if scope.get("document_ids"):
        return "selected v2 documents"
    if scope.get("blueprint_id"):
        return "this v2 blueprint"
    if scope.get("matter_id"):
        return "this v2 matter"
    return "this v2 workspace"


def _load_v2_chunks(scope: dict, message: str, top_k: int) -> list[dict]:
    query_terms = {t.lower() for t in message.split() if len(t) > 2}
    with SessionLocal() as db:
        query = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeDocument.workspace_id == scope["workspace_id"])
        )
        document_ids = scope.get("document_ids") or []
        if document_ids:
            query = query.where(KnowledgeDocument.id.in_(document_ids))
        elif scope.get("blueprint_id"):
            query = query.join(DocumentLink, DocumentLink.document_id == KnowledgeDocument.id).where(
                DocumentLink.workspace_id == scope["workspace_id"],
                DocumentLink.blueprint_id == scope["blueprint_id"],
            )
        elif scope.get("matter_id"):
            query = query.where(KnowledgeDocument.matter_id == scope["matter_id"])
        rows = db.execute(query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeChunk.chunk_index)).all()

    chunks = []
    for chunk, document in rows:
        chunks.append(
            {
                "document_id": document.id,
                "source": document.original_name,
                "content": chunk.content,
                "score": _score_chunk(query_terms, chunk.content),
                "scope": document.scope,
                "matter_id": document.matter_id,
            }
        )
    chunks.sort(key=lambda c: (c["score"], c["source"]), reverse=True)
    return chunks[:top_k]


async def _stream_v2_documents(message: str, settings: dict, scope: dict, persona: dict | None, web_results: list[dict] | None = None) -> AsyncGenerator[str, None]:
    top_k = int(settings.get("top_k", 5))
    chunks = _load_v2_chunks(scope, message, top_k)
    if not chunks:
        yield f'data: {json.dumps({"type": "error", "content": f"No indexed documents are available for {_v2_scope_name(scope)}."})}\n\n'
        return

    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['content']}" for c in chunks
    )
    system_prompt = _apply_persona_prompt(_build_system_prompt(settings), persona)
    system_prompt += f"\nLimit document-grounded claims to {_v2_scope_name(scope)}. Respect workspace, matter, blueprint, and document permissions."
    web_context = f"\n\nWeb search results:\n{format_search_context(web_results)}" if web_results else ""
    if web_results:
        system_prompt += "\nUse the supplied web search results when relevant and cite source titles or URLs."
    full_message = f"V2 document context:\n{context}{web_context}\n\nQuestion: {message}"
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    if llm_provider == "ollama":
        async for token in _stream_ollama(system_prompt, full_message, model, temperature, max_tokens, settings):
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

    for chunk in chunks:
        src = {
            "type": "source",
            "kind": "v2_document",
            "document_id": chunk["document_id"],
            "filename": chunk["source"],
            "page": None,
            "excerpt": chunk["content"][:200],
        }
        yield f'data: {json.dumps(src)}\n\n'


def _ollama_endpoint(settings: dict, path: str) -> str:
    base_url = (settings.get("ollama_base_url") or "http://localhost:11434").strip().rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _ollama_headers(settings: dict) -> dict[str, str]:
    api_key = (settings.get("ollama_api_key") or "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _stream_openai(
    chat,
    message: str,
    settings: dict,
    doc_ids: list[str] | None,
    persona: dict | None,
    web_results: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
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

    asst_id = None
    scoped_vs_id = None
    scoped_asst_id = None

    async def cleanup_scoped_resources():
        if scoped_asst_id:
            try:
                await client.beta.assistants.delete(scoped_asst_id)
            except Exception:
                pass
        if scoped_vs_id:
            try:
                await vector_stores.delete(scoped_vs_id)
            except Exception:
                pass

    try:
        conn = database.get_connection()
        if doc_ids is None:
            rows = conn.execute(
                "SELECT id, filename, original_name, openai_file_id FROM documents ORDER BY uploaded_at DESC"
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in doc_ids)
            rows = conn.execute(
                f"SELECT id, filename, original_name, openai_file_id FROM documents WHERE id IN ({placeholders})",
                doc_ids,
            ).fetchall()
        conn.close()
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": f"Failed to read selected documents: {e}"})}\n\n'
        return

    if not rows:
        yield f'data: {json.dumps({"type": "error", "content": "No current documents are available for OpenAI RAG."})}\n\n'
        return

    try:
        file_ids, failed_indexing = await _ensure_openai_indexed_documents(rows)
        if not file_ids:
            detail = f": {', '.join(failed_indexing)}" if failed_indexing else "."
            msg = f"No current documents could be indexed for OpenAI RAG{detail}"
            yield f'data: {json.dumps({"type": "error", "content": msg})}\n\n'
            return
        if failed_indexing:
            msg = f"Some selected documents could not be indexed and were skipped: {', '.join(failed_indexing)}"
            yield f'data: {json.dumps({"type": "error", "content": msg})}\n\n'

        scoped_vs = await vector_stores.create(name=f"AI Blueprint scoped chat {chat['id']}")
        scoped_vs_id = scoped_vs.id
        for file_id in file_ids:
            await vector_stores.files.create(vector_store_id=scoped_vs_id, file_id=file_id)
        for file_id in file_ids:
            for _ in range(30):
                vsf = await vector_stores.files.retrieve(vector_store_id=scoped_vs_id, file_id=file_id)
                if vsf.status == "completed":
                    break
                if vsf.status == "failed":
                    raise RuntimeError("OpenAI vector store indexing failed for a selected document")
                import asyncio
                await asyncio.sleep(1)
        model = settings.get("chat_model", "gpt-4o")
        scoped_asst = await client.beta.assistants.create(
            name="AI Blueprint Scoped Assistant",
            model=model,
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [scoped_vs_id]}},
        )
        scoped_asst_id = scoped_asst.id
        asst_id = scoped_asst_id
    except Exception as e:
        await cleanup_scoped_resources()
        yield f'data: {json.dumps({"type": "error", "content": f"Failed to prepare selected document search: {e}"})}\n\n'
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
            await cleanup_scoped_resources()
            yield f'data: {json.dumps({"type": "error", "content": f"Failed to create thread: {e}"})}\n\n'
            return

    # Add message to thread
    try:
        user_content = message
        if web_results:
            user_content = f"Web search results:\n{format_search_context(web_results)}\n\nQuestion: {message}"
        await client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_content,
        )
    except Exception as e:
        await cleanup_scoped_resources()
        yield f'data: {json.dumps({"type": "error", "content": f"Failed to send message: {e}"})}\n\n'
        return

    system_prompt = _apply_persona_prompt(_build_system_prompt(settings), persona)
    if web_results:
        system_prompt += "\nWhen web search results are supplied, use them alongside document context and cite source titles or URLs."
    top_k = int(settings.get("top_k", 5))
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    try:
        model = settings.get("chat_model", "gpt-4o")
        update_args = {
            "model": model,
            "tools": [{"type": "file_search", "file_search": {"max_num_results": top_k}}],
        }
        await client.beta.assistants.update(asst_id, **update_args)
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
    finally:
        await cleanup_scoped_resources()


async def _stream_local(message: str, settings: dict, doc_ids: list[str] | None, persona: dict | None, web_results: list[dict] | None = None) -> AsyncGenerator[str, None]:
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
    web_context = f"\n\nWeb search results:\n{format_search_context(web_results)}" if web_results else ""
    if web_results:
        system_prompt += "\nUse the supplied web search results when relevant and cite source titles or URLs."
    full_message = f"Document context:\n{context}{web_context}\n\nQuestion: {message}"
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = int(settings.get("max_tokens", 2048))

    if llm_provider == "ollama":
        async for token in _stream_ollama(system_prompt, full_message, model, temperature, max_tokens, settings):
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
    system: str, user: str, model: str, temperature: float, max_tokens: int, settings: dict | None = None
) -> AsyncGenerator[str, None]:
    import httpx
    settings = settings or {}
    ollama_model = model if model else "llama3"
    chat_url = _ollama_endpoint(settings, "/chat")
    headers = _ollama_headers(settings)
    if "ollama.com" in chat_url and not headers:
        yield f'data: {json.dumps({"type": "error", "content": "Ollama API key is not configured. Add it in Settings -> API Keys -> Ollama."})}\n\n'
        return
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                chat_url,
                headers=headers,
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
                if resp.status_code >= 400:
                    error_body = await resp.aread()
                    detail = error_body.decode("utf-8", errors="replace") or resp.reason_phrase
                    yield f'data: {json.dumps({"type": "error", "content": f"Ollama request failed ({resp.status_code}): {detail}"})}\n\n'
                    return
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
        base_url = (settings.get("ollama_base_url") or "http://localhost:11434").strip()
        local_hint = " Start local Ollama with: ollama serve" if "localhost" in base_url or "127.0.0.1" in base_url else ""
        yield f'data: {json.dumps({"type": "error", "content": f"Ollama request failed: {e}.{local_hint}"})}\n\n'


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()
    _require_v2_chat_access(request, chat)
    conn = database.get_connection()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/chats/{chat_id}/archive")
async def archive_chat(chat_id: str, request: Request):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()
    _require_v2_chat_access(request, chat)
    conn = database.get_connection()
    now = _now()
    conn.execute("UPDATE chats SET archived_at = ?, updated_at = ? WHERE id = ?", (now, now, chat_id))
    conn.commit()
    conn.close()
    return {"ok": True}
