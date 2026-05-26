"""persona effective workspace name unique

Revision ID: 0017_persona_effective_name_unique
Revises: 0016_contract_review_reports
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_persona_effective_name_unique"
down_revision = "0016_contract_review_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_rows = bind.execute(
        sa.text(
            """
            SELECT COALESCE(workspace_id, '__global__') AS effective_workspace_id,
                   name,
                   MIN(id) AS keep_id
            FROM personas_v2
            GROUP BY COALESCE(workspace_id, '__global__'), name
            HAVING COUNT(*) > 1
            """
        )
    ).mappings().all()
    for row in duplicate_rows:
        bind.execute(
            sa.text(
                """
                DELETE FROM personas_v2
                WHERE COALESCE(workspace_id, '__global__') = :effective_workspace_id
                  AND name = :name
                  AND id != :keep_id
                """
            ),
            {
                "effective_workspace_id": row["effective_workspace_id"],
                "name": row["name"],
                "keep_id": row["keep_id"],
            },
        )
    op.create_index(
        "uq_personas_v2_workspace_name_effective",
        "personas_v2",
        [sa.text("COALESCE(workspace_id, '__global__')"), "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_personas_v2_workspace_name_effective", table_name="personas_v2")
