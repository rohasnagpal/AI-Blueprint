from pydantic import BaseModel, Field


class SourceAnchor(BaseModel):
    document_id: str | None = None
    chunk_id: str | None = None
    filename: str | None = None
    chunk_index: int | None = None
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str | None = None


class IntakeResult(BaseModel):
    contract_type: str = "unknown"
    contract_category: str = "general"
    parties: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    governing_law: str | None = None
    confidence_score: float = 0.5
    routing_notes: str = ""


class ExtractedClause(BaseModel):
    clause_type: str
    title: str | None = None
    text: str
    source: SourceAnchor
    confidence_score: float = 0.6
    extraction_notes: str = ""


class PlaybookFindingResult(BaseModel):
    clause_type: str
    clause_id: str | None = None
    playbook_clause_id: str | None = None
    status: str
    deviation_summary: str | None = None
    missing: bool = False
    prohibited_match: str | None = None
    confidence_score: float = 0.7


class RiskFindingResult(BaseModel):
    clause_type: str
    clause_id: str | None = None
    risk_level: str
    likelihood: str | None = None
    impact: str | None = None
    priority: int | None = None
    reasoning: str
    requires_review: bool = False
    confidence_score: float = 0.7


class RedlineSuggestionResult(BaseModel):
    clause_id: str
    suggestion_text: str
    fallback_language: str | None = None
    rationale: str | None = None
    confidence_score: float = 0.6


class SummaryResult(BaseModel):
    audience: str
    summary_text: str
    obligations: list[str] = Field(default_factory=list)
    negotiation_points: list[str] = Field(default_factory=list)
    unusual_terms: list[str] = Field(default_factory=list)


class EscalationResult(BaseModel):
    clause_id: str | None = None
    severity: str
    reason: str
    required_action: str
    metadata: dict = Field(default_factory=dict)
