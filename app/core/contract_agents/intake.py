import re

from app.core.contract_agents.schemas import IntakeResult


def run_intake(text: str) -> IntakeResult:
    lower = text.lower()
    category = "general"
    contract_type = "Contract"
    if (
        "master services" in lower
        or "services agreement" in lower
        or "supply agreement" in lower
        or "supplier agreement" in lower
        or "vendor agreement" in lower
        or "purchase agreement" in lower
        or "purchase order terms" in lower
    ):
        category = "msa"
        contract_type = "Supply/Vendor Agreement" if "supply" in lower or "supplier" in lower else "MSA/Vendor Agreement"
    elif "data processing agreement" in lower or "data protection addendum" in lower or ("processor" in lower and "controller" in lower):
        category = "dpa"
        contract_type = "Data Processing Agreement"
    elif "statement of work" in lower or re.search(r"\bsow\b", lower):
        category = "sow"
        contract_type = "Statement of Work"
    elif "software as a service" in lower or "saas" in lower or "subscription agreement" in lower:
        category = "saas"
        contract_type = "SaaS Subscription Agreement"
    elif "consulting agreement" in lower or "professional services agreement" in lower or "consulting services" in lower:
        category = "consulting"
        contract_type = "Consulting Services Agreement"
    elif "reseller agreement" in lower or "channel partner" in lower or "authorized reseller" in lower:
        category = "reseller"
        contract_type = "Reseller Agreement"
    elif "non-disclosure" in lower or "confidentiality agreement" in lower or "nda" in lower:
        category = "nda"
        contract_type = "Non-Disclosure Agreement"

    parties = _extract_parties(text)
    dates = re.findall(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+ \d{1,2}, \d{4})\b", text)[:8]
    governing_law = _extract_governing_law(text)
    confidence = _classification_confidence(lower, category, parties, governing_law)
    return IntakeResult(
        contract_type=contract_type,
        contract_category=category,
        parties=parties,
        dates=dates,
        governing_law=governing_law,
        confidence_score=confidence,
        routing_notes=f"Selected {category} review route.",
    )


def _extract_parties(text: str) -> list[str]:
    patterns = [
        r"between\s+(.{2,120}?)\s+and\s+(.{2,120}?)(?:\.|,|\n)",
        r"by\s+and\s+between\s+(.{2,120}?)\s+and\s+(.{2,120}?)(?:\.|,|\n)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return [_clean_party(match.group(1)), _clean_party(match.group(2))]
    return []


def _extract_governing_law(text: str) -> str | None:
    match = re.search(r"governed by (?:and construed in accordance with )?the laws of ([A-Za-z ,]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip(" .")[:100] if match else None


def _clean_party(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,.;")


def _classification_confidence(lower: str, category: str, parties: list[str], governing_law: str | None) -> float:
    if category == "general":
        return 0.5 if parties or governing_law else 0.42
    score = 0.68
    if parties:
        score += 0.05
    if governing_law:
        score += 0.03
    if category in {"nda", "dpa", "sow"}:
        score += 0.06
    if category == "dpa" and ("data processing agreement" in lower or "data protection addendum" in lower):
        score += 0.04
    if category in {"saas", "consulting", "reseller"}:
        score += 0.03
    return round(min(score, 0.86), 2)
