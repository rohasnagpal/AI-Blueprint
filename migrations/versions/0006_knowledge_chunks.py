"""knowledge chunks

Revision ID: 0006_knowledge_chunks
Revises: 0005_job_events
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_knowledge_chunks"
down_revision = "0005_job_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_workspace_id", "knowledge_chunks", ["workspace_id"])
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_document_index", "knowledge_chunks", ["document_id", "chunk_index"])
    op.create_index("ix_knowledge_chunks_workspace_document", "knowledge_chunks", ["workspace_id", "document_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_workspace_document", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_index", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_workspace_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
