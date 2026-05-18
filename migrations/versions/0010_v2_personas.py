"""v2 personas

Revision ID: 0010_v2_personas
Revises: 0009_v2_secrets
Create Date: 2026-05-18
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0010_v2_personas"
down_revision = "0009_v2_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personas_v2",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False, server_default="Legal"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("constraints_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("output_format_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_personas_v2_workspace_name"),
    )
    op.create_index("ix_personas_v2_workspace_id", "personas_v2", ["workspace_id"])
    op.create_index("ix_personas_v2_created_by_user_id", "personas_v2", ["created_by_user_id"])
    op.create_index("ix_personas_v2_workspace_category", "personas_v2", ["workspace_id", "category"])

    op.create_table(
        "blueprint_personas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona_id", sa.String(length=36), sa.ForeignKey("personas_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False, server_default="participant"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("blueprint_id", "persona_id", "role", name="uq_blueprint_personas_blueprint_persona_role"),
    )
    op.create_index("ix_blueprint_personas_workspace_id", "blueprint_personas", ["workspace_id"])
    op.create_index("ix_blueprint_personas_blueprint_id", "blueprint_personas", ["blueprint_id"])
    op.create_index("ix_blueprint_personas_persona_id", "blueprint_personas", ["persona_id"])
    op.create_index("ix_blueprint_personas_created_by_user_id", "blueprint_personas", ["created_by_user_id"])
    op.create_index("ix_blueprint_personas_blueprint_role", "blueprint_personas", ["blueprint_id", "role"])

    now = datetime.now(timezone.utc)
    personas = sa.table(
        "personas_v2",
        sa.column("id", sa.String),
        sa.column("workspace_id", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("system_prompt", sa.Text),
        sa.column("constraints_json", sa.Text),
        sa.column("output_format_json", sa.Text),
        sa.column("tags_json", sa.Text),
        sa.column("is_builtin", sa.Boolean),
        sa.column("is_enabled", sa.Boolean),
        sa.column("created_by_user_id", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        personas,
        [
            {
                "id": "legal-contract-reviewer",
                "workspace_id": None,
                "name": "Contract Reviewer",
                "category": "Legal",
                "description": "Reviews contracts for clause extraction, risk, missing terms, and negotiation posture.",
                "system_prompt": "You are a careful legal contract reviewer. Ground every conclusion in supplied documents and mark unsupported points clearly.",
                "constraints_json": '["Do not invent clauses", "Separate legal risk from business risk", "Flag missing evidence"]',
                "output_format_json": '{"type":"structured_memo","sections":["findings","risks","questions","citations"]}',
                "tags_json": '["contract","risk","legal"]',
                "is_builtin": True,
                "is_enabled": True,
                "created_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "legal-devils-advocate",
                "workspace_id": None,
                "name": "Adversarial Reviewer",
                "category": "Legal",
                "description": "Challenges assumptions, weak evidence, and overconfident legal positions.",
                "system_prompt": "You are an adversarial legal reviewer. Identify unsupported assumptions, contrary evidence, and procedural or ethical risks.",
                "constraints_json": '["Challenge conclusions", "Cite evidence gaps", "Escalate high-risk uncertainty"]',
                "output_format_json": '{"type":"review","sections":["challenges","missing_evidence","risk_flags"]}',
                "tags_json": '["litigation","quality","risk"]',
                "is_builtin": True,
                "is_enabled": True,
                "created_by_user_id": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_blueprint_personas_blueprint_role", table_name="blueprint_personas")
    op.drop_index("ix_blueprint_personas_created_by_user_id", table_name="blueprint_personas")
    op.drop_index("ix_blueprint_personas_persona_id", table_name="blueprint_personas")
    op.drop_index("ix_blueprint_personas_blueprint_id", table_name="blueprint_personas")
    op.drop_index("ix_blueprint_personas_workspace_id", table_name="blueprint_personas")
    op.drop_table("blueprint_personas")
    op.drop_index("ix_personas_v2_workspace_category", table_name="personas_v2")
    op.drop_index("ix_personas_v2_created_by_user_id", table_name="personas_v2")
    op.drop_index("ix_personas_v2_workspace_id", table_name="personas_v2")
    op.drop_table("personas_v2")
