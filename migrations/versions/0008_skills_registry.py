"""skills registry

Revision ID: 0008_skills_registry
Revises: 0007_contract_review_plugin
Create Date: 2026-05-18
"""

from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0008_skills_registry"
down_revision = "0007_contract_review_plugin"
branch_labels = None
depends_on = None


SEED_SKILLS = [
    ("contract.extract_fields", "Contract Field Extraction", "Extract structured fields from indexed contract text.", "contract_review"),
    ("contract.risk_matrix", "Contract Risk Matrix", "Identify review issue areas and severity from contract text.", "contract_review"),
    ("contract.negotiation_memo", "Negotiation Memo", "Generate a negotiation memo from extraction and risk findings.", "contract_review"),
    ("contract.client_summary", "Client Summary", "Generate a concise client-facing review summary.", "contract_review"),
]


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("input_schema_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_schema_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("skill_id", sa.String(length=100), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False, server_default=""),
        sa.Column("validation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),
    )
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.create_table(
        "skill_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE")),
        sa.Column("skill_id", sa.String(length=100), sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("skill_version_id", sa.String(length=36), sa.ForeignKey("skill_versions.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_skill_runs_workspace_id", "skill_runs", ["workspace_id"])
    op.create_index("ix_skill_runs_blueprint_id", "skill_runs", ["blueprint_id"])
    op.create_index("ix_skill_runs_skill_id", "skill_runs", ["skill_id"])
    op.create_index("ix_skill_runs_skill_version_id", "skill_runs", ["skill_version_id"])
    op.create_index("ix_skill_runs_created_by_user_id", "skill_runs", ["created_by_user_id"])
    op.create_index("ix_skill_runs_workspace_created", "skill_runs", ["workspace_id", "created_at"])
    op.create_index("ix_skill_runs_blueprint_created", "skill_runs", ["blueprint_id", "created_at"])

    now = datetime.now(timezone.utc)
    skills = sa.table(
        "skills",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("category", sa.String),
        sa.column("owner", sa.String),
        sa.column("input_schema_json", sa.Text),
        sa.column("output_schema_json", sa.Text),
        sa.column("is_enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    versions = sa.table(
        "skill_versions",
        sa.column("id", sa.String),
        sa.column("skill_id", sa.String),
        sa.column("version", sa.String),
        sa.column("prompt_template", sa.Text),
        sa.column("validation_json", sa.Text),
        sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(
        skills,
        [
            {
                "id": skill_id,
                "name": name,
                "description": description,
                "category": "legal",
                "owner": owner,
                "input_schema_json": json.dumps({}),
                "output_schema_json": json.dumps({}),
                "is_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for skill_id, name, description, owner in SEED_SKILLS
        ],
    )
    op.bulk_insert(
        versions,
        [
            {
                "id": str(uuid.uuid4()),
                "skill_id": skill_id,
                "version": "1.0.0",
                "prompt_template": "deterministic",
                "validation_json": json.dumps({}),
                "created_at": now,
            }
            for skill_id, _name, _description, _owner in SEED_SKILLS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_skill_runs_blueprint_created", table_name="skill_runs")
    op.drop_index("ix_skill_runs_workspace_created", table_name="skill_runs")
    op.drop_index("ix_skill_runs_created_by_user_id", table_name="skill_runs")
    op.drop_index("ix_skill_runs_skill_version_id", table_name="skill_runs")
    op.drop_index("ix_skill_runs_skill_id", table_name="skill_runs")
    op.drop_index("ix_skill_runs_blueprint_id", table_name="skill_runs")
    op.drop_index("ix_skill_runs_workspace_id", table_name="skill_runs")
    op.drop_table("skill_runs")
    op.drop_index("ix_skill_versions_skill_id", table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_table("skills")
