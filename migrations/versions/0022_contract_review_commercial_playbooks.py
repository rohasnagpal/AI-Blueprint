"""contract review commercial playbooks

Revision ID: 0022_contract_review_commercial_playbooks
Revises: 0021_contract_review_more_builtin_playbooks
Create Date: 2026-05-27
"""

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0022_contract_review_commercial_playbooks"
down_revision = "0021_contract_review_more_builtin_playbooks"
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
            _playbook("builtin-saas-v1", "General SaaS Playbook", "saas", now),
            _playbook("builtin-consulting-v1", "General Consulting Services Playbook", "consulting", now),
            _playbook("builtin-reseller-v1", "General Reseller Playbook", "reseller", now),
        ],
    )
    op.bulk_insert(
        clauses,
        [
            _clause("builtin-saas-v1-subscription", "builtin-saas-v1", "scope", "Subscription Scope", True, "high", ["unlimited use", "unrestricted users"], "Subscription scope, users, usage limits, and service boundaries are defined.", "Customer may access the service during the subscription term only for its internal business purposes, subject to the users, usage limits, and restrictions in the order form.", now),
            _clause("builtin-saas-v1-data-security", "builtin-saas-v1", "data_security", "Security and Controls", True, "critical", ["no security obligations"], "Provider maintains reasonable administrative, technical, and physical safeguards.", "Provider will maintain reasonable administrative, technical, and physical safeguards designed to protect customer data against unauthorized access, disclosure, alteration, and destruction.", now),
            _clause("builtin-saas-v1-breach", "builtin-saas-v1", "data_breach_notice", "Security Incident Notice", True, "high", ["notice when commercially reasonable"], "Provider gives prompt notice of confirmed security incidents.", "Provider will notify customer without undue delay after confirming a security incident affecting customer data.", now),
            _clause("builtin-saas-v1-availability", "builtin-saas-v1", "warranties", "Service Availability", True, "medium", ["as-is service"], "Service levels, remedies, maintenance, and exclusions are stated.", "Provider will make the service available in accordance with the applicable service level terms, excluding scheduled maintenance, customer-caused issues, and events outside provider's reasonable control.", now),
            _clause("builtin-saas-v1-termination", "builtin-saas-v1", "termination", "Suspension and Termination", True, "high", ["terminate for convenience at any time"], "Suspension and termination rights are tied to breach, security risk, nonpayment, or legal requirements.", "Either party may terminate for uncured material breach after written notice and a reasonable cure period. Provider may suspend access only for nonpayment, security risk, or legal requirement.", now),
            _clause("builtin-consulting-v1-scope", "builtin-consulting-v1", "scope", "Services Scope", True, "high", ["undefined services"], "Services, deliverables, assumptions, dependencies, and exclusions are clear.", "Services, deliverables, assumptions, dependencies, exclusions, timeline, and acceptance criteria must be stated in the applicable statement of work.", now),
            _clause("builtin-consulting-v1-payment", "builtin-consulting-v1", "payment", "Fees and Expenses", True, "medium", ["unclear fees"], "Fees, expenses, invoice timing, and disputed invoice process are stated.", "Customer will pay undisputed invoices within 30 days of receipt. Expenses require documentation and must comply with the statement of work.", now),
            _clause("builtin-consulting-v1-ip", "builtin-consulting-v1", "ip", "Work Product and Background IP", True, "high", ["unclear ownership"], "Work product rights and retained consultant tools are clearly separated.", "Upon full payment, customer receives the agreed rights in custom deliverables. Consultant retains background IP, tools, templates, methods, know-how, and reusable materials unless expressly assigned.", now),
            _clause("builtin-consulting-v1-warranties", "builtin-consulting-v1", "warranties", "Professional Services Warranty", True, "medium", ["as-is services"], "Services are performed professionally and materially conform to the SOW.", "Consultant warrants that services will be performed in a professional and workmanlike manner and will materially conform to the applicable statement of work.", now),
            _clause("builtin-reseller-v1-territory", "builtin-reseller-v1", "scope", "Territory and Channel Rights", True, "high", ["exclusive worldwide rights"], "Territory, customer segment, exclusivity, and reservation of rights are explicit.", "Reseller rights are limited to the territory, channel, customer segment, and products stated in the agreement. Supplier reserves all rights not expressly granted.", now),
            _clause("builtin-reseller-v1-payment", "builtin-reseller-v1", "payment", "Pricing and Payment", True, "medium", ["unclear discount"], "Discounts, payment timing, taxes, credits, and chargebacks are defined.", "Reseller will pay supplier for orders under the agreed price list or discount schedule, with taxes, credits, refunds, and chargebacks handled as stated in the agreement.", now),
            _clause("builtin-reseller-v1-compliance", "builtin-reseller-v1", "warranties", "Compliance and Sales Conduct", True, "high", ["no compliance obligations"], "Reseller must comply with law, anti-bribery rules, export controls, and brand guidelines.", "Reseller will comply with applicable laws, anti-bribery obligations, export controls, sanctions, privacy rules, and supplier's reasonable brand and sales guidelines.", now),
            _clause("builtin-reseller-v1-ip", "builtin-reseller-v1", "ip", "Marks and Product IP", True, "high", ["ownership of supplier marks"], "Supplier retains product IP and marks; reseller receives a limited sales license.", "Supplier retains all product IP, trademarks, and brand assets. Reseller receives only a limited, revocable license to use approved marks for authorized resale activities.", now),
        ],
    )


def downgrade() -> None:
    playbook_ids = "'builtin-saas-v1', 'builtin-consulting-v1', 'builtin-reseller-v1'"
    op.execute(f"DELETE FROM contract_playbook_clauses WHERE playbook_id IN ({playbook_ids})")
    op.execute(f"DELETE FROM contract_playbooks WHERE id IN ({playbook_ids})")


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
