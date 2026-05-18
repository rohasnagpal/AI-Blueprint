"""v2 secrets

Revision ID: 0009_v2_secrets
Revises: 0008_skills_registry
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_v2_secrets"
down_revision = "0008_skills_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "owner_user_id", "name", "scope", name="uq_secrets_owner_name_scope"),
    )
    op.create_index("ix_secrets_workspace_id", "secrets", ["workspace_id"])
    op.create_index("ix_secrets_owner_user_id", "secrets", ["owner_user_id"])
    op.create_index("ix_secrets_created_by_user_id", "secrets", ["created_by_user_id"])
    op.create_index("ix_secrets_workspace_scope", "secrets", ["workspace_id", "scope"])


def downgrade() -> None:
    op.drop_index("ix_secrets_workspace_scope", table_name="secrets")
    op.drop_index("ix_secrets_created_by_user_id", table_name="secrets")
    op.drop_index("ix_secrets_owner_user_id", table_name="secrets")
    op.drop_index("ix_secrets_workspace_id", table_name="secrets")
    op.drop_table("secrets")
