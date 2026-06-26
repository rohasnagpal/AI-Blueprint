from typing import Any


AGENT_SPECS: list[tuple[str, str, str, int, str]] = [
    (
        "case_intake_agent",
        "Classify the litigation matter from the source evidence and user context.",
        "Return JSON with key case_snapshot containing matter_type, parties, claims, counterclaims, affirmative_defenses, relief_sought, court, jurisdiction, venue, procedural_stage, key_dates, and active_orders.",
        4000,
        "case_snapshot",
    ),
    (
        "neutral_summary_agent",
        "Draft a concise neutral litigation case summary based only on supplied evidence and clearly labeled assumptions.",
        "Return JSON with key client_or_team_summary only. The value must be a neutral paragraph identifying the dispute, parties, claims/counterclaims, relief sought, procedural posture, and important caveats without deciding merits or predicting outcome.",
        1800,
        "client_or_team_summary",
    ),
    (
        "pleadings_and_claims_agent",
        "Extract causes of action, elements, defenses, admissions, denials, disputed allegations, conceded facts, and requested relief.",
        "Return JSON with key claims_and_defenses only. The value must be an array of objects with claim_type, title, elements, defenses, admissions, missing_proof, and source.",
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
        "Build a dated litigation chronology grounded in source anchors.",
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
        "Analyze discovery served, responses, objections, missing productions, deposition needs, ESI issues, deadlines, and motion-to-compel risks.",
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
        "Produce deposition objectives, topic outlines, exhibit sequences, admissions to seek, impeachment points, and follow-up questions.",
        "Return JSON with key deposition_prep only. Each item needs witness, topics, questions, anchors, and caveats.",
        4000,
        "deposition_prep",
    ),
    (
        "motion_strategy_agent",
        "Produce pending or potential motion themes, evidentiary support, vulnerabilities, opponent responses, and procedural prerequisites.",
        "Return JSON with key motion_strategy only. Do not provide legal advice or outcome prediction.",
        4000,
        "motion_strategy",
    ),
    (
        "trial_prep_agent",
        "Produce trial themes, witness order considerations, exhibit issues, evidentiary objections, demonstrative needs, and disputed fact clusters.",
        "Return JSON with key trial_prep only. Do not predict outcome.",
        4000,
        "trial_prep",
    ),
    (
        "argument_strategy_agent",
        "Create evidence-bound argument themes, strongest points, vulnerabilities, and likely opponent responses.",
        "Return JSON with key argument_strategy only. Separate fact, inference, strategy, and missing evidence. Do not predict outcome.",
        4000,
        "argument_strategy",
    ),
    (
        "procedural_agent",
        "Track procedural orders, deadlines, hearing logistics, filings, production obligations, objections, and compliance risks.",
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
        "Draft cross-examination topic outlines tied to evidence anchors and contradictions.",
        "Return JSON with key cross_examination only. Each item needs witness, topics, questions, anchors, caveats.",
        4000,
        "cross_examination",
    ),
    (
        "settlement_and_risk_agent",
        "Summarize case risks, leverage, settlement pressure points, and decision points without recommendations or outcome predictions.",
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
    if agent_id == "neutral_summary_agent":
        claims = tools.get("claim_defense_mapper", [])
        claim_titles = ", ".join(str(item.get("title") or item.get("claim_type")) for item in claims[:6] if item.get("title") or item.get("claim_type"))
        return {
            "client_or_team_summary": (
                "This is a neutral litigation preparation summary generated from indexed matter documents. "
                f"The available materials indicate claims or defenses requiring legal review{': ' + claim_titles if claim_titles else ''}. "
                "The report does not decide merits, provide legal advice, or predict outcomes."
            )
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
