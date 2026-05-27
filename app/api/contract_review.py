import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.contract_review_runner import execute_contract_review
from app.core.contract_review_workflow_runner import execute_contract_review_workflow
from app.core.contract_agents.registry import list_contract_workflow_modules
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member
from app.core.json_utils import json_loads
from app.core.jobs import create_job, format_job
from app.core.models import (
    BlueprintInstance,
    AuditEvent,
    ContractClause,
    ContractClauseReviewDecision,
    ContractPlaybook,
    ContractPlaybookClause,
    ContractPlaybookFinding,
    ContractRedlineSuggestion,
    ContractReviewConfig,
    ContractReviewOutput,
    ContractReviewRun,
    ContractReviewStepOutput,
    ContractReviewSummary,
    ContractRiskFinding,
    DocumentLink,
    Escalation,
    KnowledgeDocument,
    User,
    utcnow,
)
from app.core.pagination import page_query_response
from app.core.task_control import run_background_job

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review", tags=["contract-review"])


class ContractReviewConfigIn(BaseModel):
    config: dict[str, Any] = {}


class ContractReviewRunIn(BaseModel):
    title: str = ""
    mode: str | None = None
    config: dict[str, Any] | None = None


class ContractClauseDecisionIn(BaseModel):
    decision: str
    note: str | None = None
    metadata: dict[str, Any] | None = None


class ContractPlaybookClauseIn(BaseModel):
    clause_type: str
    title: str
    approved_text: str | None = None
    fallback_text: str | None = None
    prohibited_patterns: list[str] = []
    required: bool = False
    severity_default: str = "medium"
    metadata: dict[str, Any] = {}


class ContractPlaybookIn(BaseModel):
    name: str
    contract_category: str
    jurisdiction: str | None = None
    version: str = "1.0"
    status: str = "active"
    rules: dict[str, Any] = {}
    clauses: list[ContractPlaybookClauseIn] = []


def _require_contract_blueprint(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, str]:
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if blueprint.plugin_id != "contract_review":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review blueprint not found")
    return blueprint, membership.role


def _format_config(config: ContractReviewConfig) -> dict:
    return {
        "id": config.id,
        "workspace_id": config.workspace_id,
        "blueprint_id": config.blueprint_id,
        "config": json_loads(config.config_json, {}),
        "created_by_user_id": config.created_by_user_id,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


def _format_run(run: ContractReviewRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "blueprint_id": run.blueprint_id,
        "title": run.title,
        "status": run.status,
        "mode": run.mode,
        "workflow_version": run.workflow_version,
        "status_detail": run.status_detail,
        "review_complete": run.status_detail == "Review complete",
        "selected_playbook_id": run.selected_playbook_id,
        "coverage_score": run.coverage_score,
        "source_anchor_version": run.source_anchor_version,
        "config_snapshot": json_loads(run.config_snapshot_json, {}),
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _format_output(output: ContractReviewOutput) -> dict:
    return {
        "id": output.id,
        "run_id": output.run_id,
        "extraction": json_loads(output.extraction_json, {}),
        "risk_matrix": json_loads(output.risk_matrix_json, []),
        "negotiation_memo": output.negotiation_memo,
        "client_summary": output.client_summary,
        "sources": json_loads(output.sources_json, []),
        "metadata": json_loads(output.metadata_json, {}),
        "created_at": output.created_at.isoformat(),
    }


def _format_playbook(playbook: ContractPlaybook) -> dict:
    return {
        "id": playbook.id,
        "workspace_id": playbook.workspace_id,
        "name": playbook.name,
        "contract_category": playbook.contract_category,
        "jurisdiction": playbook.jurisdiction,
        "version": playbook.version,
        "status": playbook.status,
        "rules": json_loads(playbook.rules_json, {}),
        "is_builtin": playbook.is_builtin,
        "created_at": playbook.created_at.isoformat(),
        "updated_at": playbook.updated_at.isoformat(),
    }


def _format_playbook_clause(clause: ContractPlaybookClause) -> dict:
    return {
        "id": clause.id,
        "playbook_id": clause.playbook_id,
        "clause_type": clause.clause_type,
        "title": clause.title,
        "approved_text": clause.approved_text,
        "fallback_text": clause.fallback_text,
        "prohibited_patterns": json_loads(clause.prohibited_patterns_json, []),
        "required": clause.required,
        "severity_default": clause.severity_default,
        "metadata": json_loads(clause.metadata_json, {}),
    }


def _format_clause(clause: ContractClause) -> dict:
    return {
        "id": clause.id,
        "workspace_id": clause.workspace_id,
        "blueprint_id": clause.blueprint_id,
        "run_id": clause.run_id,
        "document_id": clause.document_id,
        "chunk_id": clause.chunk_id,
        "clause_type": clause.clause_type,
        "title": clause.title,
        "text": clause.text,
        "source": json_loads(clause.source_json, {}),
        "page": clause.page,
        "start_offset": clause.start_offset,
        "end_offset": clause.end_offset,
        "confidence_score": clause.confidence_score,
        "review_status": clause.review_status,
        "created_at": clause.created_at.isoformat(),
        "updated_at": clause.updated_at.isoformat(),
    }


def _format_playbook_finding(finding: ContractPlaybookFinding) -> dict:
    return {
        "id": finding.id,
        "clause_id": finding.clause_id,
        "playbook_id": finding.playbook_id,
        "playbook_clause_id": finding.playbook_clause_id,
        "status": finding.status,
        "deviation_summary": finding.deviation_summary,
        "missing": finding.missing,
        "prohibited_match": finding.prohibited_match,
        "confidence_score": finding.confidence_score,
        "metadata": json_loads(finding.metadata_json, {}),
        "created_at": finding.created_at.isoformat(),
    }


def _format_risk_finding(finding: ContractRiskFinding) -> dict:
    return {
        "id": finding.id,
        "clause_id": finding.clause_id,
        "risk_level": finding.risk_level,
        "likelihood": finding.likelihood,
        "impact": finding.impact,
        "priority": finding.priority,
        "reasoning": finding.reasoning,
        "requires_review": finding.requires_review,
        "confidence_score": finding.confidence_score,
        "metadata": json_loads(finding.metadata_json, {}),
        "created_at": finding.created_at.isoformat(),
    }


def _format_redline(suggestion: ContractRedlineSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "clause_id": suggestion.clause_id,
        "suggestion_text": suggestion.suggestion_text,
        "fallback_language": suggestion.fallback_language,
        "rationale": suggestion.rationale,
        "source_playbook_id": suggestion.source_playbook_id,
        "confidence_score": suggestion.confidence_score,
        "status": suggestion.status,
        "metadata": json_loads(suggestion.metadata_json, {}),
        "created_at": suggestion.created_at.isoformat(),
    }


@router.get("/workflow-modules")
async def list_workflow_modules(workspace_id: str, blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    return {
        "items": list_contract_workflow_modules(),
        "extension_contract": {
            "status": "reserved",
            "description": "Custom workflow modules must declare stable JSON inputs and outputs before they can be inserted into a contract review stage.",
        },
    }


def _format_summary(summary: ContractReviewSummary) -> dict:
    return {
        "id": summary.id,
        "audience": summary.audience,
        "summary_text": summary.summary_text,
        "obligations": json_loads(summary.obligations_json, []),
        "negotiation_points": json_loads(summary.negotiation_points_json, []),
        "unusual_terms": json_loads(summary.unusual_terms_json, []),
        "metadata": json_loads(summary.metadata_json, {}),
        "created_at": summary.created_at.isoformat(),
        "updated_at": summary.updated_at.isoformat(),
    }


def _format_step_output(step: ContractReviewStepOutput) -> dict:
    return {
        "id": step.id,
        "step_name": step.step_name,
        "step_version": step.step_version,
        "status": step.status,
        "input": json_loads(step.input_json, {}),
        "output": json_loads(step.output_json, {}),
        "confidence_score": step.confidence_score,
        "provider": step.provider,
        "model": step.model,
        "error": step.error,
        "metadata": json_loads(step.metadata_json, {}),
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "created_at": step.created_at.isoformat(),
    }


def _format_decision(decision: ContractClauseReviewDecision) -> dict:
    return {
        "id": decision.id,
        "clause_id": decision.clause_id,
        "user_id": decision.user_id,
        "decision": decision.decision,
        "note": decision.note,
        "prior_status": json_loads(decision.prior_status_json, {}),
        "metadata": json_loads(decision.metadata_json, {}),
        "created_at": decision.created_at.isoformat(),
    }


def _format_escalation(escalation: Escalation) -> dict:
    return {
        "id": escalation.id,
        "workspace_id": escalation.workspace_id,
        "blueprint_id": escalation.blueprint_id,
        "source_type": escalation.source_type,
        "source_id": escalation.source_id,
        "severity": escalation.severity,
        "status": escalation.status,
        "reason": escalation.reason,
        "required_action": escalation.required_action,
        "metadata": json_loads(escalation.metadata_json, {}),
        "created_by_user_id": escalation.created_by_user_id,
        "resolved_by_user_id": escalation.resolved_by_user_id,
        "created_at": escalation.created_at.isoformat(),
        "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
    }


def _format_audit_event(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "workspace_id": event.workspace_id,
        "user_id": event.user_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "metadata": json_loads(event.metadata_json, {}),
        "created_at": event.created_at.isoformat(),
    }


def _contract_export_markdown(run: ContractReviewRun, output: ContractReviewOutput) -> str:
    extraction = json_loads(output.extraction_json, {})
    risk_matrix = json_loads(output.risk_matrix_json, [])
    sources = json_loads(output.sources_json, [])
    lines = [
        f"# {run.title}",
        "",
        "## Client Summary",
        output.client_summary,
        "",
        "## Structured Extraction",
    ]
    for key, value in extraction.items():
        lines.append(f"- **{key}**: {value.get('value') or 'Unsupported'}")
    lines.extend(["", "## Risk Matrix"])
    for risk in risk_matrix:
        lines.append(f"- **{risk.get('issue')}** ({risk.get('severity')}): {risk.get('finding')}")
    lines.extend(["", "## Negotiation Memo", output.negotiation_memo, "", "## Sources"])
    for source in sources:
        locator = f"chunk {source.get('chunk')}" if source.get("chunk") else "indexed excerpt"
        lines.append(f"- {source.get('filename')} {locator}: {source.get('excerpt')}")
    lines.extend(["", "## Review Status", "Human legal review required before external delivery."])
    return "\n".join(lines).strip() + "\n"


def _workflow_export_markdown(db: Session, run: ContractReviewRun, output: ContractReviewOutput) -> str:
    summaries = db.execute(select(ContractReviewSummary).where(ContractReviewSummary.run_id == run.id).order_by(ContractReviewSummary.audience)).scalars().all()
    clauses = db.execute(select(ContractClause).where(ContractClause.run_id == run.id).order_by(ContractClause.clause_type, ContractClause.created_at)).scalars().all()
    risks = db.execute(select(ContractRiskFinding).where(ContractRiskFinding.run_id == run.id)).scalars().all()
    findings = db.execute(select(ContractPlaybookFinding).where(ContractPlaybookFinding.run_id == run.id)).scalars().all()
    suggestions = db.execute(select(ContractRedlineSuggestion).where(ContractRedlineSuggestion.run_id == run.id)).scalars().all()
    decisions = db.execute(select(ContractClauseReviewDecision).where(ContractClauseReviewDecision.run_id == run.id).order_by(ContractClauseReviewDecision.created_at)).scalars().all()
    escalations = db.execute(
        select(Escalation).where(
            Escalation.workspace_id == run.workspace_id,
            Escalation.blueprint_id == run.blueprint_id,
            Escalation.source_type == "contract_review_run",
            Escalation.source_id == run.id,
        )
    ).scalars().all()
    risks_by_clause = _group_by_clause(risks)
    findings_by_clause = _group_by_clause(findings)
    suggestions_by_clause = _group_by_clause(suggestions)
    decisions_by_clause = _group_by_clause(decisions)
    lines = [
        f"# {run.title}",
        "",
        "## Review Status",
        "AI-assisted workflow draft. Human legal review required before external delivery.",
        f"- Mode: {run.mode}",
        f"- Workflow version: {run.workflow_version or 'n/a'}",
        f"- Completion: {'Human review complete' if run.status_detail == 'Review complete' else 'Human review not complete'}",
        f"- Open escalations: {sum(1 for escalation in escalations if escalation.status == 'open')}",
        f"- Human decisions recorded: {len(decisions)}",
        f"- Coverage score: {run.coverage_score if run.coverage_score is not None else 'n/a'}",
        f"- Selected playbook: {run.selected_playbook_id or 'auto/not selected'}",
        "",
        "## Summaries",
    ]
    if summaries:
        for summary in summaries:
            lines.extend(["", f"### {summary.audience.replace('_', ' ').title()}", summary.summary_text])
            points = json_loads(summary.negotiation_points_json, [])
            if points:
                lines.append("")
                lines.append("Negotiation points:")
                lines.extend(f"- {point}" for point in points)
    else:
        lines.append(output.client_summary)
    lines.extend(["", "## Clause Review"])
    if not clauses:
        lines.append("No structured clauses were extracted.")
    for index, clause in enumerate(clauses, start=1):
        source = json_loads(clause.source_json, {})
        locator = _source_locator(source)
        lines.extend(
            [
                "",
                f"### {index}. {clause.title or clause.clause_type}",
                f"- Type: {clause.clause_type}",
                f"- Review status: {clause.review_status}",
                f"- Confidence: {clause.confidence_score if clause.confidence_score is not None else 'n/a'}",
                f"- Source: {locator}",
                "",
                clause.text,
            ]
        )
        clause_findings = findings_by_clause.get(clause.id, [])
        if clause_findings:
            lines.extend(["", "Playbook comparison:"])
            for finding in clause_findings:
                lines.append(f"- {finding.status}: {finding.deviation_summary or 'No additional detail.'}")
        clause_risks = risks_by_clause.get(clause.id, [])
        if clause_risks:
            lines.extend(["", "Risks:"])
            for risk in clause_risks:
                lines.append(f"- {risk.risk_level}: {risk.reasoning}")
        clause_suggestions = suggestions_by_clause.get(clause.id, [])
        if clause_suggestions:
            lines.extend(["", "Draft suggestions:"])
            for suggestion in clause_suggestions:
                lines.append(f"- {suggestion.suggestion_text}")
        clause_decisions = decisions_by_clause.get(clause.id, [])
        if clause_decisions:
            lines.extend(["", "Human decisions:"])
            for decision in clause_decisions:
                note = f": {decision.note}" if decision.note else ""
                lines.append(f"- {decision.decision}{note} ({decision.created_at.isoformat()})")
    missing_findings = [finding for finding in findings if finding.missing]
    if missing_findings:
        lines.extend(["", "## Missing Required Protections"])
        for finding in missing_findings:
            lines.append(f"- {finding.deviation_summary or finding.status}")
    lines.extend(["", "## Export Notice", "This report is a workflow aid and is not autonomous legal advice."])
    return "\n".join(lines).strip() + "\n"


@router.get("/playbooks")
async def list_playbooks(
    workspace_id: str,
    blueprint_id: str,
    contract_category: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    query = select(ContractPlaybook).where(
        ContractPlaybook.status == "active",
        (ContractPlaybook.workspace_id == workspace_id) | (ContractPlaybook.workspace_id.is_(None)),
    )
    if contract_category:
        query = query.where(ContractPlaybook.contract_category == contract_category)
    playbooks = db.execute(query.order_by(ContractPlaybook.is_builtin.desc(), ContractPlaybook.name)).scalars().all()
    return [_format_playbook(playbook) for playbook in playbooks]


@router.get("/playbooks/{playbook_id}")
async def get_playbook(
    workspace_id: str,
    blueprint_id: str,
    playbook_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    playbook = db.execute(
        select(ContractPlaybook).where(
            ContractPlaybook.id == playbook_id,
            (ContractPlaybook.workspace_id == workspace_id) | (ContractPlaybook.workspace_id.is_(None)),
        )
    ).scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    clauses = db.execute(select(ContractPlaybookClause).where(ContractPlaybookClause.playbook_id == playbook.id).order_by(ContractPlaybookClause.title)).scalars().all()
    data = _format_playbook(playbook)
    data["clauses"] = [_format_playbook_clause(clause) for clause in clauses]
    return data


@router.post("/playbooks", status_code=status.HTTP_201_CREATED)
async def create_playbook(
    workspace_id: str,
    blueprint_id: str,
    body: ContractPlaybookIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    playbook = ContractPlaybook(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=_required_text(body.name, "playbook name"),
        contract_category=_required_text(body.contract_category, "contract category").lower(),
        jurisdiction=body.jurisdiction.strip() if body.jurisdiction else None,
        version=body.version.strip() or "1.0",
        status=_validate_playbook_status(body.status),
        rules_json=json.dumps(body.rules or {}, sort_keys=True),
        is_builtin=False,
        created_by_user_id=user.id,
    )
    db.add(playbook)
    db.flush()
    _replace_playbook_clauses(db, playbook.id, body.clauses)
    record_audit_event(
        db,
        action="contract_review.playbook.create",
        resource_type="contract_playbook",
        resource_id=playbook.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "contract_category": playbook.contract_category},
    )
    db.commit()
    db.refresh(playbook)
    return await get_playbook(workspace_id, blueprint_id, playbook.id, user, db)


@router.put("/playbooks/{playbook_id}")
async def update_playbook(
    workspace_id: str,
    blueprint_id: str,
    playbook_id: str,
    body: ContractPlaybookIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    playbook = db.execute(
        select(ContractPlaybook).where(ContractPlaybook.id == playbook_id, ContractPlaybook.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editable workspace playbook not found")
    if playbook.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in playbooks cannot be edited")
    playbook.name = _required_text(body.name, "playbook name")
    playbook.contract_category = _required_text(body.contract_category, "contract category").lower()
    playbook.jurisdiction = body.jurisdiction.strip() if body.jurisdiction else None
    playbook.version = body.version.strip() or playbook.version
    playbook.status = _validate_playbook_status(body.status)
    playbook.rules_json = json.dumps(body.rules or {}, sort_keys=True)
    playbook.updated_at = utcnow()
    db.execute(delete(ContractPlaybookClause).where(ContractPlaybookClause.playbook_id == playbook.id))
    _replace_playbook_clauses(db, playbook.id, body.clauses)
    record_audit_event(
        db,
        action="contract_review.playbook.update",
        resource_type="contract_playbook",
        resource_id=playbook.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "contract_category": playbook.contract_category},
    )
    db.commit()
    db.refresh(playbook)
    return await get_playbook(workspace_id, blueprint_id, playbook.id, user, db)


@router.get("/config")
async def get_config(workspace_id: str, blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    config = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review config not found")
    return _format_config(config)


@router.put("/config")
async def upsert_config(
    workspace_id: str,
    blueprint_id: str,
    body: ContractReviewConfigIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config_json = json.dumps(body.config, sort_keys=True)
    config = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if config:
        config.config_json = config_json
        config.updated_at = utcnow()
        action = "contract_review.config.update"
    else:
        config = ContractReviewConfig(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            config_json=config_json,
            created_by_user_id=user.id,
        )
        db.add(config)
        action = "contract_review.config.create"
    db.flush()
    record_audit_event(db, action=action, resource_type="contract_review_config", resource_id=config.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(config)
    return _format_config(config)


@router.get("/runs")
async def list_runs(workspace_id: str, blueprint_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    runs = (
        select(ContractReviewRun)
        .where(ContractReviewRun.workspace_id == workspace_id, ContractReviewRun.blueprint_id == blueprint_id)
        .order_by(ContractReviewRun.created_at.desc())
    )
    return page_query_response(db, runs, _format_run, page=page, page_size=page_size, scalars=True)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    workspace_id: str,
    blueprint_id: str,
    background_tasks: BackgroundTasks,
    body: ContractReviewRunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config = body.config
    if config is None:
        saved = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
        config = json_loads(saved.config_json, {}) if saved else {}
    mode = body.mode or config.get("mode") or "legacy"
    if mode not in {"legacy", "workflow"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported contract review mode")
    config = dict(config)
    config["mode"] = mode
    linked_document_ids = _link_config_documents(db, workspace_id, blueprint, config, user)
    config["document_ids"] = linked_document_ids
    run = ContractReviewRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        title=body.title.strip() or "Contract Review",
        status="pending",
        mode=mode,
        workflow_version="contract_review_workflow_v1" if mode == "workflow" else None,
        config_snapshot_json=json.dumps(config, sort_keys=True),
        created_by_user_id=user.id,
    )
    db.add(run)
    db.flush()
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="contract_review.run",
        metadata={"blueprint_id": blueprint_id, "run_id": run.id},
        message="Contract review queued",
    )
    record_audit_event(
        db,
        action="contract_review.run.create",
        resource_type="contract_review_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "job_id": job.id, "linked_document_ids": linked_document_ids},
    )
    db.commit()
    db.refresh(run)
    db.refresh(job)
    runner = execute_contract_review_workflow if mode == "workflow" else execute_contract_review
    background_tasks.add_task(run_background_job, job.id, runner, job.id, run.id)
    data = _format_run(run)
    data["job"] = format_job(job)
    return data


def _link_config_documents(db: Session, workspace_id: str, blueprint: BlueprintInstance, config: dict[str, Any], user: User) -> list[str]:
    raw_document_ids = config.get("document_ids") or []
    if not isinstance(raw_document_ids, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="document_ids must be a list")
    document_ids = [str(item) for item in raw_document_ids if str(item).strip()]
    if not document_ids:
        fallback_query = select(KnowledgeDocument).where(
            KnowledgeDocument.workspace_id == workspace_id,
            KnowledgeDocument.status == "indexed",
        )
        if blueprint.matter_id:
            fallback_query = fallback_query.where(KnowledgeDocument.matter_id == blueprint.matter_id)
        document_ids = [
            document.id
            for document in db.execute(fallback_query.order_by(KnowledgeDocument.created_at.asc())).scalars().all()
        ]
    if not document_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No indexed source documents are available for this Contract Review blueprint")
    linked: list[str] = []
    for document_id in document_ids:
        document = db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.id == document_id,
            )
        ).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected source document not found")
        if document.status != "indexed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Selected source document is not indexed: {document.original_name}")
        existing = db.execute(
            select(DocumentLink).where(
                DocumentLink.workspace_id == workspace_id,
                DocumentLink.blueprint_id == blueprint.id,
                DocumentLink.document_id == document_id,
            )
        ).scalar_one_or_none()
        if existing:
            linked.append(document_id)
            continue
        db.add(
            DocumentLink(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                document_id=document_id,
                blueprint_id=blueprint.id,
                link_type="source",
                created_by_user_id=user.id,
            )
        )
        linked.append(document_id)
    return linked


@router.get("/runs/{run_id}")
async def get_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    summaries = db.execute(select(ContractReviewSummary).where(ContractReviewSummary.run_id == run_id).order_by(ContractReviewSummary.audience)).scalars().all()
    return {
        "run": _format_run(run),
        "output": _format_output(output) if output else None,
        "summaries": [_format_summary(summary) for summary in summaries],
    }


@router.get("/runs/{run_id}/clauses")
async def list_run_clauses(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    risk_level: str | None = None,
    review_status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_run(db, workspace_id, blueprint_id, run_id, user)
    query = select(ContractClause).where(ContractClause.workspace_id == workspace_id, ContractClause.blueprint_id == blueprint_id, ContractClause.run_id == run_id)
    if review_status:
        query = query.where(ContractClause.review_status == review_status)
    clauses = db.execute(query.order_by(ContractClause.clause_type, ContractClause.created_at)).scalars().all()
    risk_by_clause: dict[str, list[dict]] = {}
    risks_query = select(ContractRiskFinding).where(ContractRiskFinding.run_id == run_id)
    if risk_level:
        risks_query = risks_query.where(ContractRiskFinding.risk_level == risk_level)
    for risk in db.execute(risks_query).scalars().all():
        if risk.clause_id:
            risk_by_clause.setdefault(risk.clause_id, []).append(_format_risk_finding(risk))
    if risk_level:
        clauses = [clause for clause in clauses if clause.id in risk_by_clause]
    return [{"clause": _format_clause(clause), "risks": risk_by_clause.get(clause.id, [])} for clause in clauses]


@router.get("/runs/{run_id}/clauses/{clause_id}")
async def get_run_clause(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    clause_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_run(db, workspace_id, blueprint_id, run_id, user)
    clause = db.execute(
        select(ContractClause).where(
            ContractClause.workspace_id == workspace_id,
            ContractClause.blueprint_id == blueprint_id,
            ContractClause.run_id == run_id,
            ContractClause.id == clause_id,
        )
    ).scalar_one_or_none()
    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    playbook_findings = db.execute(select(ContractPlaybookFinding).where(ContractPlaybookFinding.clause_id == clause_id)).scalars().all()
    playbook_clause_ids = [item.playbook_clause_id for item in playbook_findings if item.playbook_clause_id]
    playbook_clauses = []
    if playbook_clause_ids:
        playbook_clauses = db.execute(select(ContractPlaybookClause).where(ContractPlaybookClause.id.in_(playbook_clause_ids))).scalars().all()
    risk_findings = db.execute(select(ContractRiskFinding).where(ContractRiskFinding.clause_id == clause_id)).scalars().all()
    redlines = db.execute(select(ContractRedlineSuggestion).where(ContractRedlineSuggestion.clause_id == clause_id)).scalars().all()
    decisions = db.execute(select(ContractClauseReviewDecision).where(ContractClauseReviewDecision.clause_id == clause_id).order_by(ContractClauseReviewDecision.created_at.desc())).scalars().all()
    return {
        "clause": _format_clause(clause),
        "playbook_findings": [_format_playbook_finding(item) for item in playbook_findings],
        "playbook_clauses": [_format_playbook_clause(item) for item in playbook_clauses],
        "risk_findings": [_format_risk_finding(item) for item in risk_findings],
        "redline_suggestions": [_format_redline(item) for item in redlines],
        "decisions": [_format_decision(item) for item in decisions],
    }


@router.post("/runs/{run_id}/clauses/{clause_id}/decisions", status_code=status.HTTP_201_CREATED)
async def create_clause_decision(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    clause_id: str,
    body: ContractClauseDecisionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    if body.decision not in {"approve", "reject", "request_revision", "comment", "resolve", "escalate"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported clause decision")
    clause = db.execute(
        select(ContractClause).where(
            ContractClause.workspace_id == workspace_id,
            ContractClause.blueprint_id == blueprint_id,
            ContractClause.run_id == run_id,
            ContractClause.id == clause_id,
        )
    ).scalar_one_or_none()
    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")
    prior = {"review_status": clause.review_status}
    if body.decision in {"approve", "reject", "request_revision", "resolve", "escalate"}:
        clause.review_status = body.decision
        clause.updated_at = utcnow()
    decision = ContractClauseReviewDecision(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        run_id=run_id,
        clause_id=clause_id,
        user_id=user.id,
        decision=body.decision,
        note=body.note,
        prior_status_json=json.dumps(prior, sort_keys=True),
        metadata_json=json.dumps(body.metadata or {}, sort_keys=True),
    )
    db.add(decision)
    record_audit_event(
        db,
        action="contract_review.clause_decision.create",
        resource_type="contract_clause",
        resource_id=clause_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "run_id": run_id, "decision": body.decision},
    )
    db.commit()
    db.refresh(decision)
    return _format_decision(decision)


@router.get("/runs/{run_id}/trace")
async def get_run_trace(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_run(db, workspace_id, blueprint_id, run_id, user)
    steps = db.execute(select(ContractReviewStepOutput).where(ContractReviewStepOutput.run_id == run_id).order_by(ContractReviewStepOutput.created_at)).scalars().all()
    return [_format_step_output(step) for step in steps]


@router.get("/runs/{run_id}/audit-package")
async def get_run_audit_package(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _require_run(db, workspace_id, blueprint_id, run_id, user)
    if run.mode != "workflow":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audit package is available for structured workflow reviews")
    package = _workflow_audit_package(db, workspace_id, blueprint_id, run)
    record_audit_event(
        db,
        action="contract_review.run.audit_package",
        resource_type="contract_review_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id},
    )
    db.commit()
    return package


@router.put("/runs/{run_id}/complete")
async def complete_run_review(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    if run.mode != "workflow":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only structured workflow reviews can be marked complete")
    if run.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow processing must finish before review completion")
    blockers = _review_completion_blockers(db, workspace_id, blueprint_id, run_id)
    if blockers:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Review has unresolved blockers", "blockers": blockers})
    run.status_detail = "Review complete"
    record_audit_event(
        db,
        action="contract_review.run.complete",
        resource_type="contract_review_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id},
    )
    db.commit()
    db.refresh(run)
    return {"run": _format_run(run), "blockers": []}


@router.delete("/runs/{run_id}")
async def delete_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    db.execute(delete(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id))
    db.delete(run)
    record_audit_event(db, action="contract_review.run.delete", resource_type="contract_review_run", resource_id=run_id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    return {"ok": True}


@router.get("/runs/{run_id}/export")
async def export_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review output not found")
    record_audit_event(db, action="contract_review.run.export", resource_type="contract_review_run", resource_id=run.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    content = _workflow_export_markdown(db, run, output) if run.mode == "workflow" else _contract_export_markdown(run, output)
    return Response(content=content, media_type="text/markdown")


def _get_run_output(db: Session, workspace_id: str, blueprint_id: str, run_id: str) -> tuple[ContractReviewRun, ContractReviewOutput]:
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review output not found")
    return run, output


def _replace_playbook_clauses(db: Session, playbook_id: str, clauses: list[ContractPlaybookClauseIn]) -> None:
    for clause in clauses:
        db.add(
            ContractPlaybookClause(
                id=str(uuid.uuid4()),
                playbook_id=playbook_id,
                clause_type=_required_text(clause.clause_type, "clause type").lower(),
                title=_required_text(clause.title, "clause title"),
                approved_text=clause.approved_text,
                fallback_text=clause.fallback_text,
                prohibited_patterns_json=json.dumps(clause.prohibited_patterns or [], sort_keys=True),
                required=clause.required,
                severity_default=_validate_severity(clause.severity_default),
                metadata_json=json.dumps(clause.metadata or {}, sort_keys=True),
            )
        )


def _required_text(value: str, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name.title()} is required")
    return normalized


def _validate_playbook_status(value: str) -> str:
    normalized = (value or "active").strip().lower()
    if normalized not in {"active", "draft", "archived"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid playbook status")
    return normalized


def _validate_severity(value: str) -> str:
    normalized = (value or "medium").strip().lower()
    if normalized not in {"low", "medium", "high", "critical"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clause severity")
    return normalized


def _workflow_audit_package(db: Session, workspace_id: str, blueprint_id: str, run: ContractReviewRun) -> dict[str, Any]:
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run.id)).scalar_one_or_none()
    clauses = db.execute(select(ContractClause).where(ContractClause.run_id == run.id).order_by(ContractClause.clause_type, ContractClause.created_at)).scalars().all()
    clause_ids = [clause.id for clause in clauses]
    playbook_findings = db.execute(select(ContractPlaybookFinding).where(ContractPlaybookFinding.run_id == run.id).order_by(ContractPlaybookFinding.created_at)).scalars().all()
    risk_findings = db.execute(select(ContractRiskFinding).where(ContractRiskFinding.run_id == run.id).order_by(ContractRiskFinding.priority.desc(), ContractRiskFinding.created_at)).scalars().all()
    redlines = db.execute(select(ContractRedlineSuggestion).where(ContractRedlineSuggestion.run_id == run.id).order_by(ContractRedlineSuggestion.created_at)).scalars().all()
    decisions = db.execute(select(ContractClauseReviewDecision).where(ContractClauseReviewDecision.run_id == run.id).order_by(ContractClauseReviewDecision.created_at)).scalars().all()
    summaries = db.execute(select(ContractReviewSummary).where(ContractReviewSummary.run_id == run.id).order_by(ContractReviewSummary.audience)).scalars().all()
    steps = db.execute(select(ContractReviewStepOutput).where(ContractReviewStepOutput.run_id == run.id).order_by(ContractReviewStepOutput.created_at)).scalars().all()
    escalations = db.execute(
        select(Escalation)
        .where(
            Escalation.workspace_id == workspace_id,
            Escalation.blueprint_id == blueprint_id,
            Escalation.source_type == "contract_review_run",
            Escalation.source_id == run.id,
        )
        .order_by(Escalation.created_at)
    ).scalars().all()
    audit_resource_ids = [run.id] + clause_ids + [item.id for item in escalations]
    audit_query = select(AuditEvent).where(
        AuditEvent.workspace_id == workspace_id,
        or_(
            AuditEvent.resource_id.in_(audit_resource_ids),
            AuditEvent.metadata_json.like(f'%"run_id": "{run.id}"%'),
        ),
    )
    audit_events = db.execute(audit_query.order_by(AuditEvent.created_at)).scalars().all()
    return {
        "package_type": "contract_review_workflow_audit",
        "package_version": "1.0",
        "generated_at": utcnow().isoformat(),
        "run": _format_run(run),
        "output": _format_output(output) if output else None,
        "summaries": [_format_summary(item) for item in summaries],
        "clauses": [
            {
                "clause": _format_clause(clause),
                "playbook_findings": [_format_playbook_finding(item) for item in playbook_findings if item.clause_id == clause.id],
                "risk_findings": [_format_risk_finding(item) for item in risk_findings if item.clause_id == clause.id],
                "redline_suggestions": [_format_redline(item) for item in redlines if item.clause_id == clause.id],
                "decisions": [_format_decision(item) for item in decisions if item.clause_id == clause.id],
            }
            for clause in clauses
        ],
        "missing_playbook_findings": [_format_playbook_finding(item) for item in playbook_findings if item.clause_id is None],
        "unattached_risk_findings": [_format_risk_finding(item) for item in risk_findings if item.clause_id is None],
        "escalations": [_format_escalation(item) for item in escalations],
        "step_trace": [_format_step_output(item) for item in steps],
        "audit_events": [_format_audit_event(item) for item in audit_events],
        "human_oversight_notice": "This package records an AI-assisted contract review workflow. It is not autonomous legal advice and requires human legal oversight.",
    }


def _review_completion_blockers(db: Session, workspace_id: str, blueprint_id: str, run_id: str) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    open_escalations = db.execute(
        select(Escalation).where(
            Escalation.workspace_id == workspace_id,
            Escalation.blueprint_id == blueprint_id,
            Escalation.source_type == "contract_review_run",
            Escalation.source_id == run_id,
            Escalation.status == "open",
            Escalation.severity.in_(["high", "critical"]),
        )
    ).scalars().all()
    if open_escalations:
        blockers.append(
            {
                "type": "open_escalations",
                "count": len(open_escalations),
                "message": "Resolve or dismiss high and critical escalations before marking the review complete.",
            }
        )
    pending_clauses = db.execute(
        select(ContractClause).where(
            ContractClause.workspace_id == workspace_id,
            ContractClause.blueprint_id == blueprint_id,
            ContractClause.run_id == run_id,
            ContractClause.review_status == "pending",
        )
    ).scalars().all()
    if pending_clauses:
        blockers.append(
            {
                "type": "pending_clauses",
                "count": len(pending_clauses),
                "message": "Approve, reject, or request revision on all extracted clauses before marking the review complete.",
            }
        )
    return blockers


def _group_by_clause(items) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        clause_id = getattr(item, "clause_id", None)
        if clause_id:
            grouped.setdefault(clause_id, []).append(item)
    return grouped


def _source_locator(source: dict) -> str:
    filename = source.get("filename") or "source"
    if source.get("page"):
        return f"{filename} page {source.get('page')}"
    if source.get("chunk_index") is not None:
        return f"{filename} chunk {int(source.get('chunk_index')) + 1}"
    return filename


def _require_run(db: Session, workspace_id: str, blueprint_id: str, run_id: str, user: User) -> ContractReviewRun:
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    return run
