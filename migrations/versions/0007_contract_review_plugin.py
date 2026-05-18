"""contract review plugin tables

Revision ID: 0007_contract_review_plugin
Revises: 0006_knowledge_chunks
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_contract_review_plugin"
down_revision = "0006_knowledge_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_review_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_review_configs_workspace_id", "contract_review_configs", ["workspace_id"])
    op.create_index("ix_contract_review_configs_blueprint_id", "contract_review_configs", ["blueprint_id"], unique=True)
    op.create_index("ix_contract_review_configs_created_by_user_id", "contract_review_configs", ["created_by_user_id"])

    op.create_table(
        "contract_review_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("config_snapshot_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_contract_review_runs_workspace_id", "contract_review_runs", ["workspace_id"])
    op.create_index("ix_contract_review_runs_blueprint_id", "contract_review_runs", ["blueprint_id"])
    op.create_index("ix_contract_review_runs_created_by_user_id", "contract_review_runs", ["created_by_user_id"])
    op.create_index("ix_contract_review_runs_blueprint_status", "contract_review_runs", ["blueprint_id", "status"])
    op.create_index("ix_contract_review_runs_workspace_created", "contract_review_runs", ["workspace_id", "created_at"])

    op.create_table(
        "contract_review_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("risk_matrix_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("negotiation_memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_review_outputs_workspace_id", "contract_review_outputs", ["workspace_id"])
    op.create_index("ix_contract_review_outputs_blueprint_id", "contract_review_outputs", ["blueprint_id"])
    op.create_index("ix_contract_review_outputs_run_id", "contract_review_outputs", ["run_id"])
    op.create_index("ix_contract_review_outputs_run", "contract_review_outputs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_review_outputs_run", table_name="contract_review_outputs")
    op.drop_index("ix_contract_review_outputs_run_id", table_name="contract_review_outputs")
    op.drop_index("ix_contract_review_outputs_blueprint_id", table_name="contract_review_outputs")
    op.drop_index("ix_contract_review_outputs_workspace_id", table_name="contract_review_outputs")
    op.drop_table("contract_review_outputs")
    op.drop_index("ix_contract_review_runs_workspace_created", table_name="contract_review_runs")
    op.drop_index("ix_contract_review_runs_blueprint_status", table_name="contract_review_runs")
    op.drop_index("ix_contract_review_runs_created_by_user_id", table_name="contract_review_runs")
    op.drop_index("ix_contract_review_runs_blueprint_id", table_name="contract_review_runs")
    op.drop_index("ix_contract_review_runs_workspace_id", table_name="contract_review_runs")
    op.drop_table("contract_review_runs")
    op.drop_index("ix_contract_review_configs_created_by_user_id", table_name="contract_review_configs")
    op.drop_index("ix_contract_review_configs_blueprint_id", table_name="contract_review_configs")
    op.drop_index("ix_contract_review_configs_workspace_id", table_name="contract_review_configs")
    op.drop_table("contract_review_configs")
