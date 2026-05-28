import json

from app.core.contract_agents.schemas import PlaybookFindingResult
from app.core.json_utils import json_loads
from app.core.models import ContractClause, ContractPlaybookClause


def compare_to_playbook(clauses: list[ContractClause], playbook_clauses: list[ContractPlaybookClause]) -> list[PlaybookFindingResult]:
    findings: list[PlaybookFindingResult] = []
    clauses_by_type = {clause.clause_type: clause for clause in clauses}
    playbook_by_type = {item.clause_type: item for item in playbook_clauses}

    for clause in clauses:
        playbook_clause = playbook_by_type.get(clause.clause_type)
        if not playbook_clause:
            findings.append(
                PlaybookFindingResult(
                    clause_id=clause.id,
                    clause_type=clause.clause_type,
                    status="not_in_playbook",
                    deviation_summary="No matching playbook standard exists for this clause type.",
                    confidence_score=0.8,
                )
            )
            continue
        prohibited_match = _first_prohibited_match(clause.text, playbook_clause)
        status = "prohibited" if prohibited_match else "no_prohibited_match"
        findings.append(
            PlaybookFindingResult(
                clause_id=clause.id,
                clause_type=clause.clause_type,
                playbook_clause_id=playbook_clause.id,
                status=status,
                deviation_summary="Potential prohibited language found." if prohibited_match else "No prohibited language found by deterministic check; semantic alignment still requires review.",
                prohibited_match=prohibited_match,
                confidence_score=0.82,
            )
        )

    for playbook_clause in playbook_clauses:
        if playbook_clause.required and playbook_clause.clause_type not in clauses_by_type:
            findings.append(
                PlaybookFindingResult(
                    clause_type=playbook_clause.clause_type,
                    playbook_clause_id=playbook_clause.id,
                    status="missing",
                    deviation_summary=f"Required clause missing: {playbook_clause.title}.",
                    missing=True,
                    confidence_score=0.9,
                )
            )
    return findings


def _first_prohibited_match(text: str, playbook_clause: ContractPlaybookClause) -> str | None:
    lower = text.lower()
    patterns = json_loads(playbook_clause.prohibited_patterns_json, [])
    if not isinstance(patterns, list):
        patterns = []
    for pattern in patterns:
        value = str(pattern).lower().strip()
        if value and value in lower:
            return str(pattern)
    return None
