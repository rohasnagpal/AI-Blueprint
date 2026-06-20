from typing import Any


AGENT_SPECS: list[tuple[str, str, str, int, str]] = [
    (
        "case_intake_agent",
        "Classify the negotiation matter from the source evidence and user context.",
        "Return JSON with key case_snapshot containing matter_type, parties, negotiation_posture, relief_sought, forum_or_provider, jurisdiction, venue, negotiation_stage, key_dates, prior_negotiations, and confidentiality_constraints.",
        4000,
        "case_snapshot",
    ),
    (
        "pleadings_and_claims_agent",
        "Extract party positions, claims, defenses, concessions, disputed allegations, requested relief, and negotiation-relevant proof gaps.",
        "Return JSON with key claims_and_defenses only. The value must be an array of objects with claim_type, title, elements, defenses, admissions, missing_proof, settlement_relevance, and source.",
        4000,
        "claims_and_defenses",
    ),
    (
        "issues_and_elements_agent",
        "Identify legal or commercial issues, proof elements, burdens, disputed facts, admissions, and missing proof.",
        "Return JSON with key issues only. issues must be an array of objects with title, proof_elements, burdens, disputed_facts, admissions, missing_proof, source.",
        4000,
        "issues",
    ),
    (
        "chronology_agent",
        "Build a dated negotiation chronology grounded in source anchors.",
        "Return JSON with key chronology only. Each item needs date, description, source, confidence_score, and dispute_relevance.",
        5000,
        "chronology",
    ),
    (
        "evidence_matrix_agent",
        "Map issues and proof elements to supporting evidence, adverse evidence, and gaps.",
        "Return JSON with key evidence_matrix only. Each item needs issue, element, supporting_evidence, adverse_evidence, gaps.",
        5000,
        "evidence_matrix",
    ),
    (
        "discovery_agent",
        "Analyze information exchanged, missing materials, disclosure gaps, valuation gaps, expert/support gaps, and document needs for productive negotiation.",
        "Return JSON with key discovery_analysis only. The value must be an array of objects with item_type, description, status, source, and confidence_score.",
        4000,
        "discovery_analysis",
    ),
    (
        "witness_prep_agent",
        "Identify likely witnesses, topics, admissions, contradictions, exhibit references, and preparation questions.",
        "Return JSON with key witness_prep only. Each item needs name, role, topics, admissions, contradictions, exhibit_references, prep_questions.",
        4000,
        "witness_prep",
    ),
    (
        "deposition_prep_agent",
        "Produce participant preparation topics for client representatives, insurers, business stakeholders, witnesses, and experts.",
        "Return JSON with key deposition_prep only. Each item needs witness, topics, questions, anchors, and caveats.",
        4000,
        "deposition_prep",
    ),
    (
        "motion_strategy_agent",
        "Produce negotiation position brief themes, evidentiary support, vulnerabilities, likely counterpart responses, and confidentiality caveats.",
        "Return JSON with key motion_strategy only. Treat it as negotiation_position_brief. Do not provide legal advice, settlement recommendation, or outcome prediction.",
        4000,
        "motion_strategy",
    ),
    (
        "trial_prep_agent",
        "Produce negotiation session plan themes, caucus topics, opening presentation considerations, exhibit packets, and decision points.",
        "Return JSON with key trial_prep only. Treat it as negotiation_session_plan. Do not predict outcome.",
        4000,
        "trial_prep",
    ),
    (
        "argument_strategy_agent",
        "Create evidence-bound negotiation themes, strongest points, vulnerabilities, counterpart responses, and settlement-option framing.",
        "Return JSON with key argument_strategy only. Separate fact, inference, negotiation strategy, and missing evidence. Do not recommend settlement or predict outcome.",
        4000,
        "argument_strategy",
    ),
    (
        "procedural_agent",
        "Track negotiation logistics, confidentiality requirements, statement deadlines, attendance requirements, authority needs, and procedural tasks.",
        "Return JSON with key procedural_tasks only. Each item needs task_type, description, due_date, source, compliance_risk.",
        4000,
        "procedural_tasks",
    ),
    (
        "damages_and_remedies_agent",
        "Extract claimed relief, damages theories, mitigation, interest, costs, and evidentiary gaps.",
        "Return JSON with key damages_and_remedies only.",
        2200,
        "damages_and_remedies",
    ),
    (
        "cross_examination_agent",
        "Draft private caucus and reality-testing question outlines tied to evidence anchors and contradictions.",
        "Return JSON with key cross_examination only. Each item needs witness, topics, questions, anchors, caveats.",
        4000,
        "cross_examination",
    ),
    (
        "settlement_and_risk_agent",
        "Summarize negotiation risks, leverage factors, pressure points, BATNA/WATNA considerations, and decision points without recommendations or outcome predictions.",
        "Return JSON with key risks_and_gaps only. Each item needs risk_level, summary, leverage, decision_point, source, requires_review.",
        2200,
        "risks_and_gaps",
    ),
]


def fallback_agent_output(agent_id: str, tool_results: dict[str, Any], run_context: dict[str, Any]) -> dict[str, Any]:
    tools = {item.get("tool"): item.get("output") for item in tool_results.get("tool_results", [])}
    if agent_id == "case_intake_agent":
        return {
            "case_snapshot": {
                "dispute_type": "Unknown from indexed materials",
                "parties": [],
                "claims": [],
                "counterclaims": [],
                "affirmative_defenses": [],
                "relief_sought": [],
                "court": run_context.get("court") or "Not provided",
                "jurisdiction": run_context.get("jurisdiction") or "Not provided",
                "venue": run_context.get("venue") or "Not provided",
                "procedural_stage": run_context.get("procedural_stage") or "Not provided",
                "key_dates": run_context.get("hearing_dates") or [],
                "governing_instruments": [],
                "requires_review": True,
            }
        }
    if agent_id == "pleadings_and_claims_agent":
        return {"claims_and_defenses": tools.get("claim_defense_mapper", [])}
    if agent_id == "issues_and_elements_agent":
        return {"issues": [{"title": item.get("issue"), "proof_elements": [], "burdens": [], "disputed_facts": [], "admissions": [], "missing_proof": item.get("gaps", []), "source": (item.get("supporting_evidence") or [None])[0], "confidence_score": 0.5} for item in tools.get("issue_evidence_mapper", [])]}
    if agent_id == "chronology_agent":
        return {"chronology": tools.get("chronology_builder", [])}
    if agent_id == "evidence_matrix_agent":
        return {"evidence_matrix": tools.get("issue_evidence_mapper", [])}
    if agent_id == "discovery_agent":
        return {"discovery_analysis": tools.get("discovery_gap_analyzer", [])}
    if agent_id == "witness_prep_agent":
        return {"witness_prep": tools.get("witness_mapper", [])}
    if agent_id == "deposition_prep_agent":
        return {"deposition_prep": tools.get("deposition_outline_builder", [])}
    if agent_id == "motion_strategy_agent":
        return {"motion_strategy": tools.get("motion_argument_outline_tool", {"motions": []})}
    if agent_id == "trial_prep_agent":
        return {"trial_prep": tools.get("trial_theme_builder", {"themes": []})}
    if agent_id == "argument_strategy_agent":
        return {"argument_strategy": {"themes": tools.get("trial_theme_builder", {}).get("themes", []), "caveat": "Preparation themes require lawyer review."}}
    if agent_id == "procedural_agent":
        return {"procedural_tasks": tools.get("procedural_deadline_tool", [])}
    if agent_id == "damages_and_remedies_agent":
        return {"damages_and_remedies": tools.get("damages_extractor", {})}
    if agent_id == "cross_examination_agent":
        return {"cross_examination": tools.get("cross_exam_builder", [])}
    if agent_id == "settlement_and_risk_agent":
        return {"risks_and_gaps": [{"risk_level": "medium", "summary": "Human lawyer review required for all strategy and risk assessments.", "leverage": None, "decision_point": "Review evidence gaps and procedural assumptions.", "requires_review": True}]}
    return {}
