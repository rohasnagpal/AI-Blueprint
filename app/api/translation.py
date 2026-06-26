import hashlib
import html
import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.document_indexer import _extract_chunks
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider, get_runtime_settings_with_secrets
from app.core.models import Matter, TranslationRun, User, utcnow
from app.core.pagination import page_query_response
from app.core.storage import ALLOWED_EXTENSIONS

router = APIRouter(tags=["translation"])

TRANSLATION_MODES = {
    "legal",
    "business",
    "technical",
    "medical",
    "marketing",
    "academic",
    "plain-language",
    "literal",
}
TRANSLATION_ALLOWED_TAGS = "article|section|h1|h2|h3|p|ul|ol|li|table|thead|tbody|tr|th|td|aside|strong|em|br"
TRANSLATION_CHUNK_CHAR_LIMIT = 8_000
TRANSLATION_LLM_MAX_TOKENS = 4096


class TranslationTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=120_000)
    source_language: str = Field(default="auto", max_length=100)
    target_language: str = Field(min_length=1, max_length=100)
    mode: str = "legal"
    context: str | None = Field(default=None, max_length=4000)
    matter_id: str | None = None


def _format_translation(run: TranslationRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "matter_id": run.matter_id,
        "source_type": run.source_type,
        "source_filename": run.source_filename,
        "source_language": run.source_language,
        "detected_language": run.detected_language,
        "target_language": run.target_language,
        "mode": run.mode,
        "context": run.context,
        "translated_html": run.translated_html,
        "translated_text": run.translated_text,
        "translator_notes": json_loads(run.translator_notes_json, []),
        "warnings": json_loads(run.warnings_json, []),
        "quality_check": json_loads(run.quality_check_json, {}),
        "preserved_terms": json_loads(run.preserved_terms_json, []),
        "provider": run.provider,
        "model": run.model,
        "status": run.status,
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in TRANSLATION_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported translation mode")
    return normalized


def _validate_target_language(target_language: str) -> str:
    value = target_language.strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target language is required")
    return value[:100]


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> None:
    if not matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter is required")
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")


def _extract_upload_text(path: Path, filename: str) -> tuple[str, list[dict]]:
    try:
        chunks = _extract_chunks(path, filename)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not extract text from this file: {exc}")
    sections = []
    text_parts = []
    for index, chunk in enumerate(chunks, start=1):
        content = chunk.get("content", "").strip()
        if not content:
            continue
        if chunk.get("extraction_method") == "unsupported_placeholder" or content.startswith("Document stored but text extraction is not available"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This file type cannot be translated yet because text extraction is unavailable")
        page = chunk.get("page")
        sections.append({"index": index, "page": page, "content": content})
        label = f"[Page {page}]" if page else f"[Section {index}]"
        text_parts.append(f"{label}\n{content}")
    text = "\n\n".join(text_parts).strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No extractable text found")
    return text, sections


async def _store_translation_temp_upload(file: UploadFile) -> tuple[Path, dict]:
    original_name = Path(file.filename or "upload.bin").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File type '{ext}' not supported")
    max_bytes = get_settings().max_upload_bytes
    size_bytes = 0
    digest = hashlib.sha256()
    handle = tempfile.NamedTemporaryFile(prefix="aibp-translation-", suffix=ext, delete=False)
    path = Path(handle.name)
    try:
        with handle:
            while chunk := await file.read(1024 * 64):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds upload limit")
                digest.update(chunk)
                handle.write(chunk)
        return path, {"original_name": original_name, "content_hash": digest.hexdigest(), "size_bytes": size_bytes, "mime_type": file.content_type}
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _system_prompt(mode: str) -> str:
    mode_rules = {
        "legal": "Preserve obligations, rights, remedies, defined terms, citations, clause numbering, deadlines, exceptions, and jurisdiction-specific terms. Flag legal terms without exact equivalents.",
        "business": "Preserve commercial intent, tone, amounts, commitments, deadlines, names, and operational meaning.",
        "technical": "Preserve commands, code, API names, product names, specifications, units, parameters, and warnings.",
        "medical": "Preserve clinical meaning, diagnoses, dosages, warnings, contraindications, timings, and measurements. Flag all clinical uncertainty.",
        "marketing": "Translate naturally for the target audience while preserving claim boundaries, brand meaning, product names, and offer details.",
        "academic": "Preserve claims, citations, terminology, neutrality, structure, and hedging language.",
        "plain-language": "Simplify wording while preserving meaning. Explain complex terms in notes rather than changing regulated meaning.",
        "literal": "Translate closely with minimal rewriting. Preserve source order and wording as much as the target language allows.",
    }
    return (
        "You are a careful professional translator. Return only valid JSON with keys "
        "translated_html, translated_text, translator_notes, warnings, preserved_terms, quality_check, detected_language. "
        "Every JSON string must be validly escaped. Do not place literal line breaks inside JSON string values. "
        "Use arrays of strings for translator_notes, warnings, and preserved_terms. "
        "The translated_html value must be safe semantic HTML using article, section, h2, p, ul, ol, li, table, thead, tbody, tr, th, td, aside, strong, em, and br only. "
        "Do not include scripts, styles, event handlers, markdown fences, or explanatory text outside JSON. "
        "Preserve meaning. Do not invent missing content. Preserve names, numbers, dates, currency amounts, IDs, addresses, citations, section references, and defined terms unless translation is clearly appropriate. "
        "Keep translator notes and warnings separate from the translated text. "
        f"Mode-specific rule: {mode_rules[mode]} "
        "For legal, medical, technical, and regulated content, mark human review as required in quality_check."
    )


def _user_prompt(*, text: str, source_language: str, target_language: str, mode: str, context: str | None) -> str:
    return json.dumps(
        {
            "source_language": source_language or "auto",
            "target_language": target_language,
            "mode": mode,
            "context": context or "",
            "source_text": text,
        },
        ensure_ascii=False,
    )


def _json_from_llm(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    decoder = json.JSONDecoder(strict=False)
    try:
        data = decoder.decode(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        candidate = re.sub(r",\s*([}\]])", r"\1", match.group(0))
        data = decoder.decode(candidate)
    if not isinstance(data, dict):
        raise ValueError("Translation model returned an invalid payload")
    return data


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _sanitize_html(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"(?is)<(script|style|iframe|object|embed|link|meta|form|input|button|textarea|select)[^>]*>.*?</\1>", "", text)
    text = re.sub(r"(?is)</?(?!(?:" + TRANSLATION_ALLOWED_TAGS + r")\b)[a-z][^>]*>", "", text)

    def clean_allowed_tag(match: re.Match[str]) -> str:
        closing, tag = match.group(1), match.group(2).lower()
        if closing:
            return f"</{tag}>"
        return "<br>" if tag == "br" else f"<{tag}>"

    return re.sub(r"(?is)<(/?)(article|section|h1|h2|h3|p|ul|ol|li|table|thead|tbody|tr|th|td|aside|strong|em|br)\b[^>]*>", clean_allowed_tag, text).strip()


def _split_translation_chunks(text: str, *, limit: int = TRANSLATION_CHUNK_CHAR_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    blocks = re.split(r"(\n\s*\n)", text)
    for block in blocks:
        if not block:
            continue
        if current and current_len + len(block) > limit:
            chunks.append("".join(current).strip())
            current = []
            current_len = 0
        if len(block) > limit:
            for start in range(0, len(block), limit):
                part = block[start:start + limit].strip()
                if part:
                    chunks.append(part)
            continue
        current.append(block)
        current_len += len(block)
    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _translation_output_looks_complete(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.endswith(("।", ".", "!", "?", ":", ";", ")", "]", "}", ">", "”", '"', "'")):
        return True
    return bool(re.search(r"</(article|section|p|li|td|th|aside)>$", text, flags=re.I))


def _simple_html_translation(
    settings: dict,
    *,
    text: str,
    source_language: str,
    target_language: str,
    mode: str,
    context: str | None,
    model: str,
) -> str | None:
    system = (
        "You are a careful professional translator. Translate the source into the target language. "
        "Output only safe semantic HTML using article, section, h2, p, ul, ol, li, table, thead, tbody, tr, th, td, strong, em, and br. "
        "Do not output JSON, markdown fences, scripts, styles, or commentary outside the HTML."
    )
    user = _user_prompt(text=text, source_language=source_language, target_language=target_language, mode=mode, context=context)
    return complete_with_configured_llm(settings, system, user, model=model, temperature=0.1, max_tokens=TRANSLATION_LLM_MAX_TOKENS)


def _fallback_html(text: str, *, target_language: str, mode: str) -> dict:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    body = "\n".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs[:80])
    return {
        "translated_html": (
            f'<article class="translation-output" data-mode="{html.escape(mode)}" data-target-language="{html.escape(target_language)}">'
            f"{body}"
            '<aside class="translation-warnings"><p>No configured LLM provider was available, so translation was not performed.</p></aside>'
            "</article>"
        ),
        "translated_text": text,
        "translator_notes": ["Configure an LLM provider in Settings to perform translation."],
        "warnings": ["Translation unavailable because no LLM provider is configured."],
        "preserved_terms": [],
        "quality_check": {"human_review_required": True, "status": "not_translated"},
        "detected_language": None,
        "provider": None,
        "model": None,
    }


def _translate_single(text: str, *, source_language: str, target_language: str, mode: str, context: str | None, settings: dict, provider: str, model: str) -> dict:
    raw = complete_with_configured_llm(
        settings,
        _system_prompt(mode),
        _user_prompt(text=text, source_language=source_language, target_language=target_language, mode=mode, context=context),
        model=model,
        temperature=0.1,
        max_tokens=TRANSLATION_LLM_MAX_TOKENS,
    )
    if not raw:
        return _fallback_html(text, target_language=target_language, mode=mode)
    incomplete_raw = not str(raw).strip().endswith("}")
    try:
        data = _json_from_llm(raw)
    except (json.JSONDecodeError, ValueError):
        html_output = _simple_html_translation(
            settings,
            text=text,
            source_language=source_language,
            target_language=target_language,
            mode=mode,
            context=context,
            model=model,
        )
        if not html_output:
            raise
        html_output = html_output.strip()
        html_output = re.sub(r"^```(?:html)?\s*", "", html_output)
        html_output = re.sub(r"\s*```$", "", html_output)
        html_output = _sanitize_html(html_output)
        warnings = ["Review required: structured translation metadata may be incomplete for this run."]
        if not _translation_output_looks_complete(html_output):
            warnings.append("Review required: translated output may be incomplete because the provider response did not end cleanly.")
        return {
            "translated_html": html_output,
            "translated_text": _strip_html(html_output),
            "translator_notes": ["The model returned malformed structured JSON, so AI Blueprint regenerated a simplified HTML translation."],
            "warnings": warnings,
            "preserved_terms": [],
            "quality_check": {"human_review_required": True, "structured_metadata_complete": False},
            "detected_language": None,
            "provider": provider,
            "model": model,
        }
    translated_html = _sanitize_html(str(data.get("translated_html") or ""))
    translated_text = str(data.get("translated_text") or "").strip() or _strip_html(translated_html)
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []
    if incomplete_raw or not _translation_output_looks_complete(translated_html or translated_text):
        warnings = [*warnings, "Review required: translated output may be incomplete because the provider response did not end cleanly."]
    return {
        "translated_html": translated_html,
        "translated_text": translated_text,
        "translator_notes": data.get("translator_notes") if isinstance(data.get("translator_notes"), list) else [],
        "warnings": warnings,
        "preserved_terms": data.get("preserved_terms") if isinstance(data.get("preserved_terms"), list) else [],
        "quality_check": data.get("quality_check") if isinstance(data.get("quality_check"), dict) else {"human_review_required": True},
        "detected_language": data.get("detected_language") if data.get("detected_language") else None,
        "provider": provider,
        "model": model,
    }


def _translate(text: str, *, source_language: str, target_language: str, mode: str, context: str | None) -> dict:
    settings = get_runtime_settings_with_secrets()
    provider = configured_llm_provider(settings)
    model = settings.get("chat_model", "gpt-4o")
    if not provider:
        return _fallback_html(text, target_language=target_language, mode=mode)
    chunks = _split_translation_chunks(text)
    if len(chunks) == 1:
        return _translate_single(
            text,
            source_language=source_language,
            target_language=target_language,
            mode=mode,
            context=context,
            settings=settings,
            provider=provider,
            model=model,
        )
    translated_parts = []
    text_parts = []
    notes: list[Any] = []
    warnings: list[Any] = [f"Long source text was translated in {len(chunks)} chunks to avoid provider output truncation."]
    preserved_terms: list[Any] = []
    detected_language = None
    quality_checks = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_result = _translate_single(
            chunk,
            source_language=source_language,
            target_language=target_language,
            mode=mode,
            context=f"{context or ''}\nChunk {index} of {len(chunks)}. Preserve terminology consistently across chunks.".strip(),
            settings=settings,
            provider=provider,
            model=model,
        )
        translated_parts.append(f'<section><h2>Part {index}</h2>{chunk_result.get("translated_html") or ""}</section>')
        text_parts.append(str(chunk_result.get("translated_text") or ""))
        notes.extend(chunk_result.get("translator_notes") or [])
        warnings.extend(chunk_result.get("warnings") or [])
        preserved_terms.extend(chunk_result.get("preserved_terms") or [])
        detected_language = detected_language or chunk_result.get("detected_language")
        quality_checks.append(chunk_result.get("quality_check") or {})
    return {
        "translated_html": _sanitize_html(f'<article class="translation-output">{"".join(translated_parts)}</article>'),
        "translated_text": "\n\n".join(part for part in text_parts if part.strip()),
        "translator_notes": list(dict.fromkeys(str(item) for item in notes if str(item).strip()))[:80],
        "warnings": list(dict.fromkeys(str(item) for item in warnings if str(item).strip()))[:80],
        "preserved_terms": list(dict.fromkeys(str(item) for item in preserved_terms if str(item).strip()))[:120],
        "quality_check": {"human_review_required": True, "chunked": True, "chunks": len(chunks), "chunk_quality_checks": quality_checks[:20]},
        "detected_language": detected_language,
        "provider": provider,
        "model": model,
    }


def _result_payload(result: dict, *, source_type: str, source_filename: str | None, source_language: str, target_language: str, mode: str, context: str | None) -> dict:
    warnings = list(result.get("warnings") or [])
    if mode in {"legal", "medical", "technical"} and not any("review" in str(item).lower() for item in warnings):
        warnings.append("Human review is required before official, legal, medical, technical, or regulated use.")
    translated_html = _sanitize_html(result.get("translated_html") or "")
    return {
        "source_type": source_type,
        "source_filename": source_filename,
        "source_language": source_language,
        "detected_language": result.get("detected_language"),
        "target_language": target_language,
        "mode": mode,
        "context": context,
        "translated_html": translated_html,
        "translated_text": result.get("translated_text") or _strip_html(translated_html),
        "translator_notes": result.get("translator_notes") or [],
        "warnings": warnings,
        "preserved_terms": result.get("preserved_terms") or [],
        "quality_check": result.get("quality_check") or {"human_review_required": True},
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _save_translation_run(
    db: Session,
    *,
    workspace_id: str,
    user: User,
    source_type: str,
    source_filename: str | None,
    source_language: str,
    target_language: str,
    mode: str,
    context: str | None,
    matter_id: str | None,
    source_text: str,
    payload: dict,
) -> TranslationRun:
    run = TranslationRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=matter_id,
        source_type=source_type,
        source_filename=source_filename,
        source_language=source_language,
        detected_language=payload.get("detected_language"),
        target_language=target_language,
        mode=mode,
        context=context,
        source_text_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        translated_html=payload["translated_html"],
        translated_text=payload["translated_text"],
        translator_notes_json=json.dumps(payload["translator_notes"], sort_keys=True),
        warnings_json=json.dumps(payload["warnings"], sort_keys=True),
        quality_check_json=json.dumps(payload["quality_check"], sort_keys=True),
        preserved_terms_json=json.dumps(payload["preserved_terms"], sort_keys=True),
        provider=payload.get("provider"),
        model=payload.get("model"),
        status="completed",
        created_by_user_id=user.id,
        completed_at=utcnow(),
    )
    db.add(run)
    db.flush()
    record_audit_event(
        db,
        action="translation.run.create",
        resource_type="translation_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"source_type": source_type, "mode": mode, "target_language": target_language, "matter_id": matter_id},
    )
    return run


def _run_translation(*, text: str, source_type: str, source_filename: str | None, source_language: str, target_language: str, mode: str, context: str | None) -> dict:
    if len(text) > 120_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Source text is too large for one translation request")
    try:
        result = _translate(text, source_language=source_language, target_language=target_language, mode=mode, context=context)
    except HTTPException:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Translation model returned an invalid response: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Translation provider failed: {exc}")
    return _result_payload(
        result,
        source_type=source_type,
        source_filename=source_filename,
        source_language=source_language,
        target_language=target_language,
        mode=mode,
        context=context,
    )


@router.post("/translations/public/text")
async def public_translate_text(body: TranslationTextIn, _user: User = Depends(get_current_user)):
    mode = _validate_mode(body.mode)
    target_language = _validate_target_language(body.target_language)
    return _run_translation(
        text=body.text.strip(),
        source_type="text",
        source_filename=None,
        source_language=body.source_language.strip() or "auto",
        target_language=target_language,
        mode=mode,
        context=body.context,
    )


@router.post("/translations/public/upload")
async def public_translate_upload(
    file: UploadFile = File(...),
    source_language: str = Form(default="auto"),
    target_language: str = Form(...),
    mode: str = Form(default="legal"),
    context: str | None = Form(default=None),
    _user: User = Depends(get_current_user),
):
    mode = _validate_mode(mode)
    target_language = _validate_target_language(target_language)
    path, stored = await _store_translation_temp_upload(file)
    try:
        text, _sections = _extract_upload_text(path, stored["original_name"])
        return _run_translation(
            text=text,
            source_type="document",
            source_filename=stored["original_name"],
            source_language=source_language.strip() or "auto",
            target_language=target_language,
            mode=mode,
            context=context,
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/workspaces/{workspace_id}/translations/text")
async def workspace_translate_text(
    workspace_id: str,
    body: TranslationTextIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    mode = _validate_mode(body.mode)
    target_language = _validate_target_language(body.target_language)
    source_text = body.text.strip()
    payload = _run_translation(
        text=source_text,
        source_type="text",
        source_filename=None,
        source_language=body.source_language.strip() or "auto",
        target_language=target_language,
        mode=mode,
        context=body.context,
    )
    run = _save_translation_run(
        db,
        workspace_id=workspace_id,
        user=user,
        source_type="text",
        source_filename=None,
        source_language=payload["source_language"],
        target_language=target_language,
        mode=mode,
        context=body.context,
        matter_id=body.matter_id,
        source_text=source_text,
        payload=payload,
    )
    db.commit()
    db.refresh(run)
    saved = _format_translation(run)
    saved["persisted"] = True
    return saved


@router.post("/workspaces/{workspace_id}/translations/upload")
async def workspace_translate_upload(
    workspace_id: str,
    file: UploadFile = File(...),
    source_language: str = Form(default="auto"),
    target_language: str = Form(...),
    mode: str = Form(default="legal"),
    context: str | None = Form(default=None),
    matter_id: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, matter_id)
    mode = _validate_mode(mode)
    target_language = _validate_target_language(target_language)
    path, stored = await _store_translation_temp_upload(file)
    try:
        source_text, _sections = _extract_upload_text(path, stored["original_name"])
        payload = _run_translation(
            text=source_text,
            source_type="document",
            source_filename=stored["original_name"],
            source_language=source_language.strip() or "auto",
            target_language=target_language,
            mode=mode,
            context=context,
        )
        run = _save_translation_run(
            db,
            workspace_id=workspace_id,
            user=user,
            source_type="document",
            source_filename=stored["original_name"],
            source_language=payload["source_language"],
            target_language=target_language,
            mode=mode,
            context=context,
            matter_id=matter_id,
            source_text=source_text,
            payload=payload,
        )
        db.commit()
        db.refresh(run)
        saved = _format_translation(run)
        saved["persisted"] = True
        return saved
    finally:
        path.unlink(missing_ok=True)


@router.get("/workspaces/{workspace_id}/translations")
async def list_workspace_translations(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    query = select(TranslationRun).where(TranslationRun.workspace_id == workspace_id).order_by(TranslationRun.created_at.desc())
    return page_query_response(db, query, _format_translation, page=page, page_size=page_size, scalars=True)


@router.get("/workspaces/{workspace_id}/translations/{translation_id}")
async def get_workspace_translation(
    workspace_id: str,
    translation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    run = db.execute(select(TranslationRun).where(TranslationRun.workspace_id == workspace_id, TranslationRun.id == translation_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Translation not found")
    return _format_translation(run)
