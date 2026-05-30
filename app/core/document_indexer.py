import html
import json
import re
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from app.core.database import SessionLocal
from app.core.embeddings import dumps_vector, embed_texts
from app.core.jobs import JobCancelled, add_job_event, ensure_job_not_cancelled, update_job_status
from app.core.llm import get_runtime_settings_with_secrets
from app.core.models import Job, KnowledgeChunk, KnowledgeDocument, KnowledgeEmbedding, utcnow
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
            ensure_job_not_cancelled(db, job)
            update_job_status(db, job=job, status="running", progress=10, message="Document indexing started")
            document.status = "indexing"
            document.updated_at = utcnow()
            db.commit()
            ensure_job_not_cancelled(db, job)

            if not document.storage_key:
                raise RuntimeError("Document has no stored file to index")
            path = stored_path(document.storage_key)
            if not path.exists():
                raise RuntimeError("Stored file is missing")

            chunks = _extract_chunks(path, document.original_name)
            ensure_job_not_cancelled(db, job)
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
            db.query(KnowledgeEmbedding).filter(KnowledgeEmbedding.document_id == document.id).delete()
            chunk_rows: list[KnowledgeChunk] = []
            for index, chunk in enumerate(chunks):
                ensure_job_not_cancelled(db, job)
                metadata = {
                    "source": document.original_name,
                    "storage_key": document.storage_key,
                    "source_anchor_version": "1",
                    "filename": document.original_name,
                    "chunk_index": index,
                    "page": chunk.get("page"),
                    "start_offset": chunk.get("start_offset"),
                    "end_offset": chunk.get("end_offset"),
                    "extraction_method": chunk.get("extraction_method"),
                    "text_length": len(chunk["content"]),
                }
                row = KnowledgeChunk(
                    id=str(uuid.uuid4()),
                    workspace_id=document.workspace_id,
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk["content"],
                    metadata_json=json.dumps(metadata, sort_keys=True),
                )
                chunk_rows.append(row)
                db.add(row)
            db.flush()
            ensure_job_not_cancelled(db, job)
            provider, model, vectors = embed_texts([chunk.content for chunk in chunk_rows], get_runtime_settings_with_secrets())
            for chunk, vector in zip(chunk_rows, vectors, strict=False):
                ensure_job_not_cancelled(db, job)
                db.add(
                    KnowledgeEmbedding(
                        id=str(uuid.uuid4()),
                        workspace_id=document.workspace_id,
                        document_id=document.id,
                        chunk_id=chunk.id,
                        provider=provider,
                        model=model,
                        dimensions=len(vector),
                        vector_json=dumps_vector(vector),
                    )
                )
            size_bytes = path.stat().st_size
            add_job_event(
                db,
                job=job,
                event_type="progress",
                message="Document chunks and embeddings stored",
                metadata={
                    "document_id": document.id,
                    "storage_key": document.storage_key,
                    "size_bytes": size_bytes,
                    "chunks": len(chunks),
                    "embedding_provider": provider,
                    "embedding_model": model,
                },
            )
            update_job_status(db, job=job, status="completed", progress=100, message="Document indexing completed")
            document.status = "indexed"
            document.updated_at = utcnow()
            db.commit()
        except JobCancelled:
            document.status = "cancelled"
            document.updated_at = utcnow()
            update_job_status(db, job=job, status="cancelled", progress=job.progress, message="Document indexing cancelled")
            db.commit()
        except Exception as exc:
            document.status = "failed"
            document.updated_at = utcnow()
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Document indexing failed", error=str(exc))
            db.commit()


def _extract_chunks(path: Path, filename: str) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        pages = _extract_pdf_pages(path)
        if pages:
            return _chunk_pages(pages, extraction_method="pdf_text")
        raise RuntimeError("No extractable PDF text found")
    if suffix == ".docx":
        text = _extract_docx_text(path)
        if not text:
            raise RuntimeError("No extractable DOCX text found")
        return _chunk_text(text, extraction_method="docx_text")
    if suffix == ".xlsx":
        text = _extract_xlsx_text(path)
        if not text:
            raise RuntimeError("No extractable XLSX text found")
        return _chunk_text(text, extraction_method="xlsx_text")
    if suffix not in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
        raise RuntimeError(f"Text extraction is not available for {suffix or 'this file type'}")
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        text = parser.text()
        extraction_method = "html_text"
    else:
        if "\f" in text:
            pages = [_clean_text(page) for page in text.split("\f")]
            pages = [page for page in pages if page]
            if pages:
                return _chunk_pages(pages, extraction_method="plain_text")
        text = _clean_text(text)
        extraction_method = "plain_text"
    if not text:
        raise RuntimeError("No extractable text found")
    return _chunk_text(text, extraction_method=extraction_method)


def _extract_pdf_pages(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return []


def _extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return ""
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return _clean_text("\n\n".join(paragraphs))


def _extract_xlsx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings = _xlsx_shared_strings(archive)
            sheet_names = sorted(name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
            rows = []
            namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for sheet_name in sheet_names:
                root = ElementTree.fromstring(archive.read(sheet_name))
                for row in root.findall(".//s:row", namespace):
                    values = []
                    for cell in row.findall("s:c", namespace):
                        values.append(_xlsx_cell_text(cell, shared_strings, namespace))
                    line = "\t".join(value for value in values if value).strip()
                    if line:
                        rows.append(line)
    except Exception:
        return ""
    return _clean_text("\n".join(rows))


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except Exception:
        return []
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall(".//s:si", namespace):
        strings.append("".join(node.text or "" for node in item.findall(".//s:t", namespace)))
    return strings


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str], namespace: dict[str, str]) -> str:
    value = cell.find("s:v", namespace)
    if value is None or value.text is None:
        inline = cell.find(".//s:t", namespace)
        return (inline.text or "").strip() if inline is not None else ""
    raw = value.text.strip()
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (ValueError, IndexError):
            return ""
    return raw
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = _clean_text(page.extract_text() or "")
            pages.append(text)
        return [page for page in pages if page]
    except Exception:
        return []


def _chunk_pages(pages: list[str], *, chunk_size: int = 1200, overlap: int = 150, extraction_method: str = "plain_text") -> list[dict]:
    chunks: list[dict] = []
    for page_index, page_text in enumerate(pages, start=1):
        chunks.extend(_chunk_text(page_text, chunk_size=chunk_size, overlap=overlap, extraction_method=extraction_method, page=page_index))
    return chunks


def _chunk_text(
    text: str,
    *,
    chunk_size: int = 1200,
    overlap: int = 150,
    extraction_method: str = "plain_text",
    page: int | None = None,
) -> list[dict]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            leading_trim = len(text[start:end]) - len(text[start:end].lstrip())
            trailing_trim = len(text[start:end].rstrip())
            chunks.append(
                {
                    "content": chunk,
                    "page": page,
                    "start_offset": start + leading_trim,
                    "end_offset": start + trailing_trim,
                    "extraction_method": extraction_method,
                }
            )
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
