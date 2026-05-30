import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Depends
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
from webtools import enrich_search_results, format_search_context, web_search
from app.core.deps import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


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


class BulkChatDelete(BaseModel):
    ids: list[str]


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


def _is_contract_reviewer(persona: dict | None) -> bool:
    if not persona:
        return False
    haystack = " ".join(
        str(persona.get(key, ""))
        for key in ("id", "name", "description", "system_prompt")
    ).lower()
    return "contract reviewer" in haystack or "contract review" in haystack or "cuad" in haystack


def _document_review_query(message: str, persona: dict | None) -> str:
    if not _is_contract_reviewer(persona):
        return message
    return (
        f"{message}\n\n"
        "Review the selected contract document. Retrieve broad contract context including parties, dates, "
        "term, renewal, termination, assignment, governing law, payment, confidentiality, indemnity, "
        "liability, warranties, IP, audit, insurance, and dispute clauses."
    )


def _document_review_message(message: str, persona: dict | None, filenames: list[str]) -> str:
    if not _is_contract_reviewer(persona):
        return message
    names = ", ".join(name for name in filenames if name) or "the selected uploaded document(s)"
    return (
        f"The selected document(s) for review are: {names}.\n\n"
        "Use the document search tool/context to review those document(s). Do not ask the user to identify "
        "a document unless no selected document content is available.\n\n"
        f"User request: {message}"
    )


def _status_event(message: str, progress: int | None = None) -> str:
    payload = {"type": "status", "content": message}
    if progress is not None:
        payload["progress"] = progress
    return f"data: {json.dumps(payload)}\n\n"


def _max_tokens_for_persona(settings: dict, persona: dict | None) -> int:
    configured = int(settings.get("max_tokens", 2048))
    if _is_contract_reviewer(persona):
        return max(configured, 6000)
    return configured


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
    ]
    output_format = persona.get("output_format") or {}
    if output_format.get("type") == "json":
        parts.append("Follow the persona's required output format exactly.")
    elif _is_contract_reviewer(persona):
        parts.append("Write the final answer in clean markdown using the persona's STEP structure. Do not output HTML, JSON, or code fences unless the user explicitly asks for them.")
    else:
        parts.append("Write the final answer in natural prose or markdown. Do not output JSON unless the user explicitly asks for JSON.")
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


def _build_help_system_prompt(settings: dict) -> str:
    lang = settings.get("response_language", "English")
    return (
        "You are AI Blueprint's product help assistant. "
        f"Always respond in {lang}. "
        "Answer only from the supplied AI Blueprint help context and current app context. "
        "Give practical, step-by-step UI guidance. "
        "If the help context does not contain the answer, say you do not know from the help docs and suggest the closest relevant area. "
        "Do not provide legal advice while answering product-use questions."
    )


def _help_docs_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "help"


def _help_chunks() -> list[dict]:
    chunks = []
    root = _help_docs_dir()
    if not root.exists():
        return chunks
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = path.stem.replace("-", " ").title()
        current_heading = title
        current_lines = []

        def flush():
            body = "\n".join(current_lines).strip()
            if body:
                chunks.append(
                    {
                        "title": title,
                        "section": current_heading,
                        "source": str(path.relative_to(Path(__file__).resolve().parents[1])),
                        "content": body,
                    }
                )

        for line in text.splitlines():
            heading = re.match(r"^(#{1,3})\s+(.+)$", line)
            if heading:
                flush()
                current_heading = heading.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)
        flush()
    return chunks


def _score_help_chunk(query_terms: set[str], chunk: dict) -> int:
    title_text = f"{chunk['title']} {chunk['section']}".lower()
    source_text = chunk["source"].lower().replace("-", " ")
    content_text = chunk["content"].lower()
    title_terms = set(re.findall(r"[a-zA-Z0-9_]+", title_text))
    source_terms = set(re.findall(r"[a-zA-Z0-9_]+", source_text))
    content_terms = set(re.findall(r"[a-zA-Z0-9_]+", content_text))
    score = 0
    for term in query_terms:
        if term in title_terms:
            score += 5
        if term in source_terms:
            score += 4
        if term in content_terms:
            score += 1
    return score


def _search_help(message: str, limit: int = 5) -> list[dict]:
    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", message) if len(term) > 2}
    expansions = {
        "translate": {"translate", "translation", "translations", "translated", "translating"},
        "translation": {"translate", "translation", "translations", "translated", "translating"},
        "persona": {"persona", "personas"},
        "personas": {"persona", "personas"},
        "create": {"create", "creating", "created"},
        "sync": {"sync", "synced", "synchronization"},
        "folder": {"folder", "folders"},
        "document": {"document", "documents"},
        "documents": {"document", "documents"},
        "blueprint": {"blueprint", "blueprints"},
        "plugin": {"plugin", "plugins"},
        "matter": {"matter", "matters"},
        "workspace": {"workspace", "workspaces"},
    }
    expanded_terms = set()
    for term in terms:
        expanded_terms.update(expansions.get(term, {term}))
    terms = expanded_terms
    chunks = _help_chunks()
    if not terms:
        return chunks[:limit]
    scored = [(chunk, _score_help_chunk(terms, chunk)) for chunk in chunks]
    scored.sort(key=lambda item: (item[1], item[0]["title"], item[0]["section"]), reverse=True)
    matches = [chunk for chunk, score in scored if score > 0]
    return (matches or chunks[:limit])[:limit]


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
async def list_chats(request: Request, archived: bool = False):
    user = _optional_v2_user(request)
    conn = database.get_connection()
    where = "archived_at IS NOT NULL" if archived else "archived_at IS NULL"
    rows = conn.execute(f"SELECT * FROM chats WHERE {where} ORDER BY updated_at DESC").fetchall()
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
    use_help = doc_context == "help"
    use_documents = doc_context not in ("none", "help")
    doc_ids = None if doc_context in ("all", "none", "help") else [d.strip() for d in doc_context.split(",") if d.strip()]
    persona = _get_persona(chat["persona_id"] if "persona_id" in chat.keys() else None)
    v2_scope = _v2_scope_from_chat(chat)

    return StreamingResponse(
        _stream(chat_id, chat, body.message, settings, provider_name, doc_ids, use_documents, persona, body.web_search, v2_scope, use_help),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _detect_language(text: str) -> str:
    # Simple heuristic: check for common non-ASCII chars
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii > len(text) * 0.3:
        return "auto"  # Fall back to English if we can't detect
    return "English"


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
    use_help: bool = False,
) -> AsyncGenerator[str, None]:
    collected_content = []
    collected_sources = []
    web_results = []

    try:
        if use_web_search:
            try:
                yield _status_event("Searching the web", 6)
                web_results = await web_search(message)
                yield _status_event("Reading top web sources", 9)
                web_results = await enrich_search_results(web_results)
                for result in web_results:
                    src = {
                        "type": "source",
                        "kind": "web",
                        "filename": result.get("title") or result.get("url"),
                        "url": result.get("url"),
                        "excerpt": result.get("page_excerpt") or result.get("snippet", ""),
                    }
                    collected_sources.append(src)
                    yield f"data: {json.dumps(src)}\n\n"
            except Exception as e:
                yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'
                web_results = []
        if use_help:
            async for event in _stream_help(message, settings, persona):
                yield event
                data = _parse_sse(event)
                if data:
                    if data.get("type") == "token":
                        collected_content.append(data.get("content", ""))
                    elif data.get("type") == "source":
                        collected_sources.append(data)
        elif not use_documents:
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
        else:
            yield f'data: {json.dumps({"type": "error", "content": "Document search now requires a workspace document scope. Start a new document chat from the current workspace."})}\n\n'
    except Exception as e:
        err_event = f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'
        yield err_event

    # Save assistant message
    full_content = "".join(collected_content)
    if full_content:
        now = _now()
        assistant_message_id = str(uuid.uuid4())
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (assistant_message_id, chat_id, "assistant", full_content, json.dumps(collected_sources), now),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        conn.commit()
        conn.close()

    yield f'data: {json.dumps({"type": "done"})}\n\n'


async def _stream_help(message: str, settings: dict, persona: dict | None) -> AsyncGenerator[str, None]:
    yield _status_event("Searching AI Blueprint help", 18)
    chunks = _search_help(message)
    if not chunks:
        yield f'data: {json.dumps({"type": "error", "content": "No help documentation is available."})}\n\n'
        return

    for chunk in chunks:
        src = {
            "type": "source",
            "kind": "help",
            "filename": chunk["source"],
            "excerpt": chunk["section"],
        }
        yield f"data: {json.dumps(src)}\n\n"

    help_context = "\n\n---\n\n".join(
        f"[{chunk['source']} > {chunk['section']}]\n{chunk['content'][:2200]}"
        for chunk in chunks
    )
    system_prompt = _apply_persona_prompt(_build_help_system_prompt(settings), persona)
    full_message = (
        "AI Blueprint help context:\n"
        f"{help_context}\n\n"
        "Current app context:\n"
        "- User selected Help mode in chat.\n"
        "- Treat this as a product-use question, not a legal document question.\n\n"
        f"User help request: {message}"
    )
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = _max_tokens_for_persona(settings, persona)
    yield _status_event("Generating help answer", 55)

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
    elif llm_provider == "openrouter":
        openrouter_key = settings.get("openrouter_api_key", "")
        if not openrouter_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenRouter API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_openrouter_chat(openrouter_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "gemini":
        gemini_key = settings.get("gemini_api_key", "")
        if not gemini_key:
            yield f'data: {json.dumps({"type": "error", "content": "Google Gemini API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_gemini(gemini_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "perplexity":
        perplexity_key = settings.get("perplexity_api_key", "")
        if not perplexity_key:
            yield f'data: {json.dumps({"type": "error", "content": "Perplexity API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_perplexity(perplexity_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "mistral":
        mistral_key = settings.get("mistral_api_key", "")
        if not mistral_key:
            yield f'data: {json.dumps({"type": "error", "content": "Mistral API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_mistral(mistral_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "xai":
        xai_key = settings.get("xai_api_key", "")
        if not xai_key:
            yield f'data: {json.dumps({"type": "error", "content": "xAI API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_xai_chat(xai_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    else:
        openai_key = settings.get("openai_api_key", "")
        if not openai_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenAI API key not configured. Go to Settings → API Keys."})}\n\n'
            return
        async for token in _stream_openai_chat(openai_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token


async def _stream_general(message: str, settings: dict, persona: dict | None, web_results: list[dict] | None = None) -> AsyncGenerator[str, None]:
    yield _status_event("Preparing model request", 20)
    system_prompt = _apply_persona_prompt(_build_general_system_prompt(settings), persona)
    if web_results:
        system_prompt += "\nUse the provided web search results when relevant and cite source titles or URLs in the answer."
        message = f"Web search results:\n{format_search_context(web_results)}\n\nQuestion: {message}"
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = _max_tokens_for_persona(settings, persona)

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
    elif llm_provider == "openrouter":
        openrouter_key = settings.get("openrouter_api_key", "")
        if not openrouter_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenRouter API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_openrouter_chat(openrouter_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "gemini":
        gemini_key = settings.get("gemini_api_key", "")
        if not gemini_key:
            yield f'data: {json.dumps({"type": "error", "content": "Google Gemini API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_gemini(gemini_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "perplexity":
        perplexity_key = settings.get("perplexity_api_key", "")
        if not perplexity_key:
            yield f'data: {json.dumps({"type": "error", "content": "Perplexity API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_perplexity(perplexity_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "mistral":
        mistral_key = settings.get("mistral_api_key", "")
        if not mistral_key:
            yield f'data: {json.dumps({"type": "error", "content": "Mistral API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_mistral(mistral_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "xai":
        xai_key = settings.get("xai_api_key", "")
        if not xai_key:
            yield f'data: {json.dumps({"type": "error", "content": "xAI API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_xai_chat(xai_key, system_prompt, message, model, temperature, max_tokens):
            yield token
    else:
        openai_key = settings.get("openai_api_key", "")
        if not openai_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenAI API key not configured. Go to Settings → API Keys."})}\n\n'
            return
        yield _status_event("Waiting for model response", 55)
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
    yield _status_event(f"Searching {_v2_scope_name(scope)}", 10)
    top_k = int(settings.get("top_k", 5))
    if _is_contract_reviewer(persona):
        top_k = max(top_k, 12)
    retrieval_query = _document_review_query(message, persona)
    chunks = _load_v2_chunks(scope, retrieval_query, top_k)
    if not chunks:
        yield f'data: {json.dumps({"type": "error", "content": f"No indexed documents are available for {_v2_scope_name(scope)}."})}\n\n'
        return

    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['content']}" for c in chunks
    )
    yield _status_event(f"Found {len(chunks)} relevant document section{'s' if len(chunks) != 1 else ''}", 35)
    system_prompt = _apply_persona_prompt(_build_system_prompt(settings), persona)
    system_prompt += f"\nLimit document-grounded claims to {_v2_scope_name(scope)}. Respect workspace, matter, blueprint, and document permissions."
    web_context = f"\n\nWeb search results:\n{format_search_context(web_results)}" if web_results else ""
    if web_results:
        system_prompt += "\nUse the supplied web search results when relevant and cite source titles or URLs."
    review_message = _document_review_message(message, persona, sorted({c["source"] for c in chunks}))
    full_message = f"V2 document context:\n{context}{web_context}\n\nQuestion: {review_message}"
    llm_provider = settings.get("local_llm_provider", "openai")
    model = settings.get("chat_model", "gpt-4o")
    temperature = float(settings.get("temperature", 0.2))
    max_tokens = _max_tokens_for_persona(settings, persona)
    yield _status_event("Generating document-grounded answer", 60)

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
    elif llm_provider == "openrouter":
        openrouter_key = settings.get("openrouter_api_key", "")
        if not openrouter_key:
            yield f'data: {json.dumps({"type": "error", "content": "OpenRouter API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_openrouter_chat(openrouter_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "gemini":
        gemini_key = settings.get("gemini_api_key", "")
        if not gemini_key:
            yield f'data: {json.dumps({"type": "error", "content": "Google Gemini API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_gemini(gemini_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "perplexity":
        perplexity_key = settings.get("perplexity_api_key", "")
        if not perplexity_key:
            yield f'data: {json.dumps({"type": "error", "content": "Perplexity API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_perplexity(perplexity_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "mistral":
        mistral_key = settings.get("mistral_api_key", "")
        if not mistral_key:
            yield f'data: {json.dumps({"type": "error", "content": "Mistral API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_mistral(mistral_key, system_prompt, full_message, model, temperature, max_tokens):
            yield token
    elif llm_provider == "xai":
        xai_key = settings.get("xai_api_key", "")
        if not xai_key:
            yield f'data: {json.dumps({"type": "error", "content": "xAI API key not configured. Go to Settings -> API Keys."})}\n\n'
            return
        async for token in _stream_xai_chat(xai_key, system_prompt, full_message, model, temperature, max_tokens):
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


async def _stream_openai_chat(
    key: str,
    system: str,
    user: str,
    model: str,
    temperature: float,
    max_tokens: int,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    import openai
    client_kwargs = {"api_key": key}
    if base_url:
        client_kwargs["base_url"] = base_url
    if default_headers:
        client_kwargs["default_headers"] = default_headers
    client = openai.AsyncOpenAI(**client_kwargs)
    create_args = _chat_completion_args(model, system, user, temperature, max_tokens)
    try:
        async with await client.chat.completions.create(**create_args, stream=True) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield f'data: {json.dumps({"type": "token", "content": delta})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_openrouter_chat(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    async for token in _stream_openai_chat(
        key,
        system,
        user,
        model or "openrouter/auto",
        temperature,
        max_tokens,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Blueprint",
        },
    ):
        yield token


async def _stream_xai_chat(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    async for token in _stream_openai_chat(
        key,
        system,
        user,
        model or "grok-4.3",
        temperature,
        max_tokens,
        base_url="https://api.x.ai/v1",
    ):
        yield token


PERPLEXITY_PRESETS = {"fast-search", "pro-search", "deep-research", "advanced-deep-research"}


def _extract_provider_response_text(data: dict) -> str:
    parts = []
    for output in data.get("output") or []:
        for content in output.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])
    if parts:
        return "".join(parts)
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(item.get("text", "") for item in content if isinstance(item, dict))
    return "".join(parts)


async def _stream_perplexity(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import httpx

    model_id = model or "pro-search"
    payload = {
        "input": user,
        "instructions": system,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if model_id in PERPLEXITY_PRESETS:
        payload["preset"] = model_id
    else:
        payload["model"] = model_id
    try:
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(
                "https://api.perplexity.ai/v1/agent",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            content = _extract_provider_response_text(response.json())
        if content:
            yield f'data: {json.dumps({"type": "token", "content": content})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_mistral(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    model_id = model or "mistral-medium-latest"
    if model_id.startswith("agent:"):
        async for token in _stream_mistral_agent(key, model_id.removeprefix("agent:"), system, user, temperature, max_tokens):
            yield token
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
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
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield f'data: {json.dumps({"type": "token", "content": delta})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_mistral_agent(
    key: str, agent_id: str, system: str, user: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import httpx

    if not agent_id:
        yield f'data: {json.dumps({"type": "error", "content": "Mistral agent model IDs must use agent:<agent_id>."})}\n\n'
        return
    try:
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/agents/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "agent_id": agent_id,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            content = _extract_provider_response_text(response.json())
        if content:
            yield f'data: {json.dumps({"type": "token", "content": content})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


async def _stream_gemini(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    import httpx

    gemini_model = model or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:streamGenerateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                url,
                params={"alt": "sse"},
                headers={"content-type": "application/json", "x-goog-api-key": key},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except Exception:
                        continue
                    for candidate in data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            text = part.get("text", "")
                            if text:
                                yield f'data: {json.dumps({"type": "token", "content": text})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"type": "error", "content": str(e)})}\n\n'


def _uses_reasoning_chat_params(model: str) -> bool:
    model_id = (model or "").lower()
    return model_id.startswith(("gpt-5", "o1", "o3", "o4"))


def _chat_completion_args(model: str, system: str, user: str, temperature: float, max_tokens: int) -> dict:
    args = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if _uses_reasoning_chat_params(model):
        args["max_completion_tokens"] = max_tokens
        if (model or "").lower().startswith("gpt-5"):
            args["reasoning_effort"] = "none"
    else:
        args["temperature"] = temperature
        args["max_tokens"] = max_tokens
    return args


async def _stream_groq(
    key: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> AsyncGenerator[str, None]:
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=key)
        groq_model = model or "llama-3.1-8b-instant"
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


@router.delete("/chats")
async def delete_visible_chats(request: Request, archived: bool = False):
    if archived not in {True, False}:
        archived = False
    user = _optional_v2_user(request)
    conn = database.get_connection()
    where = "archived_at IS NOT NULL" if archived else "archived_at IS NULL"
    rows = conn.execute(f"SELECT * FROM chats WHERE {where}").fetchall()
    visible = [r for r in rows if _user_can_access_v2_scope(user, _v2_scope_from_chat(r))]
    ids = [r["id"] for r in visible]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM messages WHERE chat_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM chats WHERE id IN ({placeholders})", ids)
        conn.commit()
    conn.close()
    return {"ok": True, "deleted": len(ids)}


@router.post("/chats/bulk-delete")
async def bulk_delete_chats(body: BulkChatDelete, request: Request):
    ids = [chat_id for chat_id in dict.fromkeys(body.ids) if chat_id]
    if not ids:
        return {"ok": True, "deleted": 0}
    user = _optional_v2_user(request)
    conn = database.get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM chats WHERE id IN ({placeholders})", ids).fetchall()
    visible = [r for r in rows if _user_can_access_v2_scope(user, _v2_scope_from_chat(r))]
    allowed_ids = [r["id"] for r in visible]
    if allowed_ids:
        allowed_placeholders = ",".join("?" for _ in allowed_ids)
        conn.execute(f"DELETE FROM messages WHERE chat_id IN ({allowed_placeholders})", allowed_ids)
        conn.execute(f"DELETE FROM chats WHERE id IN ({allowed_placeholders})", allowed_ids)
        conn.commit()
    conn.close()
    return {"ok": True, "deleted": len(allowed_ids)}


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


@router.post("/chats/{chat_id}/restore")
async def restore_chat(chat_id: str, request: Request):
    conn = database.get_connection()
    chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not chat:
        conn.close()
        raise HTTPException(404, detail="Chat not found")
    conn.close()
    _require_v2_chat_access(request, chat)
    conn = database.get_connection()
    now = _now()
    conn.execute("UPDATE chats SET archived_at = NULL, updated_at = ? WHERE id = ?", (now, chat_id))
    conn.commit()
    conn.close()
    return {"ok": True}
