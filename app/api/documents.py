import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member, require_workspace_member
from app.core.document_indexer import index_document
from app.core.jobs import create_job, format_job
from app.core.models import BlueprintInstance, DocumentLink, KnowledgeDocument, Matter, User
from app.core.pagination import page_response
from app.core.storage import store_upload

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


class DocumentLinkIn(BaseModel):
    blueprint_id: str
    link_type: str = "source"


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


def _format_link(link: DocumentLink) -> dict:
    return {
        "id": link.id,
        "workspace_id": link.workspace_id,
        "document_id": link.document_id,
        "blueprint_id": link.blueprint_id,
        "link_type": link.link_type,
        "created_by_user_id": link.created_by_user_id,
        "created_at": link.created_at.isoformat(),
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
    if scope not in {"workspace", "matter", "blueprint"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document scope")


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> None:
    if matter_id:
        matter = db.execute(
            select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)
        ).scalar_one_or_none()
        if not matter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")


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
        status=status_value,
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
    query = select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)
    if matter_id:
        query = query.where(KnowledgeDocument.matter_id == matter_id)
    documents = db.execute(query.order_by(KnowledgeDocument.created_at.desc())).scalars().all()
    return page_response(documents, _format_document, page=page, page_size=page_size)


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
        scope=body.scope,
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
    matter_id: str | None = Form(default=None),
    scope: str = Form(default="workspace"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    _validate_document_scope(scope)
    stored = await store_upload(file, max_bytes=25 * 1024 * 1024)
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
        scope=scope,
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
    background_tasks.add_task(index_document, job.id, document.id)
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
    background_tasks.add_task(index_document, job.id, document.id)
    return {"document": _format_document(document), "job": format_job(job)}


@router.get("/blueprints/{blueprint_id}/links")
async def list_blueprint_documents(
    workspace_id: str,
    blueprint_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_blueprint_member(workspace_id, blueprint_id, user, db)
    rows = db.execute(
        select(DocumentLink, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == DocumentLink.document_id)
        .where(DocumentLink.workspace_id == workspace_id, DocumentLink.blueprint_id == blueprint_id)
        .order_by(DocumentLink.created_at.desc())
    ).all()
    items = [
        {"link": _format_link(link), "document": _format_document(document)}
        for link, document in rows
    ]
    return page_response(items, page=page, page_size=page_size)


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
    return {"ok": True}


@router.delete("")
async def delete_all_documents(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    documents = db.execute(select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id)).scalars().all()
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
    return {"ok": True, "deleted": len(documents)}


@router.post("/{document_id}/links", status_code=status.HTTP_201_CREATED)
async def link_document_to_blueprint(
    workspace_id: str,
    document_id: str,
    body: DocumentLinkIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = _get_document_or_404(db, workspace_id, document_id)
    blueprint, membership = require_blueprint_member(workspace_id, body.blueprint_id, user, db)
    if membership.role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    if document.matter_id and blueprint.matter_id and document.matter_id != blueprint.matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document and blueprint belong to different matters")
    link = DocumentLink(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        document_id=document_id,
        blueprint_id=body.blueprint_id,
        link_type=body.link_type,
        created_by_user_id=user.id,
    )
    db.add(link)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document is already linked to this blueprint")
    record_audit_event(
        db,
        action="document.link",
        resource_type="document_link",
        resource_id=link.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_id": document_id, "blueprint_id": body.blueprint_id, "link_type": body.link_type},
    )
    db.commit()
    db.refresh(link)
    return _format_link(link)
