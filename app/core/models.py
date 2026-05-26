from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_change_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Matter(Base):
    __tablename__ = "matters"
    __table_args__ = (
        Index("ix_matters_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BlueprintInstance(Base):
    __tablename__ = "blueprint_instances"
    __table_args__ = (
        Index("ix_blueprint_instances_workspace_status", "workspace_id", "status"),
        Index("ix_blueprint_instances_workspace_matter", "workspace_id", "matter_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str | None] = mapped_column(ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BlueprintMember(Base):
    __tablename__ = "blueprint_members"
    __table_args__ = (UniqueConstraint("blueprint_id", "user_id", name="uq_blueprint_members_blueprint_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Persona(Base):
    __tablename__ = "personas_v2"
    __table_args__ = (
        Index("ix_personas_v2_workspace_category", "workspace_id", "category"),
        Index("uq_personas_v2_workspace_name_effective", text("COALESCE(workspace_id, '__global__')"), "name", unique=True),
        UniqueConstraint("workspace_id", "name", name="uq_personas_v2_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Legal")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    constraints_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    output_format_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BlueprintPersona(Base):
    __tablename__ = "blueprint_personas"
    __table_args__ = (
        UniqueConstraint("blueprint_id", "persona_id", "role", name="uq_blueprint_personas_blueprint_persona_role"),
        Index("ix_blueprint_personas_blueprint_role", "blueprint_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="participant")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_runtime_settings_workspace_key"),
        Index("ix_runtime_settings_workspace_key", "workspace_id", "key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Escalation(Base):
    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_workspace_status", "workspace_id", "status"),
        Index("ix_escalations_blueprint_status", "blueprint_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str | None] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    required_action: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_workspace_created", "workspace_id", "created_at"),
        Index("ix_knowledge_documents_workspace_scope", "workspace_id", "scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str | None] = mapped_column(ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="workspace")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="registered")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentLink(Base):
    __tablename__ = "document_links"
    __table_args__ = (
        UniqueConstraint("document_id", "blueprint_id", "link_type", name="uq_document_links_document_blueprint_type"),
        Index("ix_document_links_blueprint_type", "blueprint_id", "link_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    link_type: Mapped[str] = mapped_column(String(64), nullable=False, default="source")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_document_index", "document_id", "chunk_index"),
        Index("ix_knowledge_chunks_workspace_document", "workspace_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "provider", "model", name="uq_knowledge_embeddings_chunk_provider_model"),
        Index("ix_knowledge_embeddings_workspace_model", "workspace_id", "provider", "model"),
        Index("ix_knowledge_embeddings_document", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CouncilConfig(Base):
    __tablename__ = "council_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CouncilRun(Base):
    __tablename__ = "council_runs_v2"
    __table_args__ = (
        Index("ix_council_runs_v2_blueprint_status", "blueprint_id", "status"),
        Index("ix_council_runs_v2_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CouncilOutput(Base):
    __tablename__ = "council_outputs_v2"
    __table_args__ = (Index("ix_council_outputs_v2_run_phase", "run_id", "phase_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("council_runs_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id: Mapped[str | None] = mapped_column(String(100))
    phase_name: Mapped[str | None] = mapped_column(String(255))
    agent_id: Mapped[str | None] = mapped_column(String(100))
    role_name: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CouncilEvidence(Base):
    __tablename__ = "council_evidence_v2"
    __table_args__ = (Index("ix_council_evidence_v2_run_phase", "run_id", "phase_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("council_runs_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id: Mapped[str | None] = mapped_column(String(100))
    phase_name: Mapped[str | None] = mapped_column(String(255))
    query: Mapped[str | None] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractReviewConfig(Base):
    __tablename__ = "contract_review_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractReviewRun(Base):
    __tablename__ = "contract_review_runs"
    __table_args__ = (
        Index("ix_contract_review_runs_blueprint_status", "blueprint_id", "status"),
        Index("ix_contract_review_runs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContractReviewOutput(Base):
    __tablename__ = "contract_review_outputs"
    __table_args__ = (Index("ix_contract_review_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    extraction_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risk_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    negotiation_memo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LegalResearchConfig(Base):
    __tablename__ = "legal_research_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LegalResearchRun(Base):
    __tablename__ = "legal_research_runs"
    __table_args__ = (
        Index("ix_legal_research_runs_blueprint_status", "blueprint_id", "status"),
        Index("ix_legal_research_runs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalResearchOutput(Base):
    __tablename__ = "legal_research_outputs"
    __table_args__ = (Index("ix_legal_research_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("legal_research_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    authority_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    legal_tests_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    citation_pack_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    research_memo: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    input_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SkillRun(Base):
    __tablename__ = "skill_runs"
    __table_args__ = (
        Index("ix_skill_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_skill_runs_blueprint_created", "blueprint_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str | None] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False, index=True)
    skill_version_id: Mapped[str | None] = mapped_column(ForeignKey("skill_versions.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = (
        Index("ix_secrets_workspace_scope", "workspace_id", "scope"),
        UniqueConstraint("workspace_id", "owner_user_id", "name", "scope", name="uq_secrets_owner_name_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PluginEnablement(Base):
    __tablename__ = "plugin_enablements"
    __table_args__ = (UniqueConstraint("workspace_id", "plugin_id", name="uq_plugin_enablements_workspace_plugin"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_workspace_status", "workspace_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
