"""contract playbook fallback language

Revision ID: 0020_contract_playbook_fallback_language
Revises: 0019_contract_review_workflow_foundation
Create Date: 2026-05-27
"""

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0020_contract_playbook_fallback_language"
down_revision = "0019_contract_review_workflow_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    playbooks = sa.table(
        "contract_playbooks",
        sa.column("id", sa.String),
        sa.column("version", sa.String),
        sa.column("rules_json", sa.Text),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    clauses = sa.table(
        "contract_playbook_clauses",
        sa.column("id", sa.String),
        sa.column("approved_text", sa.Text),
        sa.column("fallback_text", sa.Text),
        sa.column("metadata_json", sa.Text),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        playbooks.update()
        .where(playbooks.c.id == "builtin-nda-v1")
        .values(version="1.1", rules_json=json.dumps({"review_posture": "balanced", "requires_human_review": True, "redlines_require_approval": True}, sort_keys=True), updated_at=now)
    )
    op.execute(
        playbooks.update()
        .where(playbooks.c.id == "builtin-msa-v1")
        .values(version="1.1", rules_json=json.dumps({"review_posture": "balanced", "requires_human_review": True, "redlines_require_approval": True}, sort_keys=True), updated_at=now)
    )
    for item in _clause_language():
        op.execute(
            clauses.update()
            .where(clauses.c.id == item["id"])
            .values(
                approved_text=item["approved_text"],
                fallback_text=item["fallback_text"],
                metadata_json=json.dumps(item["metadata"], sort_keys=True),
                updated_at=now,
            )
        )


def downgrade() -> None:
    now = datetime.now(timezone.utc)
    playbooks = sa.table(
        "contract_playbooks",
        sa.column("id", sa.String),
        sa.column("version", sa.String),
        sa.column("rules_json", sa.Text),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    clauses = sa.table(
        "contract_playbook_clauses",
        sa.column("id", sa.String),
        sa.column("approved_text", sa.Text),
        sa.column("fallback_text", sa.Text),
        sa.column("metadata_json", sa.Text),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.execute(playbooks.update().where(playbooks.c.id.in_(["builtin-nda-v1", "builtin-msa-v1"])).values(version="1.0", rules_json='{"review_posture":"balanced","requires_human_review":true}', updated_at=now))
    for item in _clause_language():
        op.execute(clauses.update().where(clauses.c.id == item["id"]).values(approved_text=None, fallback_text=None, metadata_json="{}", updated_at=now))


def _clause_language() -> list[dict]:
    return [
        _item(
            "builtin-nda-v1-confidentiality",
            "Mutual confidentiality obligations with standard exclusions, permitted disclosures, and no transfer of ownership.",
            "Recipient shall protect Confidential Information using at least reasonable care and may use it only for the stated purpose. Obligations do not apply to information that is public, already known, independently developed, or rightfully received from a third party.",
            "nda",
        ),
        _item(
            "builtin-nda-v1-exclusions",
            "Confidentiality exclusions cover public information, prior knowledge, independent development, and third-party receipt.",
            "Confidential Information excludes information that is or becomes public without breach, was already known without restriction, is independently developed without use of Confidential Information, or is rightfully received from a third party.",
            "nda",
        ),
        _item(
            "builtin-nda-v1-term",
            "A defined confidentiality period with longer protection only for trade secrets while they remain trade secrets.",
            "Confidentiality obligations continue for three years after disclosure, except trade secrets remain protected for so long as they qualify as trade secrets under applicable law.",
            "nda",
        ),
        _item(
            "builtin-nda-v1-return",
            "Recipient must return or destroy confidential information on request, subject to archival and legal-retention copies.",
            "Upon request, Recipient will return or destroy Confidential Information, except one archival copy may be retained for legal, compliance, or backup purposes and remains subject to this agreement.",
            "nda",
        ),
        _item(
            "builtin-nda-v1-law",
            "Governing law is stated clearly and excludes conflicts rules.",
            "This agreement is governed by the laws of the agreed jurisdiction, without regard to conflict-of-laws rules.",
            "nda",
        ),
        _item(
            "builtin-nda-v1-assignment",
            "Assignment requires consent except to affiliates or successors in a merger or sale of substantially all assets.",
            "Neither party may assign this agreement without the other party's prior written consent, except to an affiliate or successor in connection with a merger, reorganization, or sale of substantially all assets.",
            "nda",
        ),
        _item(
            "builtin-msa-v1-payment",
            "Fees, invoicing, taxes, payment timing, and dispute rights are clear.",
            "Customer will pay undisputed invoices within 30 days of receipt. Customer may withhold amounts disputed in good faith if it gives prompt written notice and pays all undisputed amounts when due.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-scope",
            "Services and deliverables are defined in statements of work with change control.",
            "Services, deliverables, milestones, and acceptance criteria will be set out in an applicable statement of work. Changes require a written change order signed by both parties.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-warranties",
            "Provider warrants professional performance and compliance with applicable law.",
            "Provider warrants that services will be performed in a professional and workmanlike manner, materially conform to the applicable statement of work, and comply with applicable laws.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-liability",
            "Liability cap is mutual, commercially reasonable, and includes negotiated carve-outs.",
            "Except for excluded claims, each party's aggregate liability is capped at the fees paid or payable under the applicable statement of work in the 12 months before the claim. Excluded claims should be expressly listed and reviewed by counsel.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-indemnity",
            "Indemnities are mutual, scoped, and tied to third-party claims.",
            "Each party will defend and indemnify the other from third-party claims arising from its gross negligence, willful misconduct, violation of law, or infringement of third-party intellectual property rights, subject to prompt notice and control of defense.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-ip",
            "Background IP remains owned by the original owner, with deliverable ownership or license terms stated clearly.",
            "Each party retains its pre-existing intellectual property. Upon full payment, customer receives ownership of custom deliverables specifically identified as assigned, excluding provider tools, templates, know-how, and pre-existing materials.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-termination",
            "Termination includes breach cure rights and clear post-termination obligations.",
            "Either party may terminate for material breach if the breach is not cured within 30 days after written notice. Termination does not relieve payment obligations for services performed before the effective termination date.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-data",
            "Security obligations are stated when personal data, confidential data, or regulated data is handled.",
            "Provider will maintain reasonable administrative, technical, and physical safeguards appropriate to the data processed and will promptly notify customer of confirmed unauthorized access affecting customer data.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-law",
            "Governing law and forum are stated clearly.",
            "This agreement is governed by the laws of the agreed jurisdiction, without regard to conflict-of-laws rules, and disputes will be brought in the agreed courts unless the parties agree otherwise.",
            "msa",
        ),
        _item(
            "builtin-msa-v1-assignment",
            "Assignment requires consent with standard affiliate and successor exceptions.",
            "Neither party may assign this agreement without prior written consent, except to an affiliate or successor in connection with a merger, reorganization, or sale of substantially all assets.",
            "msa",
        ),
    ]


def _item(clause_id: str, approved_text: str, fallback_text: str, family: str) -> dict:
    return {
        "id": clause_id,
        "approved_text": approved_text,
        "fallback_text": fallback_text,
        "metadata": {"language_family": family, "language_version": "1.1", "human_approval_required": True},
    }
