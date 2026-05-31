import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.mediation_agents.orchestrator import run_agentic_mediation_prep
from app.core.mediation_agents.tools import SUPPORTED_TOOLS
from app.core.audit import record_audit_event
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.jobs import add_job_event, create_job, format_job, update_job_status
from app.core.json_utils import json_loads
from app.core.llm import configured_llm_provider, get_runtime_settings_with_secrets
from app.core.models import (
    MediationAgentStepOutput,
    MediationArgument,
    MediationChronologyEvent,
    MediationClaim,
    MediationDamagesItem,
    MediationDepositionTopic,
    MediationDiscoveryItem,
    MediationEvidenceItem,
    MediationIssue,
    MediationMotion,
    MediationPrepOutput,
    MediationPrepRun,
    MediationProceduralTask,
    MediationReviewDecision,
    MediationRiskItem,
    MediationWitness,
    BlueprintInstance,
    BlueprintMember,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    Matter,
    Plugin,
    User,
    utcnow,
)
from app.core.pagination import page_query_response
from app.core.task_control import run_background_job


router = APIRouter(prefix="/workspaces/{workspace_id}/mediation-prep", tags=["mediation-prep"])


class MediationPrepRunIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    matter_id: str
    document_ids: list[str] = Field(default_factory=list, max_length=40)
    party_role: str = Field(default="neutral analysis", max_length=80)
    court: str | None = Field(default=None, max_length=150)
    jurisdiction: str | None = Field(default=None, max_length=150)
    venue: str | None = Field(default=None, max_length=150)
    procedural_stage: str | None = Field(default=None, max_length=150)
    hearing_dates: list[str] = Field(default_factory=list, max_length=20)
    mediation_focus: str | None = Field(default=None, max_length=100)
    instructions: str | None = Field(default=None, max_length=12000)


class MediationDecisionIn(BaseModel):
    target_type: str = Field(max_length=100)
    target_id: str | None = Field(default=None, max_length=36)
    decision: str = Field(max_length=64)
    note: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> Matter:
    if not matter_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matter is required")
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return matter


def _source_chunks(db: Session, workspace_id: str, body: MediationPrepRunIn) -> list[tuple[KnowledgeChunk, KnowledgeDocument]]:
    document_ids = list(dict.fromkeys(str(item) for item in body.document_ids if str(item).strip()))[:40]
    if not document_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one indexed source document is required")
    docs = db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace_id, KnowledgeDocument.id.in_(document_ids))
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
    chunks = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.workspace_id == workspace_id, KnowledgeChunk.document_id.in_(document_ids))
        .order_by(KnowledgeDocument.original_name, KnowledgeChunk.chunk_index)
        .limit(180)
    ).all()
    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No indexed source chunks are available for mediation preparation")
    return chunks


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


def _sources(chunks: list[tuple[KnowledgeChunk, KnowledgeDocument]]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document.id,
            "chunk_id": chunk.id,
            "filename": document.original_name,
            "chunk": chunk.chunk_index + 1,
            "excerpt": chunk.content[:650],
        }
        for chunk, document in chunks[:24]
    ]


def _mediation_blueprint(db: Session, workspace_id: str, matter: Matter, user: User) -> BlueprintInstance:
    plugin = db.get(Plugin, "mediation_prep")
    if not plugin:
        plugin = Plugin(
            id="mediation_prep",
            name="Mediation Prep",
            description="Agentic mediation preparation from indexed matter documents.",
            version="1.0.0",
            is_enabled=True,
            manifest_json=json.dumps({"type": "core", "route": "/mediation-prep"}, sort_keys=True),
        )
        db.add(plugin)
        db.flush()
    name = "Standalone Mediation Prep"
    blueprint = db.execute(
        select(BlueprintInstance).where(
            BlueprintInstance.workspace_id == workspace_id,
            BlueprintInstance.matter_id == matter.id,
            BlueprintInstance.plugin_id == "mediation_prep",
            BlueprintInstance.name == name,
            BlueprintInstance.status == "active",
        )
    ).scalar_one_or_none()
    if blueprint:
        member = db.execute(select(BlueprintMember).where(BlueprintMember.blueprint_id == blueprint.id, BlueprintMember.user_id == user.id)).scalar_one_or_none()
        if not member:
            db.add(BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint.id, user_id=user.id, role="owner"))
            db.flush()
        return blueprint
    blueprint = BlueprintInstance(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=matter.id,
        plugin_id="mediation_prep",
        name=name,
        description="Hidden system blueprint used to persist standalone mediation prep agent runs.",
        status="active",
        created_by_user_id=user.id,
    )
    db.add(blueprint)
    db.add(BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint.id, user_id=user.id, role="owner"))
    db.flush()
    return blueprint


def _format_run_row(run: MediationPrepRun) -> dict[str, Any]:
    config = json_loads(run.config_snapshot_json, {})
    return {
        "id": run.id,
        "title": run.title,
        "status": run.status,
        "status_detail": run.status_detail,
        "matter_id": run.matter_id,
        "party_role": config.get("party_role"),
        "court": config.get("court"),
        "jurisdiction": config.get("jurisdiction"),
        "procedural_stage": config.get("procedural_stage"),
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error": run.error,
    }


def _format_output(run: MediationPrepRun, output: MediationPrepOutput) -> dict[str, Any]:
    return {
        "id": run.id,
        "title": run.title,
        "status": run.status,
        "matter_id": run.matter_id,
        "config": json_loads(run.config_snapshot_json, {}),
        "case_snapshot": json_loads(output.case_snapshot_json, {}),
        "claims_and_defenses": json_loads(output.claims_and_defenses_json, []),
        "issues": json_loads(output.issues_json, []),
        "chronology": json_loads(output.chronology_json, []),
        "evidence_matrix": json_loads(output.evidence_matrix_json, []),
        "discovery_analysis": json_loads(output.discovery_analysis_json, []),
        "witness_prep": json_loads(output.witness_prep_json, []),
        "deposition_prep": json_loads(output.deposition_prep_json, []),
        "motion_strategy": json_loads(output.motion_strategy_json, {}),
        "trial_prep": json_loads(output.trial_prep_json, {}),
        "argument_strategy": json_loads(output.argument_strategy_json, {}),
        "cross_examination": json_loads(output.cross_examination_json, []),
        "procedural_tasks": json_loads(output.procedural_tasks_json, []),
        "damages_and_remedies": json_loads(output.damages_and_remedies_json, {}),
        "risks_and_gaps": json_loads(output.risks_and_gaps_json, []),
        "client_or_team_summary": output.client_or_team_summary,
        "warnings": json_loads(output.warnings_json, []),
        "agentic_review": json_loads(output.agentic_review_json, {}),
        "sources": json_loads(output.sources_json, []),
        "metadata": json_loads(output.metadata_json, {}),
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _get_run_output(db: Session, workspace_id: str, run_id: str) -> tuple[MediationPrepRun, MediationPrepOutput]:
    run = db.execute(select(MediationPrepRun).where(MediationPrepRun.workspace_id == workspace_id, MediationPrepRun.id == run_id)).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mediation prep run not found")
    output = db.execute(select(MediationPrepOutput).where(MediationPrepOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mediation prep output not found")
    return run, output


def _execute_mediation_prep(
    db: Session,
    *,
    workspace_id: str,
    body: MediationPrepRunIn,
    user: User,
    run_id: str | None = None,
    job: Job | None = None,
) -> dict[str, Any]:
    matter = _validate_matter(db, workspace_id, body.matter_id)
    chunks = _source_chunks(db, workspace_id, body)
    run_id = run_id or str(uuid.uuid4())
    blueprint = _mediation_blueprint(db, workspace_id, matter, user)
    if job:
        update_job_status(db, job=job, status="running", progress=10, message="Mediation prep started")
        add_job_event(db, job=job, event_type="progress", message="Preparing source bundle", metadata={"progress": 20, "run_id": run_id})
        db.commit()
    source_bundle = _source_bundle(chunks)
    sources = _sources(chunks)
    config = {
        "matter_id": matter.id,
        "document_ids": body.document_ids,
        "party_role": body.party_role,
        "court": body.court,
        "jurisdiction": body.jurisdiction,
        "venue": body.venue,
        "procedural_stage": body.procedural_stage,
        "hearing_dates": body.hearing_dates,
        "mediation_focus": body.mediation_focus,
        "instructions": body.instructions or "",
        "supported_tools": sorted(SUPPORTED_TOOLS),
    }
    if job:
        add_job_event(db, job=job, event_type="progress", message="Running mediation agents", metadata={"progress": 45, "run_id": run_id})
        job.progress = max(job.progress, 45)
        db.commit()
    settings = get_runtime_settings_with_secrets()
    agentic = run_agentic_mediation_prep(sources=sources, source_bundle=source_bundle, run_context=config, settings=settings)
    provider = configured_llm_provider(settings)
    model = settings.get("chat_model") if provider else None
    if job:
        add_job_event(db, job=job, event_type="progress", message="Persisting mediation prep outputs", metadata={"progress": 82, "run_id": run_id})
        job.progress = max(job.progress, 82)
        db.commit()
    _persist_mediation_state(db, workspace_id=workspace_id, matter_id=matter.id, blueprint_id=blueprint.id, run_id=run_id, user=user, title=body.title or "Mediation Prep", config=config, result=agentic, sources=sources, provider=provider, model=model)
    payload = _format_output(*_get_run_output(db, workspace_id, run_id))
    record_audit_event(
        db,
        action="mediation_prep.run",
        resource_type="mediation_prep",
        resource_id=run_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"document_count": len({doc.id for _chunk, doc in chunks}), "matter_id": matter.id},
    )
    return payload


def _persist_mediation_state(db: Session, *, workspace_id: str, matter_id: str, blueprint_id: str, run_id: str, user: User, title: str, config: dict[str, Any], result: dict[str, Any], sources: list[dict[str, Any]], provider: str | None, model: str | None) -> None:
    now = utcnow()
    run = MediationPrepRun(
        id=run_id,
        workspace_id=workspace_id,
        matter_id=matter_id,
        blueprint_id=blueprint_id,
        title=title,
        status="completed",
        status_detail="Agentic mediation preparation completed.",
        config_snapshot_json=json.dumps(config, sort_keys=True),
        workflow_version="mediation_prep_workflow_v1",
        source_anchor_version="knowledge_chunk_v1",
        created_by_user_id=user.id,
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()
    db.add(
        MediationPrepOutput(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            matter_id=matter_id,
            run_id=run_id,
            case_snapshot_json=json.dumps(result.get("case_snapshot", {}), sort_keys=True),
            claims_and_defenses_json=json.dumps(result.get("claims_and_defenses", []), sort_keys=True),
            issues_json=json.dumps(result.get("issues", []), sort_keys=True),
            chronology_json=json.dumps(result.get("chronology", []), sort_keys=True),
            evidence_matrix_json=json.dumps(result.get("evidence_matrix", []), sort_keys=True),
            discovery_analysis_json=json.dumps(result.get("discovery_analysis", []), sort_keys=True),
            witness_prep_json=json.dumps(result.get("witness_prep", []), sort_keys=True),
            deposition_prep_json=json.dumps(result.get("deposition_prep", []), sort_keys=True),
            motion_strategy_json=json.dumps(result.get("motion_strategy", {}), sort_keys=True),
            trial_prep_json=json.dumps(result.get("trial_prep", {}), sort_keys=True),
            argument_strategy_json=json.dumps(result.get("argument_strategy", {}), sort_keys=True),
            cross_examination_json=json.dumps(result.get("cross_examination", []), sort_keys=True),
            procedural_tasks_json=json.dumps(result.get("procedural_tasks", []), sort_keys=True),
            damages_and_remedies_json=json.dumps(result.get("damages_and_remedies", {}), sort_keys=True),
            risks_and_gaps_json=json.dumps(result.get("risks_and_gaps", []), sort_keys=True),
            client_or_team_summary=result.get("client_or_team_summary") or "",
            warnings_json=json.dumps(result.get("warnings", []), sort_keys=True),
            agentic_review_json=json.dumps(result.get("agentic_review", {}), sort_keys=True),
            sources_json=json.dumps(sources, sort_keys=True),
            metadata_json=json.dumps({"provider": provider, "model": model}, sort_keys=True),
        )
    )
    _persist_claims(db, workspace_id, matter_id, run_id, result.get("claims_and_defenses", []))
    issue_ids = _persist_issues(db, workspace_id, matter_id, run_id, result.get("issues", []))
    db.flush()
    _persist_chronology(db, workspace_id, matter_id, run_id, result.get("chronology", []))
    _persist_evidence(db, workspace_id, matter_id, run_id, result.get("evidence_matrix", []), issue_ids)
    _persist_witnesses(db, workspace_id, matter_id, run_id, result.get("witness_prep", []))
    _persist_depositions(db, workspace_id, matter_id, run_id, result.get("deposition_prep", []))
    _persist_arguments(db, workspace_id, matter_id, run_id, result.get("argument_strategy", {}))
    _persist_motions(db, workspace_id, matter_id, run_id, result.get("motion_strategy", {}))
    _persist_discovery(db, workspace_id, matter_id, run_id, result.get("discovery_analysis", []))
    _persist_damages_items(db, workspace_id, matter_id, run_id, result.get("damages_and_remedies", {}))
    _persist_procedural_tasks(db, workspace_id, matter_id, run_id, result.get("procedural_tasks", []))
    _persist_risks(db, workspace_id, matter_id, run_id, result.get("risks_and_gaps", []))
    _persist_step_outputs(db, workspace_id, matter_id, run_id, config, result, provider, model)


def _anchor(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else {}
    if not isinstance(value, dict):
        return {}
    source = value.get("source") if isinstance(value.get("source"), dict) else value
    return source if isinstance(source, dict) else {}


def _persist_issues(db: Session, workspace_id: str, matter_id: str, run_id: str, issues: list[dict[str, Any]]) -> dict[str, str]:
    issue_ids = {}
    for item in issues[:100]:
        anchor = _anchor(item)
        issue_id = str(uuid.uuid4())
        title = str(item.get("title") or item.get("issue") or "Issue")[:255]
        issue_ids[title.lower()] = issue_id
        db.add(MediationIssue(id=issue_id, workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), title=title, category=item.get("category"), summary=item.get("summary") or "", proof_elements_json=json.dumps(item.get("proof_elements") or [], sort_keys=True), burdens_json=json.dumps(item.get("burdens") or [], sort_keys=True), disputed_facts_json=json.dumps(item.get("disputed_facts") or [], sort_keys=True), admissions_json=json.dumps(item.get("admissions") or [], sort_keys=True), missing_proof_json=json.dumps(item.get("missing_proof") or [], sort_keys=True), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor}, sort_keys=True)))
    return issue_ids


def _persist_claims(db: Session, workspace_id: str, matter_id: str, run_id: str, claims: list[dict[str, Any]]) -> None:
    for item in claims[:100]:
        anchor = _anchor(item)
        db.add(MediationClaim(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), claim_type=item.get("claim_type") or item.get("type") or "claim", title=str(item.get("title") or item.get("claim") or item.get("defense") or "Claim or defense")[:255], elements_json=json.dumps(item.get("elements") or item.get("proof_elements") or [], sort_keys=True), defenses_json=json.dumps(item.get("defenses") or item.get("affirmative_defenses") or [], sort_keys=True), admissions_json=json.dumps(item.get("admissions") or [], sort_keys=True), missing_proof_json=json.dumps(item.get("missing_proof") or item.get("gaps") or [], sort_keys=True), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "item": item}, sort_keys=True)))


def _persist_chronology(db: Session, workspace_id: str, matter_id: str, run_id: str, events: list[dict[str, Any]]) -> None:
    for item in events[:200]:
        anchor = _anchor(item)
        db.add(MediationChronologyEvent(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), event_date=item.get("date") or item.get("event_date"), description=item.get("description") or "", relevance=item.get("dispute_relevance") or item.get("relevance"), anchor_text=anchor.get("excerpt"), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor}, sort_keys=True)))


def _persist_evidence(db: Session, workspace_id: str, matter_id: str, run_id: str, matrix: list[dict[str, Any]], issue_ids: dict[str, str]) -> None:
    for item in matrix[:120]:
        issue = str(item.get("issue") or item.get("title") or "Issue")
        issue_id = issue_ids.get(issue.lower())
        for kind, key in [("supporting", "supporting_evidence"), ("adverse", "adverse_evidence")]:
            evidence_list = item.get(key) if isinstance(item.get(key), list) else []
            for evidence in evidence_list[:20]:
                anchor = _anchor(evidence)
                db.add(MediationEvidenceItem(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, issue_id=issue_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), evidence_type=kind, summary=evidence.get("summary") if isinstance(evidence, dict) else "", anchor_text=anchor.get("excerpt"), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=evidence.get("confidence_score") if isinstance(evidence, dict) else None, review_status="pending", metadata_json=json.dumps({"issue": issue, "evidence": evidence}, sort_keys=True)))
        for gap in item.get("gaps") or []:
            db.add(MediationEvidenceItem(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, issue_id=issue_id, evidence_type="gap", summary=str(gap), review_status="pending", metadata_json=json.dumps({"issue": issue}, sort_keys=True)))


def _persist_witnesses(db: Session, workspace_id: str, matter_id: str, run_id: str, witnesses: list[dict[str, Any]]) -> None:
    for item in witnesses[:80]:
        anchor = _anchor(item.get("exhibit_references") or item)
        db.add(MediationWitness(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), name=str(item.get("name") or "Witness")[:255], role=item.get("role"), topics_json=json.dumps(item.get("topics") or [], sort_keys=True), admissions_json=json.dumps(item.get("admissions") or [], sort_keys=True), contradictions_json=json.dumps(item.get("contradictions") or [], sort_keys=True), prep_questions_json=json.dumps(item.get("prep_questions") or [], sort_keys=True), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "exhibit_references": item.get("exhibit_references") or []}, sort_keys=True)))


def _persist_depositions(db: Session, workspace_id: str, matter_id: str, run_id: str, depositions: list[dict[str, Any]]) -> None:
    for item in depositions[:80]:
        anchor = _anchor(item.get("anchors") or item)
        db.add(MediationDepositionTopic(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), witness_name=str(item.get("witness") or item.get("name") or "Witness")[:255], topics_json=json.dumps(item.get("topics") or [], sort_keys=True), questions_json=json.dumps(item.get("questions") or [], sort_keys=True), anchors_json=json.dumps(item.get("anchors") or [], sort_keys=True), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "item": item}, sort_keys=True)))


def _persist_arguments(db: Session, workspace_id: str, matter_id: str, run_id: str, strategy: dict[str, Any]) -> None:
    themes = strategy.get("themes") if isinstance(strategy.get("themes"), list) else []
    for item in themes[:50]:
        db.add(MediationArgument(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, theme=str(item.get("theme") or "Argument theme")[:255], strongest_points_json=json.dumps(item.get("strongest_points") or item.get("points") or [], sort_keys=True), vulnerabilities_json=json.dumps(item.get("vulnerabilities") or [], sort_keys=True), opponent_responses_json=json.dumps(item.get("opponent_responses") or [], sort_keys=True), review_status="pending", metadata_json=json.dumps(item, sort_keys=True)))


def _persist_procedural_tasks(db: Session, workspace_id: str, matter_id: str, run_id: str, tasks: list[dict[str, Any]]) -> None:
    for item in tasks[:100]:
        anchor = _anchor(item)
        db.add(MediationProceduralTask(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), task_type=item.get("task_type") or "obligation", description=item.get("description") or "", due_date=item.get("due_date"), compliance_risk=item.get("compliance_risk"), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor}, sort_keys=True)))


def _persist_motions(db: Session, workspace_id: str, matter_id: str, run_id: str, strategy: dict[str, Any]) -> None:
    motions = strategy.get("motions") if isinstance(strategy.get("motions"), list) else strategy.get("themes") if isinstance(strategy.get("themes"), list) else []
    for item in motions[:60]:
        anchor = _anchor(item)
        db.add(MediationMotion(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), motion_type=item.get("motion_type") or "motion", title=str(item.get("title") or item.get("theme") or "Motion issue")[:255], support_json=json.dumps(item.get("support") or item.get("points") or [], sort_keys=True), vulnerabilities_json=json.dumps(item.get("vulnerabilities") or [], sort_keys=True), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "item": item}, sort_keys=True)))


def _persist_discovery(db: Session, workspace_id: str, matter_id: str, run_id: str, discovery: list[dict[str, Any]]) -> None:
    for item in discovery[:100]:
        anchor = _anchor(item)
        db.add(MediationDiscoveryItem(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), item_type=item.get("item_type") or item.get("type") or "discovery", description=item.get("description") or item.get("summary") or "", status=item.get("status"), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "item": item}, sort_keys=True)))


def _persist_damages_items(db: Session, workspace_id: str, matter_id: str, run_id: str, damages: dict[str, Any]) -> None:
    findings = damages.get("claimed_relief") if isinstance(damages.get("claimed_relief"), list) else []
    for item in findings[:100]:
        anchor = _anchor(item)
        amounts = item.get("amounts") if isinstance(item, dict) else []
        amount = ", ".join(str(value) for value in amounts[:3]) if isinstance(amounts, list) else None
        db.add(MediationDamagesItem(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), item_type="claimed_relief", amount=amount, summary=item.get("excerpt") or item.get("summary") or "", page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "item": item}, sort_keys=True)))


def _persist_risks(db: Session, workspace_id: str, matter_id: str, run_id: str, risks: list[dict[str, Any]]) -> None:
    for item in risks[:100]:
        anchor = _anchor(item)
        db.add(MediationRiskItem(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, source_document_id=anchor.get("document_id"), chunk_id=anchor.get("chunk_id"), risk_level=item.get("risk_level") or "medium", summary=item.get("summary") or "", leverage=item.get("leverage"), decision_point=item.get("decision_point"), page=anchor.get("page"), start_offset=anchor.get("start_offset"), end_offset=anchor.get("end_offset"), confidence_score=item.get("confidence_score"), review_status="pending", metadata_json=json.dumps({"source": anchor, "requires_review": item.get("requires_review", True)}, sort_keys=True)))


def _persist_step_outputs(db: Session, workspace_id: str, matter_id: str, run_id: str, config: dict[str, Any], result: dict[str, Any], provider: str | None, model: str | None) -> None:
    outputs = result.get("agent_outputs", {}) if isinstance(result.get("agent_outputs"), dict) else {}
    for step in result.get("agent_trace", []):
        step_name = step.get("step_name") or "agent_step"
        db.add(MediationAgentStepOutput(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=matter_id, run_id=run_id, step_name=step_name, step_version="agentic_mediation_prep_v1", status=step.get("status") or "completed", input_json=json.dumps(config, sort_keys=True), output_json=json.dumps(outputs.get(step_name, {}), sort_keys=True), provider=step.get("provider") or provider, model=step.get("model") or model, error=step.get("error"), metadata_json=json.dumps({"duration_ms": step.get("duration_ms")}, sort_keys=True), started_at=utcnow(), completed_at=utcnow()))


def _run_mediation_prep_job(job_id: str, workspace_id: str, user_id: str, body_data: dict[str, Any], run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        user = db.get(User, user_id)
        if not job or not user:
            return
        try:
            body = MediationPrepRunIn(**body_data)
            payload = _execute_mediation_prep(db, workspace_id=workspace_id, body=body, user=user, run_id=run_id, job=job)
            metadata = json_loads(job.metadata_json, {})
            metadata.update({"run_id": run_id, "result_url": f"/api/v2/workspaces/{workspace_id}/mediation-prep/runs/{run_id}"})
            job.metadata_json = json.dumps(metadata, sort_keys=True)
            update_job_status(db, job=job, status="completed", progress=100, message="Mediation prep completed")
            add_job_event(db, job=job, event_type="result", message="Mediation prep result ready", metadata={"run_id": run_id, "title": payload["title"]})
            db.commit()
        except Exception as exc:
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Mediation prep failed", error=str(exc))
            db.commit()


@router.get("/runs")
async def list_runs(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    rows = select(MediationPrepRun).where(MediationPrepRun.workspace_id == workspace_id).order_by(MediationPrepRun.created_at.desc())
    return page_query_response(db, rows, _format_run_row, page=page, page_size=page_size, scalars=True)


@router.post("/runs")
async def create_run(workspace_id: str, body: MediationPrepRunIn, background_tasks: BackgroundTasks, sync: bool = Query(default=False), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    if sync:
        payload = _execute_mediation_prep(db, workspace_id=workspace_id, body=body, user=user)
        db.commit()
        return payload
    _validate_matter(db, workspace_id, body.matter_id)
    _source_chunks(db, workspace_id, body)
    run_id = str(uuid.uuid4())
    job = create_job(db, workspace_id=workspace_id, created_by_user_id=user.id, job_type="mediation_prep.run", metadata={"run_id": run_id, "title": body.title or "Mediation Prep"}, message="Mediation prep queued")
    record_audit_event(db, action="mediation_prep.queue", resource_type="mediation_prep", resource_id=run_id, user_id=user.id, workspace_id=workspace_id, metadata={"job_id": job.id, "document_count": len(set(body.document_ids)), "matter_id": body.matter_id})
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, _run_mediation_prep_job, job.id, workspace_id, user.id, body.model_dump(), run_id)
    return {"status": "queued", "run_id": run_id, "job": format_job(job)}


@router.get("/runs/{run_id}")
async def get_run(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    return _format_output(*_get_run_output(db, workspace_id, run_id))


@router.get("/runs/{run_id}/claims")
async def get_claims(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_claim_payload(item) for item in db.execute(select(MediationClaim).where(MediationClaim.run_id == run_id).order_by(MediationClaim.created_at)).scalars().all()]


@router.get("/runs/{run_id}/issues")
async def get_issues(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_issue_payload(item) for item in db.execute(select(MediationIssue).where(MediationIssue.run_id == run_id).order_by(MediationIssue.created_at)).scalars().all()]


@router.get("/runs/{run_id}/chronology")
async def get_chronology(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_row_payload(item, ["event_date", "description", "relevance", "anchor_text"]) for item in db.execute(select(MediationChronologyEvent).where(MediationChronologyEvent.run_id == run_id).order_by(MediationChronologyEvent.event_date, MediationChronologyEvent.created_at)).scalars().all()]


@router.get("/runs/{run_id}/evidence")
async def get_evidence(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_row_payload(item, ["issue_id", "evidence_type", "summary", "anchor_text"]) for item in db.execute(select(MediationEvidenceItem).where(MediationEvidenceItem.run_id == run_id).order_by(MediationEvidenceItem.created_at)).scalars().all()]


@router.get("/runs/{run_id}/witnesses")
async def get_witnesses(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_witness_payload(item) for item in db.execute(select(MediationWitness).where(MediationWitness.run_id == run_id).order_by(MediationWitness.name)).scalars().all()]


@router.get("/runs/{run_id}/depositions")
async def get_depositions(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_deposition_payload(item) for item in db.execute(select(MediationDepositionTopic).where(MediationDepositionTopic.run_id == run_id).order_by(MediationDepositionTopic.created_at)).scalars().all()]


@router.get("/runs/{run_id}/discovery")
async def get_discovery(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_row_payload(item, ["item_type", "description", "status"]) for item in db.execute(select(MediationDiscoveryItem).where(MediationDiscoveryItem.run_id == run_id).order_by(MediationDiscoveryItem.created_at)).scalars().all()]


@router.get("/runs/{run_id}/motions")
async def get_motions(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_motion_payload(item) for item in db.execute(select(MediationMotion).where(MediationMotion.run_id == run_id).order_by(MediationMotion.created_at)).scalars().all()]


@router.get("/runs/{run_id}/procedural-tasks")
async def get_procedural_tasks(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    _get_run_output(db, workspace_id, run_id)
    return [_row_payload(item, ["task_type", "description", "due_date", "compliance_risk"]) for item in db.execute(select(MediationProceduralTask).where(MediationProceduralTask.run_id == run_id).order_by(MediationProceduralTask.due_date, MediationProceduralTask.created_at)).scalars().all()]


@router.get("/runs/{run_id}/audit-package")
async def get_audit_package(workspace_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    run, output = _get_run_output(db, workspace_id, run_id)
    steps = db.execute(select(MediationAgentStepOutput).where(MediationAgentStepOutput.run_id == run_id).order_by(MediationAgentStepOutput.created_at)).scalars().all()
    decisions = db.execute(select(MediationReviewDecision).where(MediationReviewDecision.run_id == run_id).order_by(MediationReviewDecision.created_at)).scalars().all()
    return {"run": _format_run_row(run), "source_evidence": json_loads(output.sources_json, []), "agent_trace": [_row_payload(step, ["step_name", "status", "provider", "model", "error"]) for step in steps], "tool_outputs": json_loads(output.agentic_review_json, {}).get("tool_results", {}), "final_outputs": _format_output(run, output), "human_review_decisions": [_decision_payload(item) for item in decisions]}


@router.post("/runs/{run_id}/decisions")
async def create_decision(workspace_id: str, run_id: str, body: MediationDecisionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    run, _output = _get_run_output(db, workspace_id, run_id)
    decision = MediationReviewDecision(id=str(uuid.uuid4()), workspace_id=workspace_id, matter_id=run.matter_id, run_id=run_id, user_id=user.id, target_type=body.target_type, target_id=body.target_id, decision=body.decision, note=body.note, prior_status_json="{}", metadata_json=json.dumps(body.metadata, sort_keys=True))
    db.add(decision)
    record_audit_event(db, action="mediation_prep.decision", resource_type="mediation_prep", resource_id=run_id, user_id=user.id, workspace_id=workspace_id, metadata={"target_type": body.target_type, "target_id": body.target_id, "decision": body.decision})
    db.commit()
    db.refresh(decision)
    return _decision_payload(decision)


@router.get("/templates")
@router.get("/playbooks")
async def list_templates(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    return [
        {"id": "standard-mediation-prep", "name": "Standard Mediation Prep", "description": "Issues, chronology, evidence, witnesses, procedure, damages, risks, and audit package."},
        {"id": "hearing-prep", "name": "Mediation Prep", "description": "Emphasizes witness prep, cross-examination, chronology, and exhibits."},
        {"id": "procedural-compliance", "name": "Procedural Compliance", "description": "Emphasizes orders, deadlines, filings, production, and objections."},
    ]


def _issue_payload(item: MediationIssue) -> dict[str, Any]:
    payload = _row_payload(item, ["title", "category", "summary"])
    payload.update({"proof_elements": json_loads(item.proof_elements_json, []), "burdens": json_loads(item.burdens_json, []), "disputed_facts": json_loads(item.disputed_facts_json, []), "admissions": json_loads(item.admissions_json, []), "missing_proof": json_loads(item.missing_proof_json, [])})
    return payload


def _claim_payload(item: MediationClaim) -> dict[str, Any]:
    payload = _row_payload(item, ["claim_type", "title"])
    payload.update({"elements": json_loads(item.elements_json, []), "defenses": json_loads(item.defenses_json, []), "admissions": json_loads(item.admissions_json, []), "missing_proof": json_loads(item.missing_proof_json, [])})
    return payload


def _witness_payload(item: MediationWitness) -> dict[str, Any]:
    payload = _row_payload(item, ["name", "role"])
    payload.update({"topics": json_loads(item.topics_json, []), "admissions": json_loads(item.admissions_json, []), "contradictions": json_loads(item.contradictions_json, []), "prep_questions": json_loads(item.prep_questions_json, [])})
    return payload


def _deposition_payload(item: MediationDepositionTopic) -> dict[str, Any]:
    payload = _row_payload(item, ["witness_name"])
    payload.update({"topics": json_loads(item.topics_json, []), "questions": json_loads(item.questions_json, []), "anchors": json_loads(item.anchors_json, [])})
    return payload


def _motion_payload(item: MediationMotion) -> dict[str, Any]:
    payload = _row_payload(item, ["motion_type", "title"])
    payload.update({"support": json_loads(item.support_json, []), "vulnerabilities": json_loads(item.vulnerabilities_json, [])})
    return payload


def _decision_payload(item: MediationReviewDecision) -> dict[str, Any]:
    return {"id": item.id, "run_id": item.run_id, "target_type": item.target_type, "target_id": item.target_id, "decision": item.decision, "note": item.note, "metadata": json_loads(item.metadata_json, {}), "created_at": item.created_at.isoformat()}


def _row_payload(item: Any, fields: list[str]) -> dict[str, Any]:
    payload = {"id": item.id, "workspace_id": item.workspace_id, "matter_id": item.matter_id, "run_id": item.run_id, "confidence_score": getattr(item, "confidence_score", None), "review_status": getattr(item, "review_status", None), "metadata": json_loads(getattr(item, "metadata_json", "{}"), {})}
    for field in fields:
        payload[field] = getattr(item, field, None)
    for field in ["source_document_id", "chunk_id", "page", "start_offset", "end_offset", "created_at"]:
        if hasattr(item, field):
            value = getattr(item, field)
            payload[field] = value.isoformat() if field == "created_at" and value else value
    return payload
