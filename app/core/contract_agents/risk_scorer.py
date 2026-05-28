from app.core.contract_agents.schemas import PlaybookFindingResult, RiskFindingResult


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def score_risks(findings: list[PlaybookFindingResult]) -> list[RiskFindingResult]:
    risks = []
    for finding in findings:
        if finding.status == "prohibited":
            level = "critical"
            reasoning = f"Clause appears to contain prohibited language: {finding.prohibited_match}."
        elif finding.status == "missing":
            level = "high"
            reasoning = finding.deviation_summary or "Required playbook protection appears to be missing."
        elif finding.status == "not_in_playbook":
            level = "medium"
            reasoning = "Clause was extracted but has no matching playbook standard."
        elif finding.status in {"approved", "no_prohibited_match"}:
            level = "low"
            reasoning = finding.deviation_summary or "No deterministic playbook issue found."
        else:
            level = "low"
            reasoning = "No deterministic playbook issue found."
        risks.append(
            RiskFindingResult(
                clause_id=finding.clause_id,
                clause_type=finding.clause_type,
                risk_level=level,
                likelihood="possible" if level in {"medium", "high"} else None,
                impact="material" if level in {"high", "critical"} else None,
                priority=RISK_ORDER[level],
                reasoning=reasoning,
                requires_review=level in {"medium", "high", "critical"},
                confidence_score=finding.confidence_score,
            )
        )
    return risks
