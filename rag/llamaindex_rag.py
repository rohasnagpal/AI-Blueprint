import asyncio
import shutil
from pathlib import Path

import database
from rag.base import RagProvider

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "ai_blueprint_docs"


def _lazy_imports():
    import chromadb
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.vector_stores.chroma import ChromaVectorStore
    return chromadb, SimpleDirectoryReader, VectorStoreIndex, StorageContext, SentenceSplitter, HuggingFaceEmbedding, ChromaVectorStore


def _get_chroma_collection():
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client, client.get_or_create_collection(COLLECTION_NAME)


class LlamaIndexRag(RagProvider):

    async def ingest(self, file_path: str, doc_id: str, filename: str) -> dict:
        (chromadb, SimpleDirectoryReader, VectorStoreIndex, StorageContext,
         SentenceSplitter, HuggingFaceEmbedding, ChromaVectorStore) = _lazy_imports()

        chunk_size = int(database.get_setting("chunk_size") or 512)
        chunk_overlap = int(database.get_setting("chunk_overlap") or 64)
        embed_model_name = database.get_setting("local_embedding_model") or "all-MiniLM-L6-v2"

        loop = asyncio.get_event_loop()

        def _do_ingest():
            import tempfile, os
            # Copy file to a temp dir so SimpleDirectoryReader can read it
            with tempfile.TemporaryDirectory() as tmp:
                dest = os.path.join(tmp, filename)
                shutil.copy(file_path, dest)
                reader = SimpleDirectoryReader(tmp)
                docs = reader.load_data()

            splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            nodes = splitter.get_nodes_from_documents(docs)

            embed_model = HuggingFaceEmbedding(model_name=embed_model_name)

            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            from llama_index.core import Settings as LISettings
            LISettings.embed_model = embed_model
            LISettings.llm = None

            index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)

            # Tag nodes with doc_id metadata
            for i, node in enumerate(nodes):
                node.metadata["doc_id"] = doc_id
                node.metadata["source"] = filename

            # Store in ChromaDB with doc_id in metadata
            texts = [n.get_content() for n in nodes]
            embeds = embed_model.get_text_embedding_batch(texts)
            ids = [f"{doc_id}_{i}" for i in range(len(nodes))]
            metadatas = [{"doc_id": doc_id, "source": filename, "chunk_index": i} for i in range(len(nodes))]
            collection.add(documents=texts, embeddings=embeds, ids=ids, metadatas=metadatas)

            return len(nodes)

        page_count = await loop.run_in_executor(None, _do_ingest)
        return {"page_count": page_count}

    async def retrieve(self, query: str, doc_ids: list[str] | None, top_k: int, threshold: float) -> list[dict]:
        (chromadb, *_, HuggingFaceEmbedding, ChromaVectorStore) = _lazy_imports()

        embed_model_name = database.get_setting("local_embedding_model") or "all-MiniLM-L6-v2"

        loop = asyncio.get_event_loop()

        def _do_retrieve():
            embed_model = HuggingFaceEmbedding(model_name=embed_model_name)
            query_embed = embed_model.get_query_embedding(query)

            chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            collection = chroma_client.get_or_create_collection(COLLECTION_NAME)

            where = {"doc_id": {"$in": doc_ids}} if doc_ids else None
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
                        chunks.append({
                            "content": text,
                            "source": meta.get("source", "unknown"),
                            "doc_id": meta.get("doc_id", ""),
                            "page": meta.get("chunk_index"),
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
