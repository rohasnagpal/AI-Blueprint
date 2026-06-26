from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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


class DocumentFolderSource(Base):
    __tablename__ = "document_folder_sources"
    __table_args__ = (
        Index("ix_document_folder_sources_workspace_matter", "workspace_id", "matter_id"),
        Index("ix_document_folder_sources_workspace_type", "workspace_id", "source_type"),
        UniqueConstraint("workspace_id", "matter_id", "source_type", "path", name="uq_document_folder_sources_scope_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="local_path")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentFolderFile(Base):
    __tablename__ = "document_folder_files"
    __table_args__ = (
        UniqueConstraint("folder_source_id", "source_path", name="uq_document_folder_files_source_path"),
        Index("ix_document_folder_files_workspace_matter", "workspace_id", "matter_id"),
        Index("ix_document_folder_files_document_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    folder_source_id: Mapped[str] = mapped_column(ForeignKey("document_folder_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    mtime: Mapped[float | None] = mapped_column(Float)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


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
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="workflow")
    workflow_version: Mapped[str | None] = mapped_column(String(50))
    status_detail: Mapped[str | None] = mapped_column(Text)
    selected_playbook_id: Mapped[str | None] = mapped_column(String(36), index=True)
    coverage_score: Mapped[float | None] = mapped_column(Float)
    source_anchor_version: Mapped[str | None] = mapped_column(String(50))
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


class ContractPlaybook(Base):
    __tablename__ = "contract_playbooks"
    __table_args__ = (
        Index("ix_contract_playbooks_workspace_category", "workspace_id", "contract_category"),
        Index("ix_contract_playbooks_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_category: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractPlaybookClause(Base):
    __tablename__ = "contract_playbook_clauses"
    __table_args__ = (
        Index("ix_contract_playbook_clauses_playbook_type", "playbook_id", "clause_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    playbook_id: Mapped[str] = mapped_column(ForeignKey("contract_playbooks.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_text: Mapped[str | None] = mapped_column(Text)
    fallback_text: Mapped[str | None] = mapped_column(Text)
    prohibited_patterns_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity_default: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractClause(Base):
    __tablename__ = "contract_clauses"
    __table_args__ = (
        Index("ix_contract_clauses_run_type", "run_id", "clause_type"),
        Index("ix_contract_clauses_run_review", "run_id", "review_status"),
        Index("ix_contract_clauses_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    clause_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    source_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractPlaybookFinding(Base):
    __tablename__ = "contract_playbook_findings"
    __table_args__ = (
        Index("ix_contract_playbook_findings_run_status", "run_id", "status"),
        Index("ix_contract_playbook_findings_clause", "clause_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id: Mapped[str | None] = mapped_column(ForeignKey("contract_clauses.id", ondelete="CASCADE"), index=True)
    playbook_id: Mapped[str | None] = mapped_column(ForeignKey("contract_playbooks.id", ondelete="SET NULL"), index=True)
    playbook_clause_id: Mapped[str | None] = mapped_column(ForeignKey("contract_playbook_clauses.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    deviation_summary: Mapped[str | None] = mapped_column(Text)
    missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prohibited_match: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractRiskFinding(Base):
    __tablename__ = "contract_risk_findings"
    __table_args__ = (
        Index("ix_contract_risk_findings_run_level", "run_id", "risk_level"),
        Index("ix_contract_risk_findings_clause", "clause_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id: Mapped[str | None] = mapped_column(ForeignKey("contract_clauses.id", ondelete="CASCADE"), index=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    likelihood: Mapped[str | None] = mapped_column(String(50))
    impact: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int | None] = mapped_column(Integer)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractRedlineSuggestion(Base):
    __tablename__ = "contract_redline_suggestions"
    __table_args__ = (
        Index("ix_contract_redline_suggestions_run_status", "run_id", "status"),
        Index("ix_contract_redline_suggestions_clause", "clause_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id: Mapped[str] = mapped_column(ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_language: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    source_playbook_id: Mapped[str | None] = mapped_column(ForeignKey("contract_playbooks.id", ondelete="SET NULL"), index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractReviewSummary(Base):
    __tablename__ = "contract_review_summaries"
    __table_args__ = (
        UniqueConstraint("run_id", "audience", name="uq_contract_review_summaries_run_audience"),
        Index("ix_contract_review_summaries_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    audience: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    obligations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    negotiation_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    unusual_terms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractReviewStepOutput(Base):
    __tablename__ = "contract_review_step_outputs"
    __table_args__ = (
        Index("ix_contract_review_step_outputs_run_step", "run_id", "step_name"),
        Index("ix_contract_review_step_outputs_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ContractClauseReviewDecision(Base):
    __tablename__ = "contract_clause_review_decisions"
    __table_args__ = (
        Index("ix_contract_clause_review_decisions_clause", "clause_id"),
        Index("ix_contract_clause_review_decisions_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("contract_review_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id: Mapped[str] = mapped_column(ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    prior_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationPrepRun(Base):
    __tablename__ = "arbitration_prep_runs"
    __table_args__ = (
        Index("ix_arbitration_prep_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_arbitration_prep_runs_matter_status", "matter_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    status_detail: Mapped[str | None] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workflow_version: Mapped[str | None] = mapped_column(String(50))
    source_anchor_version: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArbitrationPrepOutput(Base):
    __tablename__ = "arbitration_prep_outputs"
    __table_args__ = (Index("ix_arbitration_prep_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    chronology_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    witness_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    argument_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cross_examination_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    procedural_tasks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    damages_and_remedies_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risks_and_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    client_or_team_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    agentic_review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationIssue(Base):
    __tablename__ = "arbitration_issues"
    __table_args__ = (Index("ix_arbitration_issues_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proof_elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    burdens_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disputed_facts_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationChronologyEvent(Base):
    __tablename__ = "arbitration_chronology_events"
    __table_args__ = (Index("ix_arbitration_chronology_events_run_date", "run_id", "event_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    event_date: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str | None] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationEvidenceItem(Base):
    __tablename__ = "arbitration_evidence_items"
    __table_args__ = (Index("ix_arbitration_evidence_items_run_issue", "run_id", "issue_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("arbitration_issues.id", ondelete="SET NULL"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="supporting")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationWitness(Base):
    __tablename__ = "arbitration_witnesses"
    __table_args__ = (Index("ix_arbitration_witnesses_run_name", "run_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255))
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prep_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationArgument(Base):
    __tablename__ = "arbitration_arguments"
    __table_args__ = (Index("ix_arbitration_arguments_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    theme: Mapped[str] = mapped_column(String(255), nullable=False)
    strongest_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    opponent_responses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationProceduralTask(Base):
    __tablename__ = "arbitration_procedural_tasks"
    __table_args__ = (Index("ix_arbitration_procedural_tasks_run_due", "run_id", "due_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, default="obligation")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(50), index=True)
    compliance_risk: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationRiskItem(Base):
    __tablename__ = "arbitration_risk_items"
    __table_args__ = (Index("ix_arbitration_risk_items_run_level", "run_id", "risk_level"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    leverage: Mapped[str | None] = mapped_column(Text)
    decision_point: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationAgentStepOutput(Base):
    __tablename__ = "arbitration_agent_step_outputs"
    __table_args__ = (
        Index("ix_arbitration_agent_step_outputs_run_step", "run_id", "step_name"),
        Index("ix_arbitration_agent_step_outputs_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ArbitrationReviewDecision(Base):
    __tablename__ = "arbitration_review_decisions"
    __table_args__ = (Index("ix_arbitration_review_decisions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("arbitration_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    prior_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationPrepRun(Base):
    __tablename__ = "litigation_prep_runs"
    __table_args__ = (
        Index("ix_litigation_prep_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_litigation_prep_runs_matter_status", "matter_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    status_detail: Mapped[str | None] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workflow_version: Mapped[str | None] = mapped_column(String(50))
    source_anchor_version: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LitigationPrepOutput(Base):
    __tablename__ = "litigation_prep_outputs"
    __table_args__ = (Index("ix_litigation_prep_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    claims_and_defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    chronology_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    discovery_analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    witness_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    deposition_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    motion_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    trial_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    argument_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cross_examination_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    procedural_tasks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    damages_and_remedies_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risks_and_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    client_or_team_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    agentic_review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationIssue(Base):
    __tablename__ = "litigation_issues"
    __table_args__ = (Index("ix_litigation_issues_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proof_elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    burdens_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disputed_facts_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationClaim(Base):
    __tablename__ = "litigation_claims"
    __table_args__ = (Index("ix_litigation_claims_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False, default="claim")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationChronologyEvent(Base):
    __tablename__ = "litigation_chronology_events"
    __table_args__ = (Index("ix_litigation_chronology_events_run_date", "run_id", "event_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    event_date: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str | None] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationEvidenceItem(Base):
    __tablename__ = "litigation_evidence_items"
    __table_args__ = (Index("ix_litigation_evidence_items_run_issue", "run_id", "issue_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("litigation_issues.id", ondelete="SET NULL"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="supporting")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationWitness(Base):
    __tablename__ = "litigation_witnesses"
    __table_args__ = (Index("ix_litigation_witnesses_run_name", "run_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255))
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prep_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationDepositionTopic(Base):
    __tablename__ = "litigation_deposition_topics"
    __table_args__ = (Index("ix_litigation_deposition_topics_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    witness_name: Mapped[str] = mapped_column(String(255), nullable=False)
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    anchors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationArgument(Base):
    __tablename__ = "litigation_arguments"
    __table_args__ = (Index("ix_litigation_arguments_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    theme: Mapped[str] = mapped_column(String(255), nullable=False)
    strongest_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    opponent_responses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationProceduralTask(Base):
    __tablename__ = "litigation_procedural_tasks"
    __table_args__ = (Index("ix_litigation_procedural_tasks_run_due", "run_id", "due_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, default="obligation")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(50), index=True)
    compliance_risk: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationMotion(Base):
    __tablename__ = "litigation_motions"
    __table_args__ = (Index("ix_litigation_motions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    motion_type: Mapped[str] = mapped_column(String(100), nullable=False, default="motion")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    support_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationDiscoveryItem(Base):
    __tablename__ = "litigation_discovery_items"
    __table_args__ = (Index("ix_litigation_discovery_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="discovery")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(100))
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationDamagesItem(Base):
    __tablename__ = "litigation_damages_items"
    __table_args__ = (Index("ix_litigation_damages_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="damages")
    amount: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationRiskItem(Base):
    __tablename__ = "litigation_risk_items"
    __table_args__ = (Index("ix_litigation_risk_items_run_level", "run_id", "risk_level"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    leverage: Mapped[str | None] = mapped_column(Text)
    decision_point: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationAgentStepOutput(Base):
    __tablename__ = "litigation_agent_step_outputs"
    __table_args__ = (
        Index("ix_litigation_agent_step_outputs_run_step", "run_id", "step_name"),
        Index("ix_litigation_agent_step_outputs_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LitigationReviewDecision(Base):
    __tablename__ = "litigation_review_decisions"
    __table_args__ = (Index("ix_litigation_review_decisions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("litigation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    prior_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)



class MediationPrepRun(Base):
    __tablename__ = "mediation_prep_runs"
    __table_args__ = (
        Index("ix_mediation_prep_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_mediation_prep_runs_matter_status", "matter_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    status_detail: Mapped[str | None] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workflow_version: Mapped[str | None] = mapped_column(String(50))
    source_anchor_version: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediationPrepOutput(Base):
    __tablename__ = "mediation_prep_outputs"
    __table_args__ = (Index("ix_mediation_prep_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    claims_and_defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    positions_and_interests_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    chronology_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    discovery_analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    witness_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    deposition_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    motion_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    trial_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    argument_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cross_examination_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    batna_watna_zopa_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risk_allocation_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    settlement_levers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    caucus_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    impasse_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bridge_proposals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    mediator_private_prep_note_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    one_page_session_plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    procedural_tasks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    damages_and_remedies_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risks_and_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    client_or_team_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    agentic_review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationIssue(Base):
    __tablename__ = "mediation_issues"
    __table_args__ = (Index("ix_mediation_issues_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proof_elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    burdens_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disputed_facts_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationClaim(Base):
    __tablename__ = "mediation_claims"
    __table_args__ = (Index("ix_mediation_claims_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False, default="claim")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationChronologyEvent(Base):
    __tablename__ = "mediation_chronology_events"
    __table_args__ = (Index("ix_mediation_chronology_events_run_date", "run_id", "event_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    event_date: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str | None] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationEvidenceItem(Base):
    __tablename__ = "mediation_evidence_items"
    __table_args__ = (Index("ix_mediation_evidence_items_run_issue", "run_id", "issue_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("mediation_issues.id", ondelete="SET NULL"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="supporting")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationWitness(Base):
    __tablename__ = "mediation_witnesses"
    __table_args__ = (Index("ix_mediation_witnesses_run_name", "run_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255))
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prep_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationDepositionTopic(Base):
    __tablename__ = "mediation_deposition_topics"
    __table_args__ = (Index("ix_mediation_deposition_topics_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    witness_name: Mapped[str] = mapped_column(String(255), nullable=False)
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    anchors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationArgument(Base):
    __tablename__ = "mediation_arguments"
    __table_args__ = (Index("ix_mediation_arguments_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    theme: Mapped[str] = mapped_column(String(255), nullable=False)
    strongest_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    opponent_responses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationProceduralTask(Base):
    __tablename__ = "mediation_procedural_tasks"
    __table_args__ = (Index("ix_mediation_procedural_tasks_run_due", "run_id", "due_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, default="obligation")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(50), index=True)
    compliance_risk: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationMotion(Base):
    __tablename__ = "mediation_motions"
    __table_args__ = (Index("ix_mediation_motions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    motion_type: Mapped[str] = mapped_column(String(100), nullable=False, default="motion")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    support_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationDiscoveryItem(Base):
    __tablename__ = "mediation_discovery_items"
    __table_args__ = (Index("ix_mediation_discovery_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="discovery")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(100))
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationDamagesItem(Base):
    __tablename__ = "mediation_damages_items"
    __table_args__ = (Index("ix_mediation_damages_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="damages")
    amount: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationRiskItem(Base):
    __tablename__ = "mediation_risk_items"
    __table_args__ = (Index("ix_mediation_risk_items_run_level", "run_id", "risk_level"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    leverage: Mapped[str | None] = mapped_column(Text)
    decision_point: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationAgentStepOutput(Base):
    __tablename__ = "mediation_agent_step_outputs"
    __table_args__ = (
        Index("ix_mediation_agent_step_outputs_run_step", "run_id", "step_name"),
        Index("ix_mediation_agent_step_outputs_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MediationReviewDecision(Base):
    __tablename__ = "mediation_review_decisions"
    __table_args__ = (Index("ix_mediation_review_decisions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("mediation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    prior_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)




class NegotiationPrepRun(Base):
    __tablename__ = "negotiation_prep_runs"
    __table_args__ = (
        Index("ix_negotiation_prep_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_negotiation_prep_runs_matter_status", "matter_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    status_detail: Mapped[str | None] = mapped_column(Text)
    config_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workflow_version: Mapped[str | None] = mapped_column(String(50))
    source_anchor_version: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NegotiationPrepOutput(Base):
    __tablename__ = "negotiation_prep_outputs"
    __table_args__ = (Index("ix_negotiation_prep_outputs_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    case_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    claims_and_defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    chronology_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    evidence_matrix_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    discovery_analysis_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    witness_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    deposition_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    motion_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    trial_prep_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    argument_strategy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cross_examination_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    procedural_tasks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    damages_and_remedies_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    risks_and_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    client_or_team_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    agentic_review_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationIssue(Base):
    __tablename__ = "negotiation_issues"
    __table_args__ = (Index("ix_negotiation_issues_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proof_elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    burdens_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disputed_facts_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationClaim(Base):
    __tablename__ = "negotiation_claims"
    __table_args__ = (Index("ix_negotiation_claims_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False, default="claim")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    defenses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_proof_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationChronologyEvent(Base):
    __tablename__ = "negotiation_chronology_events"
    __table_args__ = (Index("ix_negotiation_chronology_events_run_date", "run_id", "event_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    event_date: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[str | None] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationEvidenceItem(Base):
    __tablename__ = "negotiation_evidence_items"
    __table_args__ = (Index("ix_negotiation_evidence_items_run_issue", "run_id", "issue_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("negotiation_issues.id", ondelete="SET NULL"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="supporting")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationWitness(Base):
    __tablename__ = "negotiation_witnesses"
    __table_args__ = (Index("ix_negotiation_witnesses_run_name", "run_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255))
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    admissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    prep_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationDepositionTopic(Base):
    __tablename__ = "negotiation_deposition_topics"
    __table_args__ = (Index("ix_negotiation_deposition_topics_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    witness_name: Mapped[str] = mapped_column(String(255), nullable=False)
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    anchors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationArgument(Base):
    __tablename__ = "negotiation_arguments"
    __table_args__ = (Index("ix_negotiation_arguments_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    theme: Mapped[str] = mapped_column(String(255), nullable=False)
    strongest_points_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    opponent_responses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationProceduralTask(Base):
    __tablename__ = "negotiation_procedural_tasks"
    __table_args__ = (Index("ix_negotiation_procedural_tasks_run_due", "run_id", "due_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, default="obligation")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(50), index=True)
    compliance_risk: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationMotion(Base):
    __tablename__ = "negotiation_motions"
    __table_args__ = (Index("ix_negotiation_motions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    motion_type: Mapped[str] = mapped_column(String(100), nullable=False, default="motion")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    support_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    vulnerabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationDiscoveryItem(Base):
    __tablename__ = "negotiation_discovery_items"
    __table_args__ = (Index("ix_negotiation_discovery_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="discovery")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(100))
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationDamagesItem(Base):
    __tablename__ = "negotiation_damages_items"
    __table_args__ = (Index("ix_negotiation_damages_items_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, default="damages")
    amount: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationRiskItem(Base):
    __tablename__ = "negotiation_risk_items"
    __table_args__ = (Index("ix_negotiation_risk_items_run_level", "run_id", "risk_level"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="SET NULL"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id", ondelete="SET NULL"), index=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    leverage: Mapped[str | None] = mapped_column(Text)
    decision_point: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationAgentStepOutput(Base):
    __tablename__ = "negotiation_agent_step_outputs"
    __table_args__ = (
        Index("ix_negotiation_agent_step_outputs_run_step", "run_id", "step_name"),
        Index("ix_negotiation_agent_step_outputs_workspace_run", "workspace_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NegotiationReviewDecision(Base):
    __tablename__ = "negotiation_review_decisions"
    __table_args__ = (Index("ix_negotiation_review_decisions_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("negotiation_prep_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    prior_status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
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


class TranslationRun(Base):
    __tablename__ = "translation_runs"
    __table_args__ = (
        Index("ix_translation_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_translation_runs_workspace_mode", "workspace_id", "mode"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str | None] = mapped_column(ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(500))
    source_language: Mapped[str] = mapped_column(String(100), nullable=False, default="auto")
    detected_language: Mapped[str | None] = mapped_column(String(100))
    target_language: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    source_text_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    translated_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translator_notes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    quality_check_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    preserved_terms_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="completed")
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DraftRun(Base):
    __tablename__ = "draft_runs"
    __table_args__ = (
        Index("ix_draft_runs_workspace_created", "workspace_id", "created_at"),
        Index("ix_draft_runs_workspace_document_type", "workspace_id", "document_type"),
        Index("ix_draft_runs_workspace_id", "workspace_id"),
        Index("ix_draft_runs_matter_id", "matter_id"),
        Index("ix_draft_runs_created_by_user_id", "created_by_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[str | None] = mapped_column(ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(150))
    tone: Mapped[str] = mapped_column(String(100), nullable=False, default="formal")
    audience: Mapped[str | None] = mapped_column(String(255))
    facts_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    draft_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    draft_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assumptions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    missing_information_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    review_warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="completed")
    error: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
