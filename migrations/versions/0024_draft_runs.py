"""draft runs

Revision ID: 0024_draft_runs
Revises: 0023_translation_runs
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_draft_runs"
down_revision = "0023_translation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("jurisdiction", sa.String(length=150), nullable=True),
        sa.Column("tone", sa.String(length=100), nullable=False, server_default="formal"),
        sa.Column("audience", sa.String(length=255), nullable=True),
        sa.Column("facts_hash", sa.String(length=128), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("draft_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("draft_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("assumptions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("missing_information_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("review_warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_draft_runs_workspace_created", "draft_runs", ["workspace_id", "created_at"])
    op.create_index("ix_draft_runs_workspace_document_type", "draft_runs", ["workspace_id", "document_type"])
    op.create_index("ix_draft_runs_workspace_id", "draft_runs", ["workspace_id"])
    op.create_index("ix_draft_runs_matter_id", "draft_runs", ["matter_id"])
    op.create_index("ix_draft_runs_created_by_user_id", "draft_runs", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_draft_runs_created_by_user_id", table_name="draft_runs")
    op.drop_index("ix_draft_runs_matter_id", table_name="draft_runs")
    op.drop_index("ix_draft_runs_workspace_id", table_name="draft_runs")
    op.drop_index("ix_draft_runs_workspace_document_type", table_name="draft_runs")
    op.drop_index("ix_draft_runs_workspace_created", table_name="draft_runs")
    op.drop_table("draft_runs")
