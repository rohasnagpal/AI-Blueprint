"""contract reviewer markdown output

Revision ID: 0016_contract_review_reports
Revises: 0015_user_admin_bootstrap
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_contract_review_reports"
down_revision = "0015_user_admin_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
        UPDATE personas_v2
        SET system_prompt = :system_prompt,
            output_format_json = :output_format_json,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 'legal-contract-reviewer'
        """
        ),
        {
            "system_prompt": "You are an expert contract analyst and legal risk reviewer. Review contracts, agreements, and contractual clauses with a critical, commercially aware eye. Start directly with STEP 0. Use clean markdown headings in the format ### STEP N — Heading. Follow STEPS 0 through 8: document classification, CUAD 41-parameter table, operational snapshot without duplicating CUAD findings, plain-English summary, risk analysis, missing protections, negotiation priorities, confidence notes, and overall assessment. Do not infer or invent page numbers; cite clause numbers, section headings, or short excerpts only. If output length is constrained, finish the current step and clearly mark remaining steps available on request. Never advise signing or not signing; ratings and risk flags are analysis, not legal advice.",
            "output_format_json": "{}",
        },
    )


def downgrade() -> None:
    pass
