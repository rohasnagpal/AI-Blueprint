import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import database

router = APIRouter(prefix="/realtime", tags=["realtime"])


class RealtimeSessionRequest(BaseModel):
    sdp: str
    persona_id: str | None = None


class RealtimeDocumentSearchRequest(BaseModel):
    query: str
    doc_context: str = "none"
    v2_workspace_id: str | None = None
    v2_matter_id: str | None = None
    v2_blueprint_id: str | None = None
    v2_document_ids: list[str] | None = None


def _document_search_tool() -> dict:
    return {
        "type": "function",
        "name": "search_documents",
        "description": (
            "Search the user's selected AI Blueprint documents, workspace, matter, or blueprint. "
            "Use this before answering questions about uploaded documents, contracts, clauses, files, "
            "matter records, workspace knowledge, or document-grounded facts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A focused semantic search query based on the user's spoken question.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def _realtime_instructions(persona_id: str | None) -> str:
    base = (
        "You are AI Blueprint, a helpful live voice assistant. "
        "Keep spoken answers concise, natural, and interruptible. "
        "If the user interrupts or changes direction, follow the latest spoken request. "
        "When speaking Hindi or any other language with grammatical gender, use feminine "
        "first-person forms for yourself as the assistant, while addressing the user neutrally "
        "or according to the user's stated preference. "
        "If the user asks about uploaded documents, selected documents, workspace knowledge, "
        "matters, blueprints, contract clauses, or anything that should be grounded in files, "
        "call search_documents first and base the spoken answer on the returned excerpts. "
        "If search_documents returns no results, say that no matching document context was found."
    )
    if not persona_id:
        return base

    conn = database.get_connection()
    row = conn.execute("SELECT name, system_prompt FROM personas WHERE id = ? AND is_enabled = 1", (persona_id,)).fetchone()
    conn.close()
    if not row:
        return base
    return f"{base}\n\nPersona: {row['name']}\nInstructions: {row['system_prompt']}"


@router.post("/session", response_class=PlainTextResponse)
async def create_realtime_session(body: RealtimeSessionRequest):
    api_key = database.get_setting("openai_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key is not configured.")
    if not body.sdp.strip():
        raise HTTPException(status_code=400, detail="SDP offer is required.")

    model = (database.get_setting("realtime_model") or "gpt-realtime").strip()
    voice = (database.get_setting("realtime_voice") or "marin").strip()
    session_config = {
        "type": "realtime",
        "model": model,
        "instructions": _realtime_instructions(body.persona_id),
        "tools": [_document_search_tool()],
        "tool_choice": "auto",
        "audio": {
            "input": {
                "transcription": {"model": "gpt-4o-mini-transcribe"},
            },
            "output": {
                "voice": voice,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={"Authorization": f"Bearer {api_key}"},
                files={
                    "sdp": (None, body.sdp, "application/sdp"),
                    "session": (None, json.dumps(session_config), "application/json"),
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Realtime session creation failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail[:1000]) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Realtime session creation failed: {exc}") from exc

    return PlainTextResponse(response.text, media_type="application/sdp")


@router.post("/search-documents")
async def search_realtime_documents(body: RealtimeDocumentSearchRequest, request: Request):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required.")

    settings = database.get_all_settings()
    top_k = min(max(int(settings.get("top_k", 5)), 1), 12)

    if body.v2_workspace_id:
        from routes.chats import _get_v2_user, _load_v2_chunks, _user_can_access_v2_scope

        scope = {
            "workspace_id": body.v2_workspace_id,
            "matter_id": body.v2_matter_id,
            "blueprint_id": body.v2_blueprint_id,
            "document_ids": body.v2_document_ids or [],
        }
        user = _get_v2_user(request)
        if not _user_can_access_v2_scope(user, scope):
            raise HTTPException(status_code=403, detail="Document scope access denied.")
        chunks = _load_v2_chunks(scope, query, top_k)
        return {
            "query": query,
            "scope": "v2",
            "results": [
                {
                    "source": chunk["source"],
                    "document_id": chunk["document_id"],
                    "excerpt": chunk["content"][:1200],
                }
                for chunk in chunks
            ],
        }

    if body.doc_context == "none":
        return {"query": query, "scope": "none", "results": []}

    doc_ids = None
    if body.doc_context not in ("all", "none"):
        doc_ids = [doc_id.strip() for doc_id in body.doc_context.split(",") if doc_id.strip()]

    try:
        from rag.llamaindex_rag import LlamaIndexRag

        provider = LlamaIndexRag()
        chunks = await provider.retrieve(
            query,
            doc_ids,
            top_k,
            float(settings.get("similarity_threshold", 0.72)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document search failed: {exc}") from exc

    return {
        "query": query,
        "scope": "legacy",
        "results": [
            {
                "source": chunk.get("source"),
                "document_id": chunk.get("doc_id") or chunk.get("document_id"),
                "excerpt": str(chunk.get("content") or "")[:1200],
            }
            for chunk in chunks
        ],
    }
