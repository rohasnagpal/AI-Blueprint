from app.core.contract_agents.schemas import EscalationResult, RiskFindingResult


def detect_escalations(risks: list[RiskFindingResult]) -> list[EscalationResult]:
    escalations = []
    for risk in risks:
        if risk.risk_level not in {"high", "critical"}:
            continue
        escalations.append(
            EscalationResult(
                clause_id=risk.clause_id,
                severity=risk.risk_level,
                reason=f"{risk.clause_type.replace('_', ' ').title()}: {risk.reasoning}",
                required_action="Human lawyer review required before external delivery.",
                metadata={"clause_type": risk.clause_type, "risk_level": risk.risk_level},
            )
        )
    return escalations
