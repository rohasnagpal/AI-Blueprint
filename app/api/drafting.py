import hashlib
import html
import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider, get_runtime_settings_with_secrets
from app.core.jobs import add_job_event, create_job, format_job, update_job_status
from app.core.models import DraftRun, Job, KnowledgeChunk, KnowledgeDocument, Matter, User, utcnow
from app.core.pagination import page_query_response
from app.core.task_control import run_background_job

router = APIRouter(tags=["drafting"])

TONES = {"formal", "neutral", "firm", "aggressive", "collaborative", "client-friendly", "plain-language"}
ALLOWED_TAGS = "article|section|header|footer|h1|h2|h3|h4|p|ol|ul|li|table|thead|tbody|tr|th|td|blockquote|aside|strong|em|br|hr|small|div|span"
DRAFT_AGENT_SEQUENCE = [
    "draft_intake_agent",
    "draft_architect_writer_agent",
    "draft_review_revision_agent",
    "draft_render_agent",
]


class DraftRequest(BaseModel):
    details: str = Field(default="", max_length=80_000)
    tone: str = Field(default="formal", max_length=100)
    matter_id: str | None = None
    source_document_ids: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict) or str(data.get("details") or "").strip():
            return data
        parts = []
        labels = [
            ("document_type", "Document type"),
            ("jurisdiction", "Jurisdiction"),
            ("parties", "Parties"),
            ("facts", "Facts"),
            ("key_terms", "Key terms"),
            ("instructions", "Instructions"),
        ]
        for key, label in labels:
            value = str(data.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value}")
        if parts:
            data = dict(data)
            data["details"] = "\n".join(parts)
        return data

    @model_validator(mode="after")
    def require_details(self) -> "DraftRequest":
        if not self.details.strip():
            raise ValueError("Please describe what you need drafted.")
        return self


def _format_draft(run: DraftRun) -> dict:
    config = json_loads(run.config_json, {})
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "matter_id": run.matter_id,
        "title": run.title,
        "document_type": run.document_type,
        "jurisdiction": run.jurisdiction,
        "tone": run.tone,
        "audience": run.audience,
        "config": config,
        "draft_html": run.draft_html,
        "draft_text": run.draft_text,
        "assumptions": json_loads(run.assumptions_json, []),
        "missing_information": json_loads(run.missing_information_json, []),
        "review_warnings": json_loads(run.review_warnings_json, []),
        "sources": json_loads(run.sources_json, []),
        "provider": run.provider,
        "model": run.model,
        "agentic_review": config.get("agentic_review") or config.get("drafting_trace", {}).get("agentic_review") or {},
        "status": run.status,
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _validate_tone(tone: str) -> str:
    value = tone.strip().lower()
    if value not in TONES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported drafting tone")
    return value


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> None:
    if not matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter is required")
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
    if any(doc.matter_id != matter_id for doc in docs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source documents must belong to the selected matter")
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


def _render_printable_html(title: str, sections: list[dict[str, Any]], *, document_type: str, preamble: str | None = None) -> str:
    parts = [f'<article class="draft-document" data-document-type="{html.escape(document_type)}">', f"<header><h1>{html.escape(title)}</h1></header>"]
    if preamble and preamble.strip():
        parts.append(f'<div class="draft-preamble">{_sanitize_html(preamble)}</div>')
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


def _trace(step_name: str, status: str, provider: str | None, model: str | None, error: str | None = None, duration_ms: int | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "step_name": step_name,
        "status": status,
        "provider": provider or "internal",
        "model": model,
        "error": error,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if metadata:
        payload["metadata"] = metadata
    return payload


def _run_draft_planner(settings: dict, body: DraftRequest, *, tone: str, source_context: str, provider: str | None, model: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fallback = {
        "strategy": "Run the standard legal drafting agent sequence.",
        "required_agents": DRAFT_AGENT_SEQUENCE,
        "quality_gates": ["missing_fact_placeholders", "source_discipline", "human_review_warning", "printable_html"],
        "stop_conditions": ["complete_revised_draft_rendered"],
    }
    if not provider:
        return fallback, [_trace("draft_planner_agent", "skipped", provider, model, "No configured LLM provider.")]
    started = time.perf_counter()
    system = (
        _system_prompt()
        + " You are a legal drafting planner. Select the bounded drafting agents needed for this request. "
        "Return JSON keys: strategy, required_agents, quality_gates, source_plan, stop_conditions. "
        f"Allowed agents: {', '.join(DRAFT_AGENT_SEQUENCE)}."
    )
    try:
        data = _call_json(
            settings,
            system=system,
            user={"task": "draft_planning", "tone": tone, "details": body.details[:12000], "has_source_context": bool(source_context)},
            model=model,
            max_tokens=1200,
            temperature=0.05,
        )
        agents = data.get("required_agents")
        if not isinstance(agents, list) or not agents:
            data["required_agents"] = DRAFT_AGENT_SEQUENCE
        else:
            data["required_agents"] = [agent for agent in agents if agent in DRAFT_AGENT_SEQUENCE] or DRAFT_AGENT_SEQUENCE
        return data, [_trace("draft_planner_agent", "completed", provider, model, duration_ms=int((time.perf_counter() - started) * 1000), metadata={"agent_count": len(data["required_agents"])})]
    except Exception as exc:
        return fallback, [_trace("draft_planner_agent", "fallback", provider, model, str(exc), int((time.perf_counter() - started) * 1000))]


def _quality_gate_report(*, sections: list[dict[str, Any]], draft_html: str, missing: list[str], warnings: list[str], source_context: str, sources_used: list[Any]) -> dict[str, Any]:
    gates = []
    gates.append({"name": "sections_present", "status": "passed" if sections else "failed"})
    gates.append({"name": "printable_html", "status": "passed" if draft_html.startswith("<article") and "</article>" in draft_html else "needs_review"})
    gates.append({"name": "missing_facts_marked", "status": "passed" if missing or "[" in draft_html else "needs_review"})
    gates.append({"name": "source_discipline", "status": "passed" if not source_context or sources_used else "needs_review"})
    gates.append({"name": "human_review_warning", "status": "passed" if any("review" in str(item).lower() for item in warnings) else "needs_review"})
    return {
        "gates": gates,
        "passed": all(gate["status"] == "passed" for gate in gates),
    }


def _intake_step(settings: dict, details: str, *, model: str, tone: str) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Extract structured drafting parameters from the user's free-form request. "
        "Infer document_type (e.g. writ petition, legal notice, employment contract), jurisdiction, parties, and key facts from context. "
        "Return JSON with keys: document_type, title, jurisdiction, parties, facts, key_terms, instructions, audience."
    )
    try:
        data = _call_json(
            settings,
            system=system,
            user={"task": "intake", "tone": tone, "details": details},
            model=model,
            max_tokens=1200,
        )
        data.setdefault("document_type", "Legal document")
        data.setdefault("facts", details)
        return data
    except Exception:
        return {
            "document_type": "Legal document",
            "title": None,
            "jurisdiction": None,
            "parties": None,
            "facts": details,
            "key_terms": None,
            "instructions": None,
            "audience": None,
        }


def _plan_and_draft_step(settings: dict, intake: dict[str, Any], *, tone: str, source_context: str, model: str, token_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Run intake, outline, and first drafting in one pass. "
        "Return JSON keys: title, preamble, outline, sections, assumptions, missing_information, review_warnings, sources_used. "
        "preamble is an optional string for formal header blocks that appear before the main sections — use it for court headers, cause titles, address blocks, and sender/recipient blocks. "
        "sections must be an array of objects with heading and body, or heading and bullets. "
        "Use numbered paragraphs and jurisdiction-correct structure for the document type. "
        "Do not truncate — produce the complete document."
    )
    return _call_json(
        settings,
        system=system,
        user={
            "task": "plan_and_draft",
            "document_type": intake.get("document_type") or "",
            "tone": tone,
            "jurisdiction": intake.get("jurisdiction") or "",
            "audience": intake.get("audience") or "",
            "parties": intake.get("parties") or "",
            "facts": intake.get("facts") or "",
            "key_terms": intake.get("key_terms") or "",
            "instructions": intake.get("instructions") or "",
            "source_context": source_context[:6000],
        },
        model=model,
        max_tokens=6000,
        temperature=0.15,
        token_callback=token_callback,
    )


def _qa_and_revise_step(settings: dict, intake: dict[str, Any], *, tone: str, draft: dict[str, Any], model: str, token_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    system = (
        _system_prompt()
        + " Review the draft like a senior lawyer, then return the revised structured draft. "
        "Return JSON keys: title, preamble, sections, assumptions, missing_information, review_warnings, qa_issues, sources_used. "
        "preamble is optional — preserve it from the draft if correct, revise if needed. "
        "Do not invent missing facts; preserve placeholders. Do not truncate — produce the complete revised document."
    )
    return _call_json(
        settings,
        system=system,
        user={"task": "qa_and_revise", "document_type": intake.get("document_type") or "", "tone": tone, "jurisdiction": intake.get("jurisdiction") or "", "draft": draft},
        model=model,
        max_tokens=6000,
        temperature=0.1,
        token_callback=token_callback,
    )


def _default_section_draft(details: str) -> dict[str, Any]:
    return {
        "sections": [{"heading": "Details", "body": details}],
        "assumptions": [],
        "missing_information": ["Plan-and-draft step failed; only raw details are shown. Human legal review is required."],
        "review_warnings": ["Human legal review is required before use."],
        "sources_used": [],
    }


def _fallback_intake_from_details(details: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for line in details.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        fields[normalized] = value.strip()
    return {
        "document_type": fields.get("document_type") or "Legal document",
        "title": fields.get("document_type") or "Draft Legal Document",
        "jurisdiction": fields.get("jurisdiction"),
        "parties": fields.get("parties"),
        "facts": fields.get("facts") or details,
        "key_terms": fields.get("key_terms"),
        "instructions": fields.get("instructions"),
        "audience": None,
    }


def _fallback_draft(details: str, *, tone: str) -> dict:
    intake = _fallback_intake_from_details(details)
    document_type = str(intake.get("document_type") or "Legal document")
    title = str(intake.get("title") or "Draft Legal Document")
    details_escaped = html.escape(details).replace("\n", "<br>")
    html_output = (
        f'<article class="draft-document">'
        f"<header><h1>{html.escape(title)}</h1></header>"
        f"<section><h2>Details</h2><p>{details_escaped}</p></section>"
        '<section><h2>Review Note</h2><p>Configure an LLM provider in Settings to generate a full legal draft.</p></section>'
        "</article>"
    )
    agentic_review = {
        "enabled": False,
        "version": "agentic_drafting_v1",
        "agent_trace": [_trace("draft_planner_agent", "skipped", None, None, "No configured LLM provider.")],
        "quality_control": {"gates": [{"name": "configured_provider", "status": "failed"}], "passed": False},
    }
    return {
        "document_type": document_type,
        "jurisdiction": intake.get("jurisdiction"),
        "title": title,
        "draft_html": html_output,
        "draft_text": _strip_html(html_output),
        "assumptions": [],
        "missing_information": ["Configured LLM provider is required for full drafting."],
        "review_warnings": ["Human legal review is required before use."],
        "sources_used": [],
        "drafting_trace": {"pipeline": "agentic_drafting_v1", "agentic_review": agentic_review, "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "exact": False}},
        "agentic_review": agentic_review,
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "exact": False},
        "intake": intake,
        "provider": None,
        "model": None,
    }


def _draft(body: DraftRequest, *, tone: str, source_context: str, progress_callback: Callable[[str, int, dict[str, Any] | None], None] | None = None) -> dict:
    settings = get_runtime_settings_with_secrets()
    provider = configured_llm_provider(settings)
    model = settings.get("chat_model", "gpt-4o")
    estimated_tokens: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "exact": False}
    agent_trace: list[dict[str, Any]] = []
    agent_outputs: dict[str, Any] = {}

    def add_tokens(usage: dict[str, Any]) -> None:
        estimated_tokens["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        estimated_tokens["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        estimated_tokens["total_tokens"] += int(usage.get("total_tokens") or 0)
        if progress_callback:
            progress_callback("Estimated token use updated", 0, {"stage": "tokens", "tokens": dict(estimated_tokens), "exact_tokens": False})

    if not provider:
        return _fallback_draft(body.details, tone=tone)

    pipeline_warnings = []

    if progress_callback:
        progress_callback("Planning drafting agents", 12, {"stage": "draft_planner_agent", "tokens": dict(estimated_tokens)})
    planner_output, planner_trace = _run_draft_planner(settings, body, tone=tone, source_context=source_context, provider=provider, model=model)
    agent_outputs["draft_planner_agent"] = planner_output
    agent_trace.extend(planner_trace)

    if progress_callback:
        progress_callback("Intake agent extracting document parameters", 20, {"stage": "draft_intake_agent", "tokens": dict(estimated_tokens)})
    started = time.perf_counter()
    try:
        intake = _intake_step(settings, body.details, model=model, tone=tone)
        agent_outputs["draft_intake_agent"] = intake
        agent_trace.append(_trace("draft_intake_agent", "completed", provider, model, duration_ms=int((time.perf_counter() - started) * 1000)))
    except Exception as exc:
        intake = {
            "document_type": "Legal document",
            "title": None,
            "jurisdiction": None,
            "parties": None,
            "facts": body.details,
            "key_terms": None,
            "instructions": None,
            "audience": None,
        }
        pipeline_warnings.append(f"Intake fallback used: {exc}")
        agent_outputs["draft_intake_agent"] = intake
        agent_trace.append(_trace("draft_intake_agent", "fallback", provider, model, str(exc), int((time.perf_counter() - started) * 1000)))

    try:
        if progress_callback:
            progress_callback("Architecture and writing agents drafting document", 45, {"stage": "draft_architect_writer_agent", "tokens": dict(estimated_tokens)})
        started = time.perf_counter()
        section_draft = _plan_and_draft_step(settings, intake, tone=tone, source_context=source_context, model=model, token_callback=add_tokens)
        agent_outputs["draft_architect_agent"] = section_draft.get("outline") if isinstance(section_draft.get("outline"), dict) else {"sections": [section.get("heading") for section in section_draft.get("sections", []) if isinstance(section, dict)]}
        agent_outputs["draft_writer_agent"] = section_draft
        agent_outputs["draft_architect_writer_agent"] = section_draft
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        agent_trace.append(_trace("draft_architect_writer_agent", "completed", provider, model, duration_ms=elapsed_ms, metadata={"logical_outputs": ["draft_architect_agent", "draft_writer_agent"]}))
    except Exception as exc:
        section_draft = _default_section_draft(body.details)
        pipeline_warnings.append(f"Plan-and-draft fallback used: {exc}")
        agent_outputs["draft_architect_agent"] = {"sections": ["Details"]}
        agent_outputs["draft_writer_agent"] = section_draft
        agent_outputs["draft_architect_writer_agent"] = section_draft
        agent_trace.append(_trace("draft_architect_writer_agent", "fallback", provider, model, str(exc), metadata={"logical_outputs": ["draft_architect_agent", "draft_writer_agent"]}))

    outline = section_draft.get("outline") if isinstance(section_draft.get("outline"), dict) else {"sections": []}
    analysis = {
        "title": section_draft.get("title") or intake.get("title") or f"Draft {intake.get('document_type', 'Legal Document').title()}",
        "missing_information": section_draft.get("missing_information") or [],
        "assumptions": section_draft.get("assumptions") or [],
        "drafting_risks": section_draft.get("review_warnings") or [],
    }

    try:
        if progress_callback:
            progress_callback("Review and revision agents checking draft", 72, {"stage": "draft_review_revision_agent", "tokens": dict(estimated_tokens)})
        started = time.perf_counter()
        data = _qa_and_revise_step(settings, intake, tone=tone, draft=section_draft, model=model, token_callback=add_tokens)
        qa = {"issues": data.get("qa_issues") if isinstance(data.get("qa_issues"), list) else [], "missing_information": data.get("missing_information") or [], "assumptions": data.get("assumptions") or [], "review_warnings": data.get("review_warnings") or []}
        agent_outputs["draft_review_agent"] = qa
        agent_outputs["draft_revision_agent"] = data
        agent_outputs["draft_review_revision_agent"] = data
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        agent_trace.append(_trace("draft_review_revision_agent", "completed", provider, model, duration_ms=elapsed_ms, metadata={"logical_outputs": ["draft_review_agent", "draft_revision_agent"]}))
    except Exception as exc:
        data = section_draft
        pipeline_warnings.append(f"QA-and-revision fallback used: {exc}")
        qa = {"issues": [str(exc)], "missing_information": data.get("missing_information") or [], "assumptions": data.get("assumptions") or [], "review_warnings": data.get("review_warnings") or []}
        agent_outputs["draft_review_agent"] = qa
        agent_outputs["draft_revision_agent"] = data
        agent_outputs["draft_review_revision_agent"] = data
        agent_trace.append(_trace("draft_review_revision_agent", "fallback", provider, model, str(exc), metadata={"logical_outputs": ["draft_review_agent", "draft_revision_agent"]}))

    sections = data.get("sections") if isinstance(data.get("sections"), list) else section_draft.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Drafting pipeline did not produce sections")

    title = str(data.get("title") or outline.get("title") or analysis.get("title") or f"Draft {intake.get('document_type', 'Legal Document').title()}")[:255]
    preamble = str(data.get("preamble") or section_draft.get("preamble") or "").strip()

    if progress_callback:
        progress_callback("Render agent producing printable HTML", 88, {"stage": "draft_render_agent", "tokens": dict(estimated_tokens)})

    document_type = str(intake.get("document_type") or "Legal document")
    started = time.perf_counter()
    draft_html = _sanitize_html(_render_printable_html(title, sections, document_type=document_type, preamble=preamble))

    missing: list[str] = []
    assumptions: list[str] = []
    warnings: list[str] = []
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
    sources_used = data.get("sources_used") if isinstance(data.get("sources_used"), list) else []
    quality_control = _quality_gate_report(sections=sections, draft_html=draft_html, missing=missing, warnings=warnings, source_context=source_context, sources_used=sources_used)
    agent_outputs["draft_render_agent"] = {"title": title, "document_type": document_type, "quality_control": quality_control}
    agent_trace.append(_trace("draft_render_agent", "completed", "internal", "draft_html_renderer_v1", duration_ms=int((time.perf_counter() - started) * 1000), metadata={"quality_passed": quality_control["passed"]}))
    agentic_review = {
        "enabled": True,
        "version": "agentic_drafting_v1",
        "planner": planner_output,
        "agent_trace": agent_trace,
        "agent_outputs": agent_outputs,
        "quality_control": quality_control,
    }

    return {
        "document_type": document_type,
        "jurisdiction": intake.get("jurisdiction"),
        "title": title,
        "draft_html": draft_html,
        "draft_text": _strip_html(draft_html),
        "assumptions": list(dict.fromkeys(str(item) for item in assumptions if str(item).strip()))[:24],
        "missing_information": list(dict.fromkeys(str(item) for item in missing if str(item).strip()))[:24],
        "review_warnings": list(dict.fromkeys(str(item) for item in warnings if str(item).strip()))[:24],
        "sources_used": sources_used,
        "drafting_trace": {"analysis": analysis, "outline": outline, "qa": qa, "pipeline": "agentic_drafting_v1", "tokens": dict(estimated_tokens), "agentic_review": agentic_review},
        "agentic_review": agentic_review,
        "token_usage": dict(estimated_tokens),
        "intake": intake,
        "provider": provider,
        "model": model,
    }


def _result_payload(body: DraftRequest, *, tone: str, source_context: str, sources: list[dict], progress_callback: Callable[[str, int, dict[str, Any] | None], None] | None = None) -> dict:
    try:
        result = _draft(body, tone=tone, source_context=source_context, progress_callback=progress_callback)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Drafting model returned an invalid response: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Drafting provider failed: {exc}")
    warnings = list(result.get("review_warnings") or [])
    if not any("review" in str(item).lower() for item in warnings):
        warnings.append("Human legal review is required before use or circulation.")
    return {
        "title": result.get("title") or f"Draft",
        "document_type": result.get("document_type") or "Legal document",
        "jurisdiction": result.get("jurisdiction"),
        "tone": tone,
        "audience": result.get("intake", {}).get("audience"),
        "draft_html": result.get("draft_html") or "",
        "draft_text": result.get("draft_text") or "",
        "assumptions": result.get("assumptions") or [],
        "missing_information": result.get("missing_information") or [],
        "review_warnings": warnings,
        "sources": sources or result.get("sources_used") or [],
        "drafting_trace": result.get("drafting_trace") or {},
        "agentic_review": result.get("agentic_review") or result.get("drafting_trace", {}).get("agentic_review") or {},
        "token_usage": result.get("token_usage") or {},
        "provider": result.get("provider"),
        "model": result.get("model"),
        "_intake": result.get("intake") or {},
    }


def _save_draft_run(db: Session, *, workspace_id: str, user: User, body: DraftRequest, payload: dict, intake: dict[str, Any]) -> DraftRun:
    run = DraftRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=body.matter_id,
        title=str(payload["title"])[:255],
        document_type=payload.get("document_type") or "Legal document",
        jurisdiction=payload.get("jurisdiction"),
        tone=payload["tone"],
        audience=payload.get("audience"),
        facts_hash=hashlib.sha256(body.details.encode("utf-8")).hexdigest(),
        config_json=json.dumps(
            {
                "details_preview": body.details[:500],
                "intake": intake,
                "source_document_ids": body.source_document_ids,
                "drafting_trace": payload.get("drafting_trace") or {},
                "agentic_review": payload.get("agentic_review") or {},
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


def _run_workspace_draft_job(job_id: str, workspace_id: str, user_id: str, body_data: dict[str, Any], tone: str, source_context: str, sources: list[dict]) -> None:
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
            add_job_event(db, job=job, event_type="progress", message="Reading draft inputs", metadata={"progress": 15, "stage": "input"})
            db.commit()
            payload = _result_payload(body, tone=tone, source_context=source_context, sources=sources, progress_callback=progress)
            intake = payload.pop("_intake", {})
            progress("Saving draft", 94, {"stage": "save", "tokens": payload.get("token_usage") or {}})
            run = _save_draft_run(db, workspace_id=workspace_id, user=user, body=body, payload=payload, intake=intake)
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
    tone = _validate_tone(body.tone)
    payload = _result_payload(body, tone=tone, source_context="", sources=[])
    payload.pop("_intake", None)
    return payload


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
    tone = _validate_tone(body.tone)
    source_context, sources = _source_context(db, workspace_id, body.matter_id, body.source_document_ids)
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="draft.run",
        metadata={"matter_id": body.matter_id},
        message="Draft generation queued",
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, _run_workspace_draft_job, job.id, workspace_id, user.id, body.model_dump(), tone, source_context, sources)
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
