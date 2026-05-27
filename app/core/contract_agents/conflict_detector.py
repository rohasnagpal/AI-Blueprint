import re

from app.core.contract_agents.schemas import EscalationResult
from app.core.models import ContractClause


UNIQUE_CLAUSE_TYPES = {"governing_law", "dispute_resolution"}


def detect_conflicts(clauses: list[ContractClause]) -> list[EscalationResult]:
    conflicts: list[EscalationResult] = []
    by_type: dict[str, list[ContractClause]] = {}
    for clause in clauses:
        by_type.setdefault(clause.clause_type, []).append(clause)

    for clause_type in UNIQUE_CLAUSE_TYPES:
        candidates = by_type.get(clause_type, [])
        if len(candidates) > 1 and _has_material_variance(candidates):
            conflicts.append(
                EscalationResult(
                    clause_id=candidates[0].id,
                    severity="high",
                    reason=f"Potential conflicting {clause_type.replace('_', ' ')} provisions found in multiple clauses.",
                    required_action="Human lawyer must reconcile the conflicting provisions before review completion.",
                    metadata={"conflict_type": "duplicate_unique_clause", "clause_type": clause_type, "clause_ids": [item.id for item in candidates]},
                )
            )

    termination_clauses = by_type.get("termination", [])
    if termination_clauses and _has_termination_conflict(termination_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=termination_clauses[0].id,
                severity="high",
                reason="Termination provisions may conflict on convenience termination or breach cure rights.",
                required_action="Human lawyer must confirm the intended termination rights and cure periods.",
                metadata={"conflict_type": "termination_terms", "clause_type": "termination", "clause_ids": [item.id for item in termination_clauses]},
            )
        )
    payment_clauses = by_type.get("payment", [])
    if payment_clauses and _has_payment_timing_conflict(payment_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=payment_clauses[0].id,
                severity="medium",
                reason="Payment provisions appear to use inconsistent invoice due dates.",
                required_action="Human lawyer must confirm the intended payment period before relying on the workflow output.",
                metadata={"conflict_type": "payment_timing", "clause_type": "payment", "clause_ids": [item.id for item in payment_clauses]},
            )
        )

    ip_clauses = by_type.get("ip", [])
    if ip_clauses and _has_ip_ownership_conflict(ip_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=ip_clauses[0].id,
                severity="high",
                reason="IP provisions appear to conflict on whether work product is assigned to the customer or retained by the provider.",
                required_action="Human lawyer must reconcile IP ownership, license, and assignment language.",
                metadata={"conflict_type": "ip_ownership", "clause_type": "ip", "clause_ids": [item.id for item in ip_clauses]},
            )
        )

    liability_clauses = by_type.get("limitation_of_liability", [])
    if liability_clauses and _has_liability_carveout_conflict(liability_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=liability_clauses[0].id,
                severity="high",
                reason="Limitation of liability provisions appear to conflict on whether indemnity, confidentiality, or IP claims are capped.",
                required_action="Human lawyer must confirm the intended liability cap and carve-outs.",
                metadata={"conflict_type": "liability_carveouts", "clause_type": "limitation_of_liability", "clause_ids": [item.id for item in liability_clauses]},
            )
        )

    breach_notice_clauses = by_type.get("data_breach_notice", [])
    if breach_notice_clauses and _has_breach_notice_timing_conflict(breach_notice_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=breach_notice_clauses[0].id,
                severity="high",
                reason="Data breach notice provisions appear to use inconsistent notification deadlines.",
                required_action="Human lawyer must confirm the required incident notification deadline.",
                metadata={"conflict_type": "data_breach_notice_timing", "clause_type": "data_breach_notice", "clause_ids": [item.id for item in breach_notice_clauses]},
            )
        )

    indemnity_clauses = by_type.get("indemnity", [])
    if indemnity_clauses and _has_indemnity_scope_conflict(indemnity_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=indemnity_clauses[0].id,
                severity="high",
                reason="Indemnity provisions appear to conflict on whether indemnity is mutual or one-way.",
                required_action="Human lawyer must confirm the intended indemnity scope.",
                metadata={"conflict_type": "indemnity_scope", "clause_type": "indemnity", "clause_ids": [item.id for item in indemnity_clauses]},
            )
        )

    term_clauses = termination_clauses + by_type.get("payment", [])
    if term_clauses and _has_renewal_conflict(term_clauses):
        conflicts.append(
            EscalationResult(
                clause_id=term_clauses[0].id,
                severity="medium",
                reason="Term or renewal provisions appear to conflict on automatic renewal.",
                required_action="Human lawyer must confirm whether renewal is automatic, optional, or requires a signed amendment.",
                metadata={"conflict_type": "renewal_terms", "clause_type": "termination", "clause_ids": [item.id for item in term_clauses]},
            )
        )
    return conflicts


def _has_material_variance(clauses: list[ContractClause]) -> bool:
    normalized = {_normalize(clause.text) for clause in clauses}
    return len(normalized) > 1


def _has_termination_conflict(clauses: list[ContractClause]) -> bool:
    texts = [clause.text.lower() for clause in clauses]
    mentions_convenience = [("convenience" in text) for text in texts]
    cure_periods = {_first_cure_period(text) for text in texts if _first_cure_period(text)}
    return (any(mentions_convenience) and not all(mentions_convenience)) or len(cure_periods) > 1


def _first_cure_period(text: str) -> str | None:
    match = re.search(r"(\d{1,3})\s+days?", text)
    return match.group(1) if match else None


def _has_payment_timing_conflict(clauses: list[ContractClause]) -> bool:
    periods = {_first_payment_period(clause.text.lower()) for clause in clauses if _first_payment_period(clause.text.lower())}
    return len(periods) > 1


def _first_payment_period(text: str) -> str | None:
    match = re.search(r"(?:net|within|due\s+within|payable\s+within)\s+(\d{1,3})\s+days?", text)
    return match.group(1) if match else None


def _has_ip_ownership_conflict(clauses: list[ContractClause]) -> bool:
    texts = [clause.text.lower() for clause in clauses]
    customer_owns = any(re.search(r"(customer|client|company)\s+(?:owns|shall own|will own)|assign(?:s|ed)?\s+to\s+(?:customer|client|company)", text) for text in texts)
    provider_retains = any(re.search(r"(provider|vendor|contractor|supplier)\s+(?:retains|owns|shall own|will own)", text) for text in texts)
    return customer_owns and provider_retains


def _has_liability_carveout_conflict(clauses: list[ContractClause]) -> bool:
    texts = [clause.text.lower() for clause in clauses]
    cap_applies_to_all = any(re.search(r"(?:all|any)\s+(?:claims|liability|damages).*?(?:subject to|capped at|limited to)", text) for text in texts)
    has_carveout = any(re.search(r"(?:except|excluding|does not apply|shall not apply).*?(?:indemn|confidential|ip|intellectual property)", text) for text in texts)
    no_carveout = any(re.search(r"(?:no|without)\s+(?:exceptions|carve-?outs)", text) for text in texts)
    return (cap_applies_to_all and has_carveout) or (has_carveout and no_carveout)


def _has_breach_notice_timing_conflict(clauses: list[ContractClause]) -> bool:
    deadlines = {_first_notice_deadline(clause.text.lower()) for clause in clauses if _first_notice_deadline(clause.text.lower())}
    return len(deadlines) > 1


def _first_notice_deadline(text: str) -> str | None:
    immediate = re.search(r"\b(?:immediately|without undue delay|as soon as practicable)\b", text)
    if immediate:
        return "immediate"
    match = re.search(r"(\d{1,3})\s+(hours?|days?)", text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    return str(value if unit.startswith("hour") else value * 24)


def _has_indemnity_scope_conflict(clauses: list[ContractClause]) -> bool:
    texts = [clause.text.lower() for clause in clauses]
    mutual = any(re.search(r"\bmutual(?:ly)?\b|each party shall indemnify|both parties shall indemnify", text) for text in texts)
    one_way = any(re.search(r"only\s+(?:provider|vendor|supplier|contractor|customer|client|company)\s+shall indemnify|(?:provider|vendor|supplier|contractor|customer|client|company)\s+shall indemnify.*\bonly\b", text) for text in texts)
    return mutual and one_way


def _has_renewal_conflict(clauses: list[ContractClause]) -> bool:
    texts = [clause.text.lower() for clause in clauses]
    automatic = any(re.search(r"auto(?:matically)?\s+renew|automatic renewal|renews automatically", text) for text in texts)
    manual = any(re.search(r"will not renew|shall not renew|no automatic renewal|renewal requires|signed amendment", text) for text in texts)
    return automatic and manual


def _normalize(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").lower())
