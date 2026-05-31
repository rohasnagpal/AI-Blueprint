"""document folder sources

Revision ID: 0028_document_folder_sources
Revises: 0027_litigation_prep
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_document_folder_sources"
down_revision = "0027_litigation_prep"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_folder_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="local_path"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "matter_id", "source_type", "path", name="uq_document_folder_sources_scope_path"),
    )
    op.create_index("ix_document_folder_sources_workspace_id", "document_folder_sources", ["workspace_id"])
    op.create_index("ix_document_folder_sources_matter_id", "document_folder_sources", ["matter_id"])
    op.create_index("ix_document_folder_sources_created_by_user_id", "document_folder_sources", ["created_by_user_id"])
    op.create_index("ix_document_folder_sources_workspace_matter", "document_folder_sources", ["workspace_id", "matter_id"])
    op.create_index("ix_document_folder_sources_workspace_type", "document_folder_sources", ["workspace_id", "source_type"])

    op.create_table(
        "document_folder_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("folder_source_id", sa.String(length=36), sa.ForeignKey("document_folder_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("mtime", sa.Float(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("folder_source_id", "source_path", name="uq_document_folder_files_source_path"),
    )
    op.create_index("ix_document_folder_files_folder_source_id", "document_folder_files", ["folder_source_id"])
    op.create_index("ix_document_folder_files_workspace_id", "document_folder_files", ["workspace_id"])
    op.create_index("ix_document_folder_files_matter_id", "document_folder_files", ["matter_id"])
    op.create_index("ix_document_folder_files_document_id", "document_folder_files", ["document_id"])
    op.create_index("ix_document_folder_files_content_hash", "document_folder_files", ["content_hash"])
    op.create_index("ix_document_folder_files_workspace_matter", "document_folder_files", ["workspace_id", "matter_id"])


def downgrade() -> None:
    op.drop_table("document_folder_files")
    op.drop_table("document_folder_sources")
