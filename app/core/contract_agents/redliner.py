from app.core.contract_agents.schemas import RedlineSuggestionResult, RiskFindingResult
from app.core.models import ContractClause, ContractPlaybookClause


def suggest_redlines(
    clauses: list[ContractClause],
    risks: list[RiskFindingResult],
    playbook_clauses: list[ContractPlaybookClause] | None = None,
) -> list[RedlineSuggestionResult]:
    clauses_by_id = {clause.id: clause for clause in clauses}
    playbook_by_type = {clause.clause_type: clause for clause in playbook_clauses or []}
    suggestions = []
    for risk in risks:
        if risk.risk_level not in {"high", "critical"} or not risk.clause_id:
            continue
        clause = clauses_by_id.get(risk.clause_id)
        if not clause:
            continue
        playbook_clause = playbook_by_type.get(clause.clause_type)
        fallback = playbook_clause.fallback_text if playbook_clause and playbook_clause.fallback_text else "Use the organization's approved fallback language for this clause type before external delivery."
        standard = playbook_clause.approved_text if playbook_clause and playbook_clause.approved_text else "the applicable playbook"
        suggestions.append(
            RedlineSuggestionResult(
                clause_id=clause.id,
                suggestion_text=f"Revise the {clause.clause_type.replace('_', ' ')} clause to align with {standard} and remove the flagged risk.",
                fallback_language=fallback,
                rationale=risk.reasoning,
                confidence_score=0.68 if playbook_clause and playbook_clause.fallback_text else 0.55,
            )
        )
    return suggestions
