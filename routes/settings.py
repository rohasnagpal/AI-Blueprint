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


def _format_live_model(provider: str, model_id: str, display_name: str | None = None) -> dict:
    return {
        "id": f"live-{provider}-{model_id}",
        "provider": provider,
        "display_name": display_name or model_id,
        "model_id": model_id,
        "enabled": True,
        "is_builtin": False,
        "is_live": True,
        "created_at": None,
        "updated_at": None,
    }


def _clean_gemini_model_id(name: str) -> str:
    return name.removeprefix("models/")


def _looks_like_openai_chat_model(model_id: str) -> bool:
    lower = model_id.lower()
    excluded = ("embedding", "whisper", "tts", "dall-e", "moderation", "realtime", "transcribe", "image")
    if any(part in lower for part in excluded):
        return False
    return lower.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))


def _looks_like_groq_chat_model(model_id: str) -> bool:
    lower = model_id.lower()
    excluded = ("whisper", "tts", "playai")
    return not any(part in lower for part in excluded)


def _ollama_endpoint(path: str) -> str:
    base_url = (database.get_setting("ollama_base_url") or "http://localhost:11434").strip().rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _ollama_headers() -> dict[str, str]:
    api_key = (database.get_setting("ollama_api_key") or "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def _live_openai_models() -> list[dict]:
    key = database.get_setting("openai_api_key")
    if not key:
        raise HTTPException(400, detail="OpenAI API key is not configured.")
    import openai

    client = openai.AsyncOpenAI(api_key=key)
    models = await client.models.list()
    rows = []
    for item in models.data:
        model_id = item.id
        if _looks_like_openai_chat_model(model_id):
            rows.append(_format_live_model("openai", model_id))
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_groq_models() -> list[dict]:
    key = database.get_setting("groq_api_key")
    if not key:
        raise HTTPException(400, detail="Groq API key is not configured.")
    from groq import AsyncGroq

    client = AsyncGroq(api_key=key)
    models = await client.models.list()
    rows = []
    for item in models.data:
        model_id = item.id
        if _looks_like_groq_chat_model(model_id):
            rows.append(_format_live_model("groq", model_id))
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_openrouter_models() -> list[dict]:
    key = database.get_setting("openrouter_api_key")
    if not key:
        raise HTTPException(400, detail="OpenRouter API key is not configured.")
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        response.raise_for_status()
        data = response.json()
    rows = []
    for item in data.get("data", []):
        model_id = item.get("id")
        if model_id:
            rows.append(_format_live_model("openrouter", model_id, item.get("name") or model_id))
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_anthropic_models() -> list[dict]:
    key = database.get_setting("anthropic_api_key")
    if not key:
        raise HTTPException(400, detail="Anthropic API key is not configured.")
    import httpx

    rows = []
    params: dict[str, str | int] = {"limit": 1000}
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                params=params,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
            )
            response.raise_for_status()
            data = response.json()
            for item in data.get("data", []):
                model_id = item.get("id")
                if model_id:
                    rows.append(_format_live_model("anthropic", model_id, item.get("display_name") or model_id))
            if not data.get("has_more") or not data.get("last_id"):
                break
            params["after_id"] = data["last_id"]
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_gemini_models() -> list[dict]:
    key = database.get_setting("gemini_api_key")
    if not key:
        raise HTTPException(400, detail="Google Gemini API key is not configured.")
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
        )
        response.raise_for_status()
        data = response.json()
    rows = []
    for item in data.get("models", []):
        methods = item.get("supportedGenerationMethods") or []
        model_id = _clean_gemini_model_id(item.get("name", ""))
        if model_id and "generateContent" in methods:
            rows.append(_format_live_model("gemini", model_id, item.get("displayName") or model_id))
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_xai_models() -> list[dict]:
    key = database.get_setting("xai_api_key")
    if not key:
        raise HTTPException(400, detail="xAI API key is not configured.")
    import openai

    client = openai.AsyncOpenAI(api_key=key, base_url="https://api.x.ai/v1")
    models = await client.models.list()
    rows = [_format_live_model("xai", item.id) for item in models.data]
    return sorted(rows, key=lambda row: row["display_name"].lower())


async def _live_ollama_models() -> list[dict]:
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(_ollama_endpoint("/tags"), headers=_ollama_headers())
        response.raise_for_status()
        data = response.json()
    rows = []
    for item in data.get("models") or []:
        model_id = item.get("name") or item.get("model")
        if model_id:
            rows.append(_format_live_model("ollama", model_id))
    return sorted(rows, key=lambda row: row["display_name"].lower())


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


@router.get("/models/live")
async def list_live_models(provider: str):
    provider = provider.strip().lower()
    loaders = {
        "openai": _live_openai_models,
        "openrouter": _live_openrouter_models,
        "anthropic": _live_anthropic_models,
        "groq": _live_groq_models,
        "ollama": _live_ollama_models,
        "gemini": _live_gemini_models,
        "xai": _live_xai_models,
    }
    if provider not in loaders:
        raise HTTPException(400, detail=f"Live model listing is not supported for provider: {provider}")
    loader = loaders[provider]
    try:
        models = await loader()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, detail=f"Could not fetch live {provider} models: {exc}") from exc
    return {"provider": provider, "source": "live", "models": models}


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
