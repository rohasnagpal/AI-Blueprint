import html
import json
import re
import uuid
from html.parser import HTMLParser
from pathlib import Path

from app.core.database import SessionLocal
from app.core.jobs import add_job_event, update_job_status
from app.core.models import Job, KnowledgeChunk, KnowledgeDocument, utcnow
from app.core.storage import stored_path


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, _attrs):
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


def index_document(job_id: str, document_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        document = db.get(KnowledgeDocument, document_id)
        if not job or not document:
            return
        try:
            update_job_status(db, job=job, status="running", progress=10, message="Document indexing started")
            document.status = "indexing"
            document.updated_at = utcnow()
            db.commit()

            if not document.storage_key:
                raise RuntimeError("Document has no stored file to index")
            path = stored_path(document.storage_key)
            if not path.exists():
                raise RuntimeError("Stored file is missing")

            chunks = _extract_chunks(path, document.original_name)
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
            for index, chunk in enumerate(chunks):
                db.add(
                    KnowledgeChunk(
                        id=str(uuid.uuid4()),
                        workspace_id=document.workspace_id,
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk,
                        metadata_json=json.dumps({"source": document.original_name, "storage_key": document.storage_key}, sort_keys=True),
                    )
                )
            size_bytes = path.stat().st_size
            add_job_event(
                db,
                job=job,
                event_type="progress",
                message="Document chunks stored",
                metadata={"document_id": document.id, "storage_key": document.storage_key, "size_bytes": size_bytes, "chunks": len(chunks)},
            )
            update_job_status(db, job=job, status="completed", progress=100, message="Document indexing completed")
            document.status = "indexed"
            document.updated_at = utcnow()
            db.commit()
        except Exception as exc:
            document.status = "failed"
            document.updated_at = utcnow()
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Document indexing failed", error=str(exc))
            db.commit()


def _extract_chunks(path: Path, filename: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
        return [f"Document stored but text extraction is not available for {suffix or 'this file type'} yet."]
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        text = parser.text()
    else:
        text = _clean_text(text)
    if not text:
        raise RuntimeError("No extractable text found")
    return _chunk_text(text)


def _chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
