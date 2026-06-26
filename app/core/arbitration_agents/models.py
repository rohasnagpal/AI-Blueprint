from typing import Any

from pydantic import BaseModel, Field


class ArbitrationSourceAnchor(BaseModel):
    document_id: str | None = None
    chunk_id: str | None = None
    filename: str | None = None
    chunk_index: int | None = None
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str | None = None


class ArbitrationWorkflow(BaseModel):
    version: str = "arbitration_prep_workflow_v2"
    case_snapshot: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    chronology: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: list[dict[str, Any]] = Field(default_factory=list)
    witness_prep: list[dict[str, Any]] = Field(default_factory=list)
    argument_strategy: dict[str, Any] = Field(default_factory=dict)
    cross_examination: list[dict[str, Any]] = Field(default_factory=list)
    procedural_tasks: list[dict[str, Any]] = Field(default_factory=list)
    damages_and_remedies: dict[str, Any] = Field(default_factory=dict)
    risks_and_gaps: list[dict[str, Any]] = Field(default_factory=list)
    client_or_team_summary: str = ""
    trace: list[dict[str, Any]] = Field(default_factory=list)
