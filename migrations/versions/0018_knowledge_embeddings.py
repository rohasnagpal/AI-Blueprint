"""knowledge embeddings

Revision ID: 0018_knowledge_embeddings
Revises: 0017_persona_effective_name_unique
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_knowledge_embeddings"
down_revision = "0017_persona_effective_name_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chunk_id", "provider", "model", name="uq_knowledge_embeddings_chunk_provider_model"),
    )
    op.create_index("ix_knowledge_embeddings_workspace_id", "knowledge_embeddings", ["workspace_id"])
    op.create_index("ix_knowledge_embeddings_document_id", "knowledge_embeddings", ["document_id"])
    op.create_index("ix_knowledge_embeddings_chunk_id", "knowledge_embeddings", ["chunk_id"])
    op.create_index("ix_knowledge_embeddings_document", "knowledge_embeddings", ["document_id"])
    op.create_index(
        "ix_knowledge_embeddings_workspace_model",
        "knowledge_embeddings",
        ["workspace_id", "provider", "model"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_embeddings_workspace_model", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_document", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_chunk_id", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_document_id", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_workspace_id", table_name="knowledge_embeddings")
    op.drop_table("knowledge_embeddings")
