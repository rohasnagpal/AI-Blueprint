"""v2 legal research plugin

Revision ID: 0013_v2_legal_research
Revises: 0012_v2_escalations
Create Date: 2026-05-18
"""

from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0013_v2_legal_research"
down_revision = "0012_v2_escalations"
branch_labels = None
depends_on = None


SEED_SKILLS = [
    ("research.authority_finder", "Authority Finder", "Extract candidate authorities from linked research material."),
    ("research.legal_test", "Legal Test Extraction", "Identify legal test elements and supporting text."),
    ("research.citation_pack", "Citation Pack", "Build a citation and evidence pack for a research memo."),
    ("research.memo", "Research Memo", "Generate an issue-rule-application-conclusion research memo."),
]


def upgrade() -> None:
    op.create_table(
        "legal_research_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("blueprint_id", name="uq_legal_research_configs_blueprint_id"),
    )
    op.create_index("ix_legal_research_configs_workspace_id", "legal_research_configs", ["workspace_id"])
    op.create_index("ix_legal_research_configs_blueprint_id", "legal_research_configs", ["blueprint_id"], unique=True)
    op.create_index("ix_legal_research_configs_created_by_user_id", "legal_research_configs", ["created_by_user_id"])

    op.create_table(
        "legal_research_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("config_snapshot_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_legal_research_runs_workspace_id", "legal_research_runs", ["workspace_id"])
    op.create_index("ix_legal_research_runs_blueprint_id", "legal_research_runs", ["blueprint_id"])
    op.create_index("ix_legal_research_runs_created_by_user_id", "legal_research_runs", ["created_by_user_id"])
    op.create_index("ix_legal_research_runs_blueprint_status", "legal_research_runs", ["blueprint_id", "status"])
    op.create_index("ix_legal_research_runs_workspace_created", "legal_research_runs", ["workspace_id", "created_at"])

    op.create_table(
        "legal_research_outputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("legal_research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authority_matrix_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("legal_tests_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("citation_pack_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("research_memo", sa.Text(), nullable=False, server_default=""),
        sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_legal_research_outputs_workspace_id", "legal_research_outputs", ["workspace_id"])
    op.create_index("ix_legal_research_outputs_blueprint_id", "legal_research_outputs", ["blueprint_id"])
    op.create_index("ix_legal_research_outputs_run_id", "legal_research_outputs", ["run_id"])
    op.create_index("ix_legal_research_outputs_run", "legal_research_outputs", ["run_id"])

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
                "owner": "legal_research",
                "input_schema_json": json.dumps({}),
                "output_schema_json": json.dumps({}),
                "is_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
            for skill_id, name, description in SEED_SKILLS
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
            for skill_id, _name, _description in SEED_SKILLS
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM skill_versions WHERE skill_id LIKE 'research.%'")
    op.execute("DELETE FROM skills WHERE id LIKE 'research.%'")
    op.drop_index("ix_legal_research_outputs_run", table_name="legal_research_outputs")
    op.drop_index("ix_legal_research_outputs_run_id", table_name="legal_research_outputs")
    op.drop_index("ix_legal_research_outputs_blueprint_id", table_name="legal_research_outputs")
    op.drop_index("ix_legal_research_outputs_workspace_id", table_name="legal_research_outputs")
    op.drop_table("legal_research_outputs")
    op.drop_index("ix_legal_research_runs_workspace_created", table_name="legal_research_runs")
    op.drop_index("ix_legal_research_runs_blueprint_status", table_name="legal_research_runs")
    op.drop_index("ix_legal_research_runs_created_by_user_id", table_name="legal_research_runs")
    op.drop_index("ix_legal_research_runs_blueprint_id", table_name="legal_research_runs")
    op.drop_index("ix_legal_research_runs_workspace_id", table_name="legal_research_runs")
    op.drop_table("legal_research_runs")
    op.drop_index("ix_legal_research_configs_created_by_user_id", table_name="legal_research_configs")
    op.drop_index("ix_legal_research_configs_blueprint_id", table_name="legal_research_configs")
    op.drop_index("ix_legal_research_configs_workspace_id", table_name="legal_research_configs")
    op.drop_table("legal_research_configs")
