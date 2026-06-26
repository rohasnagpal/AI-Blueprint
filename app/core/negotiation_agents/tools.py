import re
from collections import Counter
from typing import Any


SUPPORTED_TOOLS = {
    "targeted_document_retrieval",
    "evidence_anchor_verifier",
    "chronology_builder",
    "claim_defense_mapper",
    "issue_evidence_mapper",
    "witness_mapper",
    "deposition_outline_builder",
    "exhibit_index_tool",
    "contradiction_detector",
    "procedural_deadline_tool",
    "discovery_gap_analyzer",
    "damages_extractor",
    "privilege_sensitivity_scanner",
    "motion_argument_outline_tool",
    "trial_theme_builder",
    "cross_exam_builder",
    "negotiation_audit_package_tool",
}


def build_default_tool_requests(run_context: dict[str, Any]) -> list[dict[str, Any]]:
    terms = [
        run_context.get("party_role"),
        run_context.get("court"),
        run_context.get("jurisdiction"),
        run_context.get("procedural_stage"),
        "claims defenses positions negotiation settlement authority caucus damages",
    ]
    query = " ".join(str(term) for term in terms if term)
    return [
        {"tool": "targeted_document_retrieval", "query": query},
        {"tool": "chronology_builder"},
        {"tool": "claim_defense_mapper"},
        {"tool": "issue_evidence_mapper"},
        {"tool": "witness_mapper"},
        {"tool": "deposition_outline_builder"},
        {"tool": "exhibit_index_tool"},
        {"tool": "contradiction_detector"},
        {"tool": "procedural_deadline_tool"},
        {"tool": "discovery_gap_analyzer"},
        {"tool": "damages_extractor"},
        {"tool": "privilege_sensitivity_scanner"},
        {"tool": "motion_argument_outline_tool"},
        {"tool": "trial_theme_builder"},
        {"tool": "cross_exam_builder"},
        {"tool": "evidence_anchor_verifier"},
        {"tool": "negotiation_audit_package_tool"},
    ]


def run_negotiation_agent_tools(
    *,
    requests: list[dict[str, Any]] | None,
    source_bundle: list[dict[str, Any]],
    run_context: dict[str, Any],
    existing_outputs: dict[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_requests(requests) or build_default_tool_requests(run_context)
    results = []
    for request in normalized[:20]:
        tool = str(request.get("tool") or "").strip()
        if tool not in SUPPORTED_TOOLS:
            results.append({"tool": tool or "unknown", "status": "rejected", "error": "Unsupported negotiation agent tool."})
            continue
        results.append({"tool": tool, "status": "completed", "output": _run_tool(tool, request, source_bundle, run_context, existing_outputs)})
    return {"tool_results": results, "supported_tools": sorted(SUPPORTED_TOOLS)}


def _run_tool(tool: str, request: dict[str, Any], source_bundle: list[dict[str, Any]], run_context: dict[str, Any], existing_outputs: dict[str, Any]) -> Any:
    if tool == "targeted_document_retrieval":
        return _targeted_document_retrieval(source_bundle, str(request.get("query") or ""), int(request.get("limit") or 12))
    if tool == "evidence_anchor_verifier":
        return _evidence_anchor_verifier(source_bundle, existing_outputs)
    if tool == "chronology_builder":
        return _chronology_builder(source_bundle)
    if tool == "claim_defense_mapper":
        return _claim_defense_mapper(source_bundle)
    if tool == "issue_evidence_mapper":
        return _issue_evidence_mapper(source_bundle, existing_outputs)
    if tool == "witness_mapper":
        return _witness_mapper(source_bundle)
    if tool == "deposition_outline_builder":
        return _deposition_outline_builder(existing_outputs)
    if tool == "exhibit_index_tool":
        return _exhibit_index_tool(source_bundle)
    if tool == "contradiction_detector":
        return _contradiction_detector(source_bundle)
    if tool == "procedural_deadline_tool":
        return _procedural_deadline_tool(source_bundle, run_context)
    if tool == "discovery_gap_analyzer":
        return _discovery_gap_analyzer(source_bundle)
    if tool == "damages_extractor":
        return _damages_extractor(source_bundle)
    if tool == "privilege_sensitivity_scanner":
        return _privilege_sensitivity_scanner(source_bundle)
    if tool == "motion_argument_outline_tool":
        return _motion_argument_outline_tool(run_context, existing_outputs)
    if tool == "trial_theme_builder":
        return _trial_theme_builder(existing_outputs)
    if tool == "cross_exam_builder":
        return _cross_exam_builder(existing_outputs)
    if tool == "negotiation_audit_package_tool":
        return _negotiation_audit_package_tool(source_bundle, run_context, existing_outputs)
    return {}


def _normalize_requests(requests: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(requests, list):
        return []
    return [item for item in requests if isinstance(item, dict)]


def _targeted_document_retrieval(source_bundle: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    terms = [term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_/-]{2,}", query.lower()) if term not in {"and", "the", "for", "with"}]
    scored = []
    for source in source_bundle:
        content = str(source.get("content") or "")
        lower = content.lower()
        score = sum(lower.count(term) for term in terms) if terms else 1
        if score:
            scored.append((score, source))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [_source_result(source, score) for score, source in scored[: max(1, min(limit, 30))]]


def _evidence_anchor_verifier(source_bundle: list[dict[str, Any]], existing_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    source_text = "\n\n".join(str(source.get("content") or "") for source in source_bundle).lower()
    citations = _collect_citations(existing_outputs)
    if not citations:
        citations = [_source_result(source, 1) for source in source_bundle[:10]]
    verified = []
    for citation in citations[:60]:
        excerpt = str(citation.get("excerpt") or citation.get("anchor_text") or citation.get("summary") or "")
        supported = bool(excerpt and excerpt[:180].lower() in source_text)
        verified.append({**citation, "supported": supported, "confidence_score": 0.9 if supported else 0.25})
    return verified


def _chronology_builder(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    date_pattern = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|20\d{2}-\d{2}-\d{2})\b", re.I)
    for source in source_bundle:
        content = str(source.get("content") or "")
        for match in date_pattern.finditer(content):
            start = max(0, match.start() - 180)
            end = min(len(content), match.end() + 220)
            events.append({
                "date": match.group(0),
                "description": content[start:end].strip(),
                "relevance": "Potential negotiation chronology event requiring lawyer review.",
                "source": _source_anchor(source, content[start:end].strip()),
                "confidence_score": 0.72,
            })
    return events[:80]


def _issue_evidence_mapper(source_bundle: list[dict[str, Any]], existing_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    issue_terms = ["breach", "termination", "payment", "delay", "defect", "notice", "damages", "jurisdiction", "liability", "performance"]
    mapped = []
    for term in issue_terms:
        matches = _targeted_document_retrieval(source_bundle, term, 4)
        if matches:
            mapped.append({"issue": term, "supporting_evidence": matches[:2], "adverse_evidence": matches[2:4], "gaps": ["Confirm proof elements and burden with counsel."]})
    agent_issues = existing_outputs.get("issues_and_elements_agent", {}).get("issues")
    if isinstance(agent_issues, list):
        for issue in agent_issues[:10]:
            title = str(issue.get("title") or issue.get("issue") or "")
            if title:
                mapped.append({"issue": title, "supporting_evidence": _targeted_document_retrieval(source_bundle, title, 3), "adverse_evidence": [], "gaps": issue.get("missing_proof") or []})
    return mapped[:30]


def _claim_defense_mapper(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = ["breach", "payment", "damages", "defense", "counterclaim", "settlement", "authority", "negotiation"]
    claims = []
    for term in terms:
        matches = _targeted_document_retrieval(source_bundle, term, 3)
        if matches:
            claims.append({
                "claim_type": "defense" if "defense" in term else "claim",
                "title": term,
                "elements": [],
                "defenses": [],
                "admissions": [],
                "missing_proof": ["Confirm position, support, authority, and negotiation relevance with counsel."],
                "source": matches[0],
                "confidence_score": 0.55,
            })
    return claims[:30]


def _witness_mapper(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: Counter[str] = Counter()
    first_anchor: dict[str, dict[str, Any]] = {}
    for source in source_bundle:
        content = str(source.get("content") or "")
        for name in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", content):
            if name in {"United States", "Confidential", "Hong Kong"}:
                continue
            names[name] += 1
            first_anchor.setdefault(name, _source_anchor(source, content[:500]))
    return [
        {
            "name": name,
            "role": "Mentioned in source material; role requires lawyer review.",
            "topics": ["Facts connected to cited documents"],
            "admissions": [],
            "contradictions": [],
            "exhibit_references": [first_anchor[name]],
            "prep_questions": [f"Confirm {name}'s role, authority, knowledge, and negotiation talking points."],
            "confidence_score": min(0.85, 0.45 + count / 10),
        }
        for name, count in names.most_common(20)
    ]


def _deposition_outline_builder(existing_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    witnesses = existing_outputs.get("witness_prep_agent", {}).get("witness_prep") or []
    return [
        {
            "witness": item.get("name") or "Witness",
            "topics": item.get("topics") or ["Source-backed factual knowledge"],
            "questions": item.get("prep_questions") or ["Confirm role, documents reviewed, and relevant events."],
            "anchors": item.get("exhibit_references") or [],
            "caveats": ["Deposition outline is a preparation aid and requires lawyer review."],
        }
        for item in witnesses[:20]
    ]


def _exhibit_index_tool(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": source.get("document_id"),
            "filename": source.get("filename"),
            "document_type": _document_type(source),
            "date": _first_date(str(source.get("content") or "")),
            "author": None,
            "recipient": None,
            "relevance": "Indexed matter source for negotiation preparation.",
            "cited_issues": [],
            "source": _source_anchor(source, str(source.get("content") or "")[:500]),
        }
        for source in source_bundle[:80]
    ]


def _contradiction_detector(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    amounts: dict[str, list[dict[str, Any]]] = {}
    for source in source_bundle:
        content = str(source.get("content") or "")
        for amount in re.findall(r"(?:USD|INR|EUR|GBP|\$|₹|€|£)\s?\d[\d,]*(?:\.\d+)?", content, re.I):
            amounts.setdefault(amount.lower(), []).append(_source_anchor(source, content[:500]))
    if len(amounts) <= 1:
        return []
    return [{"type": "amount", "summary": "Multiple monetary figures appear in the source set; verify whether they conflict or refer to different claims.", "values": list(amounts.keys())[:20], "anchors": [items[0] for items in amounts.values()]}]


def _procedural_deadline_tool(source_bundle: list[dict[str, Any]], run_context: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = []
    keywords = ("deadline", "negotiation", "statement", "brief", "attendance", "authority", "confidential", "submission", "calendar")
    for source in source_bundle:
        content = str(source.get("content") or "")
        if any(word in content.lower() for word in keywords):
            tasks.append({"task_type": "negotiation_logistics", "description": content[:700], "due_date": _first_date(content), "compliance_risk": "Requires lawyer confirmation against negotiation order, protocol, or provider rules.", "source": _source_anchor(source, content[:700]), "confidence_score": 0.68})
    for value in run_context.get("hearing_dates") or []:
        tasks.append({"task_type": "negotiation_date", "description": f"User-provided negotiation/deadline date: {value}", "due_date": value, "compliance_risk": "User-provided date; verify against negotiation notice, protocol, or order.", "source": None, "confidence_score": 0.7})
    return tasks[:60]


def _damages_extractor(source_bundle: list[dict[str, Any]]) -> dict[str, Any]:
    findings = []
    for source in source_bundle:
        content = str(source.get("content") or "")
        if re.search(r"\b(damages|loss|invoice|mitigation|interest|costs|relief)\b", content, re.I):
            amounts = re.findall(r"(?:USD|INR|EUR|GBP|\$|₹|€|£)\s?\d[\d,]*(?:\.\d+)?", content, re.I)
            findings.append({"amounts": amounts, "excerpt": content[:800], "source": _source_anchor(source, content[:800])})
    return {"claimed_relief": findings[:20], "damages_theories": [], "mitigation": [], "interest": [], "costs": [], "gaps": ["Verify calculations and admissible damages evidence."]}


def _discovery_gap_analyzer(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    keywords = ("information", "documents", "valuation", "expert", "insurance", "authority", "settlement", "negotiation", "production")
    for source in source_bundle:
        content = str(source.get("content") or "")
        lower = content.lower()
        if any(keyword in lower for keyword in keywords):
            findings.append({
                "item_type": "discovery",
                "description": content[:800],
                "status": "requires_review",
                "source": _source_anchor(source, content[:800]),
                "confidence_score": 0.66,
            })
    if not findings:
        findings.append({"item_type": "gap", "description": "No negotiation information-exchange materials were detected in the indexed source set.", "status": "requires_review", "confidence_score": 0.45})
    return findings[:60]


def _privilege_sensitivity_scanner(source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags = []
    patterns = {"privileged": r"\b(privileged|attorney-client|legal advice|without prejudice)\b", "confidential": r"\b(confidential|secret|restricted)\b", "settlement": r"\b(settlement|settle|without prejudice)\b", "sensitive": r"\b(personal data|passport|bank account|medical)\b"}
    for source in source_bundle:
        content = str(source.get("content") or "")
        for kind, pattern in patterns.items():
            if re.search(pattern, content, re.I):
                flags.append({"type": kind, "summary": f"Potential {kind} material detected.", "source": _source_anchor(source, content[:700]), "requires_review": True})
    return flags[:80]


def _motion_argument_outline_tool(run_context: dict[str, Any], existing_outputs: dict[str, Any]) -> dict[str, Any]:
    role = run_context.get("party_role") or "neutral analysis"
    matrix = existing_outputs.get("evidence_matrix_agent", {}).get("evidence_matrix") or []
    return {"party_role": role, "motions": [{"title": "Negotiation position theme", "points": [str(item.get("issue") or item.get("element") or "Issue") for item in matrix[:8]], "vulnerabilities": ["Verify negotiation confidentiality, authority, and evidentiary support."], "caveat": "Negotiation position themes are preparation prompts, not legal advice, settlement recommendations, or outcome predictions."}]}


def _trial_theme_builder(existing_outputs: dict[str, Any]) -> dict[str, Any]:
    matrix = existing_outputs.get("evidence_matrix_agent", {}).get("evidence_matrix") or []
    witnesses = existing_outputs.get("witness_prep_agent", {}).get("witness_prep") or []
    return {
        "themes": [str(item.get("issue") or "Issue") for item in matrix[:8]],
        "participant_considerations": [item.get("name") for item in witnesses[:8] if item.get("name")],
        "exhibit_groups": [],
        "caucus_topics": [],
        "caveat": "Negotiation session plan outputs require lawyer review and do not predict outcomes.",
    }


def _cross_exam_builder(existing_outputs: dict[str, Any]) -> list[dict[str, Any]]:
    witnesses = existing_outputs.get("witness_prep_agent", {}).get("witness_prep") or []
    return [{"witness": item.get("name") or "Witness", "topics": item.get("topics") or [], "questions": item.get("prep_questions") or ["Confirm source-backed facts and address contradictions."], "anchors": item.get("exhibit_references") or []} for item in witnesses[:20]]


def _negotiation_audit_package_tool(source_bundle: list[dict[str, Any]], run_context: dict[str, Any], existing_outputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_documents": [{"document_id": source.get("document_id"), "filename": source.get("filename"), "chunk_id": source.get("chunk_id")} for source in source_bundle[:120]],
        "agent_trace_keys": list(existing_outputs.keys()),
        "run_context": run_context,
        "required_sections": ["source_evidence", "agent_trace", "tool_outputs", "final_outputs", "human_review_decisions"],
    }


def _collect_citations(value: Any) -> list[dict[str, Any]]:
    citations = []
    if isinstance(value, dict):
        if any(key in value for key in ["document_id", "chunk_id", "excerpt", "anchor_text"]):
            citations.append(value)
        for item in value.values():
            citations.extend(_collect_citations(item))
    elif isinstance(value, list):
        for item in value:
            citations.extend(_collect_citations(item))
    return citations


def _source_result(source: dict[str, Any], score: int | float) -> dict[str, Any]:
    content = str(source.get("content") or "")
    return {**_source_anchor(source, content[:900]), "score": score}


def _source_anchor(source: dict[str, Any], excerpt: str) -> dict[str, Any]:
    return {
        "document_id": source.get("document_id"),
        "chunk_id": source.get("chunk_id"),
        "filename": source.get("filename"),
        "chunk_index": source.get("chunk_index"),
        "page": source.get("page"),
        "start_offset": source.get("start_offset"),
        "end_offset": source.get("end_offset"),
        "excerpt": excerpt[:900],
    }


def _document_type(source: dict[str, Any]) -> str:
    name = str(source.get("filename") or "").lower()
    if "order" in name:
        return "procedural_order"
    if "witness" in name:
        return "witness_material"
    if "exhibit" in name:
        return "exhibit"
    if "claim" in name or "pleading" in name:
        return "pleading"
    return "source_document"


def _first_date(content: str) -> str | None:
    match = re.search(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}|20\d{2}-\d{2}-\d{2})\b", content, re.I)
    return match.group(0) if match else None
