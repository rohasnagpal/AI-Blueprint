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
    version: str = "mediator_prep_report_workflow_v2"
    case_snapshot: dict[str, Any] = Field(default_factory=dict)
    claims_and_defenses: list[dict[str, Any]] = Field(default_factory=list)
    positions_and_interests: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    chronology: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: list[dict[str, Any]] = Field(default_factory=list)
    discovery_analysis: list[dict[str, Any]] = Field(default_factory=list)
    witness_prep: list[dict[str, Any]] = Field(default_factory=list)
    deposition_prep: list[dict[str, Any]] = Field(default_factory=list)
    motion_strategy: dict[str, Any] = Field(default_factory=dict)
    trial_prep: dict[str, Any] = Field(default_factory=dict)
    argument_strategy: dict[str, Any] = Field(default_factory=dict)
    cross_examination: list[dict[str, Any]] = Field(default_factory=list)
    batna_watna_zopa: dict[str, Any] = Field(default_factory=dict)
    risk_allocation: list[dict[str, Any]] = Field(default_factory=list)
    settlement_levers: list[dict[str, Any]] = Field(default_factory=list)
    caucus_questions: list[dict[str, Any]] = Field(default_factory=list)
    impasse_points: list[dict[str, Any]] = Field(default_factory=list)
    bridge_proposals: list[dict[str, Any]] = Field(default_factory=list)
    mediator_private_prep_note: dict[str, Any] = Field(default_factory=dict)
    one_page_session_plan: dict[str, Any] = Field(default_factory=dict)
    procedural_tasks: list[dict[str, Any]] = Field(default_factory=list)
    damages_and_remedies: dict[str, Any] = Field(default_factory=dict)
    risks_and_gaps: list[dict[str, Any]] = Field(default_factory=list)
    client_or_team_summary: str = ""
    trace: list[dict[str, Any]] = Field(default_factory=list)
