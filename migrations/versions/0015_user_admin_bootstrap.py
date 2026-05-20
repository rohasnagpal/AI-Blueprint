"""user admin bootstrap

Revision ID: 0015_user_admin_bootstrap
Revises: 0014_workspace_soft_delete
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_user_admin_bootstrap"
down_revision = "0014_workspace_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=100)))
    op.add_column("users", sa.Column("must_change_credentials", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.execute("UPDATE users SET username = email WHERE username IS NULL")
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "must_change_credentials")
    op.drop_column("users", "username")
