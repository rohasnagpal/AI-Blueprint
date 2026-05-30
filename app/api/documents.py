import hashlib
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.document_indexer import index_document
from app.core.jobs import create_job, format_job
from app.core.models import DocumentLink, KnowledgeDocument, Matter, User
from app.core.pagination import page_query_response
from app.core.storage import delete_stored_file, store_upload
from app.core.task_control import run_background_job
from app.core.validation import validate_choice
from webtools import fetch_page_text

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])


class DocumentRegisterIn(BaseModel):
    original_name: str = Field(min_length=1, max_length=500)
    matter_id: str | None = None
    storage_key: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    scope: str = "workspace"
    status: str = "registered"


class UrlIngestIn(BaseModel):
    url: str


def _format_document(document: KnowledgeDocument) -> dict:
    return {
        "id": document.id,
        "workspace_id": document.workspace_id,
        "matter_id": document.matter_id,
        "original_name": document.original_name,
        "storage_key": document.storage_key,
        "content_hash": document.content_hash,
        "mime_type": document.mime_type,
        "size_bytes": document.size_bytes,
        "scope": document.scope,
        "status": document.status,
        "created_by_user_id": document.created_by_user_id,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


def _get_document_or_404(db: Session, workspace_id: str, document_id: str) -> KnowledgeDocument:
    document = db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.workspace_id == workspace_id,
            KnowledgeDocument.id == document_id,
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _validate_document_scope(scope: str) -> None:
    if scope not in {"workspace", "matter"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document scope")


def _validate_document_status(status_value: str) -> str:
    return validate_choice(status_value, {"registered", "stored", "indexing", "indexed", "failed", "cancelled"}, "document status")


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> Matter:
    if not matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter is required")
    matter = db.execute(
        select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)
    ).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return matter


def _safe_display_name(name: str) -> str:
    parts = []
    for part in str(name or "").replace("\\", "/").split("/"):
        clean = part.strip()
        if not clean or clean in {".", ".."}:
            continue
        parts.append(clean[:160])
    return "/".join(parts)[:500]


def _safe_index_filename(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip("-")[:120]
    return f"{safe or 'web-page'}.md"


def _store_text_document(original_name: str, content: str) -> dict:
    data = content.encode("utf-8")
    size_bytes = len(data)
    max_bytes = get_settings().max_upload_bytes
    if size_bytes > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds upload limit")
    root = get_settings().uploads_dir
    root.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(data).hexdigest()
    final_rel = Path(content_hash[:2]) / f"{content_hash}.md"
    final_path = root / final_rel
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if not final_path.exists():
        temp_path = root / f".tmp-{uuid.uuid4().hex}.md"
        temp_path.write_bytes(data)
        os.replace(temp_path, final_path)
    return {
        "original_name": original_name,
        "storage_key": final_rel.as_posix(),
        "content_hash": content_hash,
        "mime_type": "text/markdown",
        "size_bytes": size_bytes,
    }


def _unreferenced_storage_keys(db: Session, documents: list[KnowledgeDocument]) -> list[str]:
    document_ids = {document.id for document in documents}
    storage_keys = {document.storage_key for document in documents if document.storage_key}
    unreferenced: list[str] = []
    for storage_key in storage_keys:
        remaining = db.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.storage_key == storage_key,
                KnowledgeDocument.id.notin_(document_ids),
            )
        ).scalar_one()
        if remaining == 0:
            unreferenced.append(storage_key)
    return unreferenced


def _create_document(
    db: Session,
    *,
    workspace_id: str,
    user: User,
    original_name: str,
    matter_id: str | None = None,
    storage_key: str | None = None,
    content_hash: str | None = None,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    scope: str = "workspace",
    status_value: str = "registered",
) -> KnowledgeDocument:
    document = KnowledgeDocument(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=matter_id,
        original_name=original_name.strip(),
        storage_key=storage_key,
        content_hash=content_hash,
        mime_type=mime_type,
        size_bytes=size_bytes,
        scope=scope,
        status=_validate_document_status(status_value),
        created_by_user_id=user.id,
    )
    db.add(document)
    db.flush()
    record_audit_event(
        db,
        action="document.register",
        resource_type="document",
        resource_id=document.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"matter_id": matter_id, "scope": scope, "storage_key": storage_key},
    )
    return document


@router.get("")
async def list_documents(
    workspace_id: str,
    matter_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    query = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)
    query = query.where(KnowledgeDocument.matter_id == matter_id)
    return page_query_response(db, query.order_by(KnowledgeDocument.created_at.desc()), _format_document, page=page, page_size=page_size, scalars=True)


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_document(
    workspace_id: str,
    body: DocumentRegisterIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    _validate_document_scope(body.scope)
    document = _create_document(
        db,
        workspace_id=workspace_id,
        user=user,
        matter_id=body.matter_id,
        original_name=body.original_name.strip(),
        storage_key=body.storage_key,
        content_hash=body.content_hash,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        scope="matter",
        status_value=body.status,
    )
    db.commit()
    db.refresh(document)
    return _format_document(document)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    original_name: str | None = Form(default=None),
    matter_id: str | None = Form(default=None),
    scope: str = Form(default="workspace"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    _validate_document_scope(scope)
    stored = await store_upload(file, max_bytes=get_settings().max_upload_bytes)
    display_name = _safe_display_name(original_name or "") or stored["original_name"]
    document = _create_document(
        db,
        workspace_id=workspace_id,
        user=user,
        matter_id=matter_id,
        original_name=display_name,
        storage_key=stored["storage_key"],
        content_hash=stored["content_hash"],
        mime_type=stored["mime_type"],
        size_bytes=stored["size_bytes"],
        scope="matter",
        status_value="stored",
    )
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="document.index",
        metadata={"document_id": document.id, "storage_key": document.storage_key},
        message="Document indexing queued",
    )
    db.commit()
    db.refresh(document)
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, index_document, job.id, document.id)
    data = _format_document(document)
    data["job"] = format_job(job)
    return data


@router.post("/ingest-url", status_code=status.HTTP_201_CREATED)
async def ingest_url_document(
    workspace_id: str,
    body: UrlIngestIn,
    background_tasks: BackgroundTasks,
    matter_id: str | None = Query(default=None),
    scope: str = Query(default="workspace"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    _validate_document_scope(scope)
    try:
        page = await fetch_page_text(body.url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not fetch URL: {exc}")
    title = page.get("title") or body.url
    text = page.get("text") or ""
    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable text found at URL")
    markdown = f"# {title}\n\nSource: {body.url}\n\n{text}"
    stored = _store_text_document(_safe_index_filename(title), markdown)
    document = _create_document(
        db,
        workspace_id=workspace_id,
        user=user,
        matter_id=matter_id,
        original_name=stored["original_name"],
        storage_key=stored["storage_key"],
        content_hash=stored["content_hash"],
        mime_type=stored["mime_type"],
        size_bytes=stored["size_bytes"],
        scope="matter",
        status_value="stored",
    )
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="document.index",
        metadata={"document_id": document.id, "storage_key": document.storage_key, "source_url": body.url},
        message="Document indexing queued",
    )
    db.commit()
    db.refresh(document)
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, index_document, job.id, document.id)
    data = _format_document(document)
    data["job"] = format_job(job)
    return data


@router.post("/{document_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_document_index(
    workspace_id: str,
    document_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    document = _get_document_or_404(db, workspace_id, document_id)
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="document.index",
        metadata={"document_id": document.id, "storage_key": document.storage_key},
        message="Document indexing queued",
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, index_document, job.id, document.id)
    return {"document": _format_document(document), "job": format_job(job)}


@router.get("/{document_id}")
async def get_document(
    workspace_id: str,
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    return _format_document(_get_document_or_404(db, workspace_id, document_id))


@router.delete("/{document_id}")
async def delete_document(
    workspace_id: str,
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    document = _get_document_or_404(db, workspace_id, document_id)
    storage_keys_to_delete = _unreferenced_storage_keys(db, [document])
    linked = db.execute(select(DocumentLink).where(DocumentLink.document_id == document_id)).scalars().all()
    for link in linked:
        db.delete(link)
    db.delete(document)
    record_audit_event(
        db,
        action="document.delete",
        resource_type="document",
        resource_id=document_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"storage_key": document.storage_key, "link_count": len(linked)},
    )
    db.commit()
    for storage_key in storage_keys_to_delete:
        delete_stored_file(storage_key)
    return {"ok": True}


@router.delete("")
async def delete_all_documents(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    documents = db.execute(select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)).scalars().all()
    storage_keys_to_delete = _unreferenced_storage_keys(db, documents)
    links = db.execute(select(DocumentLink).where(DocumentLink.workspace_id == workspace_id)).scalars().all()
    for link in links:
        db.delete(link)
    for document in documents:
        db.delete(document)
    record_audit_event(
        db,
        action="document.delete_all",
        resource_type="document",
        resource_id=workspace_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_count": len(documents), "link_count": len(links)},
    )
    db.commit()
    for storage_key in storage_keys_to_delete:
        delete_stored_file(storage_key)
    return {"ok": True, "deleted": len(documents)}
