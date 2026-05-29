import json
import re

from app.core.json_utils import json_loads
from app.core.llm import complete_with_configured_llm


RISK_TERMS = {
    "termination": "Termination rights",
    "liability": "Liability exposure",
    "indemn": "Indemnity",
    "confidential": "Confidentiality",
    "governing law": "Governing law",
    "jurisdiction": "Jurisdiction",
    "assignment": "Assignment",
    "payment": "Payment obligations",
}


def extract_fields(text: str, config: dict) -> dict:
    fields = config.get("fields") or ["parties", "effective_date", "governing_law", "term", "payment"]
    extraction = {}
    for field in fields:
        label = str(field)
        pattern = label.replace("_", r"[\s_-]+")
        match = re.search(rf"{pattern}\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE)
        extraction[label] = {
            "value": match.group(1).strip()[:300] if match else None,
            "supported": bool(match),
        }
    return extraction


def risk_matrix(text: str) -> list[dict]:
    lower = text.lower()
    risks = []
    for needle, label in RISK_TERMS.items():
        present = needle in lower
        risks.append(
            {
                "issue": label,
                "severity": "medium" if present else "low",
                "finding": "Relevant language found for review." if present else "No obvious language found in indexed text.",
                "requires_review": present,
            }
        )
    return risks


def negotiation_memo(extraction: dict, risks: list[dict]) -> str:
    flagged = [risk["issue"] for risk in risks if risk["requires_review"]]
    missing = [key for key, value in extraction.items() if not value["supported"]]
    return (
        "Negotiation memo\n\n"
        f"Flagged issues: {', '.join(flagged) if flagged else 'None from indexed text'}.\n"
        f"Missing structured fields: {', '.join(missing) if missing else 'None'}.\n"
        "Review flagged clauses against the firm's playbook before client delivery."
    )


def client_summary(extraction: dict, risks: list[dict]) -> str:
    review_count = sum(1 for risk in risks if risk["requires_review"])
    supported = sum(1 for value in extraction.values() if value["supported"])
    return f"Indexed review found {review_count} issue area(s) requiring lawyer review and {supported} structured field(s) with apparent support."


def ai_contract_review(text: str, extraction: dict, risks: list[dict], *, sources: list[dict], config: dict, settings: dict) -> dict | None:
    system = (
        "You are a careful contract review assistant. Return only valid JSON with keys "
        "extraction, risk_matrix, negotiation_memo, client_summary. Do not provide legal advice or recommend signing."
    )
    source_text = "\n\n".join(f"[{source['filename']} chunk {source['chunk']}]\n{source['excerpt']}" for source in sources[:8])
    user = (
        "Review this indexed contract evidence. Use the provided deterministic draft as a starting point, "
        "but improve it where the evidence supports a better analysis.\n\n"
        f"Config: {json.dumps(config, sort_keys=True)}\n\n"
        f"Deterministic extraction: {json.dumps(extraction, sort_keys=True)}\n\n"
        f"Deterministic risk matrix: {json.dumps(risks, sort_keys=True)}\n\n"
        f"Evidence excerpts:\n{source_text}\n\n"
        f"Full indexed text, truncated:\n{text[:12000]}"
    )
    try:
        content = complete_with_configured_llm(
            settings,
            system,
            user,
            model=config.get("model"),
            temperature=float(config.get("temperature", 0.2)),
            max_tokens=int(config.get("max_tokens", 3000)),
        )
    except Exception:
        return None
    data = json_loads(_extract_json_object(content), {}) if content else {}
    if not isinstance(data.get("extraction"), dict) or not isinstance(data.get("risk_matrix"), list):
        return None
    return data


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value
    return value[start:end + 1]
