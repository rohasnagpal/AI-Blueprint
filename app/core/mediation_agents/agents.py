from typing import Any


AGENT_SPECS: list[tuple[str, str, str, int, str]] = [
    (
        "case_intake_agent",
        "Classify the mediation matter from the source evidence and user context.",
        "Return JSON with key case_snapshot containing matter_type, parties, mediation_posture, relief_sought, forum_or_provider, jurisdiction, venue, mediation_stage, key_dates, prior_negotiations, confidentiality_constraints, and mediator_role_caveat.",
        4000,
        "case_snapshot",
    ),
    (
        "neutral_summary_agent",
        "Draft a concise neutral case summary for the mediator based only on supplied evidence and clearly labeled assumptions.",
        "Return JSON with key client_or_team_summary only. The value must be a neutral paragraph that identifies the dispute, parties, relief sought, main defenses, settlement posture, and important caveats without deciding merits.",
        1800,
        "client_or_team_summary",
    ),
    (
        "pleadings_and_claims_agent",
        "Extract party positions, claims, defenses, concessions, disputed allegations, requested relief, and mediation-relevant proof gaps.",
        "Return JSON with key claims_and_defenses only. The value must be an array of objects with claim_type, title, elements, defenses, admissions, missing_proof, settlement_relevance, and source.",
        4000,
        "claims_and_defenses",
    ),
    (
        "positions_interests_agent",
        "Separate each party's stated positions from possible underlying interests for neutral mediator preparation.",
        "Return JSON with key positions_and_interests only. The value must be an array of objects with party, stated_positions, possible_underlying_interests, emotional_drivers, commercial_drivers, source, confidence_score, and inference_caveats.",
        4500,
        "positions_and_interests",
    ),
    (
        "issues_and_elements_agent",
        "Identify legal, factual, commercial, emotional, and procedural issues for neutral mediation preparation.",
        "Return JSON with key issues only. issues must be an array of objects with title, category, proof_elements, burdens, disputed_facts, admissions, missing_proof, emotional_or_commercial_dimension, source.",
        4000,
        "issues",
    ),
    (
        "chronology_agent",
        "Build a dated mediation chronology grounded in source anchors.",
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
        "Analyze information exchanged, missing materials, disclosure gaps, valuation gaps, expert/support gaps, and document needs for productive mediation.",
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
        "Produce mediator-brief themes, evidentiary support, vulnerabilities, likely counterpart responses, and confidentiality caveats.",
        "Return JSON with key motion_strategy only. Treat it as mediator_brief_strategy. Do not provide legal advice, settlement recommendation, or outcome prediction.",
        4000,
        "motion_strategy",
    ),
    (
        "trial_prep_agent",
        "Produce mediation session plan themes, caucus topics, opening presentation considerations, exhibit packets, and decision points.",
        "Return JSON with key trial_prep only. Treat it as mediation_session_plan. Do not predict outcome.",
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
        "Track mediation logistics, confidentiality requirements, statement deadlines, attendance requirements, authority needs, and procedural tasks.",
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
        "batna_watna_zopa_agent",
        "Prepare neutral BATNA, WATNA, and possible ZOPA or settlement-range considerations for each side without deciding the dispute.",
        "Return JSON with key batna_watna_zopa only. The value must contain party_assessments, possible_zopa, settlement_range_considerations, assumptions, evidence_gaps, confidence_score, and caveat.",
        4500,
        "batna_watna_zopa",
    ),
    (
        "risk_allocation_agent",
        "Allocate legal, factual, commercial, procedural, emotional, collectability, and timing risks between parties for mediator preparation.",
        "Return JSON with key risk_allocation only. The value must be an array of objects with risk, allocation, affected_parties, rationale, source, uncertainty, and mediator_note.",
        4000,
        "risk_allocation",
    ),
    (
        "settlement_levers_agent",
        "Identify settlement levers including payment terms, apology, confidentiality, future business, timing, releases, performance terms, and non-monetary options.",
        "Return JSON with key settlement_levers only. The value must be an array of objects with lever, parties_affected, why_it_may_matter, possible_shapes, source_or_inference, and caveats.",
        4000,
        "settlement_levers",
    ),
    (
        "cross_examination_agent",
        "Draft private caucus and reality-testing question outlines tied to evidence anchors and contradictions.",
        "Return JSON with key cross_examination only. Each item needs witness, topics, questions, anchors, caveats.",
        4000,
        "cross_examination",
    ),
    (
        "caucus_impasse_agent",
        "Generate mediator caucus questions for each party and identify likely impasse points.",
        "Return JSON with keys caucus_questions and impasse_points only. caucus_questions must be an array with party, question, purpose, source_or_assumption, and sensitivity. impasse_points must be an array with issue, why_it_may_block_settlement, early_warning_signs, and mediator_options.",
        4500,
        "caucus_impasse",
    ),
    (
        "bridge_proposal_agent",
        "Suggest possible mediator bridge proposals without deciding merits or recommending a forced outcome.",
        "Return JSON with key bridge_proposals only. Each proposal needs label, structure, parties_helped, tradeoffs, prerequisites, risks, and neutrality_caveat.",
        4000,
        "bridge_proposals",
    ),
    (
        "private_prep_agent",
        "Prepare the mediator's private prep note and one-page session plan.",
        "Return JSON with keys mediator_private_prep_note and one_page_session_plan only. Keep the note private, neutral, caveated, and focused on session management.",
        4500,
        "private_prep",
    ),
    (
        "settlement_and_risk_agent",
        "Summarize mediation risks, leverage factors, pressure points, BATNA/WATNA considerations, and decision points without recommendations or outcome predictions.",
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
        issues = tools.get("issue_evidence_mapper", [])
        claim_titles = ", ".join(str(item.get("title") or item.get("issue")) for item in [*claims[:4], *issues[:4]] if item.get("title") or item.get("issue"))
        return {
            "client_or_team_summary": (
                "This is a neutral mediator preparation summary generated from indexed matter documents. "
                f"The available materials indicate issues requiring mediator clarification{': ' + claim_titles if claim_titles else ''}. "
                "The report does not decide merits, predict outcomes, or replace mediator judgment."
            )
        }
    if agent_id == "pleadings_and_claims_agent":
        return {"claims_and_defenses": tools.get("claim_defense_mapper", [])}
    if agent_id == "positions_interests_agent":
        return {
            "positions_and_interests": [
                {
                    "party": "Party to be confirmed",
                    "stated_positions": [item.get("title") for item in tools.get("claim_defense_mapper", [])[:6] if item.get("title")],
                    "possible_underlying_interests": ["Authority, cost, timing, certainty, confidentiality, relationship, and reputational interests require mediator clarification."],
                    "emotional_drivers": ["Possible frustration, distrust, or need for acknowledgment should be tested in caucus."],
                    "commercial_drivers": ["Cash flow, business continuity, and settlement finality require confirmation."],
                    "confidence_score": 0.35,
                    "inference_caveats": ["Interests are inferred from limited source material and must not be treated as findings."],
                }
            ]
        }
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
    if agent_id == "batna_watna_zopa_agent":
        return {
            "batna_watna_zopa": {
                "party_assessments": [],
                "possible_zopa": "Not enough supported valuation or authority information to state a range. Explore brackets, non-monetary terms, and risk-adjusted movement in caucus.",
                "settlement_range_considerations": tools.get("damages_extractor", {}).get("claimed_relief", []),
                "assumptions": ["Any settlement range requires party authority, valuation support, collectability, timing, and non-monetary terms."],
                "evidence_gaps": ["Confirm prior offers, authority limits, insurer involvement, payment capacity, and non-monetary interests."],
                "confidence_score": 0.3,
                "caveat": "This is mediator preparation only and not a valuation decision or settlement recommendation.",
            }
        }
    if agent_id == "risk_allocation_agent":
        return {
            "risk_allocation": [
                {
                    "risk": item.get("summary") or "Evidence and procedural assumptions require review.",
                    "allocation": "Unallocated pending mediator clarification",
                    "affected_parties": [],
                    "rationale": item.get("decision_point") or "The source set does not support a firm allocation.",
                    "uncertainty": "high",
                    "mediator_note": "Use caucus to test how each side prices this uncertainty.",
                }
                for item in tools.get("risks_and_gaps", [])[:10]
            ]
        }
    if agent_id == "settlement_levers_agent":
        return {
            "settlement_levers": [
                {"lever": "Payment timing or structure", "parties_affected": [], "why_it_may_matter": "Can bridge valuation and cash-flow constraints.", "possible_shapes": ["lump sum", "installments", "milestone payment"], "source_or_inference": "inference", "caveats": ["Confirm authority and payment capacity."]},
                {"lever": "Confidentiality", "parties_affected": [], "why_it_may_matter": "May address reputational or business concerns.", "possible_shapes": ["mutual confidentiality", "limited carve-outs"], "source_or_inference": "inference", "caveats": ["Check legal limits and existing orders."]},
                {"lever": "Non-monetary acknowledgment or apology", "parties_affected": [], "why_it_may_matter": "May address emotional or relationship interests.", "possible_shapes": ["statement of regret", "process commitment", "future communication protocol"], "source_or_inference": "inference", "caveats": ["Avoid admissions unless parties agree."]},
            ]
        }
    if agent_id == "cross_examination_agent":
        return {"cross_examination": tools.get("cross_exam_builder", [])}
    if agent_id == "caucus_impasse_agent":
        return {
            "caucus_questions": [
                {"party": "Each party", "question": "What would make today's process feel useful even if the matter does not settle today?", "purpose": "Surface interests and process needs.", "source_or_assumption": "mediator preparation inference", "sensitivity": "medium"},
                {"party": "Each party", "question": "What information would materially change your settlement position?", "purpose": "Identify information gaps and movement conditions.", "source_or_assumption": "mediator preparation inference", "sensitivity": "medium"},
                {"party": "Each party", "question": "What terms besides money would make resolution more workable?", "purpose": "Broaden the bargaining space.", "source_or_assumption": "mediator preparation inference", "sensitivity": "low"},
            ],
            "impasse_points": [
                {"issue": "Valuation gap", "why_it_may_block_settlement": "The record does not show aligned valuation or authority.", "early_warning_signs": ["anchored opening numbers", "refusal to bracket"], "mediator_options": ["reality-test risk", "use conditional brackets", "separate monetary and non-monetary terms"]},
                {"issue": "Trust or acknowledgment gap", "why_it_may_block_settlement": "Emotional or reputational needs may be hidden behind legal positions.", "early_warning_signs": ["repeated blame framing", "rejection of practical options"], "mediator_options": ["reframe interests", "test apology or process commitments"]},
            ],
        }
    if agent_id == "bridge_proposal_agent":
        return {
            "bridge_proposals": [
                {"label": "Conditional bracket", "structure": "Ask each side privately whether movement is possible if the other side enters a defined range.", "parties_helped": ["all parties"], "tradeoffs": ["Preserves face but may expose authority limits."], "prerequisites": ["private caucus authority check"], "risks": ["May fail if numbers are premature."], "neutrality_caveat": "A bridge proposal is process management, not a merits view."},
                {"label": "Term-sheet first", "structure": "Resolve non-monetary terms, confidentiality, timing, and releases before final number movement.", "parties_helped": ["all parties"], "tradeoffs": ["Broadens value but can delay money discussion."], "prerequisites": ["identify must-have terms"], "risks": ["May be seen as avoiding core valuation."], "neutrality_caveat": "Use only if both sides see value in package building."},
            ]
        }
    if agent_id == "private_prep_agent":
        return {
            "mediator_private_prep_note": {
                "opening_frame": "Set a neutral, practical tone: the report is preparation, not a decision on merits.",
                "watch_points": ["Unsupported assumptions", "valuation gap", "authority limits", "confidentiality constraints", "emotional drivers"],
                "caucus_priorities": ["Confirm decision-makers and authority", "Test interests beneath positions", "Identify missing information blocking movement"],
                "do_not_do": ["Do not decide the dispute", "Do not pressure a party into a specific outcome", "Do not treat inferred interests as facts"],
            },
            "one_page_session_plan": {
                "opening": "Confirm confidentiality, process, authority, agenda, and mediator neutrality.",
                "joint_session": ["Brief neutral issue framing", "Confirm any agreed facts", "Identify information gaps"],
                "first_caucus": ["Positions, interests, BATNA/WATNA, authority, emotional concerns"],
                "middle_game": ["Reality-test risks", "Explore levers", "Use brackets or package terms if appropriate"],
                "closing": ["Document settlement terms or next steps, owners, deadlines, and information exchanges"],
            },
        }
    if agent_id == "settlement_and_risk_agent":
        return {"risks_and_gaps": [{"risk_level": "medium", "summary": "Human lawyer review required for all strategy and risk assessments.", "leverage": None, "decision_point": "Review evidence gaps and procedural assumptions.", "requires_review": True}]}
    return {}
