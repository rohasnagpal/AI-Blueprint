"""contract review workflow foundation

Revision ID: 0019_contract_review_workflow_foundation
Revises: 0018_knowledge_embeddings
Create Date: 2026-05-27
"""

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0019_contract_review_workflow_foundation"
down_revision = "0018_knowledge_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contract_review_runs", sa.Column("mode", sa.String(length=64), nullable=False, server_default="legacy"))
    op.add_column("contract_review_runs", sa.Column("workflow_version", sa.String(length=50), nullable=True))
    op.add_column("contract_review_runs", sa.Column("status_detail", sa.Text(), nullable=True))
    op.add_column("contract_review_runs", sa.Column("selected_playbook_id", sa.String(length=36), nullable=True))
    op.add_column("contract_review_runs", sa.Column("coverage_score", sa.Float(), nullable=True))
    op.add_column("contract_review_runs", sa.Column("source_anchor_version", sa.String(length=50), nullable=True))
    op.create_index("ix_contract_review_runs_selected_playbook_id", "contract_review_runs", ["selected_playbook_id"])

    op.create_table(
        "contract_playbooks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contract_category", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=100), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_playbooks_workspace_id", "contract_playbooks", ["workspace_id"])
    op.create_index("ix_contract_playbooks_created_by_user_id", "contract_playbooks", ["created_by_user_id"])
    op.create_index("ix_contract_playbooks_workspace_category", "contract_playbooks", ["workspace_id", "contract_category"])
    op.create_index("ix_contract_playbooks_workspace_status", "contract_playbooks", ["workspace_id", "status"])

    op.create_table(
        "contract_playbook_clauses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("playbook_id", sa.String(length=36), sa.ForeignKey("contract_playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("approved_text", sa.Text(), nullable=True),
        sa.Column("fallback_text", sa.Text(), nullable=True),
        sa.Column("prohibited_patterns_json", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("severity_default", sa.String(length=50), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_playbook_clauses_playbook_id", "contract_playbook_clauses", ["playbook_id"])
    op.create_index("ix_contract_playbook_clauses_playbook_type", "contract_playbook_clauses", ["playbook_id", "clause_type"])

    op.create_table(
        "contract_clauses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("clause_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_clauses_workspace_id", "contract_clauses", ["workspace_id"])
    op.create_index("ix_contract_clauses_blueprint_id", "contract_clauses", ["blueprint_id"])
    op.create_index("ix_contract_clauses_run_id", "contract_clauses", ["run_id"])
    op.create_index("ix_contract_clauses_document_id", "contract_clauses", ["document_id"])
    op.create_index("ix_contract_clauses_chunk_id", "contract_clauses", ["chunk_id"])
    op.create_index("ix_contract_clauses_run_type", "contract_clauses", ["run_id", "clause_type"])
    op.create_index("ix_contract_clauses_run_review", "contract_clauses", ["run_id", "review_status"])
    op.create_index("ix_contract_clauses_workspace_run", "contract_clauses", ["workspace_id", "run_id"])

    op.create_table(
        "contract_playbook_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", sa.String(length=36), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("playbook_id", sa.String(length=36), sa.ForeignKey("contract_playbooks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("playbook_clause_id", sa.String(length=36), sa.ForeignKey("contract_playbook_clauses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("deviation_summary", sa.Text(), nullable=True),
        sa.Column("missing", sa.Boolean(), nullable=False),
        sa.Column("prohibited_match", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_playbook_findings_workspace_id", "contract_playbook_findings", ["workspace_id"])
    op.create_index("ix_contract_playbook_findings_blueprint_id", "contract_playbook_findings", ["blueprint_id"])
    op.create_index("ix_contract_playbook_findings_run_id", "contract_playbook_findings", ["run_id"])
    op.create_index("ix_contract_playbook_findings_clause_id", "contract_playbook_findings", ["clause_id"])
    op.create_index("ix_contract_playbook_findings_playbook_id", "contract_playbook_findings", ["playbook_id"])
    op.create_index("ix_contract_playbook_findings_playbook_clause_id", "contract_playbook_findings", ["playbook_clause_id"])
    op.create_index("ix_contract_playbook_findings_run_status", "contract_playbook_findings", ["run_id", "status"])
    op.create_index("ix_contract_playbook_findings_clause", "contract_playbook_findings", ["clause_id"])

    op.create_table(
        "contract_risk_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", sa.String(length=36), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("risk_level", sa.String(length=50), nullable=False),
        sa.Column("likelihood", sa.String(length=50), nullable=True),
        sa.Column("impact", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_risk_findings_workspace_id", "contract_risk_findings", ["workspace_id"])
    op.create_index("ix_contract_risk_findings_blueprint_id", "contract_risk_findings", ["blueprint_id"])
    op.create_index("ix_contract_risk_findings_run_id", "contract_risk_findings", ["run_id"])
    op.create_index("ix_contract_risk_findings_clause_id", "contract_risk_findings", ["clause_id"])
    op.create_index("ix_contract_risk_findings_run_level", "contract_risk_findings", ["run_id", "risk_level"])
    op.create_index("ix_contract_risk_findings_clause", "contract_risk_findings", ["clause_id"])

    op.create_table(
        "contract_redline_suggestions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", sa.String(length=36), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=False),
        sa.Column("fallback_language", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source_playbook_id", sa.String(length=36), sa.ForeignKey("contract_playbooks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_redline_suggestions_workspace_id", "contract_redline_suggestions", ["workspace_id"])
    op.create_index("ix_contract_redline_suggestions_blueprint_id", "contract_redline_suggestions", ["blueprint_id"])
    op.create_index("ix_contract_redline_suggestions_run_id", "contract_redline_suggestions", ["run_id"])
    op.create_index("ix_contract_redline_suggestions_clause_id", "contract_redline_suggestions", ["clause_id"])
    op.create_index("ix_contract_redline_suggestions_source_playbook_id", "contract_redline_suggestions", ["source_playbook_id"])
    op.create_index("ix_contract_redline_suggestions_run_status", "contract_redline_suggestions", ["run_id", "status"])
    op.create_index("ix_contract_redline_suggestions_clause", "contract_redline_suggestions", ["clause_id"])

    op.create_table(
        "contract_review_summaries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audience", sa.String(length=64), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("obligations_json", sa.Text(), nullable=False),
        sa.Column("negotiation_points_json", sa.Text(), nullable=False),
        sa.Column("unusual_terms_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "audience", name="uq_contract_review_summaries_run_audience"),
    )
    op.create_index("ix_contract_review_summaries_workspace_id", "contract_review_summaries", ["workspace_id"])
    op.create_index("ix_contract_review_summaries_blueprint_id", "contract_review_summaries", ["blueprint_id"])
    op.create_index("ix_contract_review_summaries_run_id", "contract_review_summaries", ["run_id"])
    op.create_index("ix_contract_review_summaries_run", "contract_review_summaries", ["run_id"])

    op.create_table(
        "contract_review_step_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("step_version", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_review_step_outputs_workspace_id", "contract_review_step_outputs", ["workspace_id"])
    op.create_index("ix_contract_review_step_outputs_blueprint_id", "contract_review_step_outputs", ["blueprint_id"])
    op.create_index("ix_contract_review_step_outputs_run_id", "contract_review_step_outputs", ["run_id"])
    op.create_index("ix_contract_review_step_outputs_run_step", "contract_review_step_outputs", ["run_id", "step_name"])
    op.create_index("ix_contract_review_step_outputs_workspace_run", "contract_review_step_outputs", ["workspace_id", "run_id"])

    op.create_table(
        "contract_clause_review_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", sa.String(length=36), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("prior_status_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_clause_review_decisions_workspace_id", "contract_clause_review_decisions", ["workspace_id"])
    op.create_index("ix_contract_clause_review_decisions_blueprint_id", "contract_clause_review_decisions", ["blueprint_id"])
    op.create_index("ix_contract_clause_review_decisions_run_id", "contract_clause_review_decisions", ["run_id"])
    op.create_index("ix_contract_clause_review_decisions_clause_id", "contract_clause_review_decisions", ["clause_id"])
    op.create_index("ix_contract_clause_review_decisions_user_id", "contract_clause_review_decisions", ["user_id"])
    op.create_index("ix_contract_clause_review_decisions_clause", "contract_clause_review_decisions", ["clause_id"])
    op.create_index("ix_contract_clause_review_decisions_run", "contract_clause_review_decisions", ["run_id"])

    _seed_builtin_playbooks()


def downgrade() -> None:
    op.drop_index("ix_contract_clause_review_decisions_run", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_clause", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_user_id", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_clause_id", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_run_id", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_blueprint_id", table_name="contract_clause_review_decisions")
    op.drop_index("ix_contract_clause_review_decisions_workspace_id", table_name="contract_clause_review_decisions")
    op.drop_table("contract_clause_review_decisions")

    op.drop_index("ix_contract_review_step_outputs_workspace_run", table_name="contract_review_step_outputs")
    op.drop_index("ix_contract_review_step_outputs_run_step", table_name="contract_review_step_outputs")
    op.drop_index("ix_contract_review_step_outputs_run_id", table_name="contract_review_step_outputs")
    op.drop_index("ix_contract_review_step_outputs_blueprint_id", table_name="contract_review_step_outputs")
    op.drop_index("ix_contract_review_step_outputs_workspace_id", table_name="contract_review_step_outputs")
    op.drop_table("contract_review_step_outputs")

    op.drop_index("ix_contract_review_summaries_run", table_name="contract_review_summaries")
    op.drop_index("ix_contract_review_summaries_run_id", table_name="contract_review_summaries")
    op.drop_index("ix_contract_review_summaries_blueprint_id", table_name="contract_review_summaries")
    op.drop_index("ix_contract_review_summaries_workspace_id", table_name="contract_review_summaries")
    op.drop_table("contract_review_summaries")

    op.drop_index("ix_contract_redline_suggestions_clause", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_run_status", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_source_playbook_id", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_clause_id", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_run_id", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_blueprint_id", table_name="contract_redline_suggestions")
    op.drop_index("ix_contract_redline_suggestions_workspace_id", table_name="contract_redline_suggestions")
    op.drop_table("contract_redline_suggestions")

    op.drop_index("ix_contract_risk_findings_clause", table_name="contract_risk_findings")
    op.drop_index("ix_contract_risk_findings_run_level", table_name="contract_risk_findings")
    op.drop_index("ix_contract_risk_findings_clause_id", table_name="contract_risk_findings")
    op.drop_index("ix_contract_risk_findings_run_id", table_name="contract_risk_findings")
    op.drop_index("ix_contract_risk_findings_blueprint_id", table_name="contract_risk_findings")
    op.drop_index("ix_contract_risk_findings_workspace_id", table_name="contract_risk_findings")
    op.drop_table("contract_risk_findings")

    op.drop_index("ix_contract_playbook_findings_clause", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_run_status", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_playbook_clause_id", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_playbook_id", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_clause_id", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_run_id", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_blueprint_id", table_name="contract_playbook_findings")
    op.drop_index("ix_contract_playbook_findings_workspace_id", table_name="contract_playbook_findings")
    op.drop_table("contract_playbook_findings")

    op.drop_index("ix_contract_clauses_workspace_run", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_run_review", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_run_type", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_chunk_id", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_document_id", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_run_id", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_blueprint_id", table_name="contract_clauses")
    op.drop_index("ix_contract_clauses_workspace_id", table_name="contract_clauses")
    op.drop_table("contract_clauses")

    op.drop_index("ix_contract_playbook_clauses_playbook_type", table_name="contract_playbook_clauses")
    op.drop_index("ix_contract_playbook_clauses_playbook_id", table_name="contract_playbook_clauses")
    op.drop_table("contract_playbook_clauses")

    op.drop_index("ix_contract_playbooks_workspace_status", table_name="contract_playbooks")
    op.drop_index("ix_contract_playbooks_workspace_category", table_name="contract_playbooks")
    op.drop_index("ix_contract_playbooks_created_by_user_id", table_name="contract_playbooks")
    op.drop_index("ix_contract_playbooks_workspace_id", table_name="contract_playbooks")
    op.drop_table("contract_playbooks")

    op.drop_index("ix_contract_review_runs_selected_playbook_id", table_name="contract_review_runs")
    op.drop_column("contract_review_runs", "source_anchor_version")
    op.drop_column("contract_review_runs", "coverage_score")
    op.drop_column("contract_review_runs", "selected_playbook_id")
    op.drop_column("contract_review_runs", "status_detail")
    op.drop_column("contract_review_runs", "workflow_version")
    op.drop_column("contract_review_runs", "mode")


def _seed_builtin_playbooks() -> None:
    now = datetime.now(timezone.utc)
    playbook_table = sa.table(
        "contract_playbooks",
        sa.column("id", sa.String),
        sa.column("workspace_id", sa.String),
        sa.column("name", sa.String),
        sa.column("contract_category", sa.String),
        sa.column("jurisdiction", sa.String),
        sa.column("version", sa.String),
        sa.column("status", sa.String),
        sa.column("rules_json", sa.Text),
        sa.column("is_builtin", sa.Boolean),
        sa.column("created_by_user_id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    clause_table = sa.table(
        "contract_playbook_clauses",
        sa.column("id", sa.String),
        sa.column("playbook_id", sa.String),
        sa.column("clause_type", sa.String),
        sa.column("title", sa.String),
        sa.column("approved_text", sa.Text),
        sa.column("fallback_text", sa.Text),
        sa.column("prohibited_patterns_json", sa.Text),
        sa.column("required", sa.Boolean),
        sa.column("severity_default", sa.String),
        sa.column("metadata_json", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        playbook_table,
        [
            {
                "id": "builtin-nda-v1",
                "workspace_id": None,
                "name": "General NDA Playbook",
                "contract_category": "nda",
                "jurisdiction": None,
                "version": "1.0",
                "status": "active",
                "rules_json": '{"review_posture":"balanced","requires_human_review":true}',
                "is_builtin": True,
                "created_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "builtin-msa-v1",
                "workspace_id": None,
                "name": "General MSA/Vendor Agreement Playbook",
                "contract_category": "msa",
                "jurisdiction": None,
                "version": "1.0",
                "status": "active",
                "rules_json": '{"review_posture":"balanced","requires_human_review":true}',
                "is_builtin": True,
                "created_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    op.bulk_insert(
        clause_table,
        [
            _playbook_clause("builtin-nda-v1-confidentiality", "builtin-nda-v1", "confidentiality", "Confidentiality", True, "high", ["unlimited confidentiality without reasonable carve-outs"]),
            _playbook_clause("builtin-nda-v1-exclusions", "builtin-nda-v1", "confidentiality_exclusions", "Confidentiality Exclusions", True, "medium", ["no standard exclusions"]),
            _playbook_clause("builtin-nda-v1-term", "builtin-nda-v1", "term", "Term", True, "medium", ["perpetual obligations without scoped trade secret carve-out"]),
            _playbook_clause("builtin-nda-v1-return", "builtin-nda-v1", "return_or_destruction", "Return or Destruction", True, "medium", []),
            _playbook_clause("builtin-nda-v1-remedies", "builtin-nda-v1", "remedies", "Remedies", False, "medium", ["automatic injunctive relief without court discretion"]),
            _playbook_clause("builtin-nda-v1-law", "builtin-nda-v1", "governing_law", "Governing Law", True, "high", ["missing governing law"]),
            _playbook_clause("builtin-nda-v1-assignment", "builtin-nda-v1", "assignment", "Assignment", True, "medium", ["assignment without consent"]),
            _playbook_clause("builtin-msa-v1-payment", "builtin-msa-v1", "payment", "Payment", True, "medium", ["unclear fees", "unclear payment timing"]),
            _playbook_clause("builtin-msa-v1-scope", "builtin-msa-v1", "scope", "Scope of Services", True, "medium", ["undefined scope"]),
            _playbook_clause("builtin-msa-v1-acceptance", "builtin-msa-v1", "acceptance", "Acceptance", False, "medium", ["deemed acceptance without review period"]),
            _playbook_clause("builtin-msa-v1-warranties", "builtin-msa-v1", "warranties", "Warranties", True, "medium", ["broad warranty disclaimer"]),
            _playbook_clause("builtin-msa-v1-liability", "builtin-msa-v1", "limitation_of_liability", "Limitation of Liability", True, "critical", ["unlimited liability", "no liability cap"]),
            _playbook_clause("builtin-msa-v1-indemnity", "builtin-msa-v1", "indemnity", "Indemnity", True, "high", ["uncapped indemnity", "one-way indemnity"]),
            _playbook_clause("builtin-msa-v1-confidentiality", "builtin-msa-v1", "confidentiality", "Confidentiality", True, "medium", []),
            _playbook_clause("builtin-msa-v1-ip", "builtin-msa-v1", "ip", "Intellectual Property", True, "high", ["broad IP assignment", "unclear ownership of deliverables"]),
            _playbook_clause("builtin-msa-v1-termination", "builtin-msa-v1", "termination", "Termination", True, "high", ["no termination for convenience", "missing termination for breach"]),
            _playbook_clause("builtin-msa-v1-data", "builtin-msa-v1", "data_security", "Data and Security", False, "high", ["missing data security obligations"]),
            _playbook_clause("builtin-msa-v1-disputes", "builtin-msa-v1", "dispute_resolution", "Dispute Resolution", True, "medium", []),
            _playbook_clause("builtin-msa-v1-law", "builtin-msa-v1", "governing_law", "Governing Law", True, "high", ["missing governing law"]),
            _playbook_clause("builtin-msa-v1-assignment", "builtin-msa-v1", "assignment", "Assignment", True, "medium", ["assignment without consent"]),
            _playbook_clause("builtin-msa-v1-force-majeure", "builtin-msa-v1", "force_majeure", "Force Majeure", False, "medium", []),
            _playbook_clause("builtin-msa-v1-non-compete", "builtin-msa-v1", "non_compete", "Non-Compete", False, "critical", ["non-compete", "restraint of trade"]),
        ],
    )


def _playbook_clause(
    clause_id: str,
    playbook_id: str,
    clause_type: str,
    title: str,
    required: bool,
    severity: str,
    prohibited_patterns: list[str],
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": clause_id,
        "playbook_id": playbook_id,
        "clause_type": clause_type,
        "title": title,
        "approved_text": None,
        "fallback_text": None,
        "prohibited_patterns_json": json.dumps(prohibited_patterns, sort_keys=True),
        "required": required,
        "severity_default": severity,
        "metadata_json": "{}",
        "created_at": now,
        "updated_at": now,
    }
