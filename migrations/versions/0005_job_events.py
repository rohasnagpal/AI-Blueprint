"""job events

Revision ID: 0005_job_events
Revises: 0004_ai_council_plugin
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_job_events"
down_revision = "0004_ai_council_plugin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_index("ix_job_events_workspace_id", "job_events", ["workspace_id"])
    op.create_index("ix_job_events_job_created", "job_events", ["job_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_job_events_job_created", table_name="job_events")
    op.drop_index("ix_job_events_workspace_id", table_name="job_events")
    op.drop_index("ix_job_events_job_id", table_name="job_events")
    op.drop_table("job_events")
