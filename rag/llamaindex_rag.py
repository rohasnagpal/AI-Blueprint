import asyncio
import html
import re
import shutil
from pathlib import Path
from html.parser import HTMLParser

import database
from rag.base import RagProvider

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "ai_blueprint_docs"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return _clean_text(" ".join(self.parts))


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_documents(file_path: str, filename: str, Document) -> list:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires pypdf. Install it with: pip install pypdf") from exc

    reader = PdfReader(file_path)
    docs = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = _clean_text(page.extract_text() or "")
        if not text:
            continue
        docs.append(
            Document(
                text=text,
                metadata={"file_name": filename, "file_type": "application/pdf", "page_label": page_index},
            )
        )
    return docs


def _extract_text_document(file_path: str, filename: str, Document) -> list:
    raw = Path(file_path).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    suffix = Path(filename).suffix.lower()
    if suffix in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        text = parser.text()
    else:
        text = _clean_text(text)
    return [Document(text=text, metadata={"file_name": filename, "file_type": "text/plain"})] if text else []


def _lazy_imports():
    import chromadb
    from llama_index.core import Document, SimpleDirectoryReader
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    return chromadb, Document, SimpleDirectoryReader, SentenceSplitter, HuggingFaceEmbedding


def _get_chroma_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client, client.get_or_create_collection(COLLECTION_NAME)


class LlamaIndexRag(RagProvider):

    async def ingest(self, file_path: str, doc_id: str, filename: str) -> dict:
        (chromadb, Document, SimpleDirectoryReader, SentenceSplitter, HuggingFaceEmbedding) = _lazy_imports()

        chunk_size = int(database.get_setting("chunk_size") or 512)
        chunk_overlap = int(database.get_setting("chunk_overlap") or 64)
        embed_model_name = database.get_setting("local_embedding_model") or "all-MiniLM-L6-v2"

        loop = asyncio.get_event_loop()

        def _do_ingest():
            import tempfile, os
            suffix = Path(filename).suffix.lower()
            if suffix == ".pdf":
                docs = _extract_pdf_documents(file_path, filename, Document)
            elif suffix in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
                docs = _extract_text_document(file_path, filename, Document)
            else:
                # Copy file to a temp dir so SimpleDirectoryReader can read it.
                # This remains the fallback for formats with optional readers.
                with tempfile.TemporaryDirectory() as tmp:
                    dest = os.path.join(tmp, filename)
                    shutil.copy(file_path, dest)
                    reader = SimpleDirectoryReader(input_files=[dest])
                    docs = reader.load_data()

            if not docs:
                raise RuntimeError(f"No extractable text found in {filename}")

            splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            nodes = splitter.get_nodes_from_documents(docs)
            if not nodes:
                raise RuntimeError(f"No indexable text chunks found in {filename}")

            embed_model = HuggingFaceEmbedding(model_name=embed_model_name)

            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

            from llama_index.core import Settings as LISettings
            LISettings.embed_model = embed_model
            LISettings.llm = None

            # Store in ChromaDB with doc_id in metadata
            texts = [n.get_content() for n in nodes]
            embeds = embed_model.get_text_embedding_batch(texts)
            ids = [f"{doc_id}_{i}" for i in range(len(nodes))]
            metadatas = [
                {
                    "doc_id": doc_id,
                    "source": filename,
                    "chunk_index": i,
                    "page": n.metadata.get("page_label", "") if hasattr(n, "metadata") else "",
                }
                for i, n in enumerate(nodes)
            ]
            collection.delete(where={"doc_id": doc_id})
            collection.add(documents=texts, embeddings=embeds, ids=ids, metadatas=metadatas)

            return len(docs)

        page_count = await loop.run_in_executor(None, _do_ingest)
        return {"page_count": page_count}

    async def retrieve(self, query: str, doc_ids: list[str] | None, top_k: int, threshold: float) -> list[dict]:
        (chromadb, *_, HuggingFaceEmbedding) = _lazy_imports()

        embed_model_name = database.get_setting("local_embedding_model") or "all-MiniLM-L6-v2"

        loop = asyncio.get_event_loop()

        def _do_retrieve():
            embed_model = HuggingFaceEmbedding(model_name=embed_model_name)
            query_embed = embed_model.get_query_embedding(query)

            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

            active_doc_ids = doc_ids
            if active_doc_ids is None:
                conn = database.get_connection()
                active_doc_ids = [row["id"] for row in conn.execute("SELECT id FROM documents").fetchall()]
                conn.close()
            if not active_doc_ids:
                return []

            where = {"doc_id": {"$in": active_doc_ids}}
            results = collection.query(
                query_embeddings=[query_embed],
                n_results=min(top_k, max(1, collection.count())),
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            if results["documents"] and results["documents"][0]:
                for text, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    # ChromaDB returns L2 distance; convert to cosine-like score
                    score = 1.0 / (1.0 + dist)
                    if score >= threshold:
                        source = meta.get("source")
                        doc_id = meta.get("doc_id", "")
                        if not source or not doc_id:
                            continue
                        chunks.append({
                            "content": text,
                            "source": source,
                            "doc_id": doc_id,
                            "page": meta.get("page") or meta.get("chunk_index"),
                        })
            return chunks

        return await loop.run_in_executor(None, _do_retrieve)

    async def delete(self, doc_id: str) -> None:
        loop = asyncio.get_event_loop()

        def _do_delete():
            import chromadb
            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            try:
                collection = chroma_client.get_collection(COLLECTION_NAME)
                collection.delete(where={"doc_id": doc_id})
            except Exception:
                pass

        await loop.run_in_executor(None, _do_delete)

    async def delete_all(self) -> None:
        loop = asyncio.get_event_loop()

        def _do_delete_all():
            import chromadb
            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            try:
                chroma_client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass

        await loop.run_in_executor(None, _do_delete_all)
