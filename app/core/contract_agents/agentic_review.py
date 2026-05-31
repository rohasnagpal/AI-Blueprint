import json
import time
from typing import Any

from app.core.contract_agents.tools import run_contract_agent_tools
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider


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
    fallback = {
        "extraction": deterministic_extraction,
        "risk_matrix": deterministic_risks,
        "negotiation_memo": deterministic_negotiation_memo,
        "client_summary": deterministic_client_summary,
    }
    if not provider:
        return {
            **fallback,
            "agentic_enabled": False,
            "agent_trace": [_trace("agent_pipeline", "skipped", "No configured LLM provider.")],
            "agent_outputs": {},
        }

    state: dict[str, Any] = {
        "config": config,
        "workflow_stats": workflow.get("stats", {}),
        "workflow_intake": workflow.get("intake", {}),
        "workflow_clauses": workflow.get("clauses", [])[:30],
        "workflow_escalations": workflow.get("escalations", []),
        "deterministic": fallback,
        "sources": sources[:12],
        "text_excerpt": text[:14000],
        "available_tools": (tool_context or {}).get("supported_tools", []),
    }
    trace: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}

    planner_data, planner_error = _run_agent(
        "review_planner_agent",
        "Plan the contract review based on document type, workflow stats, user instructions, and available evidence.",
        "Return JSON with keys strategy, required_agents, tool_requests, evidence_gaps, and stop_conditions. tool_requests must be an array of objects with a tool key.",
        state,
        settings,
        model=model,
        max_tokens=1200,
    )
    if planner_error:
        trace.append(_trace("review_planner_agent", "failed", planner_error, provider, model, None))
        outputs["review_planner_agent"] = {"strategy": "Run the default specialist sequence.", "required_agents": []}
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
        state["tool_results"] = tool_results
        trace.append(_trace("agent_tool_controller", "completed", None, "internal", "contract_agent_tools_v1", elapsed_ms))

    agent_specs = [
        (
            "intake_and_extraction_agent",
            "Extract commercially relevant contract facts and correct unsupported deterministic extraction fields.",
            "Return JSON with key extraction only. extraction must be an object keyed by field name. Each value should include value, supported, evidence, and confidence_score.",
            {"deterministic_extraction": deterministic_extraction, "workflow_intake": workflow.get("intake", {})},
            2200,
        ),
        (
            "risk_analysis_agent",
            "Assess clause, playbook, business, and legal risk from the workflow outputs and source evidence.",
            "Return JSON with key risk_matrix only. risk_matrix must be an array. Each item should include issue, severity, finding, evidence, requires_review, and confidence_score.",
            {"extraction": outputs.get("intake_and_extraction_agent", {}).get("extraction", deterministic_extraction)},
            2600,
        ),
        (
            "negotiation_agent",
            "Turn the extraction and risk analysis into practical negotiation priorities and fallback positions.",
            "Return JSON with key negotiation_memo only. The value must be a concise markdown string for a lawyer.",
            {},
            1800,
        ),
        (
            "client_summary_agent",
            "Convert the lawyer-facing findings into a cautious plain-English client summary without legal advice.",
            "Return JSON with key client_summary only. The value must be a concise plain-English string.",
            {},
            1400,
        ),
        (
            "quality_control_agent",
            "Review the draft outputs for unsupported claims, legal-advice overreach, missing evidence, and internal contradictions.",
            "Return JSON with keys approved, issues, corrections. approved is boolean; issues is an array; corrections is an object that may contain extraction, risk_matrix, negotiation_memo, or client_summary.",
            {},
            1800,
        ),
    ]

    for agent_id, role, contract, extra, max_tokens in agent_specs:
        agent_input = {**state, "agent_outputs_so_far": outputs, **extra}
        started = time.perf_counter()
        data, error = _run_agent(agent_id, role, contract, agent_input, settings, model=model, max_tokens=max_tokens)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if error:
            trace.append(_trace(agent_id, "failed", error, provider, model, elapsed_ms))
            continue
        outputs[agent_id] = data
        trace.append(_trace(agent_id, "completed", None, provider, model, elapsed_ms))

    extraction = _dict_output(outputs, "intake_and_extraction_agent", "extraction", deterministic_extraction)
    risk_output = _list_output(outputs, "risk_analysis_agent", "risk_matrix", deterministic_risks)
    negotiation_output = _str_output(outputs, "negotiation_agent", "negotiation_memo", deterministic_negotiation_memo)
    summary_output = _str_output(outputs, "client_summary_agent", "client_summary", deterministic_client_summary)

    qc = outputs.get("quality_control_agent", {})
    corrections = qc.get("corrections") if isinstance(qc.get("corrections"), dict) else {}
    if qc and qc.get("approved") is False:
        revision_input = {
            **state,
            "agent_outputs_so_far": outputs,
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


def _dict_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, dict) else fallback


def _list_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, list) else fallback


def _str_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: str) -> str:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, str) and value.strip() else fallback
