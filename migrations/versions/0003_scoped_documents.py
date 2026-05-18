"""scoped documents

Revision ID: 0003_scoped_documents
Revises: 0002_blueprint_instances
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_scoped_documents"
down_revision = "0002_blueprint_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="SET NULL")),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=500)),
        sa.Column("content_hash", sa.String(length=128)),
        sa.Column("mime_type", sa.String(length=255)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="workspace"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="registered"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_documents_workspace_id", "knowledge_documents", ["workspace_id"])
    op.create_index("ix_knowledge_documents_matter_id", "knowledge_documents", ["matter_id"])
    op.create_index("ix_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"])
    op.create_index("ix_knowledge_documents_created_by_user_id", "knowledge_documents", ["created_by_user_id"])
    op.create_index("ix_knowledge_documents_workspace_created", "knowledge_documents", ["workspace_id", "created_at"])
    op.create_index("ix_knowledge_documents_workspace_scope", "knowledge_documents", ["workspace_id", "scope"])

    op.create_table(
        "document_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False, server_default="source"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "blueprint_id", "link_type", name="uq_document_links_document_blueprint_type"),
    )
    op.create_index("ix_document_links_workspace_id", "document_links", ["workspace_id"])
    op.create_index("ix_document_links_document_id", "document_links", ["document_id"])
    op.create_index("ix_document_links_blueprint_id", "document_links", ["blueprint_id"])
    op.create_index("ix_document_links_created_by_user_id", "document_links", ["created_by_user_id"])
    op.create_index("ix_document_links_blueprint_type", "document_links", ["blueprint_id", "link_type"])


def downgrade() -> None:
    op.drop_index("ix_document_links_blueprint_type", table_name="document_links")
    op.drop_index("ix_document_links_created_by_user_id", table_name="document_links")
    op.drop_index("ix_document_links_blueprint_id", table_name="document_links")
    op.drop_index("ix_document_links_document_id", table_name="document_links")
    op.drop_index("ix_document_links_workspace_id", table_name="document_links")
    op.drop_table("document_links")
    op.drop_index("ix_knowledge_documents_workspace_scope", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_workspace_created", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_created_by_user_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_matter_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_workspace_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
