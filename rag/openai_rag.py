import asyncio
from pathlib import Path

import openai

import database
from rag.base import RagProvider


def _assistants_model() -> str:
    model = database.get_setting("openai_assistants_model") or "gpt-4.1"
    if model.lower().startswith("gpt-5"):
        return "gpt-4.1"
    return model


class OpenAIRag(RagProvider):

    def _client(self) -> openai.AsyncOpenAI:
        key = database.get_setting("openai_api_key")
        if not key:
            raise ValueError("OpenAI API key is not configured. Go to Settings → API Keys.")
        return openai.AsyncOpenAI(api_key=key)

    def _vector_stores(self, client: openai.AsyncOpenAI):
        if hasattr(client, "vector_stores"):
            return client.vector_stores
        if hasattr(client, "beta") and hasattr(client.beta, "vector_stores"):
            return client.beta.vector_stores
        raise RuntimeError(
            "This OpenAI SDK does not expose vector stores. Upgrade with: pip install -U openai"
        )

    async def _ensure_vector_store(self, client: openai.AsyncOpenAI) -> str:
        vector_stores = self._vector_stores(client)
        vs_id = database.get_setting("vector_store_id")
        if vs_id:
            try:
                await vector_stores.retrieve(vs_id)
                return vs_id
            except Exception:
                pass
        vs = await vector_stores.create(name="AI Blueprint")
        database.set_setting("vector_store_id", vs.id)
        return vs.id

    async def _ensure_assistant(self, client: openai.AsyncOpenAI, vs_id: str) -> str:
        asst_id = database.get_setting("assistant_id")
        model = _assistants_model()
        if asst_id:
            try:
                await client.beta.assistants.update(
                    asst_id,
                    model=model,
                    tools=[{"type": "file_search"}],
                    tool_resources={"file_search": {"vector_store_ids": [vs_id]}},
                )
                return asst_id
            except Exception:
                pass
        asst = await client.beta.assistants.create(
            name="AI Blueprint Assistant",
            model=model,
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": [vs_id]}},
        )
        database.set_setting("assistant_id", asst.id)
        return asst.id

    async def ingest(self, file_path: str, doc_id: str, filename: str) -> dict:
        client = self._client()
        vector_stores = self._vector_stores(client)
        vs_id = await self._ensure_vector_store(client)
        await self._ensure_assistant(client, vs_id)
        with open(file_path, "rb") as f:
            uploaded = await client.files.create(file=(filename, f), purpose="assistants")
        await vector_stores.files.create(
            vector_store_id=vs_id,
            file_id=uploaded.id,
        )
        # Poll until the file is processed
        for _ in range(60):
            vsf = await vector_stores.files.retrieve(
                vector_store_id=vs_id, file_id=uploaded.id
            )
            if vsf.status == "completed":
                break
            if vsf.status == "failed":
                raise RuntimeError(f"OpenAI vector store indexing failed for {filename}")
            await asyncio.sleep(2)
        return {"openai_file_id": uploaded.id}

    async def retrieve(self, query: str, doc_ids: list[str] | None, top_k: int, threshold: float) -> list[dict]:
        # OpenAI mode: retrieval is handled by the Assistants API automatically
        return []

    async def delete(self, doc_id: str) -> None:
        conn = database.get_connection()
        row = conn.execute("SELECT openai_file_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        conn.close()
        if not row or not row["openai_file_id"]:
            return
        file_id = row["openai_file_id"]
        client = self._client()
        vector_stores = self._vector_stores(client)
        vs_id = database.get_setting("vector_store_id")
        try:
            if vs_id:
                await vector_stores.files.delete(
                    vector_store_id=vs_id, file_id=file_id
                )
        except Exception:
            pass
        try:
            await client.files.delete(file_id)
        except Exception:
            pass

    async def delete_all(self) -> None:
        conn = database.get_connection()
        rows = conn.execute("SELECT openai_file_id FROM documents WHERE openai_file_id IS NOT NULL").fetchall()
        conn.close()
        client = self._client()
        vector_stores = self._vector_stores(client)
        vs_id = database.get_setting("vector_store_id")
        for row in rows:
            fid = row["openai_file_id"]
            try:
                if vs_id:
                    await vector_stores.files.delete(vector_store_id=vs_id, file_id=fid)
            except Exception:
                pass
            try:
                await client.files.delete(fid)
            except Exception:
                pass
