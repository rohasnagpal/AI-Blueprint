"""translation runs

Revision ID: 0023_translation_runs
Revises: 0022_contract_review_commercial_playbooks
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_translation_runs"
down_revision = "0022_contract_review_commercial_playbooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_filename", sa.String(length=500), nullable=True),
        sa.Column("source_language", sa.String(length=100), nullable=False, server_default="auto"),
        sa.Column("detected_language", sa.String(length=100), nullable=True),
        sa.Column("target_language", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("source_text_hash", sa.String(length=128), nullable=False),
        sa.Column("translated_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("translated_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("translator_notes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("quality_check_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preserved_terms_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="completed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_translation_runs_workspace_created", "translation_runs", ["workspace_id", "created_at"])
    op.create_index("ix_translation_runs_workspace_mode", "translation_runs", ["workspace_id", "mode"])
    op.create_index("ix_translation_runs_workspace_id", "translation_runs", ["workspace_id"])
    op.create_index("ix_translation_runs_matter_id", "translation_runs", ["matter_id"])
    op.create_index("ix_translation_runs_source_text_hash", "translation_runs", ["source_text_hash"])
    op.create_index("ix_translation_runs_created_by_user_id", "translation_runs", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_translation_runs_created_by_user_id", table_name="translation_runs")
    op.drop_index("ix_translation_runs_source_text_hash", table_name="translation_runs")
    op.drop_index("ix_translation_runs_matter_id", table_name="translation_runs")
    op.drop_index("ix_translation_runs_workspace_id", table_name="translation_runs")
    op.drop_index("ix_translation_runs_workspace_mode", table_name="translation_runs")
    op.drop_index("ix_translation_runs_workspace_created", table_name="translation_runs")
    op.drop_table("translation_runs")
