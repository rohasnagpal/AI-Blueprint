"""v2 runtime settings

Revision ID: 0011_v2_runtime_settings
Revises: 0010_v2_personas
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_v2_runtime_settings"
down_revision = "0010_v2_personas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=50), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "key", name="uq_runtime_settings_workspace_key"),
    )
    op.create_index("ix_runtime_settings_workspace_id", "runtime_settings", ["workspace_id"])
    op.create_index("ix_runtime_settings_updated_by_user_id", "runtime_settings", ["updated_by_user_id"])
    op.create_index("ix_runtime_settings_workspace_key", "runtime_settings", ["workspace_id", "key"])


def downgrade() -> None:
    op.drop_index("ix_runtime_settings_workspace_key", table_name="runtime_settings")
    op.drop_index("ix_runtime_settings_updated_by_user_id", table_name="runtime_settings")
    op.drop_index("ix_runtime_settings_workspace_id", table_name="runtime_settings")
    op.drop_table("runtime_settings")
