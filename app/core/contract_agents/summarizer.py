from app.core.contract_agents.schemas import IntakeResult, RiskFindingResult, SummaryResult
from app.core.models import ContractClause


def build_summaries(intake: IntakeResult, clauses: list[ContractClause], risks: list[RiskFindingResult]) -> list[SummaryResult]:
    high_risks = [risk for risk in risks if risk.risk_level in {"high", "critical"}]
    review_count = sum(1 for risk in risks if risk.requires_review)
    clause_types = sorted({clause.clause_type.replace("_", " ") for clause in clauses})
    negotiation_points = [risk.reasoning for risk in high_risks[:8]]
    base = (
        f"{intake.contract_type} review found {len(clauses)} extracted clause area(s) "
        f"and {review_count} issue(s) requiring human review."
    )
    return [
        SummaryResult(
            audience="lawyer",
            summary_text=f"{base} Key clause areas: {', '.join(clause_types) if clause_types else 'none extracted'}.",
            negotiation_points=negotiation_points,
            unusual_terms=[risk.reasoning for risk in risks if risk.risk_level == "critical"],
        ),
        SummaryResult(
            audience="business",
            summary_text=f"{base} Focus first on high and critical items before negotiation.",
            negotiation_points=negotiation_points[:5],
        ),
        SummaryResult(
            audience="client",
            summary_text=f"The contract has been reviewed as an AI-assisted draft. A lawyer should review all flagged issues before advice is delivered.",
            negotiation_points=negotiation_points[:5],
        ),
    ]
