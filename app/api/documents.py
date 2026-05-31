import hashlib
import mimetypes
import os
import shutil
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
from app.core.models import DocumentFolderFile, DocumentFolderSource, DocumentLink, KnowledgeDocument, Matter, User, utcnow
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


class FolderSourceIn(BaseModel):
    matter_id: str = Field(min_length=1, max_length=36)
    path: str = Field(min_length=1, max_length=1000)
    display_name: str | None = Field(default=None, max_length=500)


class BrowserFolderSourceIn(BaseModel):
    matter_id: str = Field(min_length=1, max_length=36)
    root_name: str = Field(min_length=1, max_length=500)


class BrowserFolderSyncStartIn(BaseModel):
    source_paths: list[str] = Field(default_factory=list, max_length=5000)


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


def _format_folder_source(source: DocumentFolderSource, file_count: int = 0) -> dict:
    return {
        "id": source.id,
        "workspace_id": source.workspace_id,
        "matter_id": source.matter_id,
        "path": source.path,
        "display_name": source.display_name,
        "source_type": source.source_type,
        "status": source.status,
        "last_synced_at": source.last_synced_at.isoformat() if source.last_synced_at else None,
        "last_error": source.last_error,
        "created_by_user_id": source.created_by_user_id,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
        "file_count": file_count,
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


def _normalize_folder_path_input(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder path is required")
    if Path(raw).expanduser().is_absolute() or raw.startswith("./") or raw.startswith("../"):
        return raw
    if raw.split("/", 1)[0] in {"Users", "Volumes", "Applications", "System", "Library", "private", "tmp"}:
        return f"/{raw}"
    return raw


def _resolve_folder_path(path: str) -> Path:
    resolved = Path(_normalize_folder_path_input(path)).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder does not exist or is not a directory")
    return resolved


def _folder_display_name(path: Path, fallback: str | None = None) -> str:
    return _safe_display_name(fallback or path.name or str(path)) or "Folder"


def _iter_folder_files(root: Path, max_files: int = 5000):
    seen = 0
    for path in root.rglob("*"):
        if seen >= max_files:
            break
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".json", ".html", ".htm"}:
            continue
        seen += 1
        yield path


def _store_local_file(source: Path, *, max_bytes: int) -> dict:
    ext = source.suffix.lower()
    if ext not in {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".json", ".html", ".htm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File type '{ext}' not supported")
    size_bytes = source.stat().st_size
    if size_bytes > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds upload limit")
    digest = hashlib.sha256()
    with open(source, "rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    content_hash = digest.hexdigest()
    root = get_settings().uploads_dir
    root.mkdir(parents=True, exist_ok=True)
    final_rel = Path(content_hash[:2]) / f"{content_hash}{ext}"
    final_path = root / final_rel
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if not final_path.exists():
        temp_path = root / f".tmp-{uuid.uuid4().hex}{ext}"
        shutil.copyfile(source, temp_path)
        os.replace(temp_path, final_path)
    return {
        "original_name": source.name,
        "storage_key": final_rel.as_posix(),
        "content_hash": content_hash,
        "mime_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        "size_bytes": size_bytes,
    }


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


def _delete_document_row(db: Session, document: KnowledgeDocument | None) -> list[str]:
    if not document:
        return []
    storage_keys_to_delete = _unreferenced_storage_keys(db, [document])
    linked = db.execute(select(DocumentLink).where(DocumentLink.document_id == document.id)).scalars().all()
    for link in linked:
        db.delete(link)
    db.delete(document)
    return storage_keys_to_delete


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


def _get_folder_source_or_404(db: Session, workspace_id: str, folder_id: str) -> DocumentFolderSource:
    source = db.execute(
        select(DocumentFolderSource).where(
            DocumentFolderSource.workspace_id == workspace_id,
            DocumentFolderSource.id == folder_id,
        )
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder source not found")
    return source


def _validate_folder_source_for_upload(db: Session, workspace_id: str, matter_id: str | None, folder_source_id: str | None) -> DocumentFolderSource | None:
    if not folder_source_id:
        return None
    source = _get_folder_source_or_404(db, workspace_id, folder_source_id)
    if matter_id and source.matter_id != matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder source belongs to a different matter")
    return source


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
        _validate_matter(db, workspace_id, matter_id)
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
    folder_source_id: str | None = Form(default=None),
    source_path: str | None = Form(default=None),
    source_mtime: float | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    _validate_document_scope(scope)
    folder_source = _validate_folder_source_for_upload(db, workspace_id, matter_id, folder_source_id)
    stored = await store_upload(file, max_bytes=get_settings().max_upload_bytes)
    display_name = _safe_display_name(original_name or "") or stored["original_name"]
    source_path_clean = _safe_display_name(source_path or "")
    mapping = None
    if folder_source and source_path_clean:
        mapping = db.execute(
            select(DocumentFolderFile).where(
                DocumentFolderFile.folder_source_id == folder_source.id,
                DocumentFolderFile.source_path == source_path_clean,
            )
        ).scalar_one_or_none()
        if mapping and mapping.document_id and mapping.content_hash == stored["content_hash"]:
            existing = db.get(KnowledgeDocument, mapping.document_id)
            if existing:
                folder_source.last_synced_at = utcnow()
                folder_source.updated_at = utcnow()
                mapping.size_bytes = stored["size_bytes"]
                mapping.mtime = source_mtime
                mapping.synced_at = utcnow()
                db.commit()
                data = _format_document(existing)
                data["folder_source_id"] = folder_source.id
                data["unchanged"] = True
                return data
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
    old_document = None
    if folder_source and source_path_clean:
        if mapping and mapping.document_id:
            old_document = db.get(KnowledgeDocument, mapping.document_id)
        if not mapping:
            mapping = DocumentFolderFile(
                id=str(uuid.uuid4()),
                folder_source_id=folder_source.id,
                workspace_id=workspace_id,
                matter_id=folder_source.matter_id,
                source_path=source_path_clean,
                document_id=document.id,
                size_bytes=stored["size_bytes"],
                mtime=source_mtime,
                content_hash=stored["content_hash"],
                synced_at=utcnow(),
            )
            db.add(mapping)
        else:
            mapping.document_id = document.id
            mapping.size_bytes = stored["size_bytes"]
            mapping.mtime = source_mtime
            mapping.content_hash = stored["content_hash"]
            mapping.synced_at = utcnow()
        folder_source.last_synced_at = utcnow()
        folder_source.last_error = None
        folder_source.updated_at = utcnow()
        for storage_key in _delete_document_row(db, old_document):
            db.flush()
            delete_stored_file(storage_key)
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
    if folder_source:
        data["folder_source_id"] = folder_source.id
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


@router.get("/folders")
async def list_folder_sources(
    workspace_id: str,
    matter_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    if matter_id:
        _validate_matter(db, workspace_id, matter_id)
    query = select(DocumentFolderSource).where(DocumentFolderSource.workspace_id == workspace_id)
    if matter_id:
        query = query.where(DocumentFolderSource.matter_id == matter_id)
    sources = db.execute(query.order_by(DocumentFolderSource.created_at.desc())).scalars().all()
    counts = {
        row.folder_source_id: row.count
        for row in db.execute(
            select(DocumentFolderFile.folder_source_id, func.count(DocumentFolderFile.id).label("count"))
            .where(DocumentFolderFile.workspace_id == workspace_id)
            .group_by(DocumentFolderFile.folder_source_id)
        ).all()
    }
    return {"items": [_format_folder_source(source, counts.get(source.id, 0)) for source in sources]}


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def connect_local_folder_source(
    workspace_id: str,
    body: FolderSourceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    folder_path = _resolve_folder_path(body.path)
    path_text = str(folder_path)
    existing = db.execute(
        select(DocumentFolderSource).where(
            DocumentFolderSource.workspace_id == workspace_id,
            DocumentFolderSource.matter_id == body.matter_id,
            DocumentFolderSource.source_type == "local_path",
            DocumentFolderSource.path == path_text,
        )
    ).scalar_one_or_none()
    if existing:
        return _format_folder_source(existing)
    source = DocumentFolderSource(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=body.matter_id,
        path=path_text,
        display_name=_folder_display_name(folder_path, body.display_name),
        source_type="local_path",
        status="active",
        created_by_user_id=user.id,
    )
    db.add(source)
    record_audit_event(
        db,
        action="document.folder.connect",
        resource_type="document_folder_source",
        resource_id=source.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"matter_id": body.matter_id, "source_type": source.source_type, "path": source.path},
    )
    db.commit()
    db.refresh(source)
    return _format_folder_source(source)


@router.post("/folders/browser", status_code=status.HTTP_201_CREATED)
async def connect_browser_folder_source(
    workspace_id: str,
    body: BrowserFolderSourceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    root_name = _safe_display_name(body.root_name) or "Selected folder"
    existing = db.execute(
        select(DocumentFolderSource).where(
            DocumentFolderSource.workspace_id == workspace_id,
            DocumentFolderSource.matter_id == body.matter_id,
            DocumentFolderSource.source_type == "browser",
            DocumentFolderSource.path == root_name,
        )
    ).scalar_one_or_none()
    if existing:
        return _format_folder_source(existing)
    source = DocumentFolderSource(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=body.matter_id,
        path=root_name,
        display_name=root_name,
        source_type="browser",
        status="active",
        created_by_user_id=user.id,
    )
    db.add(source)
    record_audit_event(
        db,
        action="document.folder.connect",
        resource_type="document_folder_source",
        resource_id=source.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"matter_id": body.matter_id, "source_type": source.source_type, "path": source.path},
    )
    db.commit()
    db.refresh(source)
    return _format_folder_source(source)


@router.post("/folders/{folder_id}/browser-sync-start")
async def start_browser_folder_sync(
    workspace_id: str,
    folder_id: str,
    body: BrowserFolderSyncStartIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    source = _get_folder_source_or_404(db, workspace_id, folder_id)
    if source.source_type != "browser":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder source is not browser-selected")
    incoming = {_safe_display_name(path) for path in body.source_paths if _safe_display_name(path)}
    removed = 0
    storage_keys: list[str] = []
    mappings = db.execute(select(DocumentFolderFile).where(DocumentFolderFile.folder_source_id == source.id)).scalars().all()
    for mapping in mappings:
        if mapping.source_path in incoming:
            continue
        storage_keys.extend(_delete_document_row(db, db.get(KnowledgeDocument, mapping.document_id) if mapping.document_id else None))
        db.delete(mapping)
        removed += 1
    source.last_synced_at = utcnow()
    source.last_error = None
    source.updated_at = utcnow()
    db.commit()
    for storage_key in storage_keys:
        delete_stored_file(storage_key)
    return {"ok": True, "removed": removed}


@router.post("/folders/{folder_id}/sync")
async def sync_local_folder_source(
    workspace_id: str,
    folder_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    source = _get_folder_source_or_404(db, workspace_id, folder_id)
    if source.source_type != "local_path":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Browser-selected folders must be reselected to sync")
    root = _resolve_folder_path(source.path)
    max_bytes = get_settings().max_upload_bytes
    now = utcnow()
    added = updated = skipped = removed = too_large = failed = 0
    seen_paths: set[str] = set()
    storage_keys_to_delete: list[str] = []

    for source_file in _iter_folder_files(root):
        rel_path = _safe_display_name(str(source_file.relative_to(root)))
        if not rel_path:
            continue
        seen_paths.add(rel_path)
        stat = source_file.stat()
        mapping = db.execute(
            select(DocumentFolderFile).where(
                DocumentFolderFile.folder_source_id == source.id,
                DocumentFolderFile.source_path == rel_path,
            )
        ).scalar_one_or_none()
        if mapping and mapping.document_id and mapping.size_bytes == stat.st_size and mapping.mtime == stat.st_mtime:
            skipped += 1
            continue
        try:
            stored = _store_local_file(source_file, max_bytes=max_bytes)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
                too_large += 1
            else:
                failed += 1
            continue

        old_document = db.get(KnowledgeDocument, mapping.document_id) if mapping and mapping.document_id else None
        display_name = _safe_display_name(f"{source.display_name}/{rel_path}") or source_file.name
        document = _create_document(
            db,
            workspace_id=workspace_id,
            user=user,
            matter_id=source.matter_id,
            original_name=display_name,
            storage_key=stored["storage_key"],
            content_hash=stored["content_hash"],
            mime_type=stored["mime_type"],
            size_bytes=stored["size_bytes"],
            scope="matter",
            status_value="stored",
        )
        if mapping:
            mapping.document_id = document.id
            mapping.size_bytes = stored["size_bytes"]
            mapping.mtime = stat.st_mtime
            mapping.content_hash = stored["content_hash"]
            mapping.synced_at = now
            updated += 1
        else:
            db.add(
                DocumentFolderFile(
                    id=str(uuid.uuid4()),
                    folder_source_id=source.id,
                    workspace_id=workspace_id,
                    matter_id=source.matter_id,
                    source_path=rel_path,
                    document_id=document.id,
                    size_bytes=stored["size_bytes"],
                    mtime=stat.st_mtime,
                    content_hash=stored["content_hash"],
                    synced_at=now,
                )
            )
            added += 1
        storage_keys_to_delete.extend(_delete_document_row(db, old_document))
        job = create_job(
            db,
            workspace_id=workspace_id,
            created_by_user_id=user.id,
            job_type="document.index",
            metadata={"document_id": document.id, "storage_key": document.storage_key, "folder_source_id": source.id},
            message="Document indexing queued",
        )
        db.flush()
        background_tasks.add_task(run_background_job, job.id, index_document, job.id, document.id)

    mappings = db.execute(select(DocumentFolderFile).where(DocumentFolderFile.folder_source_id == source.id)).scalars().all()
    for mapping in mappings:
        if mapping.source_path in seen_paths:
            continue
        storage_keys_to_delete.extend(_delete_document_row(db, db.get(KnowledgeDocument, mapping.document_id) if mapping.document_id else None))
        db.delete(mapping)
        removed += 1

    source.last_synced_at = now
    source.last_error = None
    source.updated_at = now
    record_audit_event(
        db,
        action="document.folder.sync",
        resource_type="document_folder_source",
        resource_id=source.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"added": added, "updated": updated, "removed": removed, "skipped": skipped, "too_large": too_large, "failed": failed},
    )
    db.commit()
    for storage_key in storage_keys_to_delete:
        delete_stored_file(storage_key)
    return {"ok": True, "added": added, "updated": updated, "removed": removed, "skipped": skipped, "too_large": too_large, "failed": failed}


@router.delete("/folders/{folder_id}")
async def delete_folder_source(
    workspace_id: str,
    folder_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    source = _get_folder_source_or_404(db, workspace_id, folder_id)
    db.delete(source)
    record_audit_event(
        db,
        action="document.folder.delete",
        resource_type="document_folder_source",
        resource_id=folder_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"matter_id": source.matter_id, "source_type": source.source_type},
    )
    db.commit()
    return {"ok": True}


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
    folder_mappings = db.execute(select(DocumentFolderFile).where(DocumentFolderFile.document_id == document_id)).scalars().all()
    for link in linked:
        db.delete(link)
    for mapping in folder_mappings:
        db.delete(mapping)
    db.delete(document)
    record_audit_event(
        db,
        action="document.delete",
        resource_type="document",
        resource_id=document_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"storage_key": document.storage_key, "link_count": len(linked), "folder_mapping_count": len(folder_mappings)},
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
    folder_mappings = db.execute(select(DocumentFolderFile).where(DocumentFolderFile.workspace_id == workspace_id)).scalars().all()
    for link in links:
        db.delete(link)
    for mapping in folder_mappings:
        db.delete(mapping)
    for document in documents:
        db.delete(document)
    record_audit_event(
        db,
        action="document.delete_all",
        resource_type="document",
        resource_id=workspace_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_count": len(documents), "link_count": len(links), "folder_mapping_count": len(folder_mappings)},
    )
    db.commit()
    for storage_key in storage_keys_to_delete:
        delete_stored_file(storage_key)
    return {"ok": True, "deleted": len(documents)}
