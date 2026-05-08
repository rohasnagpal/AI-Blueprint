import os
import re
import uuid
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks

import database
from pydantic import BaseModel
from webtools import fetch_page_text

router = APIRouter()

UPLOADS_DIR = Path("uploads")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx", ".md", ".json", ".html", ".htm"}


class UrlIngest(BaseModel):
    url: str


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


@router.get("/documents")
async def list_documents():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    conn.close()
    return [_format_doc(r) for r in rows]


@router.post("/documents/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO documents (id, filename, original_name, size_bytes, page_count, file_type, openai_file_id, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, safe_name, file.filename, size_bytes, None, ext.lstrip(".").upper(), None, now),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(_ingest_background, doc_id, str(dest), file.filename)

    return {"id": doc_id, "original_name": file.filename, "size_bytes": size_bytes, "status": "processing"}


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
