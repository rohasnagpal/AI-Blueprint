"""ai council plugin tables

Revision ID: 0004_ai_council_plugin
Revises: 0003_scoped_documents
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_ai_council_plugin"
down_revision = "0003_scoped_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "council_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_council_configs_workspace_id", "council_configs", ["workspace_id"])
    op.create_index("ix_council_configs_blueprint_id", "council_configs", ["blueprint_id"], unique=True)
    op.create_index("ix_council_configs_created_by_user_id", "council_configs", ["created_by_user_id"])

    op.create_table(
        "council_runs_v2",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("config_snapshot_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_council_runs_v2_workspace_id", "council_runs_v2", ["workspace_id"])
    op.create_index("ix_council_runs_v2_blueprint_id", "council_runs_v2", ["blueprint_id"])
    op.create_index("ix_council_runs_v2_created_by_user_id", "council_runs_v2", ["created_by_user_id"])
    op.create_index("ix_council_runs_v2_blueprint_status", "council_runs_v2", ["blueprint_id", "status"])
    op.create_index("ix_council_runs_v2_workspace_created", "council_runs_v2", ["workspace_id", "created_at"])

    op.create_table(
        "council_outputs_v2",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("council_runs_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", sa.String(length=100)),
        sa.Column("phase_name", sa.String(length=255)),
        sa.Column("agent_id", sa.String(length=100)),
        sa.Column("role_name", sa.String(length=255)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_council_outputs_v2_workspace_id", "council_outputs_v2", ["workspace_id"])
    op.create_index("ix_council_outputs_v2_blueprint_id", "council_outputs_v2", ["blueprint_id"])
    op.create_index("ix_council_outputs_v2_run_id", "council_outputs_v2", ["run_id"])
    op.create_index("ix_council_outputs_v2_run_phase", "council_outputs_v2", ["run_id", "phase_id"])

    op.create_table(
        "council_evidence_v2",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("council_runs_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", sa.String(length=100)),
        sa.Column("phase_name", sa.String(length=255)),
        sa.Column("query", sa.Text()),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_council_evidence_v2_workspace_id", "council_evidence_v2", ["workspace_id"])
    op.create_index("ix_council_evidence_v2_blueprint_id", "council_evidence_v2", ["blueprint_id"])
    op.create_index("ix_council_evidence_v2_run_id", "council_evidence_v2", ["run_id"])
    op.create_index("ix_council_evidence_v2_run_phase", "council_evidence_v2", ["run_id", "phase_id"])


def downgrade() -> None:
    op.drop_index("ix_council_evidence_v2_run_phase", table_name="council_evidence_v2")
    op.drop_index("ix_council_evidence_v2_run_id", table_name="council_evidence_v2")
    op.drop_index("ix_council_evidence_v2_blueprint_id", table_name="council_evidence_v2")
    op.drop_index("ix_council_evidence_v2_workspace_id", table_name="council_evidence_v2")
    op.drop_table("council_evidence_v2")
    op.drop_index("ix_council_outputs_v2_run_phase", table_name="council_outputs_v2")
    op.drop_index("ix_council_outputs_v2_run_id", table_name="council_outputs_v2")
    op.drop_index("ix_council_outputs_v2_blueprint_id", table_name="council_outputs_v2")
    op.drop_index("ix_council_outputs_v2_workspace_id", table_name="council_outputs_v2")
    op.drop_table("council_outputs_v2")
    op.drop_index("ix_council_runs_v2_workspace_created", table_name="council_runs_v2")
    op.drop_index("ix_council_runs_v2_blueprint_status", table_name="council_runs_v2")
    op.drop_index("ix_council_runs_v2_created_by_user_id", table_name="council_runs_v2")
    op.drop_index("ix_council_runs_v2_blueprint_id", table_name="council_runs_v2")
    op.drop_index("ix_council_runs_v2_workspace_id", table_name="council_runs_v2")
    op.drop_table("council_runs_v2")
    op.drop_index("ix_council_configs_created_by_user_id", table_name="council_configs")
    op.drop_index("ix_council_configs_blueprint_id", table_name="council_configs")
    op.drop_index("ix_council_configs_workspace_id", table_name="council_configs")
    op.drop_table("council_configs")
