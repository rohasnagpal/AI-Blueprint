import json
import time
from typing import Any, Callable

from app.core.mediation_agents.agents import AGENT_SPECS, fallback_agent_output
from app.core.mediation_agents.tools import run_mediation_agent_tools
from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider


MAX_AUTONOMOUS_STEPS = 48
MAX_REPLANS = 4


def run_agentic_mediation_prep(
    *,
    sources: list[dict[str, Any]],
    source_bundle: list[dict[str, Any]],
    run_context: dict[str, Any],
    settings: dict[str, Any],
    progress_callback: Callable[[int, str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    provider = configured_llm_provider(settings)
    model = run_context.get("model") or settings.get("chat_model")
    fallback = _deterministic_outputs(sources, source_bundle, run_context)
    state: dict[str, Any] = {
        "run_context": run_context,
        "sources": sources[:20],
        "source_excerpt": _source_excerpt(source_bundle),
        "available_tools": run_context.get("supported_tools", []),
        "safety_rules": [
            "Do not invent facts, dates, rules, quotes, or evidence.",
            "Every material factual assertion must have an evidence anchor or be marked unsupported.",
            "Do not provide legal advice or predict outcomes.",
            "Do not decide the dispute or replace the mediator.",
            "Maintain neutral mediator framing; label party positions separately from mediator inferences.",
            "Separate fact, inference, strategy, and missing evidence.",
        ],
    }
    trace: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}
    run_state = _initial_run_state(run_context, sources, source_bundle)

    planner_data, planner_error = _run_agent(
        "mediation_planner_agent",
        "Plan the next bounded autonomous mediation preparation actions based on court, jurisdiction, venue, procedural stage, party role, documents, current working memory, open questions, tool results, and instructions.",
        "Return JSON with either next_actions or next_action. Each action must have type, name, reason, and input. Allowed types are run_tool, run_agent, verify_anchors, mark_gap, finalize, and pause_for_human_review. You may also return legacy keys strategy, required_agents, tool_requests, evidence_gaps, and stop_conditions.",
        {**state, "run_state": run_state},
        settings,
        model=model,
        max_tokens=1400,
    ) if provider else ({"strategy": "Run the default mediation preparation sequence.", "required_agents": [spec[0] for spec in AGENT_SPECS], "tool_requests": None, "evidence_gaps": [], "stop_conditions": []}, None)
    if planner_error:
        trace.append(_trace("mediation_planner_agent", "failed", planner_error, provider, model, None))
        outputs["mediation_planner_agent"] = {"strategy": "Run the default mediation preparation sequence.", "required_agents": []}
    else:
        outputs["mediation_planner_agent"] = planner_data
        trace.append(_trace("mediation_planner_agent", "completed", None, provider or "internal", model, None))
    _merge_planner_state(run_state, outputs.get("mediation_planner_agent", {}))

    action_queue = _planner_actions(outputs.get("mediation_planner_agent", {}), run_context)
    autonomous_steps: list[dict[str, Any]] = []
    interim_qc_flags: list[dict[str, Any]] = []
    tool_results = {"tool_results": [], "supported_tools": []}
    replan_count = 0
    stop_reason = None

    for step_number in range(1, MAX_AUTONOMOUS_STEPS + 1):
        if not action_queue:
            if provider and replan_count < MAX_REPLANS:
                replan_count += 1
                planner_data, planner_error = _run_agent(
                    "mediation_planner_agent",
                    "Replan based on the updated working memory. Choose only the next necessary bounded actions, or finalize if enough supported material exists.",
                    "Return JSON with next_actions or next_action using action objects with type, name, reason, and input. Use finalize when ready.",
                    {**state, "run_state": run_state, "agent_outputs_so_far": outputs},
                    settings,
                    model=model,
                    max_tokens=1200,
                )
                if planner_error:
                    trace.append(_trace("mediation_planner_agent", "failed", planner_error, provider, model, None))
                    stop_reason = "planner_replan_failed"
                    break
                outputs[f"mediation_planner_agent_replan_{replan_count}"] = planner_data
                trace.append(_trace("mediation_planner_agent", "completed", None, provider, model, None))
                _merge_planner_state(run_state, planner_data)
                action_queue = _planner_actions(planner_data, run_context)
            else:
                stop_reason = "action_queue_exhausted"
                break
        action = _normalize_action(action_queue.pop(0))
        if not action:
            continue
        action_type = action.get("type")
        if action_type == "finalize":
            stop_reason = action.get("reason") or "planner_finalized"
            autonomous_steps.append(_action_record(step_number, action, "completed", {"stop_reason": stop_reason}))
            break
        if action_type == "pause_for_human_review":
            gate = {"step": step_number, "reason": action.get("reason") or "Planner requested human review.", "action": action}
            run_state["human_review_gates"].append(gate)
            autonomous_steps.append(_action_record(step_number, action, "paused", gate))
            continue
        started = time.perf_counter()
        result, error = _execute_action(action, state, outputs, tool_results, source_bundle, run_context, settings, model, provider)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        step_name = str(result.get("step_name") or action.get("name") or action_type)
        if error:
            trace.append(_trace(step_name, "failed", error, provider if action_type == "run_agent" else "internal", model, elapsed_ms))
            autonomous_steps.append(_action_record(step_number, action, "failed", {"error": error, "duration_ms": elapsed_ms}))
            _update_run_state_after_action(run_state, action, None, error)
            _emit_progress(progress_callback, step_number, f"Mediation step failed: {step_name}", {"action": action, "error": error})
            continue
        if action_type == "run_tool":
            tool_payload = result.get("tool_result") or {}
            tool_results["tool_results"].extend(tool_payload.get("tool_results", []))
            tool_results["supported_tools"] = tool_payload.get("supported_tools", tool_results.get("supported_tools", []))
            outputs["agent_tool_controller"] = tool_results
            state["tool_results"] = tool_results
            trace.append(_trace("agent_tool_controller", "completed", None, "internal", "mediation_agent_tools_v1", elapsed_ms))
        elif action_type in {"run_agent", "verify_anchors"}:
            output_key = result.get("output_key") or step_name
            outputs[output_key] = result.get("output")
            trace.append(_trace(step_name, "completed", None, provider or "internal", model if provider else "deterministic_fallback", elapsed_ms))
        _update_run_state_after_action(run_state, action, result, None)
        flags = _interim_qc(run_state, action, result, source_bundle)
        if flags:
            interim_qc_flags.extend(flags)
            run_state["qc_flags"].extend(flags)
            run_state["human_review_gates"] = _human_review_gates(run_state, flags)
        autonomous_steps.append(_action_record(step_number, action, "completed", {"duration_ms": elapsed_ms, "result_summary": _result_summary(result), "interim_qc_flags": flags}))
        _emit_progress(progress_callback, step_number, f"Completed {step_name}", {"action": action, "duration_ms": elapsed_ms, "flags": len(flags)})

    if not tool_results.get("tool_results"):
        started = time.perf_counter()
        tool_results = run_mediation_agent_tools(requests=None, source_bundle=source_bundle, run_context=run_context, existing_outputs=outputs)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        outputs["agent_tool_controller"] = tool_results
        state["tool_results"] = tool_results
        trace.append(_trace("agent_tool_controller", "completed", None, "internal", "mediation_agent_tools_v1", elapsed_ms))

    for agent_id, _role, _contract, _max_tokens, _output_key in AGENT_SPECS:
        if agent_id not in outputs:
            fallback_data = fallback_agent_output(agent_id, tool_results, run_context)
            if fallback_data:
                outputs[agent_id] = fallback_data
                trace.append(_trace(agent_id, "completed", None, "internal", "deterministic_gap_fill", 0))

    draft = _compose_outputs(outputs, fallback)
    qc_input = {**state, "agent_outputs_so_far": outputs, "draft": draft, "run_state": run_state, "interim_qc_flags": interim_qc_flags}
    started = time.perf_counter()
    if provider:
        qc, qc_error = _run_agent(
            "quality_control_agent",
            "Check unsupported factual claims, hallucinated evidence, missing citations, contradictions, privilege or sensitivity issues, and uncaveated conclusions.",
            "Return JSON with keys approved, flagged_items, unsupported_claims, privilege_flags, warnings, and corrections. flagged_items must identify output_key paths.",
            qc_input,
            settings,
            model=model,
            max_tokens=3000,
        )
    else:
        qc, qc_error = _deterministic_qc(draft, tool_results), None
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if qc_error:
        trace.append(_trace("quality_control_agent", "failed", qc_error, provider, model, elapsed_ms))
        qc = _deterministic_qc(draft, tool_results)
    else:
        trace.append(_trace("quality_control_agent", "completed", None, provider or "internal", model if provider else "deterministic_qc", elapsed_ms))
    outputs["quality_control_agent"] = qc

    revisions_made: dict[str, Any] = {}
    flagged_items = qc.get("flagged_items") if isinstance(qc.get("flagged_items"), list) else []
    flagged_items = [*flagged_items, *interim_qc_flags]
    anchor_flags = _anchor_verification_flags(tool_results)
    flagged_items = [*flagged_items, *anchor_flags]
    if flagged_items:
        started = time.perf_counter()
        revision_input = {**state, "agent_outputs_so_far": outputs, "quality_control": qc, "draft": draft}
        if provider:
            revision_data, revision_error = _run_agent(
                "revision_controller_agent",
                "Revise only outputs flagged by quality control. Do not rewrite clean outputs.",
                "Return JSON with keys revisions_made and revised_outputs. revised_outputs may contain only flagged top-level output keys.",
                revision_input,
                settings,
                model=model,
                max_tokens=3500,
            )
        else:
            revision_data, revision_error = _deterministic_revisions(flagged_items, draft), None
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if revision_error:
            trace.append(_trace("revision_controller_agent", "failed", revision_error, provider, model, elapsed_ms))
        else:
            outputs["revision_controller_agent"] = revision_data
            trace.append(_trace("revision_controller_agent", "completed", None, provider or "internal", model if provider else "deterministic_revision", elapsed_ms))
            revised = revision_data.get("revised_outputs") if isinstance(revision_data.get("revised_outputs"), dict) else {}
            for key, value in revised.items():
                if key in draft:
                    draft[key] = value
            revisions_made = revision_data.get("revisions_made") if isinstance(revision_data.get("revisions_made"), dict) else revised

    warnings = _warnings(run_context, qc)
    run_state["stop_reason"] = stop_reason or "final_qc_completed"
    run_state["final_outputs"] = {key: bool(draft.get(key)) for key in draft}
    human_review_gates = _human_review_gates(run_state, flagged_items)
    agentic_review = {
        "planner_output": outputs.get("mediation_planner_agent", {}),
        "tool_requests": _tool_requests_from_steps(autonomous_steps) or outputs.get("mediation_planner_agent", {}).get("tool_requests") or [],
        "tool_results": tool_results,
        "autonomous_loop": {
            "enabled": True,
            "max_steps": MAX_AUTONOMOUS_STEPS,
            "steps": autonomous_steps,
            "replans": replan_count,
            "stop_reason": run_state["stop_reason"],
        },
        "working_memory": run_state,
        "human_review_gates": human_review_gates,
        "QC_flags": flagged_items,
        "revisions_made": revisions_made,
        "unsupported_claims": qc.get("unsupported_claims", []),
        "privilege_flags": qc.get("privilege_flags", []),
        "warnings": warnings,
        "agent_trace": trace,
        "agent_outputs": outputs,
        "enabled": bool(provider),
    }
    return {**draft, "warnings": warnings, "agentic_review": agentic_review, "agent_trace": trace, "agent_outputs": outputs}


def _initial_run_state(run_context: dict[str, Any], sources: list[dict[str, Any]], source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "objective": "Prepare an evidence-grounded mediation preparation package from indexed matter documents.",
        "matter_context": run_context,
        "known_facts": [],
        "open_questions": [],
        "evidence_index": sources[:20],
        "source_count": len(source_bundle),
        "issues": [],
        "tool_results": [],
        "agent_outputs": {},
        "qc_flags": [],
        "human_review_gates": [],
        "completed_steps": [],
        "next_actions": [],
        "stop_conditions": [],
        "stop_reason": None,
    }


def _merge_planner_state(run_state: dict[str, Any], planner_data: dict[str, Any]) -> None:
    if not isinstance(planner_data, dict):
        return
    for key in ["evidence_gaps", "open_questions", "stop_conditions"]:
        values = planner_data.get(key)
        if isinstance(values, list):
            target = "stop_conditions" if key == "stop_conditions" else "open_questions"
            run_state[target].extend({"source": "planner", "type": key, "value": value} for value in values[:20])
    if planner_data.get("strategy"):
        run_state["strategy"] = planner_data.get("strategy")


def _planner_actions(planner_data: dict[str, Any], run_context: dict[str, Any]) -> list[dict[str, Any]]:
    actions = planner_data.get("next_actions")
    if isinstance(actions, dict):
        actions = [actions]
    if not isinstance(actions, list):
        action = planner_data.get("next_action")
        actions = [action] if isinstance(action, dict) else []
    normalized = [_normalize_action(action) for action in actions]
    normalized = [action for action in normalized if action]
    if normalized:
        return normalized[:MAX_AUTONOMOUS_STEPS]

    tool_requests = planner_data.get("tool_requests")
    if not isinstance(tool_requests, list) or not tool_requests:
        tool_requests = [
            {"tool": "targeted_document_retrieval", "query": " ".join(str(item) for item in [run_context.get("party_role"), run_context.get("court"), run_context.get("jurisdiction"), run_context.get("procedural_stage"), "positions settlement authority caucus mediation statement damages"] if item)},
            {"tool": "chronology_builder"},
            {"tool": "claim_defense_mapper"},
            {"tool": "issue_evidence_mapper"},
            {"tool": "discovery_gap_analyzer"},
            {"tool": "witness_mapper"},
            {"tool": "deposition_outline_builder"},
            {"tool": "exhibit_index_tool"},
            {"tool": "contradiction_detector"},
            {"tool": "procedural_deadline_tool"},
            {"tool": "damages_extractor"},
            {"tool": "privilege_sensitivity_scanner"},
            {"tool": "motion_argument_outline_tool"},
            {"tool": "trial_theme_builder"},
            {"tool": "cross_exam_builder"},
            {"tool": "evidence_anchor_verifier"},
            {"tool": "mediation_audit_package_tool"},
        ]
    actions = [
        {"type": "run_tool", "name": str(request.get("tool") or "unknown"), "reason": "Planner requested source-grounding tool execution.", "input": request}
        for request in tool_requests
        if isinstance(request, dict)
    ]
    requested_agents = planner_data.get("required_agents")
    if not isinstance(requested_agents, list) or not requested_agents:
        requested_agents = [spec[0] for spec in AGENT_SPECS]
    allowed_agents = {spec[0] for spec in AGENT_SPECS}
    actions.extend(
        {"type": "run_agent", "name": str(agent_id), "reason": "Planner selected specialist agent.", "input": {}}
        for agent_id in requested_agents
        if str(agent_id) in allowed_agents
    )
    actions.append({"type": "verify_anchors", "name": "evidence_anchor_verifier", "reason": "Verify cited anchors before final QC.", "input": {"tool": "evidence_anchor_verifier"}})
    actions.append({"type": "finalize", "name": "finalize", "reason": "Default bounded action sequence completed.", "input": {}})
    return actions[:MAX_AUTONOMOUS_STEPS]


def _normalize_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    action_type = str(action.get("type") or action.get("action_type") or "").strip()
    name = str(action.get("name") or action.get("tool") or action.get("agent") or action.get("action") or "").strip()
    if action_type == "tool":
        action_type = "run_tool"
    if action_type == "agent":
        action_type = "run_agent"
    if not action_type and name:
        action_type = "run_tool" if action.get("tool") else "run_agent"
    if action_type not in {"run_tool", "run_agent", "verify_anchors", "mark_gap", "finalize", "pause_for_human_review"}:
        return {}
    if action_type == "verify_anchors" and not name:
        name = "evidence_anchor_verifier"
    if action_type in {"finalize", "mark_gap", "pause_for_human_review"} and not name:
        name = action_type
    if not name:
        return {}
    payload = action.get("input") if isinstance(action.get("input"), dict) else {}
    if action_type == "run_tool":
        payload = {**payload, "tool": payload.get("tool") or name}
    return {"type": action_type, "name": name, "reason": str(action.get("reason") or ""), "input": payload}


def _execute_action(
    action: dict[str, Any],
    state: dict[str, Any],
    outputs: dict[str, Any],
    tool_results: dict[str, Any],
    source_bundle: list[dict[str, Any]],
    run_context: dict[str, Any],
    settings: dict[str, Any],
    model: str | None,
    provider: str | None,
) -> tuple[dict[str, Any], str | None]:
    action_type = action.get("type")
    name = str(action.get("name") or "")
    if action_type in {"run_tool", "verify_anchors"}:
        request = action.get("input") if isinstance(action.get("input"), dict) else {}
        if action_type == "verify_anchors":
            request = {"tool": "evidence_anchor_verifier"}
        result = run_mediation_agent_tools(requests=[request], source_bundle=source_bundle, run_context=run_context, existing_outputs=outputs)
        return {"step_name": name, "tool_result": result}, None
    if action_type == "mark_gap":
        gap = {"summary": action.get("reason") or "Planner marked an evidence gap.", "requires_review": True}
        outputs.setdefault("planner_marked_gaps", []).append(gap)
        return {"step_name": name, "output_key": "planner_marked_gaps", "output": outputs["planner_marked_gaps"]}, None
    if action_type == "run_agent":
        spec = _agent_spec(name)
        if not spec:
            return {}, f"Unsupported mediation specialist agent: {name}"
        agent_id, role, contract, max_tokens, _output_key = spec
        agent_input = {**state, "agent_outputs_so_far": outputs, "tool_results": tool_results, "planner_action": action}
        if provider:
            data, error = _run_agent(agent_id, role, contract, agent_input, settings, model=model, max_tokens=max_tokens)
        else:
            data, error = fallback_agent_output(agent_id, tool_results, run_context), None
        if error:
            fallback_data = fallback_agent_output(agent_id, tool_results, run_context)
            if fallback_data:
                return {"step_name": agent_id, "output_key": agent_id, "output": fallback_data, "fallback_used": True}, None
            return {}, error
        return {"step_name": agent_id, "output_key": agent_id, "output": data}, None
    return {}, f"Unsupported action type: {action_type}"


def _agent_spec(agent_id: str) -> tuple[str, str, str, int, str] | None:
    for spec in AGENT_SPECS:
        if spec[0] == agent_id:
            return spec
    return None


def _update_run_state_after_action(run_state: dict[str, Any], action: dict[str, Any], result: dict[str, Any] | None, error: str | None) -> None:
    record = {"action": action, "status": "failed" if error else "completed", "error": error}
    run_state["completed_steps"].append(record)
    if error:
        run_state["open_questions"].append({"type": "failed_action", "value": error, "action": action})
        return
    if not result:
        return
    if result.get("tool_result"):
        tool_items = result["tool_result"].get("tool_results", [])
        run_state["tool_results"].extend(tool_items)
        for item in tool_items:
            output = item.get("output")
            if item.get("tool") in {"targeted_document_retrieval", "evidence_anchor_verifier"} and isinstance(output, list):
                run_state["evidence_index"].extend(output[:12])
    output_key = result.get("output_key")
    output = result.get("output")
    if output_key:
        run_state["agent_outputs"][output_key] = _result_summary(output)
    if output_key == "issues_and_elements_agent" and isinstance(output, dict):
        run_state["issues"] = output.get("issues") if isinstance(output.get("issues"), list) else run_state["issues"]


def _interim_qc(run_state: dict[str, Any], action: dict[str, Any], result: dict[str, Any] | None, source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if action.get("type") == "run_tool" and action.get("name") == "privilege_sensitivity_scanner":
        tool_items = ((result or {}).get("tool_result") or {}).get("tool_results", [])
        for item in tool_items:
            output = item.get("output")
            if isinstance(output, list) and output:
                flags.append({"output_key": "warnings", "issue": "Potential privileged or sensitive material detected during autonomous loop.", "items": output[:10], "requires_human_review": True})
    return flags


def _human_review_gates(run_state: dict[str, Any], flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates = []
    context = run_state.get("matter_context", {})
    if not context.get("court"):
        gates.append({"gate": "missing_court", "reason": "Court is absent or unspecified.", "requires_human_review": True})
    if not context.get("jurisdiction") and not context.get("venue"):
        gates.append({"gate": "missing_jurisdiction_or_venue", "reason": "Jurisdiction or venue is absent.", "requires_human_review": True})
    for flag in flags:
        if flag.get("requires_human_review") or "privilege" in str(flag).lower() or "unsupported" in str(flag).lower():
            gates.append({"gate": "qc_flag", "reason": flag.get("issue") or "QC flag requires human review.", "flag": flag, "requires_human_review": True})
    seen = set()
    unique = []
    for gate in [*run_state.get("human_review_gates", []), *gates]:
        key = json.dumps(_compact(gate), sort_keys=True)
        if key not in seen:
            unique.append(gate)
            seen.add(key)
    return unique[:50]


def _action_record(step_number: int, action: dict[str, Any], status: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"step_number": step_number, "action": action, "status": status, "metadata": metadata}


def _result_summary(result: Any) -> Any:
    if isinstance(result, dict):
        return {key: _result_summary(value) for key, value in list(result.items())[:12] if key not in {"source_excerpt"}}
    if isinstance(result, list):
        return [_result_summary(item) for item in result[:5]]
    if isinstance(result, str):
        return result[:500]
    return result


def _tool_requests_from_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = []
    for step in steps:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        if action.get("type") == "run_tool":
            request = action.get("input") if isinstance(action.get("input"), dict) else {}
            if request:
                requests.append(request)
    return requests


def _run_agent(agent_id: str, role: str, contract: str, payload: dict[str, Any], settings: dict[str, Any], *, model: str | None, max_tokens: int) -> tuple[dict[str, Any], str | None]:
    system = (
        f"You are {agent_id}, one specialist in a multi-agent mediation preparation system. "
        f"{role} Use only supplied evidence. Do not provide legal advice or predict outcomes. "
        f"Clearly mark unsupported facts and assumptions. {contract} Return only valid JSON."
    )
    user = json.dumps(_compact(payload), sort_keys=True)
    try:
        content = complete_with_configured_llm(settings, system, user, model=model, temperature=0.12, max_tokens=max_tokens)
    except Exception as exc:
        return {}, str(exc)
    data = json_loads(_extract_json_object(content), {})
    if not isinstance(data, dict) or not data:
        return {}, "Agent returned invalid JSON."
    return data, None


def _compose_outputs(outputs: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    caucus_impasse = outputs.get("caucus_impasse_agent", {}) if isinstance(outputs.get("caucus_impasse_agent"), dict) else {}
    private_prep = outputs.get("private_prep_agent", {}) if isinstance(outputs.get("private_prep_agent"), dict) else {}
    return {
        "case_snapshot": _dict_output(outputs, "case_intake_agent", "case_snapshot", fallback["case_snapshot"]),
        "claims_and_defenses": _list_output(outputs, "pleadings_and_claims_agent", "claims_and_defenses", fallback["claims_and_defenses"]),
        "positions_and_interests": _list_output(outputs, "positions_interests_agent", "positions_and_interests", fallback["positions_and_interests"]),
        "issues": _list_output(outputs, "issues_and_elements_agent", "issues", fallback["issues"]),
        "chronology": _list_output(outputs, "chronology_agent", "chronology", fallback["chronology"]),
        "evidence_matrix": _list_output(outputs, "evidence_matrix_agent", "evidence_matrix", fallback["evidence_matrix"]),
        "discovery_analysis": _list_output(outputs, "discovery_agent", "discovery_analysis", fallback["discovery_analysis"]),
        "witness_prep": _list_output(outputs, "witness_prep_agent", "witness_prep", fallback["witness_prep"]),
        "deposition_prep": _list_output(outputs, "deposition_prep_agent", "deposition_prep", fallback["deposition_prep"]),
        "motion_strategy": _dict_output(outputs, "motion_strategy_agent", "motion_strategy", fallback["motion_strategy"]),
        "trial_prep": _dict_output(outputs, "trial_prep_agent", "trial_prep", fallback["trial_prep"]),
        "argument_strategy": _dict_output(outputs, "argument_strategy_agent", "argument_strategy", fallback["argument_strategy"]),
        "cross_examination": _list_output(outputs, "cross_examination_agent", "cross_examination", fallback["cross_examination"]),
        "batna_watna_zopa": _dict_output(outputs, "batna_watna_zopa_agent", "batna_watna_zopa", fallback["batna_watna_zopa"]),
        "risk_allocation": _list_output(outputs, "risk_allocation_agent", "risk_allocation", fallback["risk_allocation"]),
        "settlement_levers": _list_output(outputs, "settlement_levers_agent", "settlement_levers", fallback["settlement_levers"]),
        "caucus_questions": caucus_impasse.get("caucus_questions") if isinstance(caucus_impasse.get("caucus_questions"), list) else fallback["caucus_questions"],
        "impasse_points": caucus_impasse.get("impasse_points") if isinstance(caucus_impasse.get("impasse_points"), list) else fallback["impasse_points"],
        "bridge_proposals": _list_output(outputs, "bridge_proposal_agent", "bridge_proposals", fallback["bridge_proposals"]),
        "mediator_private_prep_note": private_prep.get("mediator_private_prep_note") if isinstance(private_prep.get("mediator_private_prep_note"), dict) else fallback["mediator_private_prep_note"],
        "one_page_session_plan": private_prep.get("one_page_session_plan") if isinstance(private_prep.get("one_page_session_plan"), dict) else fallback["one_page_session_plan"],
        "procedural_tasks": _list_output(outputs, "procedural_agent", "procedural_tasks", fallback["procedural_tasks"]),
        "damages_and_remedies": _dict_output(outputs, "damages_and_remedies_agent", "damages_and_remedies", fallback["damages_and_remedies"]),
        "risks_and_gaps": _list_output(outputs, "settlement_and_risk_agent", "risks_and_gaps", fallback["risks_and_gaps"]),
        "client_or_team_summary": _summary(outputs, fallback),
    }


def _deterministic_outputs(sources: list[dict[str, Any]], source_bundle: list[dict[str, Any]], run_context: dict[str, Any]) -> dict[str, Any]:
    first = sources[0] if sources else {}
    anchor = first or (source_bundle[0] if source_bundle else {})
    source = {
        "document_id": anchor.get("document_id"),
        "chunk_id": anchor.get("chunk_id"),
        "filename": anchor.get("filename"),
        "excerpt": anchor.get("excerpt") or str(anchor.get("content") or "")[:500],
    }
    return {
        "case_snapshot": {"forum_or_provider": run_context.get("court"), "jurisdiction": run_context.get("jurisdiction"), "venue": run_context.get("venue"), "mediation_stage": run_context.get("procedural_stage"), "requires_review": True},
        "claims_and_defenses": [{"claim_type": "position", "title": "Mediation positions require lawyer classification", "elements": [], "defenses": [], "admissions": [], "missing_proof": ["Confirm party positions, concessions, authority, and missing support."], "source": source, "confidence_score": 0.4}],
        "positions_and_interests": [{"party": "Party to be confirmed", "stated_positions": ["Review pleadings, briefs, correspondence, and offers to classify stated positions."], "possible_underlying_interests": ["Cost, timing, certainty, confidentiality, relationship, reputation, and acknowledgment interests require mediator clarification."], "emotional_drivers": ["Potential frustration, distrust, or need to be heard should be explored without treating it as fact."], "commercial_drivers": ["Cash flow, business continuity, payment timing, and future dealings require confirmation."], "source": source, "confidence_score": 0.35, "inference_caveats": ["Interests are mediator hypotheses, not findings."]}],
        "issues": [{"title": "Issues require lawyer classification", "summary": "Indexed documents were processed; issue classification requires human legal review.", "proof_elements": [], "burdens": [], "disputed_facts": [], "admissions": [], "missing_proof": ["Confirm claims, counterclaims, and proof elements."], "source": source, "confidence_score": 0.4}],
        "chronology": [],
        "evidence_matrix": [{"issue": "Unclassified issue", "supporting_evidence": [source] if source else [], "adverse_evidence": [], "gaps": ["Map source evidence to elements after lawyer review."]}],
        "discovery_analysis": [{"item_type": "information_gap", "description": "Information-exchange posture requires lawyer review against mediation goals, valuation support, and authority needs.", "status": "requires_review", "confidence_score": 0.4}],
        "witness_prep": [],
        "deposition_prep": [],
        "motion_strategy": {"motions": [], "caveat": "Mediator brief strategy requires lawyer review and confidentiality verification."},
        "trial_prep": {"themes": [], "caveat": "Mediation session planning requires lawyer review and does not predict outcomes."},
        "argument_strategy": {"themes": [], "caveat": "No legal advice, settlement recommendation, or outcome prediction. Negotiation themes require lawyer review."},
        "cross_examination": [],
        "batna_watna_zopa": {"party_assessments": [], "possible_zopa": "Not enough supported valuation, authority, or prior-offer information to state a range.", "settlement_range_considerations": [], "assumptions": ["Explore authority, payment capacity, non-monetary terms, prior offers, and litigation/arbitration alternatives."], "evidence_gaps": ["Prior offers, authority limits, insurer position, collectability, and non-monetary interests."], "confidence_score": 0.3, "caveat": "Mediator preparation only; not a valuation decision or recommendation."},
        "risk_allocation": [{"risk": "Uncertain merits, valuation, timing, or collectability risk", "allocation": "Requires caucus testing with each party", "affected_parties": [], "rationale": "Source materials do not support a firm neutral allocation.", "source": source, "uncertainty": "high", "mediator_note": "Ask each side how it prices this uncertainty."}],
        "settlement_levers": [
            {"lever": "Payment timing", "parties_affected": [], "why_it_may_matter": "Can bridge valuation and cash-flow constraints.", "possible_shapes": ["lump sum", "installments", "milestones"], "source_or_inference": "inference", "caveats": ["Confirm authority and payment capacity."]},
            {"lever": "Confidentiality", "parties_affected": [], "why_it_may_matter": "May address reputational or business concerns.", "possible_shapes": ["mutual confidentiality", "limited permitted disclosures"], "source_or_inference": "inference", "caveats": ["Verify legal limits and existing orders."]},
            {"lever": "Non-monetary acknowledgment", "parties_affected": [], "why_it_may_matter": "May address emotional interests not captured by money.", "possible_shapes": ["statement of regret", "process commitment"], "source_or_inference": "inference", "caveats": ["Avoid admissions unless agreed."]},
        ],
        "caucus_questions": [{"party": "Each party", "question": "What interests must be protected for any resolution to work?", "purpose": "Separate interests from positions.", "source_or_assumption": "mediator preparation inference", "sensitivity": "medium"}],
        "impasse_points": [{"issue": "Valuation gap", "why_it_may_block_settlement": "No supported settlement range or authority information is available.", "early_warning_signs": ["fixed anchors", "refusal to bracket"], "mediator_options": ["reality-test risk", "explore package terms", "use conditional brackets"]}],
        "bridge_proposals": [{"label": "Package proposal", "structure": "Combine money, timing, confidentiality, releases, and non-monetary terms before testing final number movement.", "parties_helped": ["all parties"], "tradeoffs": ["More complex than a single number."], "prerequisites": ["authority check"], "risks": ["May be premature before interests are known."], "neutrality_caveat": "Process option only, not a merits recommendation."}],
        "mediator_private_prep_note": {"opening_frame": "Explain that the process is neutral and the mediator will not decide the dispute.", "watch_points": ["authority", "valuation gap", "missing information", "confidentiality", "emotional drivers"], "caucus_priorities": ["interests", "BATNA/WATNA", "movement conditions"], "do_not_do": ["do not decide merits", "do not treat inferred interests as facts"]},
        "one_page_session_plan": {"opening": "Confirm confidentiality, process, authority, and agenda.", "joint_session": ["neutral issue framing", "agreed facts", "information gaps"], "first_caucus": ["positions", "interests", "authority", "BATNA/WATNA"], "middle_game": ["reality testing", "settlement levers", "bridge proposals"], "closing": ["settlement terms or next steps"]},
        "procedural_tasks": [],
        "damages_and_remedies": {"claimed_relief": [], "gaps": ["Verify relief, damages, mitigation, interest, and costs evidence."]},
        "risks_and_gaps": [{"risk_level": "medium", "summary": "Evidence and procedural assumptions require lawyer review.", "requires_review": True}],
        "client_or_team_summary": "Mediation preparation package generated from indexed matter documents. Human lawyer review is required before use or circulation.",
    }


def _deterministic_qc(draft: dict[str, Any], tool_results: dict[str, Any]) -> dict[str, Any]:
    tool_map = {item.get("tool"): item.get("output") for item in tool_results.get("tool_results", [])}
    privilege_flags = tool_map.get("privilege_sensitivity_scanner", [])
    flagged = []
    if not draft.get("issues"):
        flagged.append({"output_key": "issues", "issue": "No issues generated."})
    if not draft.get("evidence_matrix"):
        flagged.append({"output_key": "evidence_matrix", "issue": "No evidence matrix generated."})
    if privilege_flags:
        flagged.append({"output_key": "warnings", "issue": "Potential privileged or sensitive material detected."})
    return {"approved": not flagged, "flagged_items": flagged, "unsupported_claims": [], "privilege_flags": privilege_flags, "warnings": [], "corrections": {}}


def _deterministic_revisions(flagged_items: list[dict[str, Any]], draft: dict[str, Any]) -> dict[str, Any]:
    revised: dict[str, Any] = {}
    keys = {item.get("output_key") for item in flagged_items}
    if "issues" in keys and not draft.get("issues"):
        revised["issues"] = [{"title": "Unclassified issue", "summary": "No supported issue classification was available.", "missing_proof": ["Lawyer review required."], "requires_review": True}]
    if "evidence_matrix" in keys and not draft.get("evidence_matrix"):
        revised["evidence_matrix"] = [{"issue": "Unclassified issue", "supporting_evidence": [], "adverse_evidence": [], "gaps": ["No supported source anchors available."]}]
    return {"revisions_made": {key: "Revised flagged output only." for key in revised}, "revised_outputs": revised}


def _warnings(run_context: dict[str, Any], qc: dict[str, Any]) -> list[str]:
    warnings = [
        "AI-assisted mediator preparation. This report does not decide the dispute and does not replace the mediator.",
        "This output is not legal advice, does not predict outcomes, and should remain a private preparation aid unless reviewed for sharing.",
    ]
    if not run_context.get("court"):
        warnings.append("Court is absent or unspecified; procedural assumptions must be verified.")
    if not run_context.get("jurisdiction") and not run_context.get("venue"):
        warnings.append("Jurisdiction or venue is absent; procedural assumptions must be verified.")
    warnings.extend(str(item.get("summary") or item.get("issue") or item) for item in qc.get("privilege_flags", [])[:5])
    return list(dict.fromkeys(warnings))


def _summary(outputs: dict[str, Any], fallback: dict[str, Any]) -> str:
    value = outputs.get("client_or_team_summary")
    if isinstance(value, str) and value.strip():
        return value
    value = outputs.get("neutral_summary_agent", {}).get("client_or_team_summary")
    if isinstance(value, str) and value.strip():
        return value
    return fallback["client_or_team_summary"]


def _source_excerpt(source_bundle: list[dict[str, Any]], *, max_chars: int = 16000) -> str:
    if not source_bundle:
        return ""
    by_document: dict[str, list[dict[str, Any]]] = {}
    for item in source_bundle:
        key = str(item.get("document_id") or item.get("filename") or "source")
        by_document.setdefault(key, []).append(item)
    snippets: list[str] = []
    for items in by_document.values():
        for source in items[:2]:
            label = f"[{source.get('filename') or 'Source'} chunk {int(source.get('chunk_index') or 0) + 1}]"
            content = str(source.get("content") or "")[:1800]
            if content:
                snippets.append(f"{label}\n{content}")
    text = "\n\n".join(snippets)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _emit_progress(callback: Callable[[int, str, dict[str, Any]], None] | None, step_number: int, message: str, metadata: dict[str, Any]) -> None:
    if not callback:
        return
    progress = min(80, 45 + int((step_number / max(1, MAX_AUTONOMOUS_STEPS)) * 35))
    try:
        callback(progress, message, metadata)
    except Exception:
        return


def _anchor_verification_flags(tool_results: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for item in tool_results.get("tool_results", []):
        if item.get("tool") != "evidence_anchor_verifier":
            continue
        unsupported = [entry for entry in item.get("output", []) if isinstance(entry, dict) and entry.get("supported") is False]
        if unsupported:
            flags.append({"output_key": "evidence_anchors", "issue": "Unsupported or unverified evidence anchors detected in consolidated post-loop verification.", "unsupported": unsupported[:20], "requires_human_review": True})
    return flags


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:6500]
    return value


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value
    return value[start:end + 1]


def _trace(step_name: str, status: str, error: str | None = None, provider: str | None = None, model: str | None = None, duration_ms: int | None = None) -> dict[str, Any]:
    return {"step_name": step_name, "status": status, "provider": provider, "model": model, "duration_ms": duration_ms, "error": error}


def _dict_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: dict[str, Any]) -> dict[str, Any]:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, dict) else fallback


def _list_output(outputs: dict[str, Any], agent_id: str, key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    value = outputs.get(agent_id, {}).get(key)
    return value if isinstance(value, list) else fallback
