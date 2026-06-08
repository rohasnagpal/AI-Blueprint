import re


_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:sk|pk|rk|xai|gsk|ant|AIza)[-_A-Za-z0-9]{12,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|token|secret|authorization)\b\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
]


def sanitize_provider_error(
    error: object,
    *,
    fallback: str = "The provider request failed. Check your API key, billing, quota, and model settings.",
) -> str:
    text = str(error or "").strip()
    if not text:
        return fallback
    lower = text.lower()
    if any(term in lower for term in ("authentication", "unauthorized", "api key", "invalid_api_key", "incorrect api key")):
        return fallback
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text[:500]
