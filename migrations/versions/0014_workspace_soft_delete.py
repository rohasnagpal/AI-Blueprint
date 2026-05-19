"""workspace soft delete

Revision ID: 0014_workspace_soft_delete
Revises: 0013_v2_legal_research
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_workspace_soft_delete"
down_revision = "0013_v2_legal_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workspaces_deleted_at", "workspaces", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_workspaces_deleted_at", table_name="workspaces")
    op.drop_column("workspaces", "deleted_at")
