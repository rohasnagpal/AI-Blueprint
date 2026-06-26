"""mediator report output fields

Revision ID: 0031_mediator_report_outputs
Revises: 0030_negotiation_prep
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_mediator_report_outputs"
down_revision = "0030_negotiation_prep"
branch_labels = None
depends_on = None


_COLUMNS: list[tuple[str, str]] = [
    ("positions_and_interests_json", "[]"),
    ("batna_watna_zopa_json", "{}"),
    ("risk_allocation_json", "[]"),
    ("settlement_levers_json", "[]"),
    ("caucus_questions_json", "[]"),
    ("impasse_points_json", "[]"),
    ("bridge_proposals_json", "[]"),
    ("mediator_private_prep_note_json", "{}"),
    ("one_page_session_plan_json", "{}"),
]


def upgrade() -> None:
    for name, default in _COLUMNS:
        op.add_column("mediation_prep_outputs", sa.Column(name, sa.Text(), nullable=False, server_default=default))


def downgrade() -> None:
    for name, _default in reversed(_COLUMNS):
        op.drop_column("mediation_prep_outputs", name)
