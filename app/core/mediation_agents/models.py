from typing import Any

from pydantic import BaseModel, Field


class MediationSourceAnchor(BaseModel):
    document_id: str | None = None
    chunk_id: str | None = None
    filename: str | None = None
    chunk_index: int | None = None
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str | None = None


class MediationWorkflow(BaseModel):
    version: str = "mediation_prep_workflow_v1"
    case_snapshot: dict[str, Any] = Field(default_factory=dict)
    claims_and_defenses: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    chronology: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: list[dict[str, Any]] = Field(default_factory=list)
    discovery_analysis: list[dict[str, Any]] = Field(default_factory=list)
    witnesses: list[dict[str, Any]] = Field(default_factory=list)
    deposition_prep: list[dict[str, Any]] = Field(default_factory=list)
    motion_strategy: dict[str, Any] = Field(default_factory=dict)
    trial_prep: dict[str, Any] = Field(default_factory=dict)
    procedural_tasks: list[dict[str, Any]] = Field(default_factory=list)
    damages_and_remedies: dict[str, Any] = Field(default_factory=dict)
    risks_and_gaps: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
