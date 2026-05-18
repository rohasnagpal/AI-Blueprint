"""v2 escalations

Revision ID: 0012_v2_escalations
Revises: 0011_v2_runtime_settings
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_v2_escalations"
down_revision = "0011_v2_runtime_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "escalations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE")),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=100)),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("required_action", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_escalations_workspace_id", "escalations", ["workspace_id"])
    op.create_index("ix_escalations_blueprint_id", "escalations", ["blueprint_id"])
    op.create_index("ix_escalations_created_by_user_id", "escalations", ["created_by_user_id"])
    op.create_index("ix_escalations_resolved_by_user_id", "escalations", ["resolved_by_user_id"])
    op.create_index("ix_escalations_workspace_status", "escalations", ["workspace_id", "status"])
    op.create_index("ix_escalations_blueprint_status", "escalations", ["blueprint_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_escalations_blueprint_status", table_name="escalations")
    op.drop_index("ix_escalations_workspace_status", table_name="escalations")
    op.drop_index("ix_escalations_resolved_by_user_id", table_name="escalations")
    op.drop_index("ix_escalations_created_by_user_id", table_name="escalations")
    op.drop_index("ix_escalations_blueprint_id", table_name="escalations")
    op.drop_index("ix_escalations_workspace_id", table_name="escalations")
    op.drop_table("escalations")
