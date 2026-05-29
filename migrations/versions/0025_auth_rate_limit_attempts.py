"""auth rate limit attempts

Revision ID: 0025_auth_rate_limit_attempts
Revises: 0024_draft_runs
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_auth_rate_limit_attempts"
down_revision = "0024_draft_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limit_attempts",
        sa.Column("client_key", sa.Text(), nullable=False),
        sa.Column("attempted_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_auth_rate_limit_attempts_key_time",
        "auth_rate_limit_attempts",
        ["client_key", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limit_attempts_key_time", table_name="auth_rate_limit_attempts")
    op.drop_table("auth_rate_limit_attempts")
