"""litigation prep workflow

Revision ID: 0027_litigation_prep
Revises: 0026_arbitration_prep
Create Date: 2026-05-31
"""

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0027_litigation_prep"
down_revision = "0026_arbitration_prep"
branch_labels = None
depends_on = None


def _ts() -> datetime:
    return datetime.now(timezone.utc)


def _common_source_columns(run_fk: str) -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey(run_fk, ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), nullable=True),
    ]


def _anchor_columns() -> list[sa.Column]:
    return [
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "plugins",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("version", sa.String),
            sa.column("is_enabled", sa.Boolean),
            sa.column("manifest_json", sa.Text),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": "litigation_prep",
                "name": "Litigation Prep",
                "description": "Agentic litigation preparation from indexed matter documents.",
                "version": "1.0.0",
                "is_enabled": True,
                "manifest_json": json.dumps({"type": "core", "route": "/litigation-prep"}, sort_keys=True),
                "created_at": _ts(),
                "updated_at": _ts(),
            }
        ],
    )

    op.create_table(
        "litigation_prep_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("config_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("workflow_version", sa.String(length=50), nullable=True),
        sa.Column("source_anchor_version", sa.String(length=50), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name, cols in {
        "ix_litigation_prep_runs_workspace_id": ["workspace_id"],
        "ix_litigation_prep_runs_matter_id": ["matter_id"],
        "ix_litigation_prep_runs_blueprint_id": ["blueprint_id"],
        "ix_litigation_prep_runs_created_by_user_id": ["created_by_user_id"],
        "ix_litigation_prep_runs_workspace_created": ["workspace_id", "created_at"],
        "ix_litigation_prep_runs_matter_status": ["matter_id", "status"],
    }.items():
        op.create_index(name, "litigation_prep_runs", cols)

    op.create_table(
        "litigation_prep_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False),
        *[sa.Column(name, sa.Text(), nullable=False, server_default=default) for name, default in [
            ("case_snapshot_json", "{}"), ("claims_and_defenses_json", "[]"), ("issues_json", "[]"),
            ("chronology_json", "[]"), ("evidence_matrix_json", "[]"), ("discovery_analysis_json", "[]"),
            ("witness_prep_json", "[]"), ("deposition_prep_json", "[]"), ("motion_strategy_json", "{}"),
            ("trial_prep_json", "{}"), ("argument_strategy_json", "{}"), ("cross_examination_json", "[]"),
            ("procedural_tasks_json", "[]"), ("damages_and_remedies_json", "{}"),
            ("risks_and_gaps_json", "[]"), ("warnings_json", "[]"), ("agentic_review_json", "{}"),
            ("sources_json", "[]"), ("metadata_json", "{}"),
        ]],
        sa.Column("client_or_team_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in {
        "ix_litigation_prep_outputs_workspace_id": ["workspace_id"],
        "ix_litigation_prep_outputs_matter_id": ["matter_id"],
        "ix_litigation_prep_outputs_run_id": ["run_id"],
        "ix_litigation_prep_outputs_run": ["run_id"],
    }.items():
        op.create_index(name, "litigation_prep_outputs", cols)

    op.create_table("litigation_issues", *_common_source_columns("litigation_prep_runs.id"), sa.Column("title", sa.String(length=255), nullable=False), sa.Column("category", sa.String(length=100), nullable=True), sa.Column("summary", sa.Text(), nullable=False, server_default=""), sa.Column("proof_elements_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("burdens_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("disputed_facts_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("admissions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("missing_proof_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_claims", *_common_source_columns("litigation_prep_runs.id"), sa.Column("claim_type", sa.String(length=100), nullable=False, server_default="claim"), sa.Column("title", sa.String(length=255), nullable=False), sa.Column("elements_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("defenses_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("admissions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("missing_proof_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_chronology_events", *_common_source_columns("litigation_prep_runs.id"), sa.Column("event_date", sa.String(length=50), nullable=True), sa.Column("description", sa.Text(), nullable=False), sa.Column("relevance", sa.Text(), nullable=True), sa.Column("anchor_text", sa.Text(), nullable=True), *_anchor_columns())
    op.create_table("litigation_evidence_items", *_common_source_columns("litigation_prep_runs.id"), sa.Column("issue_id", sa.String(length=36), sa.ForeignKey("litigation_issues.id", ondelete="SET NULL"), nullable=True), sa.Column("evidence_type", sa.String(length=64), nullable=False, server_default="supporting"), sa.Column("summary", sa.Text(), nullable=False, server_default=""), sa.Column("anchor_text", sa.Text(), nullable=True), *_anchor_columns())
    op.create_table("litigation_witnesses", *_common_source_columns("litigation_prep_runs.id"), sa.Column("name", sa.String(length=255), nullable=False), sa.Column("role", sa.String(length=255), nullable=True), sa.Column("topics_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("admissions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("contradictions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("prep_questions_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_deposition_topics", *_common_source_columns("litigation_prep_runs.id"), sa.Column("witness_name", sa.String(length=255), nullable=False), sa.Column("topics_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("questions_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("anchors_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_arguments", *_common_source_columns("litigation_prep_runs.id"), sa.Column("theme", sa.String(length=255), nullable=False), sa.Column("strongest_points_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("vulnerabilities_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("opponent_responses_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_procedural_tasks", *_common_source_columns("litigation_prep_runs.id"), sa.Column("task_type", sa.String(length=100), nullable=False, server_default="obligation"), sa.Column("description", sa.Text(), nullable=False), sa.Column("due_date", sa.String(length=50), nullable=True), sa.Column("compliance_risk", sa.Text(), nullable=True), *_anchor_columns())
    op.create_table("litigation_motions", *_common_source_columns("litigation_prep_runs.id"), sa.Column("motion_type", sa.String(length=100), nullable=False, server_default="motion"), sa.Column("title", sa.String(length=255), nullable=False), sa.Column("support_json", sa.Text(), nullable=False, server_default="[]"), sa.Column("vulnerabilities_json", sa.Text(), nullable=False, server_default="[]"), *_anchor_columns())
    op.create_table("litigation_discovery_items", *_common_source_columns("litigation_prep_runs.id"), sa.Column("item_type", sa.String(length=100), nullable=False, server_default="discovery"), sa.Column("description", sa.Text(), nullable=False), sa.Column("status", sa.String(length=100), nullable=True), *_anchor_columns())
    op.create_table("litigation_damages_items", *_common_source_columns("litigation_prep_runs.id"), sa.Column("item_type", sa.String(length=100), nullable=False, server_default="damages"), sa.Column("amount", sa.String(length=100), nullable=True), sa.Column("summary", sa.Text(), nullable=False, server_default=""), *_anchor_columns())
    op.create_table("litigation_risk_items", *_common_source_columns("litigation_prep_runs.id"), sa.Column("risk_level", sa.String(length=50), nullable=False, server_default="medium"), sa.Column("summary", sa.Text(), nullable=False), sa.Column("leverage", sa.Text(), nullable=True), sa.Column("decision_point", sa.Text(), nullable=True), *_anchor_columns())

    detail_indexes = {
        "litigation_issues": [("ix_litigation_issues_run", ["run_id"])],
        "litigation_claims": [("ix_litigation_claims_run", ["run_id"])],
        "litigation_chronology_events": [("ix_litigation_chronology_events_run_date", ["run_id", "event_date"])],
        "litigation_evidence_items": [("ix_litigation_evidence_items_run_issue", ["run_id", "issue_id"])],
        "litigation_witnesses": [("ix_litigation_witnesses_run_name", ["run_id", "name"])],
        "litigation_deposition_topics": [("ix_litigation_deposition_topics_run", ["run_id"])],
        "litigation_arguments": [("ix_litigation_arguments_run", ["run_id"])],
        "litigation_procedural_tasks": [("ix_litigation_procedural_tasks_run_due", ["run_id", "due_date"])],
        "litigation_motions": [("ix_litigation_motions_run", ["run_id"])],
        "litigation_discovery_items": [("ix_litigation_discovery_items_run", ["run_id"])],
        "litigation_damages_items": [("ix_litigation_damages_items_run", ["run_id"])],
        "litigation_risk_items": [("ix_litigation_risk_items_run_level", ["run_id", "risk_level"])],
    }
    for table, indexes in detail_indexes.items():
        for col in ["workspace_id", "matter_id", "run_id", "source_document_id", "chunk_id"]:
            op.create_index(f"ix_{table}_{col}", table, [col])
        for name, cols in indexes:
            op.create_index(name, table, cols)
    op.create_index("ix_litigation_evidence_items_issue_id", "litigation_evidence_items", ["issue_id"])

    op.create_table(
        "litigation_agent_step_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("step_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in {
        "ix_litigation_agent_step_outputs_workspace_id": ["workspace_id"],
        "ix_litigation_agent_step_outputs_matter_id": ["matter_id"],
        "ix_litigation_agent_step_outputs_run_id": ["run_id"],
        "ix_litigation_agent_step_outputs_run_step": ["run_id", "step_name"],
        "ix_litigation_agent_step_outputs_workspace_run": ["workspace_id", "run_id"],
    }.items():
        op.create_index(name, "litigation_agent_step_outputs", cols)

    op.create_table(
        "litigation_review_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("prior_status_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in {
        "ix_litigation_review_decisions_workspace_id": ["workspace_id"],
        "ix_litigation_review_decisions_matter_id": ["matter_id"],
        "ix_litigation_review_decisions_run_id": ["run_id"],
        "ix_litigation_review_decisions_user_id": ["user_id"],
        "ix_litigation_review_decisions_target_id": ["target_id"],
        "ix_litigation_review_decisions_run": ["run_id"],
    }.items():
        op.create_index(name, "litigation_review_decisions", cols)


def downgrade() -> None:
    for table in [
        "litigation_review_decisions",
        "litigation_agent_step_outputs",
        "litigation_risk_items",
        "litigation_damages_items",
        "litigation_discovery_items",
        "litigation_motions",
        "litigation_procedural_tasks",
        "litigation_arguments",
        "litigation_deposition_topics",
        "litigation_witnesses",
        "litigation_evidence_items",
        "litigation_chronology_events",
        "litigation_claims",
        "litigation_issues",
        "litigation_prep_outputs",
        "litigation_prep_runs",
    ]:
        op.drop_table(table)
    op.execute("DELETE FROM plugins WHERE id = 'litigation_prep'")
