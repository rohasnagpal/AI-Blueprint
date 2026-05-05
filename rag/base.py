from abc import ABC, abstractmethod


class RagProvider(ABC):
    @abstractmethod
    async def ingest(self, file_path: str, doc_id: str, filename: str) -> dict:
        """Chunk, embed and store a document. Return metadata."""

    @abstractmethod
    async def retrieve(self, query: str, doc_ids: list[str] | None, top_k: int, threshold: float) -> list[dict]:
        """Return list of {content, source, doc_id, page} dicts."""

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        pass

    @abstractmethod
    async def delete_all(self) -> None:
        pass
