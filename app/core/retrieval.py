from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import LOCAL_EMBEDDING_MODEL, LOCAL_EMBEDDING_PROVIDER, cosine_similarity, embed_texts, loads_vector
from app.core.llm import get_runtime_settings_with_secrets
from app.core.models import DocumentLink, KnowledgeChunk, KnowledgeDocument, KnowledgeEmbedding


def retrieve_scoped_evidence(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    embedded = _retrieve_embedded_evidence(
        db,
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        query=query,
        top_k=top_k,
    )
    if embedded:
        return embedded
    return _retrieve_local_fallback(
        db,
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        query=query,
        top_k=top_k,
    )


def _retrieve_embedded_evidence(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    settings = get_runtime_settings_with_secrets()
    provider, model, query_vectors = embed_texts([query], settings)
    query_vector = query_vectors[0] if query_vectors else []
    evidence = _retrieve_stored_embedding_rows(
        db,
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        query_vector=query_vector,
        provider=provider,
        model=model,
        top_k=top_k,
    )
    if evidence:
        return evidence
    if (provider, model) != (LOCAL_EMBEDDING_PROVIDER, LOCAL_EMBEDDING_MODEL):
        _local_provider, _local_model, local_query_vectors = embed_texts([query], {})
        return _retrieve_stored_embedding_rows(
            db,
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            query_vector=local_query_vectors[0] if local_query_vectors else [],
            provider=LOCAL_EMBEDDING_PROVIDER,
            model=LOCAL_EMBEDDING_MODEL,
            top_k=top_k,
        )
    return []


def _retrieve_stored_embedding_rows(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str,
    query_vector: list[float],
    provider: str,
    model: str,
    top_k: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(KnowledgeEmbedding, KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeChunk, KnowledgeChunk.id == KnowledgeEmbedding.chunk_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeEmbedding.document_id)
        .join(DocumentLink, DocumentLink.document_id == KnowledgeDocument.id)
        .where(
            DocumentLink.workspace_id == workspace_id,
            DocumentLink.blueprint_id == blueprint_id,
            KnowledgeDocument.status == "indexed",
            KnowledgeEmbedding.provider == provider,
            KnowledgeEmbedding.model == model,
        )
        .order_by(KnowledgeChunk.chunk_index)
    ).all()
    if not rows:
        return []

    scored = []
    for embedding, chunk, document in rows:
        score = cosine_similarity(query_vector, loads_vector(embedding.vector_json))
        scored.append((score, embedding, chunk, document))
    scored.sort(key=lambda item: (item[0], -item[2].chunk_index), reverse=True)
    return [
        {
            "filename": document.original_name,
            "doc_id": document.id,
            "page": chunk.chunk_index + 1,
            "excerpt": chunk.content[:800],
            "content": chunk.content,
            "score": round(score, 6),
            "retrieval": "v2_embedding_index",
            "embedding_provider": embedding.provider,
            "embedding_model": embedding.model,
        }
        for score, embedding, chunk, document in scored[: max(1, top_k)]
    ]


def _retrieve_local_fallback(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(DocumentLink, DocumentLink.document_id == KnowledgeDocument.id)
        .where(
            DocumentLink.workspace_id == workspace_id,
            DocumentLink.blueprint_id == blueprint_id,
            KnowledgeDocument.status == "indexed",
        )
        .order_by(KnowledgeChunk.chunk_index)
    ).all()
    if not rows:
        return []

    _provider, _model, query_vectors = embed_texts([query], {})
    query_vector = query_vectors[0] if query_vectors else []
    scored = []
    for chunk, document in rows:
        _provider, _model, chunk_vectors = embed_texts([chunk.content], {})
        score = cosine_similarity(query_vector, chunk_vectors[0] if chunk_vectors else [])
        scored.append((score, chunk, document))
    scored.sort(key=lambda item: (item[0], -item[1].chunk_index), reverse=True)

    evidence = []
    for score, chunk, document in scored[: max(1, top_k)]:
        evidence.append(
            {
                "filename": document.original_name,
                "doc_id": document.id,
                "page": chunk.chunk_index + 1,
                "excerpt": chunk.content[:800],
                "content": chunk.content,
                "score": round(score, 6),
                "retrieval": "v2_local_embedding_fallback",
            }
        )
    return evidence
