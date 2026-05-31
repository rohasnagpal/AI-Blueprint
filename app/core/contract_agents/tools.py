import re
from typing import Any

from app.core.json_utils import json_loads
from app.core.models import ContractPlaybook, ContractPlaybookClause


SUPPORTED_TOOLS = {
    "targeted_document_retrieval",
    "playbook_lookup",
    "clause_evidence_verifier",
    "conflict_scan",
    "risk_scoring",
    "missing_clause_detector",
    "redline_fallback_lookup",
    "escalation_candidates",
    "audit_package_outline",
}


def build_default_tool_requests(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    clause_types = [item.get("clause", {}).get("clause_type") for item in workflow.get("clauses", [])]
    clause_types = [item for item in clause_types if item]
    priority_types = clause_types[:8] or ["termination", "limitation_of_liability", "indemnity", "governing_law"]
    return [
        {"tool": "targeted_document_retrieval", "query": " ".join(priority_types)},
        {"tool": "playbook_lookup", "clause_types": priority_types},
        {"tool": "clause_evidence_verifier"},
        {"tool": "conflict_scan"},
        {"tool": "missing_clause_detector"},
        {"tool": "redline_fallback_lookup", "clause_types": priority_types},
        {"tool": "escalation_candidates"},
        {"tool": "audit_package_outline"},
    ]


def run_contract_agent_tools(
    *,
    requests: list[dict[str, Any]] | None,
    source_bundle: list[dict[str, Any]],
    workflow: dict[str, Any],
    playbook: ContractPlaybook | None,
    playbook_clauses: list[ContractPlaybookClause],
) -> dict[str, Any]:
    normalized = _normalize_requests(requests) or build_default_tool_requests(workflow)
    results = []
    for request in normalized[:16]:
        tool = str(request.get("tool") or "").strip()
        if tool not in SUPPORTED_TOOLS:
            results.append({"tool": tool or "unknown", "status": "rejected", "error": "Unsupported contract agent tool."})
            continue
        results.append({"tool": tool, "status": "completed", "output": _run_tool(tool, request, source_bundle, workflow, playbook, playbook_clauses)})
    return {"tool_results": results, "supported_tools": sorted(SUPPORTED_TOOLS)}


def _run_tool(
    tool: str,
    request: dict[str, Any],
    source_bundle: list[dict[str, Any]],
    workflow: dict[str, Any],
    playbook: ContractPlaybook | None,
    playbook_clauses: list[ContractPlaybookClause],
) -> Any:
    if tool == "targeted_document_retrieval":
        return _targeted_document_retrieval(source_bundle, str(request.get("query") or ""), int(request.get("limit") or 8))
    if tool == "playbook_lookup":
        return _playbook_lookup(playbook, playbook_clauses, _requested_clause_types(request, workflow))
    if tool == "clause_evidence_verifier":
        return _clause_evidence_verifier(workflow, source_bundle)
    if tool == "conflict_scan":
        return _conflict_scan(workflow)
    if tool == "risk_scoring":
        return _risk_scoring(workflow)
    if tool == "missing_clause_detector":
        return _missing_clause_detector(workflow, playbook_clauses)
    if tool == "redline_fallback_lookup":
        return _redline_fallback_lookup(playbook_clauses, _requested_clause_types(request, workflow))
    if tool == "escalation_candidates":
        return _escalation_candidates(workflow)
    if tool == "audit_package_outline":
        return _audit_package_outline(workflow, playbook)
    return {}


def _normalize_requests(requests: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(requests, list):
        return []
    return [item for item in requests if isinstance(item, dict)]


def _requested_clause_types(request: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    values = request.get("clause_types")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        values = [item.get("clause", {}).get("clause_type") for item in workflow.get("clauses", [])]
    return [str(item) for item in values if item][:20]


def _targeted_document_retrieval(source_bundle: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    terms = [term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_/-]{2,}", query.lower()) if term not in {"and", "the", "for"}]
    scored = []
    for source in source_bundle:
        content = str(source.get("content") or "")
        lower = content.lower()
        score = sum(lower.count(term) for term in terms) if terms else 0
        if score:
            scored.append((score, source))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "score": score,
            "document_id": source.get("document_id"),
            "chunk_id": source.get("chunk_id"),
            "filename": source.get("filename"),
            "chunk_index": source.get("chunk_index"),
            "page": source.get("page"),
            "excerpt": str(source.get("content") or "")[:800],
        }
        for score, source in scored[: max(1, min(limit, 20))]
    ]


def _playbook_lookup(playbook: ContractPlaybook | None, playbook_clauses: list[ContractPlaybookClause], clause_types: list[str]) -> dict[str, Any]:
    wanted = set(clause_types)
    clauses = [clause for clause in playbook_clauses if not wanted or clause.clause_type in wanted]
    return {
        "playbook": {
            "id": playbook.id,
            "name": playbook.name,
            "contract_category": playbook.contract_category,
            "jurisdiction": playbook.jurisdiction,
            "rules": json_loads(playbook.rules_json, {}),
        } if playbook else None,
        "clauses": [_format_playbook_clause(clause) for clause in clauses[:30]],
    }


def _clause_evidence_verifier(workflow: dict[str, Any], source_bundle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_text = "\n\n".join(str(source.get("content") or "").lower() for source in source_bundle)
    findings = []
    for item in workflow.get("clauses", []):
        clause = item.get("clause") or {}
        text = str(clause.get("text") or "")
        excerpt = str((clause.get("source") or {}).get("excerpt") or "")
        needle = (excerpt or text[:160]).strip().lower()
        supported = bool(needle and needle in source_text)
        findings.append(
            {
                "clause_id": clause.get("id"),
                "clause_type": clause.get("clause_type"),
                "supported": supported,
                "evidence_excerpt": excerpt[:300],
                "confidence_score": 0.9 if supported else 0.35,
            }
        )
    return findings


def _conflict_scan(workflow: dict[str, Any]) -> dict[str, Any]:
    conflicts = [item for item in workflow.get("escalations", []) if (item.get("metadata") or {}).get("conflict_type")]
    return {"conflicts": conflicts, "count": len(conflicts)}


def _risk_scoring(workflow: dict[str, Any]) -> dict[str, Any]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in workflow.get("clauses", []):
        for risk in item.get("risks", []):
            level = risk.get("risk_level") or "low"
            counts[level] = counts.get(level, 0) + 1
    for risk in workflow.get("unattached_risk_findings", []):
        level = risk.get("risk_level") or "low"
        counts[level] = counts.get(level, 0) + 1
    return {"counts": counts, "review_needed": workflow.get("stats", {}).get("review_needed", 0)}


def _missing_clause_detector(workflow: dict[str, Any], playbook_clauses: list[ContractPlaybookClause]) -> list[dict[str, Any]]:
    extracted = {item.get("clause", {}).get("clause_type") for item in workflow.get("clauses", [])}
    return [
        {
            "playbook_clause_id": clause.id,
            "clause_type": clause.clause_type,
            "title": clause.title,
            "severity_default": clause.severity_default,
            "required": clause.required,
        }
        for clause in playbook_clauses
        if clause.required and clause.clause_type not in extracted
    ]


def _redline_fallback_lookup(playbook_clauses: list[ContractPlaybookClause], clause_types: list[str]) -> list[dict[str, Any]]:
    wanted = set(clause_types)
    return [
        {
            "playbook_clause_id": clause.id,
            "clause_type": clause.clause_type,
            "title": clause.title,
            "approved_text": clause.approved_text,
            "fallback_text": clause.fallback_text,
        }
        for clause in playbook_clauses
        if (not wanted or clause.clause_type in wanted) and (clause.fallback_text or clause.approved_text)
    ][:30]


def _escalation_candidates(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "clause_id": item.get("clause_id"),
            "severity": item.get("severity"),
            "reason": item.get("reason"),
            "required_action": item.get("required_action"),
        }
        for item in workflow.get("escalations", [])
    ]


def _audit_package_outline(workflow: dict[str, Any], playbook: ContractPlaybook | None) -> dict[str, Any]:
    return {
        "workflow_version": workflow.get("version"),
        "trace_steps": [step.get("step_name") for step in workflow.get("trace", [])],
        "playbook_id": playbook.id if playbook else None,
        "required_sections": [
            "source_documents",
            "deterministic_workflow_trace",
            "agent_tool_results",
            "agent_outputs",
            "quality_control",
            "final_outputs",
            "human_decisions",
        ],
    }


def _format_playbook_clause(clause: ContractPlaybookClause) -> dict[str, Any]:
    return {
        "id": clause.id,
        "clause_type": clause.clause_type,
        "title": clause.title,
        "approved_text": clause.approved_text,
        "fallback_text": clause.fallback_text,
        "prohibited_patterns": json_loads(clause.prohibited_patterns_json, []),
        "required": clause.required,
        "severity_default": clause.severity_default,
        "metadata": json_loads(clause.metadata_json, {}),
    }
