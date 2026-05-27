import os
import re
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks

import database
from pydantic import BaseModel
from webtools import fetch_page_text

router = APIRouter()

UPLOADS_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".json", ".html", ".htm"}


class UrlIngest(BaseModel):
    url: str


class ConnectedFolderIn(BaseModel):
    path: str


ABSOLUTE_PATH_PREFIXES = (
    "Users",
    "Volumes",
    "Applications",
    "System",
    "Library",
    "private",
    "tmp",
    "home",
    "mnt",
    "opt",
    "var",
)


def _safe_index_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:120]
    return f"{safe or 'web-page'}.md"


def _get_provider():
    from rag.openai_rag import OpenAIRag
    from rag.llamaindex_rag import LlamaIndexRag
    provider = database.get_setting("rag_provider")
    return OpenAIRag() if provider == "openai" else LlamaIndexRag()


def _format_doc(row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "original_name": row["original_name"],
        "size_bytes": row["size_bytes"],
        "page_count": row["page_count"],
        "file_type": row["file_type"],
        "openai_file_id": row["openai_file_id"],
        "uploaded_at": row["uploaded_at"],
    }


def _format_folder(row, file_count: int = 0) -> dict:
    return {
        "id": row["id"],
        "path": row["path"],
        "enabled": bool(row["enabled"]),
        "last_synced_at": row["last_synced_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "file_count": file_count,
    }


def _normalize_folder_path_input(path: str) -> str:
    raw = path.strip()
    if not raw:
        raise HTTPException(400, detail="Folder path is required.")
    if Path(raw).expanduser().is_absolute():
        return raw
    if raw.startswith("./") or raw.startswith("../"):
        return raw
    first_part = raw.replace("\\", "/").split("/", 1)[0]
    if first_part in ABSOLUTE_PATH_PREFIXES:
        return f"/{raw}"
    return raw


def _resolve_folder_path(path: str) -> str:
    raw = _normalize_folder_path_input(path)
    resolved = Path(raw).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(400, detail="Folder does not exist or is not a directory.")
    return str(resolved)


def _safe_display_path(path: str) -> str:
    parts = []
    for part in path.replace("\\", "/").split("/"):
        clean = part.strip()
        if not clean or clean in {".", ".."}:
            continue
        parts.append(clean[:160])
    return "/".join(parts)[:500]


def _iter_folder_files(root: Path, max_files: int = 1000):
    seen = 0
    for path in root.rglob("*"):
        if seen >= max_files:
            break
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        seen += 1
        yield path


@router.get("/documents")
async def list_documents():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    conn.close()
    return [_format_doc(r) for r in rows]


@router.get("/connected-folders")
async def list_connected_folders():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM connected_folders ORDER BY created_at DESC").fetchall()
    counts = {
        row["folder_id"]: row["count"]
        for row in conn.execute("SELECT folder_id, COUNT(*) AS count FROM connected_folder_files GROUP BY folder_id").fetchall()
    }
    conn.close()
    return [_format_folder(row, counts.get(row["id"], 0)) for row in rows]


@router.post("/connected-folders", status_code=201)
async def add_connected_folder(body: ConnectedFolderIn):
    folder_path = _resolve_folder_path(body.path)
    now = datetime.now(timezone.utc).isoformat()
    folder_id = str(uuid.uuid4())
    conn = database.get_connection()
    existing = conn.execute("SELECT * FROM connected_folders WHERE path = ?", (folder_path,)).fetchone()
    if existing:
        conn.close()
        return _format_folder(existing)
    conn.execute(
        "INSERT INTO connected_folders (id, path, enabled, last_synced_at, created_at, updated_at) VALUES (?, ?, 1, NULL, ?, ?)",
        (folder_id, folder_path, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM connected_folders WHERE id = ?", (folder_id,)).fetchone()
    conn.close()
    return _format_folder(row)


@router.delete("/connected-folders/{folder_id}")
async def remove_connected_folder(folder_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM connected_folders WHERE id = ?", (folder_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Connected folder not found")
    conn.execute("DELETE FROM connected_folder_files WHERE folder_id = ?", (folder_id,))
    conn.execute("DELETE FROM connected_folders WHERE id = ?", (folder_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/connected-folders/{folder_id}/sync")
async def sync_connected_folder(folder_id: str, background_tasks: BackgroundTasks):
    max_mb = int(database.get_setting("max_file_size_mb") or 25)
    max_bytes = max_mb * 1024 * 1024
    conn = database.get_connection()
    folder = conn.execute("SELECT * FROM connected_folders WHERE id = ?", (folder_id,)).fetchone()
    if not folder:
        conn.close()
        raise HTTPException(404, detail="Connected folder not found")

    root = Path(folder["path"])
    if not root.exists() or not root.is_dir():
        conn.close()
        raise HTTPException(400, detail="Connected folder is no longer available.")

    UPLOADS_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    updated = 0
    skipped = 0
    too_large = 0
    unsupported = 0
    removed = 0
    seen_source_paths = set()

    for source in _iter_folder_files(root):
        stat = source.stat()
        if stat.st_size > max_bytes:
            too_large += 1
            continue
        source_path = str(source.resolve())
        seen_source_paths.add(source_path)
        mapping = conn.execute("SELECT * FROM connected_folder_files WHERE source_path = ?", (source_path,)).fetchone()
        if mapping and mapping["doc_id"] and mapping["size_bytes"] == stat.st_size and float(mapping["mtime"]) == stat.st_mtime:
            skipped += 1
            continue

        ext = source.suffix.lower()
        doc_id = str(uuid.uuid4())
        safe_name = f"{doc_id}{ext}"
        dest = UPLOADS_DIR / safe_name
        shutil.copy2(source, dest)

        old_doc_id = mapping["doc_id"] if mapping else None
        old_filename = None
        if old_doc_id:
            old_doc = conn.execute("SELECT filename FROM documents WHERE id = ?", (old_doc_id,)).fetchone()
            old_filename = old_doc["filename"] if old_doc else None
            conn.execute("DELETE FROM documents WHERE id = ?", (old_doc_id,))

        conn.execute(
            "INSERT INTO documents (id, filename, original_name, size_bytes, page_count, file_type, openai_file_id, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, safe_name, str(source.relative_to(root)), stat.st_size, None, ext.lstrip(".").upper(), None, now),
        )
        if mapping:
            conn.execute(
                "UPDATE connected_folder_files SET doc_id = ?, size_bytes = ?, mtime = ?, synced_at = ? WHERE id = ?",
                (doc_id, stat.st_size, stat.st_mtime, now, mapping["id"]),
            )
            updated += 1
        else:
            conn.execute(
                "INSERT INTO connected_folder_files (id, folder_id, source_path, doc_id, size_bytes, mtime, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), folder_id, source_path, doc_id, stat.st_size, stat.st_mtime, now),
            )
            added += 1

        background_tasks.add_task(_ingest_background, doc_id, str(dest), source.name)
        if old_doc_id:
            background_tasks.add_task(_delete_background, old_doc_id)
        if old_filename:
            old_path = UPLOADS_DIR / old_filename
            if old_path.exists():
                os.remove(old_path)

    mappings = conn.execute("SELECT * FROM connected_folder_files WHERE folder_id = ?", (folder_id,)).fetchall()
    for mapping in mappings:
        if mapping["source_path"] in seen_source_paths:
            continue
        old_doc_id = mapping["doc_id"]
        old_filename = None
        if old_doc_id:
            old_doc = conn.execute("SELECT filename FROM documents WHERE id = ?", (old_doc_id,)).fetchone()
            old_filename = old_doc["filename"] if old_doc else None
            conn.execute("DELETE FROM documents WHERE id = ?", (old_doc_id,))
            background_tasks.add_task(_delete_background, old_doc_id)
        conn.execute("DELETE FROM connected_folder_files WHERE id = ?", (mapping["id"],))
        if old_filename:
            old_path = UPLOADS_DIR / old_filename
            if old_path.exists():
                os.remove(old_path)
        removed += 1

    conn.execute("UPDATE connected_folders SET last_synced_at = ?, updated_at = ? WHERE id = ?", (now, now, folder_id))
    conn.commit()
    conn.close()
    return {"ok": True, "added": added, "updated": updated, "removed": removed, "skipped": skipped, "too_large": too_large, "unsupported": unsupported}


@router.post("/documents/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), original_path: str = Form("")):
    max_mb = int(database.get_setting("max_file_size_mb") or 25)
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail=f"File type '{ext}' not supported. Allowed: PDF, DOCX, TXT, CSV, XLSX, MD, JSON, HTML")

    UPLOADS_DIR.mkdir(exist_ok=True)
    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}{ext}"
    dest = UPLOADS_DIR / safe_name

    size_bytes = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 64):
            size_bytes += len(chunk)
            if size_bytes > max_mb * 1024 * 1024:
                out.close()
                os.remove(dest)
                raise HTTPException(413, detail=f"File exceeds {max_mb} MB limit.")
            out.write(chunk)

    now = datetime.now(timezone.utc).isoformat()
    display_name = _safe_display_path(original_path) or file.filename
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO documents (id, filename, original_name, size_bytes, page_count, file_type, openai_file_id, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, safe_name, display_name, size_bytes, None, ext.lstrip(".").upper(), None, now),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(_ingest_background, doc_id, str(dest), display_name)

    return {"id": doc_id, "original_name": display_name, "size_bytes": size_bytes, "status": "processing"}


@router.post("/web/ingest-url")
@router.post("/documents/url")
async def ingest_url_document(body: UrlIngest, background_tasks: BackgroundTasks):
    max_mb = int(database.get_setting("max_file_size_mb") or 25)
    try:
        page = await fetch_page_text(body.url)
    except Exception as e:
        raise HTTPException(400, detail=f"Could not read URL: {e}")

    content = f"# {page['title']}\n\nSource: {page['url']}\n\n{page['text']}\n"
    data = content.encode("utf-8")
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, detail=f"Fetched page exceeds {max_mb} MB limit.")

    UPLOADS_DIR.mkdir(exist_ok=True)
    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}.md"
    dest = UPLOADS_DIR / safe_name
    with open(dest, "wb") as out:
        out.write(data)

    display_name = f"{page['title']} ({page['url']})"
    now = datetime.now(timezone.utc).isoformat()
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO documents (id, filename, original_name, size_bytes, page_count, file_type, openai_file_id, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, safe_name, display_name[:500], len(data), None, "URL", None, now),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(_ingest_background, doc_id, str(dest), _safe_index_filename(page["title"]))
    return {"id": doc_id, "original_name": display_name, "size_bytes": len(data), "status": "processing"}


async def _ingest_background(doc_id: str, file_path: str, filename: str):
    try:
        provider = _get_provider()
        meta = await provider.ingest(file_path, doc_id, filename)
        conn = database.get_connection()
        updates = []
        params = []
        if "openai_file_id" in meta:
            updates.append("openai_file_id = ?")
            params.append(meta["openai_file_id"])
        if "page_count" in meta:
            updates.append("page_count = ?")
            params.append(meta["page_count"])
        if updates:
            params.append(doc_id)
            conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ingest error for {doc_id}: {e}")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, background_tasks: BackgroundTasks):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Document not found")
    filename = row["filename"]
    conn.execute("DELETE FROM connected_folder_files WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

    background_tasks.add_task(_delete_background, doc_id)
    upload_path = UPLOADS_DIR / filename
    if upload_path.exists():
        os.remove(upload_path)

    return {"ok": True}


async def _delete_background(doc_id: str):
    try:
        provider = _get_provider()
        await provider.delete(doc_id)
    except Exception as e:
        print(f"Delete error for {doc_id}: {e}")


@router.delete("/documents")
async def delete_all_documents(background_tasks: BackgroundTasks):
    conn = database.get_connection()
    rows = conn.execute("SELECT filename FROM documents").fetchall()
    conn.execute("UPDATE connected_folder_files SET doc_id = NULL")
    conn.execute("DELETE FROM documents")
    conn.commit()
    conn.close()

    for row in rows:
        path = UPLOADS_DIR / row["filename"]
        if path.exists():
            os.remove(path)

    background_tasks.add_task(_delete_all_background)
    return {"ok": True}


async def _delete_all_background():
    try:
        provider = _get_provider()
        await provider.delete_all()
    except Exception as e:
        print(f"Delete all error: {e}")
