"""blueprint instances

Revision ID: 0002_blueprint_instances
Revises: 0001_v2_foundation
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_blueprint_instances"
down_revision = "0001_v2_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blueprint_instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matter_id", sa.String(length=36), sa.ForeignKey("matters.id", ondelete="SET NULL")),
        sa.Column("plugin_id", sa.String(length=100), sa.ForeignKey("plugins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_blueprint_instances_workspace_id", "blueprint_instances", ["workspace_id"])
    op.create_index("ix_blueprint_instances_matter_id", "blueprint_instances", ["matter_id"])
    op.create_index("ix_blueprint_instances_plugin_id", "blueprint_instances", ["plugin_id"])
    op.create_index("ix_blueprint_instances_created_by_user_id", "blueprint_instances", ["created_by_user_id"])
    op.create_index("ix_blueprint_instances_workspace_status", "blueprint_instances", ["workspace_id", "status"])
    op.create_index("ix_blueprint_instances_workspace_matter", "blueprint_instances", ["workspace_id", "matter_id"])

    op.create_table(
        "blueprint_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("blueprint_id", sa.String(length=36), sa.ForeignKey("blueprint_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("blueprint_id", "user_id", name="uq_blueprint_members_blueprint_user"),
    )
    op.create_index("ix_blueprint_members_blueprint_id", "blueprint_members", ["blueprint_id"])
    op.create_index("ix_blueprint_members_user_id", "blueprint_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_blueprint_members_user_id", table_name="blueprint_members")
    op.drop_index("ix_blueprint_members_blueprint_id", table_name="blueprint_members")
    op.drop_table("blueprint_members")
    op.drop_index("ix_blueprint_instances_workspace_matter", table_name="blueprint_instances")
    op.drop_index("ix_blueprint_instances_workspace_status", table_name="blueprint_instances")
    op.drop_index("ix_blueprint_instances_created_by_user_id", table_name="blueprint_instances")
    op.drop_index("ix_blueprint_instances_plugin_id", table_name="blueprint_instances")
    op.drop_index("ix_blueprint_instances_matter_id", table_name="blueprint_instances")
    op.drop_index("ix_blueprint_instances_workspace_id", table_name="blueprint_instances")
    op.drop_table("blueprint_instances")
