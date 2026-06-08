import json
import re
import time
from typing import Any, Callable

from app.core.contract_agents.tools import run_contract_agent_tools
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider


class ContractReviewAgentError(RuntimeError):
    pass


def run_agentic_contract_review(
    *,
    text: str,
    sources: list[dict[str, Any]],
    config: dict[str, Any],
    workflow: dict[str, Any],
    deterministic_extraction: dict[str, Any],
    deterministic_risks: list[dict[str, Any]],
    deterministic_negotiation_memo: str,
    deterministic_client_summary: str,
    settings: dict[str, Any],
    tool_context: dict[str, Any] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    provider = configured_llm_provider(settings)
    model = config.get("model") or settings.get("chat_model")
    if not provider:
        raise ContractReviewAgentError("Contract review could not run because no LLM provider is configured.")

    base_payload: dict[str, Any] = {
        "config": config,
        "workflow": _workflow_digest(workflow),
        "source_excerpts": _source_excerpts(sources),
        "available_tools": (tool_context or {}).get("supported_tools", []),
    }
    trace: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}

    planner_data, planner_error = _run_agent(
        "review_planner_agent",
        "Plan the contract review based on document type, workflow stats, user instructions, and available evidence.",
        "Return JSON with keys strategy, required_agents, tool_requests, evidence_gaps, and stop_conditions. tool_requests must be an array of objects with a tool key.",
        {
            **base_payload,
            "priority_clause_types": _priority_clause_types(workflow),
            "instructions": config.get("instructions") or "",
        },
        settings,
        model=model,
        max_tokens=1200,
    )
    planner_data = _normalize_agent_output("review_planner_agent", planner_data)
    planner_shape_error = None if planner_error else _agent_output_validation_error("review_planner_agent", planner_data)
    if planner_error:
        if _is_invalid_json_error(planner_error):
            planner_data = _fallback_agent_output(
                "review_planner_agent",
                deterministic_extraction=deterministic_extraction,
                deterministic_risks=deterministic_risks,
                deterministic_negotiation_memo=deterministic_negotiation_memo,
                deterministic_client_summary=deterministic_client_summary,
            )
            outputs["review_planner_agent"] = planner_data
            trace.append(_trace("review_planner_agent", "fallback", planner_error, provider, model, None))
            _emit_progress(progress_callback, "Planner returned malformed JSON; using deterministic review plan", 48)
        else:
            trace.append(_trace("review_planner_agent", "failed", planner_error, provider, model, None))
            _raise_agent_error(provider, planner_error)
    elif planner_shape_error:
        planner_data = _fallback_agent_output(
            "review_planner_agent",
            deterministic_extraction=deterministic_extraction,
            deterministic_risks=deterministic_risks,
            deterministic_negotiation_memo=deterministic_negotiation_memo,
            deterministic_client_summary=deterministic_client_summary,
        )
        outputs["review_planner_agent"] = planner_data
        trace.append(_trace("review_planner_agent", "fallback", planner_shape_error, provider, model, None))
        _emit_progress(progress_callback, "Planner returned incomplete JSON; using deterministic review plan", 48)
    else:
        outputs["review_planner_agent"] = planner_data
        trace.append(_trace("review_planner_agent", "completed", None, provider, model, None))
        _emit_progress(progress_callback, "Review planner completed", 48)

    if tool_context:
        _emit_progress(progress_callback, "Running contract review tools", 50)
        started = time.perf_counter()
        tool_results = run_contract_agent_tools(
            requests=outputs.get("review_planner_agent", {}).get("tool_requests"),
            source_bundle=tool_context.get("source_bundle", []),
            workflow=workflow,
            playbook=tool_context.get("playbook"),
            playbook_clauses=tool_context.get("playbook_clauses", []),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        outputs["agent_tool_controller"] = tool_results
        trace.append(_trace("agent_tool_controller", "completed", None, "internal", "contract_agent_tools_v1", elapsed_ms))
        _emit_progress(progress_callback, "Contract review tools completed", 52)

    agent_specs = [
        (
            "intake_and_extraction_agent",
            "Extract commercially relevant contract facts and correct unsupported deterministic extraction fields.",
            "Return JSON with key extraction only. extraction must be an object keyed by field name. Each value should include value, supported, evidence, and confidence_score.",
            3000,
        ),
        (
            "risk_analysis_agent",
            "Assess clause, playbook, business, and legal risk from the workflow outputs and source evidence.",
            "Return JSON with key risk_matrix only. risk_matrix must be an array. Each item must include issue, severity, clause_id, clause_type, finding, evidence, requires_review, confidence_score, and recommended_action.",
            3200,
        ),
        (
            "negotiation_agent",
            "Turn the extraction and risk analysis into practical negotiation priorities and fallback positions.",
            "Return JSON with key negotiation_memo only. The value must be a markdown string with sections ## Priority Issues, ## Fallback Positions, ## Walk-Away Conditions, and ## Open Questions.",
            1800,
        ),
        (
            "client_summary_agent",
            "Convert the lawyer-facing findings into a cautious plain-English client summary without legal advice.",
            "Return JSON with key client_summary only. The value must be a concise plain-English string.",
            1400,
        ),
        (
            "quality_control_agent",
            "Review the draft outputs for unsupported claims, legal-advice overreach, missing evidence, and internal contradictions.",
            "Return JSON with keys approved, issues, corrections. approved is boolean; issues is an array; corrections is an object that may contain extraction, risk_matrix, negotiation_memo, or client_summary.",
            2400,
        ),
    ]
    agent_progress = {
        "intake_and_extraction_agent": (54, 60, "Extracting contract facts"),
        "risk_analysis_agent": (62, 68, "Analyzing contract risks"),
        "negotiation_agent": (70, 74, "Drafting negotiation positions"),
        "client_summary_agent": (76, 78, "Drafting client summary"),
        "quality_control_agent": (80, 84, "Running quality control"),
    }

    for agent_id, role, contract, max_tokens in agent_specs:
        start_progress, done_progress, message = agent_progress.get(agent_id, (54, 60, f"Running {agent_id}"))
        _emit_progress(progress_callback, message, start_progress)
        extra = _task_payload(agent_id, workflow, sources, text, deterministic_extraction, outputs)
        agent_input = _agent_payload(base_payload, agent_id, extra)
        started = time.perf_counter()
        data, error = _run_agent(agent_id, role, contract, agent_input, settings, model=model, max_tokens=max_tokens)
        data = _normalize_agent_output(agent_id, data)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        shape_error = None if error else _agent_output_validation_error(agent_id, data)
        if error:
            if _is_invalid_json_error(error):
                data = _fallback_agent_output(
                    agent_id,
                    deterministic_extraction=deterministic_extraction,
                    deterministic_risks=deterministic_risks,
                    deterministic_negotiation_memo=deterministic_negotiation_memo,
                    deterministic_client_summary=deterministic_client_summary,
                )
                trace.append(_trace(agent_id, "fallback", error, provider, model, elapsed_ms))
                _emit_progress(progress_callback, f"{_agent_label(agent_id)} returned malformed JSON; using deterministic fallback", done_progress)
            else:
                trace.append(_trace(agent_id, "failed", error, provider, model, elapsed_ms))
                _raise_agent_error(provider, error)
        elif shape_error:
            data = _fallback_agent_output(
                agent_id,
                deterministic_extraction=deterministic_extraction,
                deterministic_risks=deterministic_risks,
                deterministic_negotiation_memo=deterministic_negotiation_memo,
                deterministic_client_summary=deterministic_client_summary,
            )
            trace.append(_trace(agent_id, "fallback", shape_error, provider, model, elapsed_ms))
            _emit_progress(progress_callback, f"{_agent_label(agent_id)} returned incomplete JSON; using deterministic fallback", done_progress)
        outputs[agent_id] = data
        if not error and not shape_error:
            trace.append(_trace(agent_id, "completed", None, provider, model, elapsed_ms))
            _emit_progress(progress_callback, f"{_agent_label(agent_id)} completed", done_progress)

    extraction = _dict_output(outputs, "intake_and_extraction_agent", "extraction")
    risk_output = _list_output(outputs, "risk_analysis_agent", "risk_matrix")
    negotiation_output = _str_output(outputs, "negotiation_agent", "negotiation_memo")
    summary_output = _str_output(outputs, "client_summary_agent", "client_summary")

    qc = outputs.get("quality_control_agent", {})
    corrections = qc.get("corrections") if isinstance(qc.get("corrections"), dict) else {}
    if qc and qc.get("approved") is False:
        _emit_progress(progress_callback, "Applying quality control revisions", 86)
        revision_input = {
            **base_payload,
            "quality_control": qc,
            "draft": {
                "extraction": extraction,
                "risk_matrix": risk_output,
                "negotiation_memo": negotiation_output,
                "client_summary": summary_output,
            },
        }
        started = time.perf_counter()
        revision_data, revision_error = _run_agent(
            "revision_controller_agent",
            "Revise only the outputs called out by quality control, using evidence and prior agent outputs.",
            "Return JSON with optional keys extraction, risk_matrix, negotiation_memo, client_summary, and revision_notes.",
            revision_input,
            settings,
            model=model,
            max_tokens=2600,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if revision_error:
            if _is_invalid_json_error(revision_error):
                trace.append(_trace("revision_controller_agent", "fallback", revision_error, provider, model, elapsed_ms))
                _emit_progress(progress_callback, "Revision agent returned malformed JSON; keeping reviewed draft", 88)
            else:
                trace.append(_trace("revision_controller_agent", "failed", revision_error, provider, model, elapsed_ms))
                _raise_agent_error(provider, revision_error)
        else:
            outputs["revision_controller_agent"] = revision_data
            trace.append(_trace("revision_controller_agent", "completed", None, provider, model, elapsed_ms))
            corrections = {**corrections, **revision_data}
            _emit_progress(progress_callback, "Quality control revisions completed", 88)
    if isinstance(corrections.get("extraction"), dict):
        extraction = corrections["extraction"]
    if isinstance(corrections.get("risk_matrix"), list):
        risk_output = corrections["risk_matrix"]
    if isinstance(corrections.get("negotiation_memo"), str):
        negotiation_output = corrections["negotiation_memo"]
    if isinstance(corrections.get("client_summary"), str):
        summary_output = corrections["client_summary"]

    return {
        "extraction": extraction,
        "risk_matrix": risk_output,
        "negotiation_memo": negotiation_output,
        "client_summary": summary_output,
        "agentic_enabled": True,
        "agent_trace": trace,
        "agent_outputs": outputs,
        "quality_control": qc,
    }


def _emit_progress(progress_callback: Callable[[str, int], None] | None, message: str, progress: int) -> None:
    if progress_callback:
        progress_callback(message, progress)


def _agent_label(agent_id: str) -> str:
    return agent_id.replace("_", " ").replace(" agent", "").title()


def _agent_payload(base: dict[str, Any], agent_id: str, task_payload: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "config": base.get("config", {}),
        "workflow": base.get("workflow", {}),
        "task": task_payload,
    }
    if agent_id in {"intake_and_extraction_agent", "negotiation_agent", "quality_control_agent"}:
        excerpt_limit = 3 if agent_id == "negotiation_agent" else 6
        excerpt_chars = 400 if agent_id == "negotiation_agent" else 700
        payload["source_excerpts"] = _source_excerpts(base.get("source_excerpts", []), limit=excerpt_limit, excerpt_chars=excerpt_chars)
    return payload


def _task_payload(
    agent_id: str,
    workflow: dict[str, Any],
    sources: list[dict[str, Any]],
    text: str,
    deterministic_extraction: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    if agent_id == "intake_and_extraction_agent":
        return {
            "deterministic_extraction": deterministic_extraction,
            "intake": workflow.get("intake", {}),
            "evidence": _intake_evidence(text, sources),
        }
    if agent_id == "risk_analysis_agent":
        extraction = _optional_dict_output(outputs, "intake_and_extraction_agent", "extraction", deterministic_extraction)
        extraction_view, uncertain_extraction_fields = _risk_extraction_view(extraction)
        return {
            "extraction": extraction_view,
            "uncertain_extraction_fields": uncertain_extraction_fields,
            "clauses": _selected_workflow_clauses(workflow),
            "unattached_risks": _compact_risks(workflow.get("unattached_risk_findings", []), limit=12),
            "escalations": _compact_escalations(workflow.get("escalations", []), limit=12),
            "tool_results": _tool_digest(
                outputs.get("agent_tool_controller", {}),
                include=("risk_scoring", "missing_clause_detector", "conflict_scan", "escalation_candidates", "playbook_lookup"),
            ),
        }
    if agent_id == "negotiation_agent":
        return {
            "extraction": _dict_output(outputs, "intake_and_extraction_agent", "extraction"),
            "risk_matrix": _list_output(outputs, "risk_analysis_agent", "risk_matrix"),
            "escalations": _compact_escalations(workflow.get("escalations", []), limit=8),
            "fallback_language": _tool_digest(outputs.get("agent_tool_controller", {}), include=("redline_fallback_lookup", "missing_clause_detector")),
            "grounding_clause_excerpts": _selected_workflow_clauses(workflow, limit=5),
        }
    if agent_id == "client_summary_agent":
        return {
            "extraction": _dict_output(outputs, "intake_and_extraction_agent", "extraction"),
            "risk_matrix": _list_output(outputs, "risk_analysis_agent", "risk_matrix"),
            "negotiation_memo": _str_output(outputs, "negotiation_agent", "negotiation_memo"),
        }
    if agent_id == "quality_control_agent":
        return {
            "draft": {
                "extraction": _dict_output(outputs, "intake_and_extraction_agent", "extraction"),
                "risk_matrix": _list_output(outputs, "risk_analysis_agent", "risk_matrix"),
                "negotiation_memo": _str_output(outputs, "negotiation_agent", "negotiation_memo"),
                "client_summary": _str_output(outputs, "client_summary_agent", "client_summary"),
            },
            "source_excerpts": _source_excerpts(sources, limit=5, excerpt_chars=500),
            "escalations": _compact_escalations(workflow.get("escalations", []), limit=8),
        }
    return {}


def _workflow_digest(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": workflow.get("version"),
        "intake": workflow.get("intake", {}),
        "stats": workflow.get("stats", {}),
        "coverage_score": workflow.get("coverage_score"),
        "summaries": _compact_summaries(workflow.get("summaries", []), limit=3),
        "top_clause_types": _priority_clause_types(workflow),
        "escalation_count": len(workflow.get("escalations", []) or []),
    }


def _priority_clause_types(workflow: dict[str, Any], *, limit: int = 12) -> list[str]:
    scores: dict[str, int] = {}
    for item in workflow.get("clauses", []) or []:
        clause_type = str((item.get("clause") or {}).get("clause_type") or "")
        if not clause_type:
            continue
        score = 1
        for risk in item.get("risks", []) or []:
            score = max(score, {"critical": 5, "high": 4, "medium": 3, "low": 1}.get(risk.get("risk_level"), 1))
        scores[clause_type] = max(scores.get(clause_type, 0), score)
    for risk in workflow.get("unattached_risk_findings", []) or []:
        clause_type = str(risk.get("clause_type") or "")
        if clause_type:
            scores[clause_type] = max(scores.get(clause_type, 0), {"critical": 5, "high": 4, "medium": 3, "low": 1}.get(risk.get("risk_level"), 1))
    return [item[0] for item in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _selected_workflow_clauses(workflow: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    items = list(workflow.get("clauses", []) or [])

    def rank(item: dict[str, Any]) -> tuple[int, float, str]:
        risks = item.get("risks", []) or []
        risk_rank = max([{"critical": 5, "high": 4, "medium": 3, "low": 1}.get(risk.get("risk_level"), 0) for risk in risks] or [0])
        clause = item.get("clause") or {}
        confidence = float(clause.get("confidence_score") or 0)
        return (-risk_rank, -confidence, str(clause.get("clause_type") or ""))

    return [_compact_clause_item(item) for item in sorted(items, key=rank)[:limit]]


def _compact_clause_item(item: dict[str, Any]) -> dict[str, Any]:
    clause = item.get("clause") or {}
    return {
        "id": clause.get("id"),
        "clause_type": clause.get("clause_type"),
        "title": clause.get("title"),
        "text": _truncate(clause.get("text"), 500),
        "source": _compact_source(clause.get("source") or {}, excerpt_chars=250),
        "risks": _compact_risks(item.get("risks", []), limit=4),
        "playbook_findings": _compact_findings(item.get("playbook_findings", []), limit=4),
        "redline_suggestions": _compact_redlines(item.get("redline_suggestions", []), limit=2),
    }


def _source_excerpts(sources: list[dict[str, Any]], *, limit: int = 6, excerpt_chars: int = 700) -> list[dict[str, Any]]:
    return [
        {
            "filename": source.get("filename"),
            "chunk": source.get("chunk"),
            "excerpt": _truncate(source.get("excerpt"), excerpt_chars),
        }
        for source in (sources or [])[:limit]
    ]


def _risk_extraction_view(extraction: dict[str, Any], *, confidence_floor: float = 0.4) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reliable: dict[str, Any] = {}
    uncertain: list[dict[str, Any]] = []
    for key, value in (extraction or {}).items():
        if not isinstance(value, dict):
            reliable[key] = value
            continue
        confidence = _confidence_score(value)
        supported = value.get("supported")
        if confidence is not None and confidence < confidence_floor:
            uncertain.append({"field": key, "reason": "low_confidence", "confidence_score": confidence, "value": _truncate(value.get("value"), 300)})
            continue
        if supported is False:
            uncertain.append({"field": key, "reason": "unsupported", "confidence_score": confidence, "value": _truncate(value.get("value"), 300)})
            continue
        reliable[key] = value
    return reliable, uncertain


def _confidence_score(value: dict[str, Any]) -> float | None:
    raw = value.get("confidence_score")
    if raw is None:
        raw = value.get("confidence")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _intake_evidence(text: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "opening_excerpt": _truncate(text, 1800),
        "source_excerpts": _source_excerpts(sources, limit=4, excerpt_chars=600),
    }


def _tool_digest(tool_results: dict[str, Any], *, include: tuple[str, ...], limit: int = 8) -> list[dict[str, Any]]:
    allowed = set(include)
    results = []
    for result in (tool_results or {}).get("tool_results", []) or []:
        tool = result.get("tool")
        if tool not in allowed:
            continue
        results.append({"tool": tool, "status": result.get("status"), "output": _compact_tool_output(result.get("output"))})
        if len(results) >= limit:
            break
    return results


def _compact_tool_output(output: Any) -> Any:
    if isinstance(output, list):
        return [_compact_tool_output(item) for item in output[:8]]
    if isinstance(output, dict):
        keep = {}
        for key, value in output.items():
            if key in {"metadata", "source_json"}:
                continue
            keep[key] = _compact_tool_output(value)
        return keep
    if isinstance(output, str):
        return _truncate(output, 500)
    return output


def _compact_summaries(summaries: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "audience": item.get("audience"),
            "summary_text": _truncate(item.get("summary_text"), 500),
            "negotiation_points": [_truncate(point, 250) for point in (item.get("negotiation_points") or [])[:5]],
        }
        for item in (summaries or [])[:limit]
    ]


def _compact_escalations(escalations: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "clause_id": item.get("clause_id"),
            "severity": item.get("severity"),
            "reason": _truncate(item.get("reason"), 350),
            "required_action": _truncate(item.get("required_action"), 250),
            "metadata": item.get("metadata"),
        }
        for item in (escalations or [])[:limit]
    ]


def _compact_risks(risks: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "clause_id": item.get("clause_id"),
            "clause_type": item.get("clause_type"),
            "risk_level": item.get("risk_level") or item.get("severity"),
            "reasoning": _truncate(item.get("reasoning") or item.get("finding"), 350),
            "requires_review": item.get("requires_review"),
            "evidence": _truncate(item.get("evidence"), 350),
        }
        for item in (risks or [])[:limit]
    ]


def _compact_findings(findings: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "status": item.get("status"),
            "deviation_summary": _truncate(item.get("deviation_summary"), 300),
            "prohibited_match": _truncate(item.get("prohibited_match"), 160),
        }
        for item in (findings or [])[:limit]
    ]


def _compact_redlines(redlines: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "suggestion_text": _truncate(item.get("suggestion_text"), 350),
            "fallback_language": _truncate(item.get("fallback_language"), 350),
            "rationale": _truncate(item.get("rationale"), 250),
        }
        for item in (redlines or [])[:limit]
    ]


def _compact_source(source: dict[str, Any], *, excerpt_chars: int) -> dict[str, Any]:
    return {
        "filename": source.get("filename"),
        "chunk_index": source.get("chunk_index"),
        "page": source.get("page"),
        "excerpt": _truncate(source.get("excerpt"), excerpt_chars),
    }


def _truncate(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _specialist_instructions(agent_id: str) -> str:
    instructions = {
        "review_planner_agent": (
            "Choose a focused review strategy based on document type, user instructions, coverage gaps, and available tools. "
            "Tool requests should be specific and justified by the supplied workflow facts."
        ),
        "intake_and_extraction_agent": (
            "Extract only facts supported by the supplied contract evidence. Keep unsupported or ambiguous fields but mark supported false and set a low confidence_score. "
            "Use field names that are stable across commercial contracts, such as parties, effective_date, term, payment_terms, termination_rights, liability_cap, indemnity, confidentiality, ip_ownership, governing_law, and dispute_resolution."
        ),
        "risk_analysis_agent": (
            "Severity definitions: critical means an issue may defeat the commercial purpose, create uncapped or existential exposure, block enforceability, or require immediate lawyer escalation; "
            "high means material financial, operational, IP, confidentiality, termination, compliance, or dispute risk; "
            "medium means negotiable ambiguity, imbalance, missing detail, or process risk that should be corrected before signing; "
            "low means drafting cleanup, minor inconsistency, or monitoring point. "
            "Every finding must cite clause_id when available, identify clause_type, quote or paraphrase evidence, avoid severity inflation, and explain why human review is or is not required. "
            "Do not rely on uncertain_extraction_fields as true facts; use them only to flag open questions."
        ),
        "negotiation_agent": (
            "Write for a lawyer preparing negotiation positions. Use the required markdown section headings exactly. "
            "Tie each priority issue and fallback position to a cited risk, clause_id, or provided source excerpt. "
            "Fallback positions should be practical contract language or negotiating asks, not generic advice. "
            "Walk-away conditions should be reserved for critical or unresolved high risks."
        ),
        "client_summary_agent": (
            "Write in plain English for a client or internal business stakeholder. Be cautious, avoid legal advice, avoid predicting outcomes, and separate business risk from legal risk. "
            "Mention that lawyer review is required for material points."
        ),
        "quality_control_agent": (
            "Check whether each risk has a clause_id or evidence citation, whether severities match the definitions, whether any output treats uncertain extraction fields as proven, "
            "whether the negotiation memo contradicts the risk matrix, whether the client summary overstates advice or omits material high risks, and whether any finding lacks support. "
            "If corrections are needed, return corrected objects or strings only for the affected output keys."
        ),
        "revision_controller_agent": (
            "Apply only the requested quality-control corrections. Preserve supported findings, keep citations, and do not introduce new uncited issues."
        ),
    }
    return instructions.get(agent_id, "")


def _normalize_agent_output(agent_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    normalized = dict(data)
    if agent_id == "review_planner_agent":
        normalized.setdefault("strategy", data.get("plan") or data.get("review_strategy") or "targeted")
        normalized["tool_requests"] = _first_list(data, "tool_requests", "tools", "requests", "recommended_tools") or []
        normalized["required_agents"] = _first_list(data, "required_agents", "agents") or []
        normalized["evidence_gaps"] = _first_list(data, "evidence_gaps", "gaps", "open_questions") or []
        normalized["stop_conditions"] = _first_list(data, "stop_conditions", "stopping_conditions") or []
        return normalized
    if agent_id == "intake_and_extraction_agent":
        extraction = _first_dict(data, "extraction", "extracted_fields", "fields", "contract_facts", "facts")
        if extraction is not None:
            normalized["extraction"] = extraction
        return normalized
    if agent_id == "risk_analysis_agent":
        risk_matrix = _first_list(data, "risk_matrix", "risks", "risk_findings", "findings", "issues")
        if risk_matrix is None:
            nested = _first_dict(data, "risk_analysis", "analysis")
            if nested is not None:
                risk_matrix = _first_list(nested, "risk_matrix", "risks", "risk_findings", "findings", "issues")
        if risk_matrix is not None:
            normalized["risk_matrix"] = risk_matrix
        return normalized
    if agent_id == "negotiation_agent":
        memo = _first_str(data, "negotiation_memo", "memo", "markdown", "negotiation_strategy", "summary")
        if memo is not None:
            normalized["negotiation_memo"] = memo
        return normalized
    if agent_id == "client_summary_agent":
        summary = _first_str(data, "client_summary", "summary", "plain_english_summary", "client_memo")
        if summary is not None:
            normalized["client_summary"] = summary
        return normalized
    if agent_id == "quality_control_agent":
        normalized["approved"] = data.get("approved") if isinstance(data.get("approved"), bool) else not bool(data.get("issues"))
        normalized["issues"] = _first_list(data, "issues", "qc_issues", "findings", "flags") or []
        corrections = _first_dict(data, "corrections", "recommended_corrections", "revisions") or {}
        normalized["corrections"] = corrections
        return normalized
    return normalized


def _agent_output_validation_error(agent_id: str, data: dict[str, Any]) -> str | None:
    if agent_id == "review_planner_agent":
        if not isinstance(data.get("strategy"), str) or not isinstance(data.get("tool_requests"), list):
            return "Agent returned incomplete JSON: review planner output must include strategy and tool_requests."
    if agent_id == "intake_and_extraction_agent" and not isinstance(data.get("extraction"), dict):
        return "Agent returned incomplete JSON: intake output must include object extraction."
    if agent_id == "risk_analysis_agent" and not isinstance(data.get("risk_matrix"), list):
        return "Agent returned incomplete JSON: risk analysis output must include list risk_matrix."
    if agent_id == "negotiation_agent" and not _nonempty_str(data.get("negotiation_memo")):
        return "Agent returned incomplete JSON: negotiation output must include text negotiation_memo."
    if agent_id == "client_summary_agent" and not _nonempty_str(data.get("client_summary")):
        return "Agent returned incomplete JSON: client summary output must include text client_summary."
    if agent_id == "quality_control_agent":
        if not isinstance(data.get("approved"), bool) or not isinstance(data.get("issues"), list) or not isinstance(data.get("corrections"), dict):
            return "Agent returned incomplete JSON: quality control output must include approved, issues, and corrections."
    return None


def _first_list(data: dict[str, Any], *keys: str) -> list[Any] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value["items"]
    return None


def _first_dict(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return None


def _first_str(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if _nonempty_str(value):
            return value.strip()
    return None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _run_agent(
    agent_id: str,
    role: str,
    contract: str,
    payload: dict[str, Any],
    settings: dict[str, Any],
    *,
    model: str | None,
    max_tokens: int,
) -> tuple[dict[str, Any], str | None]:
    system = (
        f"You are {agent_id}, one specialist in a multi-agent contract review system. "
        f"{role} Ground every conclusion in supplied evidence. Do not recommend signing. "
        f"{_specialist_instructions(agent_id)} {contract} Return only valid JSON."
    )
    user = json.dumps(_compact(payload), sort_keys=True)
    try:
        content = complete_with_configured_llm(
            settings,
            system,
            user,
            model=model,
            temperature=0.15,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        return {}, str(exc)
    data = _parse_agent_json(content)
    if not isinstance(data, dict) or not data:
        repair_system = (
            "You convert model output into valid JSON. Return only one JSON object. "
            "Do not include markdown fences, commentary, citations, or trailing commas."
        )
        repair_user = json.dumps(
            {
                "agent_id": agent_id,
                "required_contract": contract,
                "invalid_output": _truncate(content, 12000),
            },
            sort_keys=True,
        )
        try:
            repaired_content = complete_with_configured_llm(
                settings,
                repair_system,
                repair_user,
                model=model,
                temperature=0,
                max_tokens=max(800, min(max_tokens, 1800)),
            )
        except Exception as exc:
            return {}, str(exc)
        data = _parse_agent_json(repaired_content)
    if not isinstance(data, dict) or not data:
        return {}, "Agent returned invalid JSON."
    return data, None


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value[:40]]
    if isinstance(value, str):
        return value[:6000]
    return value


def _parse_agent_json(value: str | None) -> dict[str, Any]:
    parsed = json_loads(_extract_json_object(value), {})
    if isinstance(parsed, dict) and parsed:
        return parsed
    repaired = _repair_json_text(_extract_json_object(value))
    return json_loads(repaired, {})


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return text[index:index + end]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return text
    return text[start:end + 1]


def _repair_json_text(value: str | None) -> str | None:
    if not value:
        return value
    text = value.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def _raise_agent_error(provider: str | None, error: str | None) -> None:
    if not error:
        return
    provider_name = _provider_label(provider)
    if _is_payload_size_error(error):
        raise ContractReviewAgentError(
            f"{provider_name} rejected the request as too large for the configured model/token limit. "
            "Reduce the selected document scope, use a model with a larger context/token allowance, or split the review into smaller runs."
        )
    raise ContractReviewAgentError(f"Contract review could not run because {provider_name} returned an agent error: {error}")


def _provider_label(provider: str | None) -> str:
    labels = {"openai": "OpenAI", "xai": "xAI"}
    if not provider:
        return "The configured provider"
    return labels.get(provider.lower(), provider.title())


def _is_invalid_json_error(error: str | None) -> bool:
    return bool(error and "invalid json" in error.lower())


def _fallback_agent_output(
    agent_id: str,
    *,
    deterministic_extraction: dict[str, Any],
    deterministic_risks: list[dict[str, Any]],
    deterministic_negotiation_memo: str,
    deterministic_client_summary: str,
) -> dict[str, Any]:
    if agent_id == "review_planner_agent":
        return {
            "strategy": "deterministic_fallback",
            "required_agents": [],
            "tool_requests": [],
            "evidence_gaps": ["One or more specialist agents returned malformed JSON; deterministic review outputs were used."],
            "stop_conditions": [],
        }
    if agent_id == "intake_and_extraction_agent":
        return {"extraction": deterministic_extraction}
    if agent_id == "risk_analysis_agent":
        return {"risk_matrix": deterministic_risks}
    if agent_id == "negotiation_agent":
        return {"negotiation_memo": deterministic_negotiation_memo}
    if agent_id == "client_summary_agent":
        return {"client_summary": deterministic_client_summary}
    if agent_id == "quality_control_agent":
        return {
            "approved": True,
            "issues": [{"issue": "Quality control agent returned malformed JSON; deterministic outputs require human review."}],
            "corrections": {},
        }
    return {}


def _is_payload_size_error(error: str) -> bool:
    lower = error.lower()
    size_markers = ("request too large", "too many tokens", "maximum context", "context length", "token limit")
    quota_markers = ("tokens per minute", "tpm", "requested")
    return any(marker in lower for marker in size_markers) or ("rate_limit_exceeded" in lower and any(marker in lower for marker in quota_markers))


def _trace(
    step_name: str,
    status: str,
    error: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "step_name": step_name,
        "status": status,
        "provider": provider,
        "model": model,
        "duration_ms": duration_ms,
        "error": error,
    }


def _optional_dict_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, dict) else fallback


def _dict_output(outputs: dict[str, Any], agent_id: str, key: str) -> dict[str, Any]:
    value = outputs.get(agent_id, {}).get(key)
    if not isinstance(value, dict):
        raise ContractReviewAgentError(f"Contract review agent `{agent_id}` did not return required object `{key}`.")
    return value


def _list_output(outputs: dict[str, Any], agent_id: str, key: str) -> list[dict[str, Any]]:
    value = outputs.get(agent_id, {}).get(key)
    if not isinstance(value, list):
        raise ContractReviewAgentError(f"Contract review agent `{agent_id}` did not return required list `{key}`.")
    return value


def _str_output(outputs: dict[str, Any], agent_id: str, key: str) -> str:
    value = outputs.get(agent_id, {}).get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractReviewAgentError(f"Contract review agent `{agent_id}` did not return required text `{key}`.")
    return value
