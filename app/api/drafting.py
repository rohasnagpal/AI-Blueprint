import hashlib
import html
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider, get_legacy_settings_with_secrets
from app.core.jobs import add_job_event, create_job, format_job, update_job_status
from app.core.models import DraftRun, Job, KnowledgeChunk, KnowledgeDocument, Matter, User, utcnow
from app.core.pagination import page_query_response
from app.core.task_control import run_background_job

router = APIRouter(tags=["drafting"])

TONES = {"formal", "neutral", "firm", "aggressive", "collaborative", "client-friendly", "plain-language"}
ALLOWED_TAGS = "article|section|header|footer|h1|h2|h3|h4|p|ol|ul|li|table|thead|tbody|tr|th|td|blockquote|aside|strong|em|br|hr|small|div|span"


class DraftRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    document_type: str = Field(default="Legal notice", min_length=1, max_length=150)
    jurisdiction: str | None = Field(default=None, max_length=150)
    tone: str = Field(default="formal", max_length=100)
    audience: str | None = Field(default=None, max_length=255)
    parties: str | None = Field(default=None, max_length=4000)
    facts: str = Field(min_length=1, max_length=80_000)
    key_terms: str | None = Field(default=None, max_length=20_000)
    instructions: str | None = Field(default=None, max_length=12_000)
    matter_id: str | None = None
    source_document_ids: list[str] = Field(default_factory=list, max_length=12)


def _format_draft(run: DraftRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "matter_id": run.matter_id,
        "title": run.title,
        "document_type": run.document_type,
        "jurisdiction": run.jurisdiction,
        "tone": run.tone,
        "audience": run.audience,
        "config": json_loads(run.config_json, {}),
        "draft_html": run.draft_html,
        "draft_text": run.draft_text,
        "assumptions": json_loads(run.assumptions_json, []),
        "missing_information": json_loads(run.missing_information_json, []),
        "review_warnings": json_loads(run.review_warnings_json, []),
        "sources": json_loads(run.sources_json, []),
        "provider": run.provider,
        "model": run.model,
        "status": run.status,
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _validate_document_type(document_type: str) -> str:
    value = re.sub(r"\s+", " ", document_type.strip())
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document type is required")
    return value[:150]


def _validate_tone(tone: str) -> str:
    value = tone.strip().lower()
    if value not in TONES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported drafting tone")
    return value


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> None:
    if not matter_id:
        return
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")


def _source_context(db: Session, workspace_id: str, matter_id: str | None, document_ids: list[str]) -> tuple[str, list[dict[str, Any]]]:
    if not document_ids:
        return "", []
    unique_ids = list(dict.fromkeys(document_ids))[:12]
    docs = db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.workspace_id == workspace_id,
            KnowledgeDocument.id.in_(unique_ids),
        )
    ).scalars().all()
    docs_by_id = {doc.id: doc for doc in docs}
    missing = [doc_id for doc_id in unique_ids if doc_id not in docs_by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more source documents were not found")
    if matter_id and any(doc.matter_id not in {None, matter_id} for doc in docs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source documents must belong to the selected matter or workspace scope")
    chunks = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.document_id.in_(unique_ids))
        .order_by(KnowledgeDocument.original_name, KnowledgeChunk.chunk_index)
        .limit(36)
    ).all()
    source_lines = []
    sources = []
    for chunk, doc in chunks:
        excerpt = chunk.content.strip()[:1600]
        if not excerpt:
            continue
        source_lines.append(f"[{doc.original_name} | chunk {chunk.chunk_index}]\n{excerpt}")
        sources.append({"document_id": doc.id, "filename": doc.original_name, "chunk": chunk.chunk_index, "excerpt": excerpt[:360]})
    return "\n\n".join(source_lines), sources


def _system_prompt() -> str:
    return (
        "You are a careful legal drafting assistant. Return only valid JSON. "
        "Every JSON string must be validly escaped. Do not place literal line breaks inside JSON string values. "
        "Do not output markdown fences or commentary outside JSON. "
        "Do not invent facts, dates, addresses, citations, statutory references, party names, or negotiated terms. "
        "Use placeholders in square brackets for missing facts. "
        "If source excerpts are supplied, use them only as context and identify material source usage."
    )


def _user_prompt(body: DraftRequest, *, document_type: str, tone: str, source_context: str) -> str:
    return json.dumps(
        {
            "document_type": document_type,
            "requested_title": body.title or "",
            "jurisdiction": body.jurisdiction or "",
            "tone": tone,
            "audience": body.audience or "",
            "parties": body.parties or "",
            "facts": body.facts,
            "key_terms": body.key_terms or "",
            "instructions": body.instructions or "",
            "source_context": source_context,
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
        data = decoder.decode(re.sub(r",\s*([}\]])", r"\1", match.group(0)))
    if not isinstance(data, dict):
        raise ValueError("Drafting model returned an invalid payload")
    return data


def _strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</(?:p|h1|h2|h3|h4|li|tr|section|article)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _sanitize_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style|iframe|object|embed|link|meta)[^>]*>.*?</\1>", "", value or "")
    text = re.sub(r"(?is)</?(?!(?:" + ALLOWED_TAGS + r")\b)[a-z][^>]*>", "", text)
    text = re.sub(r"\s+on[a-z]+\s*=\s*(?:(['\"]).*?\1|[^\s>]+)", "", text, flags=re.I | re.S)
    text = re.sub(r"\s+(href|src)\s*=\s*(['\"])\s*javascript:.*?\2", "", text, flags=re.I | re.S)
    return text.strip()


def _paragraph_html(text: str) -> str:
    safe = html.escape(str(text or "").strip()).replace("\n", "<br>")
    return f"<p>{safe}</p>" if safe else ""


def _list_html(items: list[Any]) -> str:
    clean = [html.escape(str(item).strip()) for item in items if str(item).strip()]
    if not clean:
        return ""
    return "<ol>" + "".join(f"<li>{item}</li>" for item in clean) + "</ol>"


def _render_printable_html(title: str, sections: list[dict[str, Any]], *, document_type: str) -> str:
    parts = [f'<article class="draft-document" data-document-type="{html.escape(document_type)}">', f"<header><h1>{html.escape(title)}</h1></header>"]
    for index, section in enumerate(sections, start=1):
        heading = str(section.get("heading") or f"Section {index}").strip()
        body = section.get("body")
        bullets = section.get("bullets")
        html_body = _list_html(bullets) if isinstance(bullets, list) and bullets else _paragraph_html(str(body or ""))
        parts.append(f"<section><h2>{html.escape(heading)}</h2>{html_body}</section>")
    parts.append("</article>")
    return "".join(parts)


def _estimate_tokens(*parts: str) -> int:
    return max(1, sum(len(part or "") for part in parts) // 4)


def _call_json(
    settings: dict,
    *,
    system: str,
    user: dict[str, Any],
    model: str,
    max_tokens: int = 3000,
    temperature: float = 0.1,
    token_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    user_json = json.dumps(user, ensure_ascii=False)
    prompt_tokens = _estimate_tokens(system, user_json)
    raw = complete_with_configured_llm(settings, system, user_json, model=model, temperature=temperature, max_tokens=max_tokens)
    if not raw:
        raise ValueError("Drafting model returned an empty response")
    completion_tokens = _estimate_tokens(raw)
    if token_callback:
        token_callback({"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens, "exact": False})
    try:
        return _json_from_llm(raw)
    except (json.JSONDecodeError, ValueError):
        repair_system = (
            "Return only valid JSON. Repair the malformed JSON-like text from the user. "
            "Preserve all recoverable keys and content. Do not add commentary, markdown fences, or new facts."
        )
        repaired = complete_with_configured_llm(
            settings,
            repair_system,
            json.dumps({"malformed_json": raw[:12000]}, ensure_ascii=False),
            model=model,
            temperature=0,
            max_tokens=min(max_tokens, 2500),
        )
        if not repaired:
            raise
        if token_callback:
            repair_prompt_tokens = _estimate_tokens(repair_system, raw[:12000])
            repair_completion_tokens = _estimate_tokens(repaired)
            token_callback({"prompt_tokens": repair_prompt_tokens, "completion_tokens": repair_completion_tokens, "total_tokens": repair_prompt_tokens + repair_completion_tokens, "exact": False, "repair": True})
        return _json_from_llm(repaired)


def _analysis_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, source_context: str, model: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Analyze the requested legal document. Return JSON keys: title, document_family, purpose, governing_context, required_sections, missing_information, assumptions, drafting_risks, source_use_plan."
    )
    data = _call_json(
        settings,
        system=system,
        user={"task": "analyze_intent", "request": json.loads(_user_prompt(body, document_type=document_type, tone=tone, source_context=source_context[:6000]))},
        model=model,
        max_tokens=1400,
    )
    data.setdefault("title", body.title or f"Draft {document_type.title()}")
    return data


def _outline_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, analysis: dict[str, Any], model: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Build a professional drafting outline. Return JSON keys: title, sections. sections must be an array of objects with heading, purpose, required_points, risk_notes."
    )
    data = _call_json(
        settings,
        system=system,
        user={"task": "build_outline", "document_type": document_type, "tone": tone, "jurisdiction": body.jurisdiction or "", "analysis": analysis},
        model=model,
        max_tokens=1600,
    )
    if not isinstance(data.get("sections"), list) or not data["sections"]:
        data["sections"] = [{"heading": "Background", "purpose": "Set out the facts.", "required_points": [], "risk_notes": []}]
    data.setdefault("title", analysis.get("title") or body.title or f"Draft {document_type.title()}")
    return data


def _section_draft_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, analysis: dict[str, Any], outline: dict[str, Any], source_context: str, model: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Draft each section as structured content, not HTML. Return JSON keys: sections, assumptions, missing_information, review_warnings, sources_used. "
        "Each section object must have heading and body, or heading and bullets. Use numbered clause style where appropriate."
    )
    return _call_json(
        settings,
        system=system,
        user={
            "task": "draft_sections",
            "document_type": document_type,
            "tone": tone,
            "jurisdiction": body.jurisdiction or "",
            "audience": body.audience or "",
            "parties": body.parties or "",
            "facts": body.facts,
            "key_terms": body.key_terms or "",
            "instructions": body.instructions or "",
            "analysis": analysis,
            "outline": outline,
            "source_context": source_context,
        },
        model=model,
        max_tokens=3200,
        temperature=0.15,
    )


def _qa_step(settings: dict, body: DraftRequest, *, document_type: str, analysis: dict[str, Any], outline: dict[str, Any], draft: dict[str, Any], model: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Review the draft like a senior lawyer. Return JSON keys: issues, missing_information, assumptions, review_warnings, revision_instructions. "
        "Focus on missing facts, undefined terms, unsupported claims, jurisdiction risk, inconsistent dates or amounts, structure gaps, tone mismatch, and placeholders."
    )
    return _call_json(
        settings,
        system=system,
        user={"task": "quality_review", "document_type": document_type, "request_facts": body.facts, "analysis": analysis, "outline": outline, "draft": draft},
        model=model,
        max_tokens=2000,
    )


def _revision_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, draft: dict[str, Any], qa: dict[str, Any], model: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Revise the draft using the QA findings. Return JSON keys: title, sections, assumptions, missing_information, review_warnings, sources_used. "
        "Each section object must have heading and body, or heading and bullets. Preserve placeholders for facts that are not known."
    )
    return _call_json(
        settings,
        system=system,
        user={"task": "revise_sections", "document_type": document_type, "tone": tone, "jurisdiction": body.jurisdiction or "", "draft": draft, "qa": qa},
        model=model,
        max_tokens=3200,
        temperature=0.1,
    )


def _plan_and_draft_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, source_context: str, model: str, token_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Run intake, outline, and first drafting in one pass. Return JSON keys: title, outline, sections, assumptions, missing_information, review_warnings, sources_used. "
        "sections must be an array of objects with heading and body, or heading and bullets. Use a professional structure appropriate to the requested document type."
    )
    return _call_json(
        settings,
        system=system,
        user={
            "task": "plan_and_draft",
            "document_type": document_type,
            "tone": tone,
            "jurisdiction": body.jurisdiction or "",
            "audience": body.audience or "",
            "parties": body.parties or "",
            "facts": body.facts,
            "key_terms": body.key_terms or "",
            "instructions": body.instructions or "",
            "source_context": source_context[:6000],
        },
        model=model,
        max_tokens=3400,
        temperature=0.15,
        token_callback=token_callback,
    )


def _qa_and_revise_step(settings: dict, body: DraftRequest, *, document_type: str, tone: str, draft: dict[str, Any], model: str, token_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Review the draft like a senior lawyer, then return the revised structured draft. "
        "Return JSON keys: title, sections, assumptions, missing_information, review_warnings, qa_issues, sources_used. "
        "Do not invent missing facts; preserve placeholders."
    )
    return _call_json(
        settings,
        system=system,
        user={"task": "qa_and_revise", "document_type": document_type, "tone": tone, "jurisdiction": body.jurisdiction or "", "draft": draft},
        model=model,
        max_tokens=3400,
        temperature=0.1,
        token_callback=token_callback,
    )


def _default_analysis(body: DraftRequest, *, document_type: str) -> dict[str, Any]:
    return {
        "title": body.title or f"Draft {document_type.title()}",
        "document_family": document_type,
        "purpose": body.instructions or f"Prepare a {document_type}.",
        "governing_context": body.jurisdiction or "[Jurisdiction]",
        "required_sections": ["Title", "Parties", "Background", "Operative provisions", "Signatures"],
        "missing_information": ["Add complete party details, dates, addresses, commercial terms, and governing law where applicable."],
        "assumptions": [],
        "drafting_risks": ["Generated draft requires legal review before use."],
        "source_use_plan": [],
    }


def _default_outline(analysis: dict[str, Any]) -> dict[str, Any]:
    title = str(analysis.get("title") or "Draft")
    required = analysis.get("required_sections") if isinstance(analysis.get("required_sections"), list) else []
    headings = [str(item).strip() for item in required if str(item).strip()] or ["Background", "Operative Provisions", "Signatures"]
    return {
        "title": title,
        "sections": [{"heading": heading, "purpose": f"Draft the {heading.lower()} section.", "required_points": [], "risk_notes": []} for heading in headings[:12]],
    }


def _default_section_draft(body: DraftRequest, outline: dict[str, Any]) -> dict[str, Any]:
    sections = []
    outline_sections = outline.get("sections") if isinstance(outline.get("sections"), list) else []
    for item in outline_sections:
        heading = str(item.get("heading") if isinstance(item, dict) else item).strip() or "Section"
        if heading.lower() in {"background", "recitals", "facts"}:
            body_text = body.facts
        elif heading.lower() in {"parties", "party details"}:
            body_text = body.parties or "[Insert complete party details.]"
        elif heading.lower() in {"operative provisions", "terms", "key terms"}:
            body_text = body.key_terms or "[Insert operative clauses and commercial terms.]"
        elif heading.lower() in {"signatures", "execution"}:
            body_text = "[Insert signature blocks, dates, names, designations, and execution details.]"
        else:
            body_text = "[Draft this section after confirming the missing facts and instructions.]"
        sections.append({"heading": heading, "body": body_text})
    return {
        "sections": sections or [{"heading": "Background", "body": body.facts}],
        "assumptions": [],
        "missing_information": ["Some sections were generated from fallback structure because the drafting model returned an invalid intermediate response."],
        "review_warnings": ["Human legal review is required before use."],
        "sources_used": [],
    }


def _fallback_draft(body: DraftRequest, *, document_type: str, tone: str) -> dict:
    title = body.title or f"Draft {document_type.title()}"
    facts = html.escape(body.facts).replace("\n", "<br>")
    key_terms = html.escape(body.key_terms or "").replace("\n", "<br>")
    html_output = (
        f'<article class="draft-document">'
        f"<header><h1>{html.escape(title)}</h1><p><strong>Document type:</strong> {html.escape(document_type)}</p></header>"
        f"<section><h2>Background</h2><p>{facts}</p></section>"
        f"{f'<section><h2>Key Terms</h2><p>{key_terms}</p></section>' if key_terms else ''}"
        '<section><h2>Review Note</h2><p>Configure an LLM provider in Settings to generate a full legal draft.</p></section>'
        "</article>"
    )
    return {
        "title": title,
        "draft_html": html_output,
        "draft_text": _strip_html(html_output),
        "assumptions": [],
        "missing_information": ["Configured LLM provider is required for full drafting."],
        "review_warnings": ["Human legal review is required before use."],
        "sources_used": [],
        "provider": None,
        "model": None,
    }


def _draft(body: DraftRequest, *, document_type: str, tone: str, source_context: str, progress_callback: Callable[[str, int, dict[str, Any] | None], None] | None = None) -> dict:
    settings = get_legacy_settings_with_secrets()
    provider = configured_llm_provider(settings)
    model = settings.get("chat_model", "gpt-4o")
    estimated_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "exact": False}

    def add_tokens(usage: dict[str, Any]) -> None:
        estimated_tokens["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        estimated_tokens["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        estimated_tokens["total_tokens"] += int(usage.get("total_tokens") or 0)
        if progress_callback:
            progress_callback("Estimated token use updated", 0, {"stage": "tokens", "tokens": dict(estimated_tokens), "exact_tokens": False})

    if not provider:
        return _fallback_draft(body, document_type=document_type, tone=tone)
    pipeline_warnings = []
    try:
        if progress_callback:
            progress_callback("Planning document structure and drafting sections", 35, {"stage": "plan_and_draft", "tokens": dict(estimated_tokens)})
        section_draft = _plan_and_draft_step(settings, body, document_type=document_type, tone=tone, source_context=source_context, model=model, token_callback=add_tokens)
    except Exception as exc:
        analysis = _default_analysis(body, document_type=document_type)
        outline = _default_outline(analysis)
        section_draft = _default_section_draft(body, outline)
        pipeline_warnings.append(f"Plan-and-draft fallback used: {exc}")
    outline = section_draft.get("outline") if isinstance(section_draft.get("outline"), dict) else {"sections": []}
    analysis = {"title": section_draft.get("title") or body.title or f"Draft {document_type.title()}", "missing_information": section_draft.get("missing_information") or [], "assumptions": section_draft.get("assumptions") or [], "drafting_risks": section_draft.get("review_warnings") or []}
    try:
        if progress_callback:
            progress_callback("Reviewing draft and revising weak sections", 70, {"stage": "qa_and_revise", "tokens": dict(estimated_tokens)})
        data = _qa_and_revise_step(settings, body, document_type=document_type, tone=tone, draft=section_draft, model=model, token_callback=add_tokens)
    except Exception as exc:
        qa = {"issues": [], "missing_information": [], "assumptions": [], "review_warnings": ["QA fallback used; review the draft carefully."], "revision_instructions": []}
        data = section_draft
        pipeline_warnings.append(f"QA-and-revision fallback used: {exc}")
    if "qa" not in locals():
        qa = {"issues": data.get("qa_issues") if isinstance(data.get("qa_issues"), list) else [], "missing_information": data.get("missing_information") or [], "assumptions": data.get("assumptions") or [], "review_warnings": data.get("review_warnings") or []}
    sections = data.get("sections") if isinstance(data.get("sections"), list) else section_draft.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Drafting pipeline did not produce sections")
    title = str(data.get("title") or outline.get("title") or analysis.get("title") or body.title or f"Draft {document_type.title()}")[:255]
    if progress_callback:
        progress_callback("Rendering printable HTML", 88, {"stage": "render", "tokens": dict(estimated_tokens)})
    draft_html = _sanitize_html(_render_printable_html(title, sections, document_type=document_type))
    missing = []
    assumptions = []
    warnings = []
    for payload, key in ((analysis, "missing_information"), (section_draft, "missing_information"), (qa, "missing_information"), (data, "missing_information")):
        if isinstance(payload.get(key), list):
            missing.extend(payload[key])
    for payload, key in ((analysis, "assumptions"), (section_draft, "assumptions"), (qa, "assumptions"), (data, "assumptions")):
        if isinstance(payload.get(key), list):
            assumptions.extend(payload[key])
    for payload, key in ((analysis, "drafting_risks"), (section_draft, "review_warnings"), (qa, "review_warnings"), (data, "review_warnings")):
        if isinstance(payload.get(key), list):
            warnings.extend(payload[key])
    warnings.extend(pipeline_warnings)
    return {
        "title": title,
        "draft_html": draft_html,
        "draft_text": _strip_html(draft_html),
        "assumptions": list(dict.fromkeys(str(item) for item in assumptions if str(item).strip()))[:24],
        "missing_information": list(dict.fromkeys(str(item) for item in missing if str(item).strip()))[:24],
        "review_warnings": list(dict.fromkeys(str(item) for item in warnings if str(item).strip()))[:24],
        "sources_used": data.get("sources_used") if isinstance(data.get("sources_used"), list) else [],
        "drafting_trace": {"analysis": analysis, "outline": outline, "qa": qa, "pipeline": "plan_draft_qa_revision_render_v2", "tokens": dict(estimated_tokens)},
        "token_usage": dict(estimated_tokens),
        "provider": provider,
        "model": model,
    }


def _result_payload(body: DraftRequest, *, document_type: str, tone: str, source_context: str, sources: list[dict], progress_callback: Callable[[str, int, dict[str, Any] | None], None] | None = None) -> dict:
    try:
        result = _draft(body, document_type=document_type, tone=tone, source_context=source_context, progress_callback=progress_callback)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Drafting model returned an invalid response: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Drafting provider failed: {exc}")
    warnings = list(result.get("review_warnings") or [])
    if not any("review" in str(item).lower() for item in warnings):
        warnings.append("Human legal review is required before use or circulation.")
    return {
        "title": result.get("title") or body.title or f"Draft {document_type.title()}",
        "document_type": document_type,
        "jurisdiction": body.jurisdiction,
        "tone": tone,
        "audience": body.audience,
        "draft_html": result.get("draft_html") or "",
        "draft_text": result.get("draft_text") or "",
        "assumptions": result.get("assumptions") or [],
        "missing_information": result.get("missing_information") or [],
        "review_warnings": warnings,
        "sources": sources or result.get("sources_used") or [],
        "drafting_trace": result.get("drafting_trace") or {},
        "token_usage": result.get("token_usage") or {},
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _save_draft_run(db: Session, *, workspace_id: str, user: User, body: DraftRequest, payload: dict) -> DraftRun:
    run = DraftRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=body.matter_id,
        title=str(payload["title"])[:255],
        document_type=payload["document_type"],
        jurisdiction=payload.get("jurisdiction"),
        tone=payload["tone"],
        audience=payload.get("audience"),
        facts_hash=hashlib.sha256(body.facts.encode("utf-8")).hexdigest(),
        config_json=json.dumps(
            {
                "parties": body.parties,
                "key_terms": body.key_terms,
                "instructions": body.instructions,
                "source_document_ids": body.source_document_ids,
                "drafting_trace": payload.get("drafting_trace") or {},
                "token_usage": payload.get("token_usage") or {},
            },
            sort_keys=True,
        ),
        draft_html=payload["draft_html"],
        draft_text=payload["draft_text"],
        assumptions_json=json.dumps(payload["assumptions"], sort_keys=True),
        missing_information_json=json.dumps(payload["missing_information"], sort_keys=True),
        review_warnings_json=json.dumps(payload["review_warnings"], sort_keys=True),
        sources_json=json.dumps(payload["sources"], sort_keys=True),
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
        action="draft.run.create",
        resource_type="draft_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_type": run.document_type, "matter_id": run.matter_id, "source_document_count": len(body.source_document_ids)},
    )
    return run


def _run_workspace_draft_job(job_id: str, workspace_id: str, user_id: str, body_data: dict[str, Any], document_type: str, tone: str, source_context: str, sources: list[dict]) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        user = db.get(User, user_id)
        if not job or not user:
            return

        def progress(message: str, progress_value: int, metadata: dict[str, Any] | None = None) -> None:
            if progress_value:
                job.progress = max(job.progress, min(99, progress_value))
            add_job_event(db, job=job, event_type="progress", message=message, metadata={"progress": job.progress, **(metadata or {})})
            db.commit()

        try:
            body = DraftRequest(**body_data)
            update_job_status(db, job=job, status="running", progress=10, message="Draft generation started")
            add_job_event(db, job=job, event_type="progress", message="Reading draft inputs", metadata={"progress": 15, "stage": "input", "document_type": document_type})
            db.commit()
            payload = _result_payload(body, document_type=document_type, tone=tone, source_context=source_context, sources=sources, progress_callback=progress)
            progress("Saving draft", 94, {"stage": "save", "tokens": payload.get("token_usage") or {}})
            run = _save_draft_run(db, workspace_id=workspace_id, user=user, body=body, payload=payload)
            metadata = json_loads(job.metadata_json, {})
            metadata["draft_id"] = run.id
            metadata["token_usage"] = payload.get("token_usage") or {}
            job.metadata_json = json.dumps(metadata, sort_keys=True)
            update_job_status(db, job=job, status="completed", progress=100, message="Draft generation completed")
            db.commit()
        except Exception as exc:
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Draft generation failed", error=str(exc))
            db.commit()


@router.post("/drafts/public")
async def public_create_draft(body: DraftRequest, _user: User = Depends(get_current_user)):
    document_type = _validate_document_type(body.document_type)
    tone = _validate_tone(body.tone)
    return _result_payload(body, document_type=document_type, tone=tone, source_context="", sources=[])


@router.post("/workspaces/{workspace_id}/drafts")
async def workspace_create_draft(
    workspace_id: str,
    body: DraftRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    document_type = _validate_document_type(body.document_type)
    tone = _validate_tone(body.tone)
    source_context, sources = _source_context(db, workspace_id, body.matter_id, body.source_document_ids)
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="draft.run",
        metadata={"document_type": document_type, "matter_id": body.matter_id},
        message="Draft generation queued",
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, _run_workspace_draft_job, job.id, workspace_id, user.id, body.model_dump(), document_type, tone, source_context, sources)
    return {"job": format_job(job), "status": "queued"}


@router.get("/workspaces/{workspace_id}/drafts")
async def list_workspace_drafts(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    query = select(DraftRun).where(DraftRun.workspace_id == workspace_id).order_by(DraftRun.created_at.desc())
    return page_query_response(db, query, _format_draft, page=page, page_size=page_size, scalars=True)


@router.get("/workspaces/{workspace_id}/drafts/{draft_id}")
async def get_workspace_draft(
    workspace_id: str,
    draft_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    run = db.execute(select(DraftRun).where(DraftRun.workspace_id == workspace_id, DraftRun.id == draft_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return _format_draft(run)
