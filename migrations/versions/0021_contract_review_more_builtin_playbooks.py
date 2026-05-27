"""contract review more builtin playbooks

Revision ID: 0021_contract_review_more_builtin_playbooks
Revises: 0020_contract_playbook_fallback_language
Create Date: 2026-05-27
"""

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0021_contract_review_more_builtin_playbooks"
down_revision = "0020_contract_playbook_fallback_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    playbooks = sa.table(
        "contract_playbooks",
        sa.column("id", sa.String),
        sa.column("workspace_id", sa.String),
        sa.column("name", sa.String),
        sa.column("contract_category", sa.String),
        sa.column("jurisdiction", sa.String),
        sa.column("version", sa.String),
        sa.column("status", sa.String),
        sa.column("rules_json", sa.Text),
        sa.column("is_builtin", sa.Boolean),
        sa.column("created_by_user_id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    clauses = sa.table(
        "contract_playbook_clauses",
        sa.column("id", sa.String),
        sa.column("playbook_id", sa.String),
        sa.column("clause_type", sa.String),
        sa.column("title", sa.String),
        sa.column("approved_text", sa.Text),
        sa.column("fallback_text", sa.Text),
        sa.column("prohibited_patterns_json", sa.Text),
        sa.column("required", sa.Boolean),
        sa.column("severity_default", sa.String),
        sa.column("metadata_json", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        playbooks,
        [
            _playbook("builtin-dpa-v1", "General DPA Playbook", "dpa", now),
            _playbook("builtin-sow-v1", "General SOW Playbook", "sow", now),
        ],
    )
    op.bulk_insert(
        clauses,
        [
            _clause("builtin-dpa-v1-processing", "builtin-dpa-v1", "data_processing", "Processing Instructions", True, "critical", ["process personal data for any purpose"], "Processor acts only on documented controller instructions.", "Processor will process personal data only on documented instructions from controller and only for the services described in the agreement.", now),
            _clause("builtin-dpa-v1-security", "builtin-dpa-v1", "data_security", "Security Measures", True, "critical", ["no security obligations"], "Processor maintains appropriate technical and organizational security measures.", "Processor will maintain administrative, technical, and physical safeguards appropriate to the nature of the personal data and processing activities.", now),
            _clause("builtin-dpa-v1-breach", "builtin-dpa-v1", "data_breach_notice", "Security Incident Notice", True, "high", ["notice when commercially reasonable"], "Processor gives prompt notice of confirmed security incidents.", "Processor will notify controller without undue delay after confirming a security incident affecting personal data.", now),
            _clause("builtin-dpa-v1-subprocessors", "builtin-dpa-v1", "subprocessors", "Subprocessors", True, "high", ["unrestricted subprocessors"], "Subprocessor use requires notice, flow-down obligations, and an objection right.", "Processor may engage subprocessors only with required notice and written obligations that protect personal data at least as strongly as this DPA.", now),
            _clause("builtin-dpa-v1-deletion", "builtin-dpa-v1", "return_or_destruction", "Return or Deletion", True, "medium", [], "Personal data is returned or deleted at the end of services subject to legal retention.", "At termination, processor will return or delete personal data unless retention is required by law.", now),
            _clause("builtin-sow-v1-scope", "builtin-sow-v1", "scope", "Scope and Deliverables", True, "high", ["undefined scope"], "Services, deliverables, milestones, and assumptions are specific.", "The statement of work must define services, deliverables, milestones, dependencies, assumptions, and exclusions with enough detail to price and manage performance.", now),
            _clause("builtin-sow-v1-acceptance", "builtin-sow-v1", "acceptance", "Acceptance Criteria", True, "medium", ["deemed accepted immediately"], "Acceptance criteria and review periods are objective.", "Customer will review deliverables against objective acceptance criteria within a defined review period and will identify specific nonconformities in writing.", now),
            _clause("builtin-sow-v1-change", "builtin-sow-v1", "change_control", "Change Control", True, "medium", ["oral change orders"], "Out-of-scope work requires a written change order.", "Changes to scope, timeline, fees, or deliverables require a written change order approved by both parties.", now),
            _clause("builtin-sow-v1-payment", "builtin-sow-v1", "payment", "Fees and Invoicing", True, "medium", ["unclear fees"], "Fees, milestones, expenses, and invoice timing are clear.", "Fees, payment milestones, reimbursable expenses, and invoice timing must be stated in the statement of work.", now),
            _clause("builtin-sow-v1-ip", "builtin-sow-v1", "ip", "Deliverable IP", True, "high", ["unclear ownership of deliverables"], "Deliverable ownership and retained provider materials are clear.", "The SOW must state whether deliverables are assigned or licensed and must exclude provider background IP, tools, templates, and know-how unless expressly transferred.", now),
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM contract_playbook_clauses WHERE playbook_id IN ('builtin-dpa-v1', 'builtin-sow-v1')")
    op.execute("DELETE FROM contract_playbooks WHERE id IN ('builtin-dpa-v1', 'builtin-sow-v1')")


def _playbook(playbook_id: str, name: str, category: str, now: datetime) -> dict:
    return {
        "id": playbook_id,
        "workspace_id": None,
        "name": name,
        "contract_category": category,
        "jurisdiction": None,
        "version": "1.0",
        "status": "active",
        "rules_json": json.dumps({"review_posture": "balanced", "requires_human_review": True, "redlines_require_approval": True}, sort_keys=True),
        "is_builtin": True,
        "created_by_user_id": None,
        "created_at": now,
        "updated_at": now,
    }


def _clause(clause_id: str, playbook_id: str, clause_type: str, title: str, required: bool, severity: str, prohibited: list[str], approved: str, fallback: str, now: datetime) -> dict:
    return {
        "id": clause_id,
        "playbook_id": playbook_id,
        "clause_type": clause_type,
        "title": title,
        "approved_text": approved,
        "fallback_text": fallback,
        "prohibited_patterns_json": json.dumps(prohibited, sort_keys=True),
        "required": required,
        "severity_default": severity,
        "metadata_json": json.dumps({"language_version": "1.0", "human_approval_required": True}, sort_keys=True),
        "created_at": now,
        "updated_at": now,
    }
