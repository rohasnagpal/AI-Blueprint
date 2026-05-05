from fastapi import APIRouter
from pydantic import BaseModel

import database

router = APIRouter()


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


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
