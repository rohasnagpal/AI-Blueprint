import json
import time
from typing import Any

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
    if planner_error:
        trace.append(_trace("review_planner_agent", "failed", planner_error, provider, model, None))
        _raise_agent_error(provider, planner_error)
    else:
        outputs["review_planner_agent"] = planner_data
        trace.append(_trace("review_planner_agent", "completed", None, provider, model, None))

    if tool_context:
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

    agent_specs = [
        (
            "intake_and_extraction_agent",
            "Extract commercially relevant contract facts and correct unsupported deterministic extraction fields.",
            "Return JSON with key extraction only. extraction must be an object keyed by field name. Each value should include value, supported, evidence, and confidence_score.",
            2200,
        ),
        (
            "risk_analysis_agent",
            "Assess clause, playbook, business, and legal risk from the workflow outputs and source evidence.",
            "Return JSON with key risk_matrix only. risk_matrix must be an array. Each item should include issue, severity, finding, evidence, requires_review, and confidence_score.",
            2600,
        ),
        (
            "negotiation_agent",
            "Turn the extraction and risk analysis into practical negotiation priorities and fallback positions.",
            "Return JSON with key negotiation_memo only. The value must be a concise markdown string for a lawyer.",
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
            1800,
        ),
    ]

    for agent_id, role, contract, max_tokens in agent_specs:
        extra = _task_payload(agent_id, workflow, sources, text, deterministic_extraction, outputs)
        agent_input = _agent_payload(base_payload, agent_id, extra)
        started = time.perf_counter()
        data, error = _run_agent(agent_id, role, contract, agent_input, settings, model=model, max_tokens=max_tokens)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if error:
            trace.append(_trace(agent_id, "failed", error, provider, model, elapsed_ms))
            _raise_agent_error(provider, error)
        outputs[agent_id] = data
        trace.append(_trace(agent_id, "completed", None, provider, model, elapsed_ms))

    extraction = _dict_output(outputs, "intake_and_extraction_agent", "extraction")
    risk_output = _list_output(outputs, "risk_analysis_agent", "risk_matrix")
    negotiation_output = _str_output(outputs, "negotiation_agent", "negotiation_memo")
    summary_output = _str_output(outputs, "client_summary_agent", "client_summary")

    qc = outputs.get("quality_control_agent", {})
    corrections = qc.get("corrections") if isinstance(qc.get("corrections"), dict) else {}
    if qc and qc.get("approved") is False:
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
            trace.append(_trace("revision_controller_agent", "failed", revision_error, provider, model, elapsed_ms))
            _raise_agent_error(provider, revision_error)
        else:
            outputs["revision_controller_agent"] = revision_data
            trace.append(_trace("revision_controller_agent", "completed", None, provider, model, elapsed_ms))
            corrections = {**corrections, **revision_data}
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


def _agent_payload(base: dict[str, Any], agent_id: str, task_payload: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "config": base.get("config", {}),
        "workflow": base.get("workflow", {}),
        "task": task_payload,
    }
    if agent_id in {"intake_and_extraction_agent", "quality_control_agent"}:
        payload["source_excerpts"] = base.get("source_excerpts", [])
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
        return {
            "extraction": _optional_dict_output(outputs, "intake_and_extraction_agent", "extraction", deterministic_extraction),
            "clauses": _selected_workflow_clauses(workflow),
            "unattached_risks": _compact_risks(workflow.get("unattached_risk_findings", []), limit=12),
            "escalations": _compact_escalations(workflow.get("escalations", []), limit=8),
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


def _selected_workflow_clauses(workflow: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
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
        f"{contract} Return only valid JSON."
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
    data = json_loads(_extract_json_object(content), {})
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


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value
    return value[start:end + 1]


def _raise_agent_error(provider: str | None, error: str | None) -> None:
    if not error:
        return
    provider_name = provider.title() if provider else "The configured provider"
    if _is_payload_size_error(error):
        raise ContractReviewAgentError(
            f"{provider_name} rejected the request as too large for the configured model/token limit. "
            "Reduce the selected document scope, use a model with a larger context/token allowance, or split the review into smaller runs."
        )
    raise ContractReviewAgentError(f"Contract review could not run because {provider_name} returned an agent error: {error}")


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
