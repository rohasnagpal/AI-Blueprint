import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import database

router = APIRouter()


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


class ModelIn(BaseModel):
    provider: str
    display_name: str
    model_id: str
    enabled: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_model(row) -> dict:
    return {
        "id": row["id"],
        "provider": row["provider"],
        "display_name": row["display_name"],
        "model_id": row["model_id"],
        "enabled": bool(row["enabled"]),
        "is_builtin": bool(row["is_builtin"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _ollama_endpoint(path: str) -> str:
    base_url = (database.get_setting("ollama_base_url") or "http://localhost:11434").strip().rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _ollama_headers() -> dict[str, str]:
    api_key = (database.get_setting("ollama_api_key") or "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


@router.get("/settings")
async def get_settings():
    return database.get_all_settings()


@router.put("/settings")
async def update_settings(body: SettingsUpdate):
    for key, value in body.settings.items():
        database.set_setting(key, value)
    return {"ok": True}


@router.get("/settings/test-connection")
async def test_connection():
    provider = database.get_setting("rag_provider")
    if provider == "openai":
        key = database.get_setting("openai_api_key")
        if not key:
            return {"ok": False, "error": "OpenAI API key is not set. Go to Settings → API Keys."}
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=key)
            models = await client.models.list()
            return {"ok": True, "message": f"Connected to OpenAI. {len(list(models))} models available."}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    else:
        try:
            import chromadb
            return {"ok": True, "message": "Local RAG (ChromaDB) is available."}
        except ImportError:
            return {"ok": False, "error": "chromadb is not installed. Run: pip install chromadb"}


@router.get("/settings/test-ollama")
async def test_ollama():
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(_ollama_endpoint("/tags"), headers=_ollama_headers())
            response.raise_for_status()
            data = response.json()
        models = data.get("models") or []
        return {"ok": True, "message": f"Connected to Ollama. {len(models)} models available."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/models")
async def list_models():
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM ai_models ORDER BY provider, display_name"
    ).fetchall()
    conn.close()
    return [_format_model(row) for row in rows]


@router.post("/models")
async def create_model(body: ModelIn):
    now = _now()
    model_id = str(uuid.uuid4())
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO ai_models
        (id, provider, display_name, model_id, enabled, is_builtin, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            model_id,
            body.provider.strip().lower(),
            body.display_name.strip(),
            body.model_id.strip(),
            1 if body.enabled else 0,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    return _format_model(row)


@router.put("/models/{model_row_id}")
async def update_model(model_row_id: str, body: ModelIn):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_row_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Model not found")
    now = _now()
    conn.execute(
        """
        UPDATE ai_models
        SET provider = ?, display_name = ?, model_id = ?, enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            body.provider.strip().lower(),
            body.display_name.strip(),
            body.model_id.strip(),
            1 if body.enabled else 0,
            now,
            model_row_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_row_id,)).fetchone()
    conn.close()
    return _format_model(row)


@router.delete("/models/{model_row_id}")
async def delete_model(model_row_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_row_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Model not found")
    conn.execute("DELETE FROM ai_models WHERE id = ?", (model_row_id,))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_models_seeded', 'true')")
    conn.commit()
    conn.close()
    return {"ok": True}
