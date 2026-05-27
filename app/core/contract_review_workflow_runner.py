import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contract_agents.clause_extractor import extract_clauses
from app.core.contract_agents.conflict_detector import detect_conflicts
from app.core.contract_agents.escalation_detector import detect_escalations
from app.core.contract_agents.intake import run_intake
from app.core.contract_agents.playbook_comparator import compare_to_playbook
from app.core.contract_agents.redliner import suggest_redlines
from app.core.contract_agents.risk_scorer import score_risks
from app.core.contract_agents.summarizer import build_summaries
from app.core.database import SessionLocal
from app.core.jobs import JobCancelled, add_job_event, ensure_job_not_cancelled, update_job_status
from app.core.json_utils import json_loads
from app.core.models import (
    ContractClause,
    ContractPlaybook,
    ContractPlaybookClause,
    ContractPlaybookFinding,
    ContractRedlineSuggestion,
    ContractReviewOutput,
    ContractReviewRun,
    ContractReviewStepOutput,
    ContractReviewSummary,
    ContractRiskFinding,
    DocumentLink,
    Escalation,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    utcnow,
)
from app.core.skills import record_skill_run


WORKFLOW_VERSION = "contract_review_workflow_v1"


def execute_contract_review_workflow(job_id: str, run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run = db.get(ContractReviewRun, run_id)
        if not job or not run:
            return
        try:
            ensure_job_not_cancelled(db, job)
            config = json_loads(run.config_snapshot_json, {})
            run.status = "running"
            run.started_at = utcnow()
            run.mode = "workflow"
            run.workflow_version = WORKFLOW_VERSION
            run.source_anchor_version = "1"
            run.status_detail = "Workflow review started"
            update_job_status(db, job=job, status="running", progress=5, message="Contract workflow review started")
            db.commit()

            chunks = _linked_chunks(db, run)
            if not chunks:
                raise RuntimeError("No indexed documents are linked to this Contract Review blueprint")
            source_bundle = _source_bundle(chunks)
            full_text = "\n\n".join(item["content"] for item in source_bundle)
            _record_step(db, run, "source_bundle", {"linked_documents": len(chunks)}, {"chunks": len(source_bundle), "text_chars": len(full_text)}, status="completed")
            add_job_event(db, job=job, event_type="progress", message="Loaded source bundle", metadata={"progress": 12, "chunks": len(source_bundle)})
            job.progress = 12
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            intake = run_intake(full_text)
            _record_step(db, run, "intake", {"text_chars": len(full_text)}, intake.model_dump(), confidence=intake.confidence_score)
            add_job_event(db, job=job, event_type="progress", message="Completed intake", metadata={"progress": 22, "contract_category": intake.contract_category})
            job.progress = 22
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            playbook = _select_playbook(db, config, intake.contract_category)
            if playbook:
                run.selected_playbook_id = playbook.id
            clause_results = extract_clauses(source_bundle)
            clauses = _persist_clauses(db, run, clause_results)
            _record_step(db, run, "clause_extraction", {"chunks": len(source_bundle)}, [item.model_dump() for item in clause_results], confidence=_avg([item.confidence_score for item in clause_results]))
            add_job_event(db, job=job, event_type="progress", message="Extracted contract clauses", metadata={"progress": 40, "clauses": len(clauses)})
            job.progress = 40
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            playbook_clauses = _playbook_clauses(db, playbook.id) if playbook else []
            comparison_results = compare_to_playbook(clauses, playbook_clauses)
            _persist_playbook_findings(db, run, comparison_results, playbook)
            _record_step(
                db,
                run,
                "playbook_comparison",
                {"playbook_id": playbook.id if playbook else None, "clauses": len(clauses)},
                [item.model_dump() for item in comparison_results],
                confidence=_avg([item.confidence_score for item in comparison_results]),
            )
            add_job_event(db, job=job, event_type="progress", message="Compared clauses to playbook", metadata={"progress": 55, "findings": len(comparison_results)})
            job.progress = 55
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            risk_results = score_risks(comparison_results)
            _persist_risk_findings(db, run, risk_results)
            _record_step(db, run, "risk_scoring", {"findings": len(comparison_results)}, [item.model_dump() for item in risk_results], confidence=_avg([item.confidence_score for item in risk_results]))
            add_job_event(db, job=job, event_type="progress", message="Scored contract risks", metadata={"progress": 68, "risks": len(risk_results)})
            job.progress = 68
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            conflict_results = detect_conflicts(clauses)
            _record_step(db, run, "conflict_detection", {"clauses": len(clauses)}, [item.model_dump() for item in conflict_results], status="completed")
            add_job_event(db, job=job, event_type="progress", message="Checked contract conflicts", metadata={"progress": 72, "conflicts": len(conflict_results)})
            job.progress = 72
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            redline_results = suggest_redlines(clauses, risk_results, playbook_clauses)
            _persist_redlines(db, run, redline_results, playbook)
            _record_step(db, run, "redline_suggestions", {"risks": len(risk_results)}, [item.model_dump() for item in redline_results], confidence=_avg([item.confidence_score for item in redline_results]))
            add_job_event(db, job=job, event_type="progress", message="Generated draft redline suggestions", metadata={"progress": 78, "suggestions": len(redline_results)})
            job.progress = 78
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            summary_results = build_summaries(intake, clauses, risk_results)
            _persist_summaries(db, run, summary_results)
            _record_step(db, run, "summarization", {"clauses": len(clauses), "risks": len(risk_results)}, [item.model_dump() for item in summary_results], status="completed")
            add_job_event(db, job=job, event_type="progress", message="Built review summaries", metadata={"progress": 86, "summaries": len(summary_results)})
            job.progress = 86
            job.heartbeat_at = utcnow()
            db.commit()

            ensure_job_not_cancelled(db, job)
            escalation_results = detect_escalations(risk_results) + conflict_results
            _persist_escalations(db, run, escalation_results)
            _record_step(db, run, "escalation_detection", {"risks": len(risk_results), "conflicts": len(conflict_results)}, [item.model_dump() for item in escalation_results], status="completed")
            run.coverage_score = _coverage_score(clauses, playbook_clauses)
            _persist_compat_output(db, run, intake.model_dump(), risk_results, summary_results, source_bundle)
            run.status = "completed"
            run.status_detail = "Workflow review completed as AI-assisted draft"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="completed", progress=100, message="Contract workflow review completed")
            db.commit()
        except JobCancelled:
            run.status = "cancelled"
            run.status_detail = "Workflow review cancelled"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="cancelled", progress=job.progress, message="Contract workflow review cancelled")
            db.commit()
        except Exception as exc:
            if run:
                run.status = "failed"
                run.status_detail = "Workflow review failed"
                run.error = str(exc)
                run.completed_at = utcnow()
            if job:
                update_job_status(db, job=job, status="failed", progress=job.progress, message="Contract workflow review failed", error=str(exc))
            db.commit()


def _linked_chunks(db: Session, run: ContractReviewRun):
    return db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(DocumentLink, DocumentLink.document_id == KnowledgeDocument.id)
        .where(
            DocumentLink.workspace_id == run.workspace_id,
            DocumentLink.blueprint_id == run.blueprint_id,
            KnowledgeDocument.status == "indexed",
        )
        .order_by(KnowledgeDocument.original_name, KnowledgeChunk.chunk_index)
    ).all()


def _source_bundle(chunks) -> list[dict[str, Any]]:
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


def _select_playbook(db: Session, config: dict, category: str) -> ContractPlaybook | None:
    if config.get("playbook_id"):
        playbook = db.get(ContractPlaybook, str(config["playbook_id"]))
        if playbook:
            return playbook
    preferred = category if category in {"msa", "nda", "dpa", "sow", "saas", "consulting", "reseller"} else None
    query = select(ContractPlaybook).where(ContractPlaybook.status == "active")
    if preferred:
        query = query.where(ContractPlaybook.contract_category == preferred)
    return db.execute(query.order_by(ContractPlaybook.is_builtin.desc(), ContractPlaybook.created_at.asc())).scalars().first()


def _playbook_clauses(db: Session, playbook_id: str) -> list[ContractPlaybookClause]:
    return list(db.execute(select(ContractPlaybookClause).where(ContractPlaybookClause.playbook_id == playbook_id)).scalars().all())


def _persist_clauses(db: Session, run: ContractReviewRun, clause_results) -> list[ContractClause]:
    rows = []
    for item in clause_results:
        row = ContractClause(
            id=str(uuid.uuid4()),
            workspace_id=run.workspace_id,
            blueprint_id=run.blueprint_id,
            run_id=run.id,
            document_id=item.source.document_id,
            chunk_id=item.source.chunk_id,
            clause_type=item.clause_type,
            title=item.title,
            text=item.text,
            normalized_text=item.text.lower(),
            source_json=json.dumps(item.source.model_dump(), sort_keys=True),
            page=item.source.page,
            start_offset=item.source.start_offset,
            end_offset=item.source.end_offset,
            confidence_score=item.confidence_score,
            review_status="pending",
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _persist_playbook_findings(db: Session, run: ContractReviewRun, findings, playbook: ContractPlaybook | None) -> None:
    for item in findings:
        db.add(
            ContractPlaybookFinding(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                clause_id=item.clause_id,
                playbook_id=playbook.id if playbook else None,
                playbook_clause_id=item.playbook_clause_id,
                status=item.status,
                deviation_summary=item.deviation_summary,
                missing=item.missing,
                prohibited_match=item.prohibited_match,
                confidence_score=item.confidence_score,
            )
        )


def _persist_risk_findings(db: Session, run: ContractReviewRun, risks) -> None:
    for item in risks:
        db.add(
            ContractRiskFinding(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                clause_id=item.clause_id,
                risk_level=item.risk_level,
                likelihood=item.likelihood,
                impact=item.impact,
                priority=item.priority,
                reasoning=item.reasoning,
                requires_review=item.requires_review,
                confidence_score=item.confidence_score,
            )
        )


def _persist_redlines(db: Session, run: ContractReviewRun, suggestions, playbook: ContractPlaybook | None) -> None:
    for item in suggestions:
        db.add(
            ContractRedlineSuggestion(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                clause_id=item.clause_id,
                suggestion_text=item.suggestion_text,
                fallback_language=item.fallback_language,
                rationale=item.rationale,
                source_playbook_id=playbook.id if playbook else None,
                confidence_score=item.confidence_score,
                status="draft",
            )
        )


def _persist_summaries(db: Session, run: ContractReviewRun, summaries) -> None:
    for item in summaries:
        db.add(
            ContractReviewSummary(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                audience=item.audience,
                summary_text=item.summary_text,
                obligations_json=json.dumps(item.obligations, sort_keys=True),
                negotiation_points_json=json.dumps(item.negotiation_points, sort_keys=True),
                unusual_terms_json=json.dumps(item.unusual_terms, sort_keys=True),
            )
        )


def _persist_escalations(db: Session, run: ContractReviewRun, escalations) -> None:
    for item in escalations:
        db.add(
            Escalation(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                source_type="contract_review_run",
                source_id=run.id,
                severity=item.severity,
                status="open",
                reason=item.reason,
                required_action=item.required_action,
                metadata_json=json.dumps(item.metadata | {"clause_id": item.clause_id}, sort_keys=True),
                created_by_user_id=run.created_by_user_id,
            )
        )


def _record_step(
    db: Session,
    run: ContractReviewRun,
    step_name: str,
    input_data: dict,
    output_data: dict | list,
    *,
    status: str = "completed",
    confidence: float | None = None,
    error: str | None = None,
) -> None:
    now = utcnow()
    db.add(
        ContractReviewStepOutput(
            id=str(uuid.uuid4()),
            workspace_id=run.workspace_id,
            blueprint_id=run.blueprint_id,
            run_id=run.id,
            step_name=step_name,
            step_version="1",
            status=status,
            input_json=json.dumps(input_data or {}, sort_keys=True),
            output_json=json.dumps(output_data if output_data is not None else {}, sort_keys=True),
            confidence_score=confidence,
            error=error,
            metadata_json=json.dumps({"runner": WORKFLOW_VERSION}, sort_keys=True),
            started_at=now,
            completed_at=now if status in {"completed", "failed"} else None,
        )
    )
    record_skill_run(
        db,
        workspace_id=run.workspace_id,
        blueprint_id=run.blueprint_id,
        skill_id=f"contract.workflow.{step_name}",
        created_by_user_id=run.created_by_user_id,
        input_data=input_data,
        output_data=output_data,
        metadata={"runner": WORKFLOW_VERSION},
        status=status,
        error=error,
    )


def _persist_compat_output(db: Session, run: ContractReviewRun, intake: dict, risks, summaries, source_bundle: list[dict]) -> None:
    lawyer_summary = next((item.summary_text for item in summaries if item.audience == "lawyer"), "")
    client_summary = next((item.summary_text for item in summaries if item.audience == "client"), "")
    risk_matrix = [
        {
            "issue": risk.clause_type.replace("_", " ").title(),
            "severity": risk.risk_level,
            "finding": risk.reasoning,
            "requires_review": risk.requires_review,
        }
        for risk in risks
    ]
    db.add(
        ContractReviewOutput(
            id=str(uuid.uuid4()),
            workspace_id=run.workspace_id,
            blueprint_id=run.blueprint_id,
            run_id=run.id,
            extraction_json=json.dumps(intake, sort_keys=True),
            risk_matrix_json=json.dumps(risk_matrix, sort_keys=True),
            negotiation_memo=lawyer_summary,
            client_summary=client_summary,
            sources_json=json.dumps(_sources(source_bundle), sort_keys=True),
            metadata_json=json.dumps({"runner": WORKFLOW_VERSION}, sort_keys=True),
        )
    )


def _sources(source_bundle: list[dict]) -> list[dict]:
    return [
        {
            "filename": item.get("filename"),
            "doc_id": item.get("document_id"),
            "chunk": (item.get("chunk_index") or 0) + 1,
            "excerpt": item.get("content", "")[:500],
        }
        for item in source_bundle[:10]
    ]


def _coverage_score(clauses: list[ContractClause], playbook_clauses: list[ContractPlaybookClause]) -> float | None:
    required = [item for item in playbook_clauses if item.required]
    if not required:
        return None
    extracted_types = {item.clause_type for item in clauses}
    covered = sum(1 for item in required if item.clause_type in extracted_types)
    return round(covered / len(required), 4)


def _avg(values: list[float]) -> float | None:
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 4) if values else None
