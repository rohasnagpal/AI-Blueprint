import re

from app.core.contract_agents.schemas import ExtractedClause, SourceAnchor


CLAUSE_KEYWORDS = {
    "indemnity": ["indemn"],
    "limitation_of_liability": ["limitation of liability", "liability cap", "aggregate liability"],
    "termination": ["termination", "terminate", "suspension", "suspend access", "non-renewal", "renewal"],
    "confidentiality": ["confidential"],
    "ip": ["intellectual property", "work product", "deliverables", "ownership", "background ip", "trademark", "marks", "brand assets", "license to use"],
    "payment": ["payment", "fees", "invoice", "pricing", "discount", "taxes", "expenses", "chargebacks"],
    "dispute_resolution": ["dispute", "arbitration", "jurisdiction", "venue"],
    "governing_law": ["governing law", "laws of"],
    "warranties": ["warrant", "warranty", "service level", "sla", "availability", "uptime", "compliance", "anti-bribery", "export controls", "sales conduct"],
    "force_majeure": ["force majeure"],
    "assignment": ["assignment", "assign"],
    "non_compete": ["non-compete", "non compete", "restraint of trade"],
    "data_security": ["data security", "personal data", "security controls", "customer data", "safeguards", "security measures"],
    "data_processing": ["data processing", "processor", "controller", "subprocessor", "data subject"],
    "data_breach_notice": ["security incident", "data breach", "breach notification", "unauthorized access"],
    "scope": ["scope of work", "statement of work", "services", "deliverables", "subscription", "authorized users", "usage limits", "territory", "channel rights", "customer segment"],
    "acceptance": ["acceptance criteria", "acceptance testing", "deemed accepted"],
    "change_control": ["change order", "change control", "out of scope"],
}


def extract_clauses(chunks: list[dict], *, window_size: int = 8000, overlap: int = 600) -> list[ExtractedClause]:
    windows = _windows(chunks, window_size=window_size, overlap=overlap)
    extracted: list[ExtractedClause] = []
    for window in windows:
        for segment in _segments(window["text"]):
            text = segment["text"]
            clause_type = _classify(segment)
            if not clause_type:
                continue
            source_start = _source_offset(window.get("start_offset"), segment["start"])
            source_end = _source_offset(window.get("start_offset"), segment["end"])
            extracted.append(
                ExtractedClause(
                    clause_type=clause_type,
                    title=_title_for(clause_type),
                    text=text[:6000],
                    source=SourceAnchor(
                        document_id=window.get("document_id"),
                        chunk_id=window.get("chunk_id"),
                        filename=window.get("filename"),
                        chunk_index=window.get("chunk_index"),
                        page=window.get("page"),
                        start_offset=source_start,
                        end_offset=source_end,
                        excerpt=text[:500],
                    ),
                    confidence_score=0.72,
                    extraction_notes="Keyword-classified first-pass clause extraction.",
                )
            )
    return _dedupe(extracted)


def _windows(chunks: list[dict], *, window_size: int, overlap: int) -> list[dict]:
    windows = []
    for chunk in chunks:
        text = chunk.get("content", "")
        if len(text) <= window_size:
            item = dict(chunk)
            item["text"] = text
            windows.append(item)
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + window_size)
            item = dict(chunk)
            item["text"] = text[start:end]
            if item.get("start_offset") is not None:
                item["start_offset"] = int(item["start_offset"]) + start
            if item.get("start_offset") is not None:
                item["end_offset"] = int(item["start_offset"]) + len(item["text"])
            windows.append(item)
            if end == len(text):
                break
            start = max(end - overlap, start + 1)
    return windows


def _segments(text: str) -> list[dict]:
    parts = _split_with_offsets(text, r"\n\s*(?=(?:\d+\.|[A-Z][A-Z\s]{4,}|[A-Z][A-Za-z ]{3,}:))")
    if len(parts) <= 1:
        parts = _split_with_offsets(text, r"(?<=[.;])\s+(?=[A-Z][A-Za-z ]{3,})")
    segments = []
    for part in parts:
        raw = part["text"]
        leading_trim = len(raw) - len(raw.lstrip())
        trailing_trim = len(raw.rstrip())
        cleaned = re.sub(r"\s+", " ", raw.strip())
        if len(cleaned) >= 30:
            segments.append({"text": cleaned, "start": part["start"] + leading_trim, "end": part["start"] + trailing_trim})
    return segments


def _split_with_offsets(text: str, pattern: str) -> list[dict]:
    pieces = []
    start = 0
    for match in re.finditer(pattern, text):
        end = match.start()
        if end > start:
            pieces.append({"text": text[start:end], "start": start, "end": end})
        start = match.end()
    if start < len(text):
        pieces.append({"text": text[start:], "start": start, "end": len(text)})
    return pieces


def _classify(segment: dict | str) -> str | None:
    text = segment["text"] if isinstance(segment, dict) else segment
    lower = text.lower()
    for clause_type, keywords in CLAUSE_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return clause_type
    return None


def _source_offset(base: int | None, local_offset: int) -> int | None:
    if base is None:
        return None
    return int(base) + local_offset


def _title_for(clause_type: str) -> str:
    return clause_type.replace("_", " ").title()


def _dedupe(clauses: list[ExtractedClause]) -> list[ExtractedClause]:
    seen = set()
    result = []
    for clause in clauses:
        key = (clause.clause_type, re.sub(r"\W+", "", clause.text.lower())[:240])
        if key in seen:
            continue
        seen.add(key)
        result.append(clause)
    return result
