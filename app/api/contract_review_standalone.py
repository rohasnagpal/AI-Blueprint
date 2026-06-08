import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import database
from app.core.contract_agents.clause_extractor import extract_clauses
from app.core.contract_agents.conflict_detector import detect_conflicts
from app.core.contract_agents.escalation_detector import detect_escalations
from app.core.contract_agents.playbook_comparator import compare_to_playbook
from app.core.contract_agents.redliner import suggest_redlines
from app.core.contract_agents.risk_scorer import score_risks
from app.core.contract_agents.summarizer import build_summaries
from app.core.contract_agents.intake import run_intake
from app.core.contract_agents.agentic_review import ContractReviewAgentError, run_agentic_contract_review
from app.core.contract_agents.tools import SUPPORTED_TOOLS
from app.core.audit import record_audit_event
from app.core.contract_review_utils import client_summary, extract_fields, negotiation_memo, risk_matrix
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.error_sanitizer import sanitize_provider_error
from app.core.jobs import add_job_event, create_job, format_job, update_job_status
from app.core.json_utils import json_loads
from app.core.llm import configured_llm_provider, get_runtime_settings_with_secrets
from app.core.pagination import page_query_response
from app.core.secrets import decrypt_secret
from app.core.task_control import run_background_job
from app.core.models import (
    BlueprintInstance,
    BlueprintMember,
    ContractClause,
    ContractClauseReviewDecision,
    ContractPlaybook,
    ContractPlaybookClause,
    ContractPlaybookFinding,
    ContractRedlineSuggestion,
    ContractReviewOutput,
    ContractReviewRun,
    ContractReviewStepOutput,
    ContractReviewSummary,
    ContractRiskFinding,
    Escalation,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    Matter,
    Secret,
    User,
    utcnow,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/contract-review", tags=["contract-review-standalone"])


class StandaloneContractReviewIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    matter_id: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=12)
    playbook_id: str | None = None
    review_depth: str = Field(default="standard", max_length=50)
    instructions: str | None = Field(default=None, max_length=12000)


def _format_playbook(playbook: ContractPlaybook) -> dict:
    return {
        "id": playbook.id,
        "name": playbook.name,
        "contract_category": playbook.contract_category,
        "jurisdiction": playbook.jurisdiction,
        "version": playbook.version,
        "status": playbook.status,
        "is_builtin": playbook.is_builtin,
        "rules": json_loads(playbook.rules_json, {}),
    }


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> Matter:
    if not matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter is required")
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return matter


def _source_chunks(db: Session, workspace_id: str, body: StandaloneContractReviewIn) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
    document_ids = list(dict.fromkeys(str(item) for item in body.document_ids if str(item).strip()))[:12]
    if document_ids:
        docs = db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.id.in_(document_ids),
            )
        ).scalars().all()
        docs_by_id = {doc.id: doc for doc in docs}
        missing = [doc_id for doc_id in document_ids if doc_id not in docs_by_id]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more selected documents were not found")
        for doc in docs:
            if doc.status != "indexed":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Selected document is not indexed: {doc.original_name}")
            if doc.matter_id != body.matter_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected documents must belong to the selected matter")
        query = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.document_id.in_(document_ids))
        )
    else:
        query = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeDocument.status == "indexed")
        )
        if body.matter_id:
            query = query.where(KnowledgeDocument.matter_id == body.matter_id)
    chunks = db.execute(query.order_by(KnowledgeDocument.original_name, KnowledgeChunk.chunk_index).limit(80)).all()
    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No indexed contract documents are available for review")
    return chunks


def _sources(chunks: list[tuple[KnowledgeChunk, KnowledgeDocument]]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document.id,
            "filename": document.original_name,
            "chunk": chunk.chunk_index + 1,
            "excerpt": chunk.content[:500],
        }
        for chunk, document in chunks[:16]
    ]


def _source_bundle(chunks: list[tuple[KnowledgeChunk, KnowledgeDocument]]) -> list[dict[str, Any]]:
    bundle = []
    for chunk, document in chunks:
        metadata = json_loads(chunk.metadata_json, {})
        bundle.append(
            {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "filename": document.original_name,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "page": metadata.get("page"),
                "start_offset": metadata.get("start_offset"),
                "end_offset": metadata.get("end_offset"),
                "extraction_method": metadata.get("extraction_method"),
            }
        )
    return bundle


def _playbook_clauses(db: Session, playbook_id: str | None) -> list[ContractPlaybookClause]:
    if not playbook_id:
        return []
    return list(db.execute(select(ContractPlaybookClause).where(ContractPlaybookClause.playbook_id == playbook_id)).scalars().all())


def _first_playbook_for_category(db: Session, category: str | None, workspace_id: str) -> ContractPlaybook | None:
    query = select(ContractPlaybook).where(
        ContractPlaybook.status == "active",
        (ContractPlaybook.workspace_id == workspace_id) | (ContractPlaybook.workspace_id.is_(None)),
    )
    if category:
        query = query.where(ContractPlaybook.contract_category == category)
    playbooks = db.execute(query.order_by(ContractPlaybook.created_at.asc())).scalars().all()
    return sorted(playbooks, key=lambda item: (item.workspace_id is None, not item.is_builtin, item.created_at))[0] if playbooks else None


def _select_playbook(db: Session, workspace_id: str, playbook_id: str | None, category: str) -> ContractPlaybook | None:
    if playbook_id:
        playbook = db.execute(
            select(ContractPlaybook).where(
                ContractPlaybook.id == playbook_id,
                ContractPlaybook.status == "active",
                (ContractPlaybook.workspace_id == workspace_id) | (ContractPlaybook.workspace_id.is_(None)),
            )
        ).scalar_one_or_none()
        if not playbook:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
        return playbook
    preferred = category if category in {"msa", "nda", "dpa", "sow", "saas", "consulting", "reseller"} else None
    fallbacks = {"saas": ["msa"], "sow": ["msa"], "consulting": ["msa"], "reseller": ["msa"]}
    for candidate in ([preferred] if preferred else []) + fallbacks.get(category, []):
        playbook = _first_playbook_for_category(db, candidate, workspace_id)
        if playbook:
            return playbook
    return None


def _standalone_clause(workspace_id: str, run_id: str, item) -> ContractClause:
    source = item.source.model_dump()
    return ContractClause(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id="standalone",
        run_id=run_id,
        document_id=item.source.document_id,
        chunk_id=item.source.chunk_id,
        clause_type=item.clause_type,
        title=item.title,
        text=item.text,
        normalized_text=item.text.lower(),
        source_json=json.dumps(source, sort_keys=True),
        page=item.source.page,
        start_offset=item.source.start_offset,
        end_offset=item.source.end_offset,
        confidence_score=item.confidence_score,
        review_status="pending",
    )


def _format_clause(clause: ContractClause) -> dict[str, Any]:
    return {
        "id": clause.id,
        "clause_type": clause.clause_type,
        "title": clause.title,
        "text": clause.text,
        "source": json_loads(clause.source_json, {}),
        "confidence_score": clause.confidence_score,
        "review_status": clause.review_status,
    }


def _format_run_row(run: ContractReviewRun) -> dict[str, Any]:
    config = json_loads(run.config_snapshot_json, {})
    return {
        "id": run.id,
        "title": run.title,
        "mode": run.mode,
        "status": run.status,
        "status_detail": run.status_detail,
        "review_depth": config.get("review_depth"),
        "playbook_id": run.selected_playbook_id,
        "coverage_score": run.coverage_score,
        "config_snapshot": config,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


def _format_persisted_run(db: Session, workspace_id: str, run_id: str) -> dict[str, Any]:
    run = db.execute(select(ContractReviewRun).where(ContractReviewRun.workspace_id == workspace_id, ContractReviewRun.id == run_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract review output not found")
    metadata = json_loads(output.metadata_json, {})
    playbook = db.get(ContractPlaybook, run.selected_playbook_id) if run.selected_playbook_id else None
    return {
        "id": run.id,
        "title": run.title,
        "mode": "standalone",
        "review_depth": json_loads(run.config_snapshot_json, {}).get("review_depth", "standard"),
        "playbook": _format_playbook(playbook) if playbook else None,
        "extraction": json_loads(output.extraction_json, {}),
        "risk_matrix": json_loads(output.risk_matrix_json, []),
        "negotiation_memo": output.negotiation_memo,
        "client_summary": output.client_summary,
        "sources": json_loads(output.sources_json, []),
        "workflow": metadata.get("workflow", {}),
        "agentic_review": metadata.get("agentic_review", {"enabled": False, "trace": []}),
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "persisted": {"blueprint_id": run.blueprint_id, "run_id": run.id},
        "review_warnings": ["AI-assisted contract review. Human legal review is required before use or circulation."],
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _coverage_score(clauses: list[ContractClause], playbook_clauses: list[ContractPlaybookClause]) -> float | None:
    required = [item for item in playbook_clauses if item.required]
    if not required:
        return None
    extracted_types = {item.clause_type for item in clauses}
    return round(sum(1 for item in required if item.clause_type in extracted_types) / len(required), 4)


def _standalone_blueprint(db: Session, workspace_id: str, matter: Matter, user: User) -> BlueprintInstance:
    name = "Standalone Contract Review"
    blueprint = db.execute(
        select(BlueprintInstance).where(
            BlueprintInstance.workspace_id == workspace_id,
            BlueprintInstance.matter_id == matter.id,
            BlueprintInstance.plugin_id == "contract_review",
            BlueprintInstance.name == name,
            BlueprintInstance.status == "active",
        )
    ).scalar_one_or_none()
    if blueprint:
        member = db.execute(
            select(BlueprintMember).where(BlueprintMember.blueprint_id == blueprint.id, BlueprintMember.user_id == user.id)
        ).scalar_one_or_none()
        if not member:
            db.add(BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint.id, user_id=user.id, role="owner"))
            db.flush()
        return blueprint
    blueprint = BlueprintInstance(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=matter.id,
        plugin_id="contract_review",
        name=name,
        description="Hidden system blueprint used to persist standalone contract review agent runs.",
        status="active",
        created_by_user_id=user.id,
    )
    db.add(blueprint)
    db.add(BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint.id, user_id=user.id, role="owner"))
    db.flush()
    return blueprint


def _persist_review_state(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User,
    title: str,
    config: dict[str, Any],
    workflow: dict[str, Any],
    selected_playbook: ContractPlaybook | None,
    extraction: dict[str, Any],
    risks: list[dict[str, Any]],
    negotiation_memo_text: str,
    client_summary_text: str,
    sources: list[dict[str, Any]],
    agentic_review: dict[str, Any],
    provider: str | None,
    model: str | None,
) -> None:
    now = utcnow()
    run = ContractReviewRun(
        id=run_id,
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        title=title,
        status="completed",
        config_snapshot_json=json.dumps(config, sort_keys=True),
        mode="agentic_standalone",
        workflow_version=workflow.get("version") or "contract_review_workflow_v1",
        status_detail="Agentic standalone contract review completed.",
        selected_playbook_id=selected_playbook.id if selected_playbook else None,
        coverage_score=workflow.get("coverage_score"),
        source_anchor_version="knowledge_chunk_v1",
        created_by_user_id=user.id,
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()
    db.add(
        ContractReviewOutput(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            run_id=run_id,
            extraction_json=json.dumps(extraction, sort_keys=True),
            risk_matrix_json=json.dumps(risks, sort_keys=True),
            negotiation_memo=negotiation_memo_text,
            client_summary=client_summary_text,
            sources_json=json.dumps(sources, sort_keys=True),
            metadata_json=json.dumps(
                {
                    "agentic_review": {
                        "enabled": bool(agentic_review.get("agentic_enabled")),
                        "trace": agentic_review.get("agent_trace", []),
                        "quality_control": agentic_review.get("quality_control", {}),
                        "outputs": agentic_review.get("agent_outputs", {}),
                    },
                    "workflow": workflow,
                    "provider": provider,
                    "model": model,
                },
                sort_keys=True,
            ),
        )
    )
    _persist_workflow_detail(db, workspace_id, blueprint_id, run_id, user, workflow, selected_playbook)
    _persist_step_outputs(db, workspace_id, blueprint_id, run_id, config, workflow, agentic_review, provider, model)


def _persist_workflow_detail(
    db: Session,
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User,
    workflow: dict[str, Any],
    selected_playbook: ContractPlaybook | None,
) -> None:
    clauses_by_id: dict[str, dict[str, Any]] = {}
    for item in workflow.get("clauses", []):
        clause = item.get("clause") or {}
        clause_id = clause.get("id") or str(uuid.uuid4())
        source = clause.get("source") if isinstance(clause.get("source"), dict) else {}
        clauses_by_id[clause_id] = clause
        db.add(
            ContractClause(
                id=clause_id,
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                run_id=run_id,
                document_id=source.get("document_id"),
                chunk_id=source.get("chunk_id"),
                clause_type=clause.get("clause_type") or "unknown",
                title=clause.get("title"),
                text=clause.get("text") or "",
                normalized_text=(clause.get("text") or "").lower(),
                source_json=json.dumps(source, sort_keys=True),
                page=source.get("page"),
                start_offset=source.get("start_offset"),
                end_offset=source.get("end_offset"),
                confidence_score=clause.get("confidence_score"),
                review_status=clause.get("review_status") or "pending",
            )
        )
        for finding in item.get("playbook_findings", []):
            db.add(
                ContractPlaybookFinding(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    blueprint_id=blueprint_id,
                    run_id=run_id,
                    clause_id=finding.get("clause_id"),
                    playbook_id=selected_playbook.id if selected_playbook else None,
                    playbook_clause_id=finding.get("playbook_clause_id"),
                    status=finding.get("status") or "unknown",
                    deviation_summary=finding.get("deviation_summary"),
                    missing=bool(finding.get("missing")),
                    prohibited_match=finding.get("prohibited_match"),
                    confidence_score=finding.get("confidence_score"),
                    metadata_json=json.dumps({"source": "agentic_standalone_workflow"}, sort_keys=True),
                )
            )
        for risk in item.get("risks", []):
            _add_risk_finding(db, workspace_id, blueprint_id, run_id, risk)
        for redline in item.get("redline_suggestions", []):
            db.add(
                ContractRedlineSuggestion(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    blueprint_id=blueprint_id,
                    run_id=run_id,
                    clause_id=redline.get("clause_id"),
                    suggestion_text=redline.get("suggestion_text") or "",
                    fallback_language=redline.get("fallback_language"),
                    rationale=redline.get("rationale"),
                    source_playbook_id=selected_playbook.id if selected_playbook else None,
                    confidence_score=redline.get("confidence_score"),
                    status="draft",
                    metadata_json=json.dumps({"source": "agentic_standalone_workflow"}, sort_keys=True),
                )
            )
    for risk in workflow.get("unattached_risk_findings", []):
        _add_risk_finding(db, workspace_id, blueprint_id, run_id, risk)
    for summary in workflow.get("summaries", []):
        db.add(
            ContractReviewSummary(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                run_id=run_id,
                audience=summary.get("audience") or "summary",
                summary_text=summary.get("summary_text") or "",
                obligations_json=json.dumps(summary.get("obligations") or [], sort_keys=True),
                negotiation_points_json=json.dumps(summary.get("negotiation_points") or [], sort_keys=True),
                unusual_terms_json=json.dumps(summary.get("unusual_terms") or [], sort_keys=True),
                metadata_json=json.dumps({"source": "agentic_standalone_workflow"}, sort_keys=True),
            )
        )
    for escalation in workflow.get("escalations", []):
        db.add(
            Escalation(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                source_type="contract_review_run",
                source_id=run_id,
                severity=escalation.get("severity") or "high",
                status="open",
                reason=escalation.get("reason") or "Contract review escalation",
                required_action=escalation.get("required_action") or "Human lawyer review required.",
                metadata_json=json.dumps(
                    {"clause_id": escalation.get("clause_id"), **(escalation.get("metadata") or {})},
                    sort_keys=True,
                ),
                created_by_user_id=user.id,
            )
        )


def _add_risk_finding(db: Session, workspace_id: str, blueprint_id: str, run_id: str, risk: dict[str, Any]) -> None:
    db.add(
        ContractRiskFinding(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            run_id=run_id,
            clause_id=risk.get("clause_id"),
            risk_level=risk.get("risk_level") or risk.get("severity") or "low",
            likelihood=risk.get("likelihood"),
            impact=risk.get("impact"),
            priority=risk.get("priority"),
            reasoning=risk.get("reasoning") or risk.get("finding") or "",
            requires_review=bool(risk.get("requires_review")),
            confidence_score=risk.get("confidence_score"),
            metadata_json=json.dumps({"source": "agentic_standalone_workflow"}, sort_keys=True),
        )
    )


def _persist_step_outputs(
    db: Session,
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    config: dict[str, Any],
    workflow: dict[str, Any],
    agentic_review: dict[str, Any],
    provider: str | None,
    model: str | None,
) -> None:
    agent_outputs = agentic_review.get("agent_outputs", {}) if isinstance(agentic_review.get("agent_outputs"), dict) else {}
    for step in workflow.get("trace", []):
        db.add(
            ContractReviewStepOutput(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                run_id=run_id,
                step_name=step.get("step_name") or "workflow_step",
                step_version=workflow.get("version"),
                status=step.get("status") or "completed",
                input_json=json.dumps(config, sort_keys=True),
                output_json=json.dumps(step, sort_keys=True),
                confidence_score=step.get("confidence_score"),
                provider=None,
                model=None,
                error=step.get("error"),
                metadata_json=json.dumps({"kind": "deterministic_workflow"}, sort_keys=True),
                started_at=utcnow(),
                completed_at=utcnow(),
            )
        )
    for step in agentic_review.get("agent_trace", []):
        step_name = step.get("step_name") or "agent_step"
        db.add(
            ContractReviewStepOutput(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                blueprint_id=blueprint_id,
                run_id=run_id,
                step_name=step_name,
                step_version="agentic_contract_review_v1",
                status=step.get("status") or "completed",
                input_json=json.dumps(config, sort_keys=True),
                output_json=json.dumps(agent_outputs.get(step_name, {}), sort_keys=True),
                confidence_score=None,
                provider=step.get("provider") or provider,
                model=step.get("model") or model,
                error=step.get("error"),
                metadata_json=json.dumps({"kind": "llm_agent", "duration_ms": step.get("duration_ms")}, sort_keys=True),
                started_at=utcnow(),
                completed_at=utcnow(),
            )
        )


def _workflow_review(db: Session, workspace_id: str, run_id: str, chunks: list[tuple[KnowledgeChunk, KnowledgeDocument]], playbook_id: str | None) -> tuple[dict[str, Any], ContractPlaybook | None]:
    bundle = _source_bundle(chunks)
    full_text = "\n\n".join(item["content"] for item in bundle)
    intake = run_intake(full_text)
    playbook = _select_playbook(db, workspace_id, playbook_id, intake.contract_category)
    playbook_clauses = _playbook_clauses(db, playbook.id if playbook else None)
    extracted = extract_clauses(bundle)
    clauses = [_standalone_clause(workspace_id, run_id, item) for item in extracted]
    playbook_findings = compare_to_playbook(clauses, playbook_clauses)
    risks = score_risks(playbook_findings)
    conflicts = detect_conflicts(clauses)
    redlines = suggest_redlines(clauses, risks, playbook_clauses)
    summaries = build_summaries(intake, clauses, risks)
    escalations = detect_escalations(risks) + conflicts
    risks_by_clause: dict[str, list[dict[str, Any]]] = {}
    for risk in risks:
        if risk.clause_id:
            risks_by_clause.setdefault(risk.clause_id, []).append(risk.model_dump())
    findings_by_clause: dict[str, list[dict[str, Any]]] = {}
    for finding in playbook_findings:
        if finding.clause_id:
            findings_by_clause.setdefault(finding.clause_id, []).append(finding.model_dump())
    redlines_by_clause: dict[str, list[dict[str, Any]]] = {}
    for redline in redlines:
        redlines_by_clause.setdefault(redline.clause_id, []).append(redline.model_dump())
    return (
        {
            "version": "contract_review_workflow_v1",
            "intake": intake.model_dump(),
            "coverage_score": _coverage_score(clauses, playbook_clauses),
            "stats": {
                "clauses": len(clauses),
                "review_needed": sum(1 for risk in risks if risk.requires_review),
                "high": sum(1 for risk in risks if risk.risk_level == "high"),
                "critical": sum(1 for risk in risks if risk.risk_level == "critical"),
                "escalations": len(escalations),
            },
            "summaries": [item.model_dump() for item in summaries],
            "clauses": [
                {
                    "clause": _format_clause(clause),
                    "risks": risks_by_clause.get(clause.id, []),
                    "playbook_findings": findings_by_clause.get(clause.id, []),
                    "redline_suggestions": redlines_by_clause.get(clause.id, []),
                }
                for clause in clauses
            ],
            "unattached_risk_findings": [risk.model_dump() for risk in risks if not risk.clause_id],
            "escalations": [item.model_dump() for item in escalations],
            "trace": [
                {"step_name": "intake", "status": "completed", "confidence_score": intake.confidence_score},
                {"step_name": "clause_extraction", "status": "completed", "confidence_score": None},
                {"step_name": "playbook_comparison", "status": "completed", "confidence_score": None},
                {"step_name": "risk_scoring", "status": "completed", "confidence_score": None},
                {"step_name": "conflict_detection", "status": "completed", "confidence_score": None},
                {"step_name": "redline_suggestions", "status": "completed", "confidence_score": None},
                {"step_name": "summarization", "status": "completed", "confidence_score": None},
                {"step_name": "escalation_detection", "status": "completed", "confidence_score": None},
            ],
        },
        playbook,
    )


@router.get("/playbooks")
async def list_standalone_playbooks(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    playbooks = db.execute(
        select(ContractPlaybook)
        .where(
            ContractPlaybook.status == "active",
            (ContractPlaybook.workspace_id == workspace_id) | (ContractPlaybook.workspace_id.is_(None)),
        )
        .order_by(ContractPlaybook.is_builtin.desc(), ContractPlaybook.name)
    ).scalars().all()
    return [_format_playbook(playbook) for playbook in playbooks]


@router.get("/runs")
async def list_standalone_runs(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    rows = (
        select(ContractReviewRun)
        .where(ContractReviewRun.workspace_id == workspace_id, ContractReviewRun.mode == "agentic_standalone")
        .order_by(ContractReviewRun.created_at.desc())
    )
    return page_query_response(db, rows, _format_run_row, page=page, page_size=page_size, scalars=True)


@router.get("/runs/{run_id}")
async def get_standalone_run(
    workspace_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    return _format_persisted_run(db, workspace_id, run_id)


@router.delete("/runs/{run_id}")
async def delete_standalone_run(
    workspace_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.id == run_id,
            ContractReviewRun.mode == "agentic_standalone",
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract review run not found")
    for model in (
        ContractClauseReviewDecision,
        ContractRedlineSuggestion,
        ContractRiskFinding,
        ContractPlaybookFinding,
        ContractReviewSummary,
        ContractReviewStepOutput,
        ContractReviewOutput,
        ContractClause,
    ):
        db.execute(delete(model).where(model.workspace_id == workspace_id, model.run_id == run_id))
    db.execute(
        delete(Escalation).where(
            Escalation.workspace_id == workspace_id,
            Escalation.source_type == "contract_review_run",
            Escalation.source_id == run_id,
        )
    )
    db.delete(run)
    record_audit_event(
        db,
        action="contract_review_standalone.delete",
        resource_type="contract_review_standalone",
        resource_id=run_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"title": run.title},
    )
    db.commit()
    return {"deleted": True, "id": run_id}


def _execute_standalone_contract_review(
    db: Session,
    *,
    workspace_id: str,
    body: StandaloneContractReviewIn,
    user: User,
    run_id: str | None = None,
    job: Job | None = None,
) -> dict[str, Any]:
    matter = _validate_matter(db, workspace_id, body.matter_id)
    chunks = _source_chunks(db, workspace_id, body)
    run_id = run_id or str(uuid.uuid4())
    blueprint = _standalone_blueprint(db, workspace_id, matter, user)
    if job:
        update_job_status(db, job=job, status="running", progress=10, message="Contract review started")
        add_job_event(db, job=job, event_type="progress", message="Running deterministic workflow", metadata={"progress": 20, "run_id": run_id})
        db.commit()
    workflow, selected_playbook = _workflow_review(db, workspace_id, run_id, chunks, body.playbook_id)
    playbook_clauses = _playbook_clauses(db, selected_playbook.id if selected_playbook else None)
    source_bundle = _source_bundle(chunks)
    if job:
        add_job_event(db, job=job, event_type="progress", message="Running specialist contract agents", metadata={"progress": 45, "run_id": run_id})
        job.progress = max(job.progress, 45)
        db.commit()
    full_text = "\n\n".join(chunk.content for chunk, _document in chunks)
    config = {
        "review_depth": body.review_depth or "standard",
        "instructions": body.instructions or "",
        "playbook_id": selected_playbook.id if selected_playbook else None,
        "playbook_name": selected_playbook.name if selected_playbook else None,
        "mode": "standalone",
        "matter_id": matter.id,
        "document_ids": body.document_ids,
    }
    extraction = extract_fields(full_text, config)
    risks = risk_matrix(full_text)
    sources = _sources(chunks)
    deterministic_negotiation_memo = negotiation_memo(extraction, risks)
    deterministic_client_summary = client_summary(extraction, risks)
    settings = _runtime_settings_for_workspace(db, workspace_id, user)

    def agent_progress(message: str, progress: int) -> None:
        if not job:
            return
        job.progress = max(job.progress or 0, progress)
        add_job_event(db, job=job, event_type="progress", message=message, metadata={"progress": job.progress, "run_id": run_id})
        db.commit()

    try:
        agentic_review = run_agentic_contract_review(
            text=full_text,
            sources=sources,
            config=config,
            workflow=workflow,
            deterministic_extraction=extraction,
            deterministic_risks=risks,
            deterministic_negotiation_memo=deterministic_negotiation_memo,
            deterministic_client_summary=deterministic_client_summary,
            settings=settings,
            tool_context={
                "source_bundle": source_bundle,
                "playbook": selected_playbook,
                "playbook_clauses": playbook_clauses,
                "supported_tools": sorted(SUPPORTED_TOOLS),
            },
            progress_callback=agent_progress,
        )
    except ContractReviewAgentError as exc:
        if not _is_recoverable_agent_output_error(str(exc)):
            raise
        agent_progress("Specialist agents returned malformed JSON; using deterministic review output", 84)
        agentic_review = _deterministic_agentic_review_fallback(
            provider=configured_llm_provider(settings),
            model=settings.get("chat_model"),
            error=str(exc),
            extraction=extraction,
            risks=risks,
            negotiation_memo_text=deterministic_negotiation_memo,
            client_summary_text=deterministic_client_summary,
        )
    extraction = agentic_review.get("extraction", extraction)
    risks = agentic_review.get("risk_matrix", risks)
    negotiation_memo_text = agentic_review.get("negotiation_memo") or deterministic_negotiation_memo
    client_summary_text = agentic_review.get("client_summary") or deterministic_client_summary
    provider = configured_llm_provider(settings)
    model = settings.get("chat_model") if provider else None
    if job:
        add_job_event(db, job=job, event_type="progress", message="Persisting review trace", metadata={"progress": 80, "run_id": run_id})
        job.progress = max(job.progress, 80)
        db.commit()
    _persist_review_state(
        db,
        workspace_id=workspace_id,
        blueprint_id=blueprint.id,
        run_id=run_id,
        user=user,
        title=body.title or "Contract Review",
        config=config,
        workflow=workflow,
        selected_playbook=selected_playbook,
        extraction=extraction,
        risks=risks,
        negotiation_memo_text=negotiation_memo_text,
        client_summary_text=client_summary_text,
        sources=sources,
        agentic_review=agentic_review,
        provider=provider,
        model=model,
    )
    payload = {
        "id": run_id,
        "title": body.title or "Contract Review",
        "mode": "standalone",
        "review_depth": config["review_depth"],
        "playbook": _format_playbook(selected_playbook) if selected_playbook else None,
        "extraction": extraction,
        "risk_matrix": risks,
        "negotiation_memo": negotiation_memo_text,
        "client_summary": client_summary_text,
        "sources": sources,
        "workflow": workflow,
        "agentic_review": {
            "enabled": bool(agentic_review.get("agentic_enabled")),
            "trace": agentic_review.get("agent_trace", []),
            "quality_control": agentic_review.get("quality_control", {}),
            "outputs": agentic_review.get("agent_outputs", {}),
        },
        "provider": provider,
        "model": model,
        "persisted": {"blueprint_id": blueprint.id, "run_id": run_id},
        "review_warnings": ["AI-assisted contract review. Human legal review is required before use or circulation."],
    }
    record_audit_event(
        db,
        action="contract_review_standalone.run",
        resource_type="contract_review_standalone",
        resource_id=payload["id"],
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_count": len({doc.id for _chunk, doc in chunks}), "playbook_id": body.playbook_id},
    )
    return payload


def _runtime_settings_for_workspace(db: Session, workspace_id: str, user: User) -> dict:
    settings = get_runtime_settings_with_secrets()
    secret_rows = db.execute(
        select(Secret).where(
            Secret.workspace_id == workspace_id,
            Secret.status == "active",
            (
                (Secret.scope.in_(("workspace", "admin")))
                | ((Secret.scope == "user") & (Secret.owner_user_id == user.id))
            ),
        )
    ).scalars()
    for secret in secret_rows:
        setting_key = secret.name.strip().lower()
        if setting_key not in database.API_KEY_FIELDS:
            continue
        value = decrypt_secret(secret.encrypted_value)
        if value:
            settings[setting_key] = value
    return settings


def _is_agent_invalid_json_error(error: str) -> bool:
    return _is_recoverable_agent_output_error(error)


def _is_recoverable_agent_output_error(error: str) -> bool:
    lower = (error or "").lower()
    return "invalid json" in lower or "did not return required" in lower or "incomplete json" in lower


def _deterministic_agentic_review_fallback(
    *,
    provider: str | None,
    model: str | None,
    error: str,
    extraction: dict[str, Any],
    risks: list[dict[str, Any]],
    negotiation_memo_text: str,
    client_summary_text: str,
) -> dict[str, Any]:
    return {
        "extraction": extraction,
        "risk_matrix": risks,
        "negotiation_memo": negotiation_memo_text,
        "client_summary": client_summary_text,
        "agentic_enabled": True,
        "quality_control": {
            "approved": True,
            "issues": [{"issue": "Specialist agents returned malformed JSON; deterministic outputs require human review."}],
            "corrections": {},
        },
        "agent_trace": [
            {
                "step_name": "agentic_contract_review",
                "status": "fallback",
                "provider": provider,
                "model": model,
                "duration_ms": None,
                "error": error,
            }
        ],
        "agent_outputs": {
            "deterministic_fallback": {
                "reason": "invalid_agent_json",
                "error": error,
            }
        },
    }


def _run_standalone_contract_review_job(job_id: str, workspace_id: str, user_id: str, body_data: dict[str, Any], run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        user = db.get(User, user_id)
        if not job or not user:
            return
        try:
            body = StandaloneContractReviewIn(**body_data)
            payload = _execute_standalone_contract_review(db, workspace_id=workspace_id, body=body, user=user, run_id=run_id, job=job)
            metadata = json_loads(job.metadata_json, {})
            metadata.update({"run_id": run_id, "result_url": f"/api/v2/workspaces/{workspace_id}/contract-review/runs/{run_id}"})
            job.metadata_json = json.dumps(metadata, sort_keys=True)
            update_job_status(db, job=job, status="completed", progress=100, message="Contract review completed")
            add_job_event(db, job=job, event_type="result", message="Contract review result ready", metadata={"run_id": run_id, "title": payload["title"]})
            db.commit()
        except Exception as exc:
            update_job_status(
                db,
                job=job,
                status="failed",
                progress=job.progress,
                message="Contract review failed",
                error=sanitize_provider_error(exc),
            )
            db.commit()


@router.post("")
@router.post("/", include_in_schema=False)
async def run_standalone_contract_review(
    workspace_id: str,
    body: StandaloneContractReviewIn,
    background_tasks: BackgroundTasks,
    sync: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    if sync:
        try:
            payload = _execute_standalone_contract_review(db, workspace_id=workspace_id, body=body, user=user)
        except ContractReviewAgentError as exc:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
        db.commit()
        return payload
    _validate_matter(db, workspace_id, body.matter_id)
    _source_chunks(db, workspace_id, body)
    run_id = str(uuid.uuid4())
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="contract_review.run",
        metadata={"run_id": run_id, "title": body.title or "Contract Review"},
        message="Contract review queued",
    )
    record_audit_event(
        db,
        action="contract_review_standalone.queue",
        resource_type="contract_review_standalone",
        resource_id=run_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"job_id": job.id, "document_count": len(set(body.document_ids)), "playbook_id": body.playbook_id},
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, _run_standalone_contract_review_job, job.id, workspace_id, user.id, body.model_dump(), run_id)
    return {"status": "queued", "run_id": run_id, "job": format_job(job)}
