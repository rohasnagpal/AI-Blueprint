import json
import re
from typing import Any, Callable

from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm, configured_llm_provider


ProgressCallback = Callable[[str, int, str], None]


ROLE_SIGNATURES: dict[str, tuple[str, ...]] = {
    "auditor": ("audit", "auditor", "working paper", "methodology", "schedule of exception", "report conclusion"),
    "bank": ("bank", "account", "statement", "transfer", "beneficial owner", "kyc"),
    "management": ("approval", "authority matrix", "board", "director", "managing director", "management"),
    "investigation": ("investigating officer", "seizure", "certificate", "chain of custody", "65b", "63 certificate", "case diary"),
    "eyewitness": ("saw", "identified", "presence", "scene", "identification", "line-up"),
    "expert": ("expert", "opinion", "methodology", "basis", "report"),
    "vendor": ("vendor", "supplier", "invoice", "delivery", "goods", "purchase order", "receipt"),
}


def run_agentic_cross_exam_prep(
    *,
    sources: list[dict[str, Any]],
    source_bundle: list[dict[str, Any]],
    run_context: dict[str, Any],
    settings: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    emit = progress_callback or (lambda _message, _progress, _step: None)
    witness = str(run_context.get("target_witness") or "Selected witness").strip()
    provider = configured_llm_provider(settings)
    model = run_context.get("model") or settings.get("chat_model")
    public_source_bundle = _public_source_bundle(source_bundle)
    public_sources = _public_sources(sources)

    emit("Reading matter documents", 28, "case_ingestion")
    witness_identity = _resolve_witness_identity(public_source_bundle, witness)
    relevant_sources = _relevant_sources(public_source_bundle, witness_identity)
    case_map = _case_map(public_source_bundle, relevant_sources, witness, witness_identity)

    emit("Building opponent theory", 38, "opponent_theory")
    opponent_theory = _opponent_theory(relevant_sources, witness)

    emit("Finding witness contradictions", 50, "contradiction_hunter")
    contradictions = _contradictions(relevant_sources)

    emit("Designing cross-examination tree", 64, "cross_tree")
    llm_status = {"status": "skipped", "reason": "No configured LLM provider."}
    plan = {}
    if provider:
        plan, llm_status = _llm_cross_plan(settings, model, run_context, witness, relevant_sources, case_map, opponent_theory, contradictions)
    if not plan:
        plan = _deterministic_cross_plan(run_context, witness, relevant_sources, case_map, opponent_theory, contradictions)

    emit("Filtering risky questions", 74, "risk_control")
    plan = _normalize_plan(plan, run_context, witness, relevant_sources, case_map, opponent_theory, contradictions)

    emit("Simulating judge and opponent repair", 80, "judge_and_repair")
    return _to_litigation_output(plan, public_sources, run_context, provider, model, llm_status)


def _llm_cross_plan(settings: dict[str, Any], model: str | None, run_context: dict[str, Any], witness: str, relevant_sources: list[dict[str, Any]], case_map: dict[str, Any], opponent_theory: str, contradictions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    system = (
        "You are a specialist cross-examination strategy agent. Build a controlled, witness-specific courtroom cross plan from the supplied record. "
        "Do not write generic litigation prep. Do not invent facts. Every material point must come from the supplied excerpts or be marked provisional. "
        "Prefer short leading questions, admissions, contradiction bundles, risk controls, judge concerns, opponent repair, and stopping points. Return only valid JSON."
    )
    user = json.dumps(
        {
            "target_witness": witness,
            "side": run_context.get("party_role") or "defence / accused",
            "objective": run_context.get("cross_objective") or "Prepare full cross",
            "risk_level": run_context.get("risk_level") or "balanced",
            "language": run_context.get("output_language") or "English",
            "red_lines": run_context.get("red_lines") or "",
            "focus_notes": run_context.get("focus_notes") or "",
            "case_map": case_map,
            "opponent_theory": opponent_theory,
            "contradictions": contradictions,
            "witness_binding": _witness_binding_summary(case_map, relevant_sources),
            "strict_witness_rule": "Only ask this witness for facts within this witness's personal knowledge. Do not ask this witness to admit another witness's specialist conclusions or records unless the purpose is a tightly framed confrontation question.",
            "side_alignment_rule": "Classify each fact by which side it helps. For defence/accused, do not convert defence-favourable facts into prosecution admissions. The goal is to make the witness unable to prove the specific element they are called to prove, not to assert or confirm the opponent's theory of the case.",
            "source_excerpts": [_source_brief(source) for source in relevant_sources[:18]],
            "required_schema": {
                "strategy_summary": "string",
                "witness_role": "string",
                "objective": "string",
                "opponent_uses_witness_to_prove": "string",
                "do_not_contest": ["string"],
                "contest": ["string"],
                "core_attack": "string",
                "admissions_to_obtain": ["string"],
                "contradiction_bundles": [{"contradiction": "string", "source_1": "string", "source_2": "string", "why_it_matters": "string", "questions": ["string"]}],
                "cross_tree": [{"question": "string", "purpose": "string", "expected_answer": "string", "if_evasive": "string", "if_denied": "string", "document_to_confront": "string", "source_anchor": "filename/page/chunk or exact source label", "risk": "low|medium|high", "stop_or_continue": "string", "do_not_ask_if": "string"}],
                "questions_to_avoid": [{"question_or_area": "string", "reason": "string", "better": "string"}],
                "judge_questions": [{"question": "string", "best_answer": "string"}],
                "opponent_repair": [{"repair": "string", "counter": "string"}],
                "closing_use": "string",
                "missing_material": ["string"],
            },
        },
        sort_keys=True,
    )
    try:
        content = complete_with_configured_llm(settings, system, user, model=model, temperature=0.08, max_tokens=7000)
    except Exception as exc:
        return {}, {"status": "failed", "reason": f"LLM call failed: {exc}"}
    data = json_loads(_extract_json_object(content), {})
    if isinstance(data, dict) and data:
        return data, {"status": "completed", "reason": ""}
    likely_truncated = bool(content and content.strip() and not content.rstrip().endswith("}"))
    reason = "LLM returned invalid JSON; deterministic fallback used."
    if likely_truncated:
        reason = "LLM response appears truncated or incomplete; deterministic fallback used."
    return {}, {"status": "failed", "reason": reason}


def _deterministic_cross_plan(run_context: dict[str, Any], witness: str, relevant_sources: list[dict[str, Any]], case_map: dict[str, Any], opponent_theory: str, contradictions: list[dict[str, Any]]) -> dict[str, Any]:
    objective = run_context.get("cross_objective") or "Prepare full cross"
    focus = run_context.get("focus_notes") or ""
    red_lines = run_context.get("red_lines") or ""
    witness_hits = [_source_brief(source) for source in relevant_sources[:6]]
    key_docs = [item["label"] for item in witness_hits[:4]]
    admissions = _admissions_from_sources(relevant_sources, witness)
    bundles = contradictions[:5] or _basic_bundles(relevant_sources, witness)
    cross_tree = _apply_risk_level(_question_tree(witness, admissions, bundles, key_docs), run_context.get("risk_level") or "balanced")
    return {
        "strategy_summary": f"Prepare a controlled cross of {witness}. The plan is provisional where the indexed record does not contain a direct witness-specific excerpt.",
        "witness_role": case_map.get("witness_role") or f"{witness} appears in the indexed matter record; exact role must be confirmed from the source documents.",
        "objective": objective,
        "opponent_uses_witness_to_prove": opponent_theory,
        "do_not_contest": [red_lines] if red_lines else ["Do not contest neutral background facts unless they carry legal weight.", "Do not ask open-ended questions that let the witness retell the opponent's case."],
        "contest": [focus] if focus else ["The witness's personal knowledge, timing, source of information, and any unsupported inference."],
        "core_attack": _core_attack(bundles, admissions, run_context, case_map),
        "admissions_to_obtain": admissions,
        "contradiction_bundles": bundles,
        "cross_tree": cross_tree,
        "questions_to_avoid": [
            {"question_or_area": "Why are you lying?", "reason": "Argumentative and gives the witness room to explain.", "better": "Fix the prior statement, then confront the omission or inconsistency."},
            {"question_or_area": "Broad questions about the whole dispute.", "reason": "Lets the witness repeat harmful narrative.", "better": "Ask only one fact per question and stop after the admission."},
        ],
        "judge_questions": [
            {"question": "Why is this contradiction material?", "best_answer": "Because it affects the witness's ability to prove the specific bridge assigned to this witness, not merely a collateral detail."},
            {"question": "Is the attack based on delay alone?", "best_answer": "No. The attack should connect delay, omission or improvement, and lack of corroboration."},
        ],
        "opponent_repair": [
            {"repair": "The other side may say any omission is minor or explainable.", "counter": "Keep the focus on whether the first reliable version contained the decisive fact."},
            {"repair": "The other side may rely on documents independent of this witness.", "counter": "Separate what the document proves from what this witness can personally prove."},
        ],
        "closing_use": f"{witness} should be used only for admissions that are fixed in the record. If the witness cannot personally support the decisive link, the final argument should say the bridge remains unproved by this witness.",
        "missing_material": _missing_material(relevant_sources),
    }


def _normalize_plan(plan: dict[str, Any], run_context: dict[str, Any], witness: str, relevant_sources: list[dict[str, Any]], case_map: dict[str, Any], opponent_theory: str, contradictions: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _deterministic_cross_plan(run_context, witness, relevant_sources, case_map, opponent_theory, contradictions)
    normalized = {}
    for key, fallback_value in fallback.items():
        value = plan.get(key)
        if isinstance(fallback_value, list):
            normalized[key] = value if isinstance(value, list) and value else fallback_value
        elif isinstance(fallback_value, str):
            normalized[key] = value if isinstance(value, str) and value.strip() else fallback_value
        else:
            normalized[key] = value or fallback_value
    normalized, first_stats = _sanitize_plan(normalized)
    normalized = _remove_wrong_witness_material(normalized, case_map)
    normalized = _align_plan_to_side(normalized, run_context, case_map, relevant_sources)
    normalized = _enrich_question_tree(normalized)
    normalized, second_stats = _sanitize_plan(normalized)
    normalized["_sanitizer_stats"] = _merge_sanitizer_stats(first_stats, second_stats)
    return normalized


def _enrich_question_tree(plan: dict[str, Any]) -> dict[str, Any]:
    tree = plan.get("cross_tree")
    if not isinstance(tree, list):
        return plan
    for item in tree:
        if not isinstance(item, dict):
            continue
        confront = str(item.get("document_to_confront") or "").strip()
        if not str(item.get("source_anchor") or "").strip():
            item["source_anchor"] = confront or "Confirm source anchor before courtroom use."
        if not str(item.get("do_not_ask_if") or "").strip():
            item["do_not_ask_if"] = "Do not ask if the source anchor is unverified, the fact is outside this witness's personal knowledge, or the answer would let the witness retell the opponent's case."
    return plan


def _witness_binding_summary(case_map: dict[str, Any], relevant_sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "target_witness": case_map.get("target_witness"),
        "aliases": case_map.get("witness_aliases") or [],
        "roles": case_map.get("witness_roles") or [],
        "relevant_sources": [_source_label(source) for source in relevant_sources[:8]],
        "rule": "If a source excerpt concerns a different witness, use it only as a confrontation document and do not ask the target witness to admit that other witness's conclusions.",
    }


def _remove_wrong_witness_material(plan: dict[str, Any], case_map: dict[str, Any]) -> dict[str, Any]:
    wrong_witness_terms = _wrong_witness_terms(case_map)
    if not wrong_witness_terms:
        return plan

    def belongs_to_wrong_witness(value: Any) -> bool:
        text = str(value).lower()
        return any(term in text for term in wrong_witness_terms)

    for key in ["admissions_to_obtain", "contest", "do_not_contest"]:
        values = plan.get(key)
        if isinstance(values, list):
            plan[key] = [item for item in values if not belongs_to_wrong_witness(item)]

    bundles = plan.get("contradiction_bundles")
    if isinstance(bundles, list):
        plan["contradiction_bundles"] = [item for item in bundles if not belongs_to_wrong_witness(item)]

    tree = plan.get("cross_tree")
    if isinstance(tree, list):
        plan["cross_tree"] = [item for item in tree if not belongs_to_wrong_witness(item)]

    avoid = plan.get("questions_to_avoid")
    if isinstance(avoid, list):
        plan["questions_to_avoid"] = [item for item in avoid if not belongs_to_wrong_witness(item)]
    return plan


def _sanitize_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    stats = {"admissions_removed": 0, "bundles_removed": 0, "tree_removed": 0, "avoid_removed": 0}
    admissions = plan.get("admissions_to_obtain")
    if isinstance(admissions, list):
        filtered = [item for item in admissions if _is_witness_admission(item)]
        stats["admissions_removed"] = len(admissions) - len(filtered)
        plan["admissions_to_obtain"] = filtered

    bundles = plan.get("contradiction_bundles")
    if isinstance(bundles, list):
        filtered = [item for item in bundles if _is_safe_contradiction_bundle(item)]
        stats["bundles_removed"] = len(bundles) - len(filtered)
        plan["contradiction_bundles"] = filtered

    tree = plan.get("cross_tree")
    if isinstance(tree, list):
        filtered = [item for item in tree if _is_safe_question_item(item)]
        stats["tree_removed"] = len(tree) - len(filtered)
        plan["cross_tree"] = filtered

    avoid = plan.get("questions_to_avoid")
    if isinstance(avoid, list):
        filtered = [item for item in avoid if _is_safe_question_item(item)]
        stats["avoid_removed"] = len(avoid) - len(filtered)
        plan["questions_to_avoid"] = filtered
    return plan, stats


def _merge_sanitizer_stats(*stats_items: dict[str, int]) -> dict[str, int]:
    merged = {"admissions_removed": 0, "bundles_removed": 0, "tree_removed": 0, "avoid_removed": 0}
    for stats in stats_items:
        for key in merged:
            merged[key] += int(stats.get(key) or 0)
    return merged


def _wrong_witness_terms(case_map: dict[str, Any]) -> list[str]:
    target_roles = _role_categories(case_map.get("witness_roles") or [])
    if not target_roles:
        return []
    terms: list[str] = []
    for role, signature_terms in ROLE_SIGNATURES.items():
        if role not in target_roles:
            terms.extend(signature_terms)
    return list(dict.fromkeys(term.lower() for term in terms))


def _role_categories(roles: list[Any]) -> set[str]:
    text = " ".join(str(role).lower() for role in roles)
    categories: set[str] = set()
    for role, signature_terms in ROLE_SIGNATURES.items():
        if role in text or any(term in text for term in signature_terms):
            categories.add(role)
    return categories


def _align_plan_to_side(plan: dict[str, Any], run_context: dict[str, Any], case_map: dict[str, Any], relevant_sources: list[dict[str, Any]]) -> dict[str, Any]:
    if _is_proponent_side(run_context):
        plan["do_not_contest"] = _ensure_list(plan.get("do_not_contest"))
        _append_unique(plan["do_not_contest"], "Do not overstate facts this witness cannot prove from personal knowledge or authenticated documents.")
        _append_unique(plan["do_not_contest"], "Do not ask questions that let the witness volunteer avoidable defence explanations.")
        if not str(plan.get("closing_use") or "").strip():
            plan["closing_use"] = "Use this witness to establish the precise evidentiary link assigned to them, while preserving corroboration and avoiding unnecessary openings for the opposing side."
        return plan

    if not _is_defence_side(run_context):
        return plan

    prosecution_theory_terms = ["proved conspiracy", "prove the accused committed", "prove that the accused", "establish that the accused committed", "demonstrate that the accused", "prove guilt", "establish guilt"]
    if any(term in str(plan.get("core_attack", "")).lower() for term in prosecution_theory_terms):
        plan["core_attack"] = "Impeach this witness on reliability, personal knowledge, and the specific evidentiary bridge they are asked to prove; do not convert the opponent's theory into a defence admission."

    admissions = plan.get("admissions_to_obtain") if isinstance(plan.get("admissions_to_obtain"), list) else []
    plan["admissions_to_obtain"] = [item for item in admissions if _is_witness_admission(item)]

    plan["do_not_contest"] = _ensure_list(plan.get("do_not_contest"))
    _append_unique(plan["do_not_contest"], "Do not contest defence-favourable background facts merely because the opponent may also mention them.")
    _append_unique(plan["do_not_contest"], "Do not ask this witness to prove another witness's specialist conclusion unless the question is expressly framed as a confrontation with a document.")

    if not str(plan.get("closing_use") or "").strip():
        plan["closing_use"] = "Use this witness only for admissions and contradictions fixed in the record. If the witness cannot prove the decisive link from personal knowledge, argue that the bridge remains unsafe."
    return plan


def _is_defence_side(run_context: dict[str, Any]) -> bool:
    side = str(run_context.get("party_role") or "").lower()
    return any(term in side for term in ["defence", "defense", "accused", "defendant", "respondent"])


def _is_proponent_side(run_context: dict[str, Any]) -> bool:
    side = str(run_context.get("party_role") or "").lower()
    return any(term in side for term in ["complainant", "prosecution", "plaintiff", "claimant"])


def _apply_risk_level(tree: list[dict[str, Any]], risk_level: str) -> list[dict[str, Any]]:
    risk = str(risk_level or "balanced").lower()
    if risk == "conservative":
        return [item for item in tree if str(item.get("risk") or "medium").lower() != "high"]
    if risk == "aggressive":
        for item in tree:
            if str(item.get("risk") or "").lower() == "low":
                item["stop_or_continue"] = item.get("stop_or_continue") or "Continue if the answer opens a verified impeachment point."
        return tree
    return tree


def _to_litigation_output(plan: dict[str, Any], sources: list[dict[str, Any]], run_context: dict[str, Any], provider: str | None, model: str | None, llm_status: dict[str, Any]) -> dict[str, Any]:
    witness = str(run_context.get("target_witness") or "Selected witness")
    sanitizer_stats = plan.pop("_sanitizer_stats", {}) if isinstance(plan, dict) else {}
    warnings = [
        "AI-assisted cross-examination preparation. Human legal review is required before courtroom use.",
        "Questions are preparation drafts, not legal advice.",
        *[f"Missing or provisional: {item}" for item in plan["missing_material"][:5]],
    ]
    if llm_status.get("status") != "completed":
        warnings.append(str(llm_status.get("reason") or "LLM plan was not used; deterministic fallback used."))
    if run_context.get("source_chunks_truncated"):
        warnings.append(f"Only {run_context.get('source_chunk_count')} of {run_context.get('source_chunk_total')} indexed chunks were read for this run. Narrow the matter or selected documents if material appears missing.")
    removed_count = sum(int(value or 0) for value in sanitizer_stats.values())
    if removed_count:
        warnings.append(f"Risk filter removed {removed_count} unsafe or malformed item(s) from the generated plan.")
    witness_prep = [{
        "name": witness,
        "role": plan["witness_role"],
        "topics": [plan["opponent_uses_witness_to_prove"], plan["core_attack"]],
        "admissions": plan["admissions_to_obtain"],
        "contradictions": plan["contradiction_bundles"],
        "exhibit_references": sources[:6],
        "prep_questions": [item.get("question") for item in plan["cross_tree"][:8] if isinstance(item, dict)],
    }]
    return {
        "case_snapshot": {"matter_type": "cross_examination_prep", "target_witness": witness, "objective": plan["objective"], "requires_review": True},
        "claims_and_defenses": [],
        "issues": [{"title": "Witness objective", "summary": plan["objective"], "admissions": plan["admissions_to_obtain"], "missing_proof": plan["missing_material"], "source": sources[0] if sources else {}}],
        "chronology": [],
        "evidence_matrix": [{"issue": "Cross-examination attack", "element": plan["core_attack"], "supporting_evidence": plan["contradiction_bundles"], "adverse_evidence": [], "gaps": plan["missing_material"]}],
        "discovery_analysis": [],
        "witness_prep": witness_prep,
        "deposition_prep": [{"witness": witness, "topics": plan["contest"], "questions": [item.get("question") for item in plan["cross_tree"] if isinstance(item, dict)], "anchors": sources[:8], "caveats": plan["do_not_contest"]}],
        "motion_strategy": {},
        "trial_prep": {"judge_questions": plan["judge_questions"], "do_not_contest": plan["do_not_contest"], "contest": plan["contest"]},
        "argument_strategy": {"opponent_repair": plan["opponent_repair"], "closing_use": plan["closing_use"]},
        "cross_examination": plan["cross_tree"],
        "procedural_tasks": [],
        "damages_and_remedies": {},
        "risks_and_gaps": plan["questions_to_avoid"],
        "client_or_team_summary": plan["strategy_summary"],
        "warnings": warnings,
        "agentic_review": {
            "agent_trace": [
                {"step_name": "case_ingestion_agent", "status": "completed", "provider": "internal", "model": "cross_exam_v1"},
                {"step_name": "opponent_theory_agent", "status": "completed", "provider": "internal", "model": "cross_exam_v1"},
                {"step_name": "contradiction_hunter_agent", "status": "completed", "provider": "internal", "model": "cross_exam_v1"},
                {"step_name": "cross_examination_tree_agent", "status": llm_status.get("status") if provider else "fallback", "provider": provider or "internal", "model": model or "deterministic_cross_exam_v1", "error": llm_status.get("reason") if llm_status.get("status") == "failed" else None},
                {"step_name": "risk_control_agent", "status": "completed", "provider": "internal", "model": "cross_exam_v1", "removed": sanitizer_stats},
                {"step_name": "judge_simulation_agent", "status": "completed", "provider": "internal", "model": "cross_exam_v1"},
            ],
            "cross_exam_plan": plan,
            "enabled": bool(provider and llm_status.get("status") == "completed"),
            "llm_status": llm_status,
            "sanitizer": sanitizer_stats,
        },
        "agent_trace": [],
        "agent_outputs": {},
        "metadata": {"provider": provider, "model": model, "workflow_mode": "cross_exam_prep"},
    }


def _resolve_witness_identity(source_bundle: list[dict[str, Any]], witness: str) -> dict[str, Any]:
    aliases = [witness]
    roles = []
    pw_match = re.search(r"\bPW[-\s]?(\d+)\b", witness, re.I)
    if pw_match:
        pw = pw_match.group(1)
        pw_pattern = rf"PW[-\s]?{re.escape(pw)}"
        for source in source_bundle:
            content = str(source.get("content") or "")
            for pattern in [
                rf"(?:Statement|Draft Examination-in-Chief)\s+of\s+(?:Mr\.|Ms\.|Smt\.)?\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{1,3}})[^.\n]{{0,120}}\({pw_pattern}\)",
                rf"{pw_pattern}\s*\(([^)]+)\)",
                rf"{pw_pattern}\s*[:\-–]\s*(?:Mr\.|Ms\.|Smt\.)?\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{1,3}})",
            ]:
                for match in re.finditer(pattern, content, re.I):
                    candidate = _clean_alias(match.group(1))
                    if candidate:
                        aliases.append(candidate)
            for match in re.finditer(rf"(.{{0,120}}{pw_pattern}.{{0,180}})", content, re.I | re.S):
                window = match.group(1)
                for role, signature_terms in ROLE_SIGNATURES.items():
                    if any(re.search(rf"\b{re.escape(term)}\b", window, re.I) for term in signature_terms):
                        roles.append(role)
    else:
        requested_terms = [term for term in re.findall(r"[A-Za-z][A-Za-z-]{2,}", witness) if term.lower() not in {"the", "and", "for"}]
        for role, signature_terms in ROLE_SIGNATURES.items():
            if role in witness.lower() or any(term in witness.lower() for term in signature_terms):
                roles.append(role)
        if requested_terms:
            query = "|".join(re.escape(term) for term in requested_terms[:4])
            for source in source_bundle[:80]:
                content = str(source.get("content") or "")
                for match in re.finditer(rf"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,3}}[^.\n]{{0,120}}(?:{query})[^.\n]{{0,120}})", content, re.I):
                    candidate = _clean_alias(match.group(1))
                    if candidate and len(candidate.split()) <= 6:
                        aliases.append(candidate)
                for match in re.finditer(rf"(.{{0,140}}(?:{query}).{{0,180}})", content, re.I | re.S):
                    window = match.group(1)
                    for role, signature_terms in ROLE_SIGNATURES.items():
                        if any(re.search(rf"\b{re.escape(term)}\b", window, re.I) for term in signature_terms):
                            roles.append(role)
    for alias in list(aliases):
        aliases.extend(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", alias))
    aliases = list(dict.fromkeys(alias for alias in (_clean_alias(item) for item in aliases) if alias and len(alias) >= 2))
    roles = list(dict.fromkeys(roles))
    return {"requested": witness, "aliases": aliases, "roles": roles, "pw_number": pw_match.group(1) if pw_match else None}


def _public_source_bundle(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public = [source for source in source_bundle if not _is_hidden_source(source)]
    return public


def _public_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public = [source for source in sources if not _is_hidden_source(source)]
    return public


def _is_hidden_source(source: dict[str, Any]) -> bool:
    filename = str(source.get("filename") or "").lower()
    return _is_hidden_source_name(filename)


def _is_hidden_source_name(filename: str) -> bool:
    hidden_terms = [
        "hidden_evaluation",
        "answer_key",
        "answer key",
        "contradiction_map",
        "contradiction map",
        "evaluation_answer",
        "rubric",
        "section_t",
        "section t",
    ]
    return any(term in filename for term in hidden_terms)


def _clean_alias(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" .,:;—–-")
    cleaned = re.sub(r"\b(?:the|witness|vendor|supplier|auditor|chartered accountant)\b", "", cleaned, flags=re.I).strip()
    return cleaned.strip(" .,:;—–-")[:80]


def _relevant_sources(source_bundle: list[dict[str, Any]], witness_identity: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = witness_identity.get("aliases") or [witness_identity.get("requested") or ""]
    roles = witness_identity.get("roles") or []
    terms = [term.lower() for alias in aliases for term in re.findall(r"[A-Za-z0-9-]{2,}", alias)]
    role_terms = [term.lower() for role in roles for term in re.findall(r"[A-Za-z0-9-]{3,}", role)]
    target_role_categories = _role_categories(roles)
    target_signature_terms = [term for role in target_role_categories for term in ROLE_SIGNATURES.get(role, ())]
    other_signature_terms = [term for role, signature_terms in ROLE_SIGNATURES.items() if role not in target_role_categories for term in signature_terms]
    pw_number = witness_identity.get("pw_number")
    other_pw_pattern = re.compile(r"\bPW[-\s]?(\d+)\b", re.I)
    scored = []
    for index, source in enumerate(source_bundle):
        content = str(source.get("content") or "")
        lower = content.lower()
        score = sum(lower.count(term) for term in terms) if terms else 0
        score += 2 * sum(lower.count(term) for term in role_terms)
        score += 3 * sum(lower.count(term.lower()) for term in target_signature_terms)
        if pw_number and re.search(rf"\bPW[-\s]?{re.escape(str(pw_number))}\b", content, re.I):
            score += 12
        other_pw = {match.group(1) for match in other_pw_pattern.finditer(content) if not pw_number or match.group(1) != str(pw_number)}
        if other_pw and (not pw_number or not re.search(rf"\bPW[-\s]?{re.escape(str(pw_number))}\b", content, re.I)):
            score -= 8
        if target_role_categories:
            score -= sum(2 for term in other_signature_terms if term.lower() in lower)
        if score > 0:
            clipped = _clip_source_to_witness(source, witness_identity)
            scored.append((score, index, clipped))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if scored:
        return [source for _score, _index, source in scored[:24]]
    return [_clip_source_to_witness(source, witness_identity) for source in source_bundle[:8]]


def _clip_source_to_witness(source: dict[str, Any], witness_identity: dict[str, Any]) -> dict[str, Any]:
    content = str(source.get("content") or "")
    aliases = witness_identity.get("aliases") or []
    patterns = [re.escape(alias) for alias in aliases if alias]
    if witness_identity.get("pw_number"):
        patterns.append(rf"PW[-\s]?{re.escape(str(witness_identity['pw_number']))}")
    windows = []
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.I):
            start = max(0, match.start() - 900)
            end = min(len(content), match.end() + 1400)
            windows.append(content[start:end].strip())
    clipped = dict(source)
    if windows:
        clipped["content"] = "\n\n".join(_dedupe_windows(windows))[:6500]
        clipped["witness_clipped"] = True
    return clipped


def _dedupe_windows(windows: list[str], *, max_windows: int = 8) -> list[str]:
    unique = []
    seen = set()
    for window in windows:
        key = re.sub(r"\s+", " ", window[:220]).lower()
        if key not in seen:
            unique.append(window)
            seen.add(key)
    return unique[:max_windows]


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value:
        return [value]
    return []


def _append_unique(items: list[Any], value: Any) -> None:
    if not any(str(item).strip().lower() == str(value).strip().lower() for item in items):
        items.append(value)


def _contains_any(value: Any, terms: list[str]) -> bool:
    text = str(value).lower()
    return any(term.lower() in text for term in terms)


def _is_witness_admission(value: Any) -> bool:
    text = str(value).strip()
    if not text:
        return False
    lowered = text.lower()
    strategy_terms = [
        "must answer",
        "prepare for",
        "rather than",
        "should be explained",
        "subject to proof",
        "do not",
        "avoid",
        "belongs in",
        "may deny",
        "may create",
    ]
    return not any(term in lowered for term in strategy_terms)


def _is_safe_contradiction_bundle(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    text = str(value).lower()
    rejected_terms = [
        "potential tension between:",
        "answer_key",
        "answer key",
        "contradiction_map",
        "hidden_evaluation",
        "section_t",
    ]
    if any(term in text for term in rejected_terms):
        return False
    contradiction = str(value.get("contradiction") or "").strip()
    source_1 = str(value.get("source_1") or "").strip()
    source_2 = str(value.get("source_2") or "").strip()
    questions = value.get("questions")
    return bool(contradiction and source_1 and source_2 and isinstance(questions, list) and questions)


def _is_safe_question_item(value: Any) -> bool:
    if isinstance(value, str):
        text = value.strip()
        return bool(text and not _looks_like_raw_source_text(text))
    if not isinstance(value, dict):
        return False
    text = " ".join(str(part) for part in value.values() if isinstance(part, (str, int, float))).strip()
    if not text or _looks_like_raw_source_text(text):
        return False
    question = str(value.get("question") or value.get("question_or_area") or "").strip()
    return bool(question and not _looks_like_raw_source_text(question))


def _looks_like_raw_source_text(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if compact.count(" | ") >= 3 or compact.count("\t") >= 3:
        return True
    raw_markers = ["source_1", "source_2"]
    return any(marker in compact.lower() for marker in raw_markers) and not compact.endswith("?")


def _all_text(sources: list[dict[str, Any]]) -> str:
    return "\n".join(str(source.get("content") or "") for source in sources)


def _case_map(source_bundle: list[dict[str, Any]], relevant_sources: list[dict[str, Any]], witness: str, witness_identity: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(str(source.get("content") or "") for source in relevant_sources[:8])
    role = ""
    role_match = re.search(rf"({re.escape(witness)}[^.\n]{{0,220}})", text, re.I)
    if role_match:
        role = role_match.group(1).strip()
    if not role:
        for alias in witness_identity.get("aliases") or []:
            role_match = re.search(rf"({re.escape(alias)}[^.\n]{{0,220}})", text, re.I)
            if role_match:
                role = role_match.group(1).strip()
                break
    return {
        "target_witness": witness,
        "witness_aliases": witness_identity.get("aliases") or [witness],
        "witness_roles": witness_identity.get("roles") or [],
        "witness_role": role,
        "document_count": len(source_bundle),
        "relevant_excerpt_count": len(relevant_sources),
    }


def _opponent_theory(relevant_sources: list[dict[str, Any]], witness: str) -> str:
    witness_terms = [term.lower() for term in re.findall(r"[A-Za-z0-9-]{3,}", witness)]
    legal_terms = ["accused", "payment", "approved", "identified", "saw", "statement", "motive", "opportunity", "breach", "loss", "delivery", "recovery", "intent", "knowledge"]
    scored: list[tuple[int, str]] = []
    for source in relevant_sources:
        content = str(source.get("content") or "")
        for sentence in _sentences(content):
            lower = sentence.lower()
            score = 0
            score += 5 if witness.lower() in lower else 0
            score += 2 * sum(1 for term in witness_terms if term in lower)
            score += sum(1 for term in legal_terms if re.search(rf"\b{re.escape(term)}\b", lower))
            if score:
                scored.append((score, sentence[:500]))
    if scored:
        scored.sort(key=lambda item: (-item[0], len(item[1])))
        return scored[0][1]
    return f"The opponent may use {witness} to prove one link in the factual chain. Confirm the exact link from the record."


def _contradictions(relevant_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    contradiction_markers = ("contradicts", "inconsistent with", "omits", "omission", "improvement", "first statement", "later statement", "earlier statement")
    for source in relevant_sources:
        sentences = [
            sentence for sentence in _sentences(str(source.get("content") or ""))
            if any(marker in sentence.lower() for marker in contradiction_markers)
            and not _looks_like_raw_source_text(sentence)
        ]
        for sentence in sentences[:2]:
            bundles.append({
                "contradiction": sentence[:260],
                "source_1": _source_label(source),
                "source_2": "Confirm against the prior/later version or objective record before use.",
                "why_it_matters": "Use only if counsel verifies this is a legally usable inconsistency, omission, or improvement.",
                "questions": ["This point does not appear the same way in the earlier record, correct?"],
            })
    return bundles[:6]


def _basic_bundles(relevant_sources: list[dict[str, Any]], witness: str) -> list[dict[str, Any]]:
    return [{
        "contradiction": f"No precise contradiction for {witness} was automatically established from the indexed excerpts.",
        "source_1": _source_label(relevant_sources[0]) if relevant_sources else "Not found",
        "source_2": "Upload prior statements, EIC, affidavit, and objective records to strengthen this bundle.",
        "why_it_matters": "Cross should not allege contradiction unless the source pair is confirmed.",
        "questions": ["You can only speak to facts personally known to you, correct?", "Anything outside your personal knowledge comes from documents or what others told you, correct?"],
    }]


def _admissions_from_sources(relevant_sources: list[dict[str, Any]], witness: str) -> list[str]:
    admissions = []
    patterns = [
        r"do not recall[^.\n]*",
        r"do not think[^.\n]*",
        r"not fully sure[^.\n]*",
        r"not always maintained[^.\n]*",
        r"did not myself[^.\n]*",
        r"never[^.\n]*",
        r"no document[^.\n]*",
        r"will not answer[^.\n]*",
        r"does not establish[^.\n]*",
        r"two versions[^.\n]*",
    ]
    text = "\n".join(str(source.get("content") or "") for source in relevant_sources)
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            admissions.append(match.group(0).strip())
    if not admissions:
        admissions = [
            f"You are the witness identified as {witness}.",
            "You can speak only to documents you personally created, saw, or verified.",
            "Facts outside your personal knowledge come from records or what others told you.",
        ]
    return [item for item in list(dict.fromkeys(admissions)) if _is_witness_admission(item)][:8]


def _question_tree(witness: str, admissions: list[str], bundles: list[dict[str, Any]], key_docs: list[str]) -> list[dict[str, Any]]:
    questions = [
        {
            "question": f"You are {witness}, correct?",
            "purpose": "Fix witness identity and role.",
            "expected_answer": "Yes.",
            "if_evasive": "I am only asking you to confirm your identity as this witness.",
            "if_denied": "Ask the witness to state their full name and role.",
            "document_to_confront": key_docs[0] if key_docs else "Witness list / statement",
            "source_anchor": key_docs[0] if key_docs else "Witness list / statement",
            "risk": "low",
            "stop_or_continue": "Continue after identity is fixed.",
            "do_not_ask_if": "Do not ask if identity is admitted or the witness identity is uncertain from the record.",
        }
    ]
    for admission in admissions[:5]:
        questions.append({
            "question": _leading_question(admission),
            "purpose": "Obtain a controlled admission from the record.",
            "expected_answer": "Yes or qualified yes.",
            "if_evasive": "Break the proposition into date, document, and personal-knowledge parts.",
            "if_denied": "Confront with the cited document if available; otherwise move on.",
            "document_to_confront": key_docs[min(len(questions) - 1, len(key_docs) - 1)] if key_docs else "Relevant source document",
            "source_anchor": key_docs[min(len(questions) - 1, len(key_docs) - 1)] if key_docs else "Relevant source document",
            "risk": "medium",
            "stop_or_continue": "Continue only if the answer narrows the witness's proof value.",
            "do_not_ask_if": "Do not ask if the admission is not traceable to this witness or would invite narrative explanation.",
        })
    for bundle in bundles[:3]:
        questions.append({
            "question": (bundle.get("questions") or ["Your version changed on this point, correct?"])[0],
            "purpose": bundle.get("why_it_matters") or "Expose contradiction or omission.",
            "expected_answer": "Admission or denial.",
            "if_evasive": "Return to the exact prior statement and ask whether those words appear there.",
            "if_denied": "Confront with source 1, then source 2. Do not argue.",
            "document_to_confront": bundle.get("source_1") or "Prior statement",
            "source_anchor": bundle.get("source_1") or "Prior statement",
            "risk": "medium",
            "stop_or_continue": "Stop after the contradiction is fixed.",
            "do_not_ask_if": "Do not ask if both contradiction sources have not been verified and marked for confrontation.",
        })
    return questions[:10]


def _core_attack(bundles: list[dict[str, Any]], admissions: list[str], run_context: dict[str, Any] | None = None, case_map: dict[str, Any] | None = None) -> str:
    run_context = run_context or {}
    if bundles and "No precise contradiction" not in str(bundles[0].get("contradiction")):
        return "Use prior/later version tension to narrow the witness's reliability on the decisive fact."
    if admissions:
        return "Use controlled admissions to confine the witness to personal knowledge and documents actually verified."
    return "Keep the cross narrow until stronger source material is uploaded."


def _missing_material(relevant_sources: list[dict[str, Any]]) -> list[str]:
    text = "\n".join(str(source.get("content") or "") for source in relevant_sources).lower()
    missing = []
    checks = [("prior witness statement", "statement"), ("examination-in-chief", "examination-in-chief"), ("source document to confront", "document"), ("electronic evidence certificate / extraction material", "65b")]
    for label, term in checks:
        if term not in text:
            missing.append(label)
    return missing[:6]


def _leading_question(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip(" .")
    if len(clean) > 160:
        clean = clean[:157].rstrip() + "..."
    return f"{clean}, correct?"


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if len(item.strip()) > 30]


def _source_brief(source: dict[str, Any]) -> dict[str, str]:
    content = re.sub(r"\s+", " ", str(source.get("content") or source.get("excerpt") or "")).strip()
    return {"label": _source_label(source), "excerpt": content[:900]}


def _source_label(source: dict[str, Any]) -> str:
    chunk = source.get("chunk_index")
    if chunk is not None:
        try:
            return f"{source.get('filename') or 'Source'} · chunk {int(chunk) + 1}"
        except Exception:
            pass
    return str(source.get("filename") or "Source")


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value
    return value[start:end + 1]
