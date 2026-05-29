import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contract_agents.clause_extractor import extract_clauses
from app.core.contract_agents.conflict_detector import detect_conflicts
from app.core.contract_agents.escalation_detector import detect_escalations
from app.core.contract_agents.playbook_comparator import compare_to_playbook
from app.core.contract_agents.redliner import suggest_redlines
from app.core.contract_agents.risk_scorer import score_risks
from app.core.contract_agents.summarizer import build_summaries
from app.core.contract_agents.intake import run_intake
from app.core.audit import record_audit_event
from app.core.contract_review_runner import _ai_contract_review, _client_summary, _extract_fields, _negotiation_memo, _risk_matrix
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.json_utils import json_loads
from app.core.llm import configured_llm_provider, get_legacy_settings_with_secrets
from app.core.models import ContractClause, ContractPlaybook, ContractPlaybookClause, KnowledgeChunk, KnowledgeDocument, Matter, User

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


def _validate_matter(db: Session, workspace_id: str, matter_id: str | None) -> None:
    if not matter_id:
        return
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")


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
            if body.matter_id and doc.matter_id not in {None, body.matter_id}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected documents must belong to the selected matter or workspace scope")
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
    return _first_playbook_for_category(db, None, workspace_id)


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


def _coverage_score(clauses: list[ContractClause], playbook_clauses: list[ContractPlaybookClause]) -> float | None:
    required = [item for item in playbook_clauses if item.required]
    if not required:
        return None
    extracted_types = {item.clause_type for item in clauses}
    return round(sum(1 for item in required if item.clause_type in extracted_types) / len(required), 4)


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


@router.post("")
@router.post("/", include_in_schema=False)
async def run_standalone_contract_review(
    workspace_id: str,
    body: StandaloneContractReviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    _validate_matter(db, workspace_id, body.matter_id)
    chunks = _source_chunks(db, workspace_id, body)
    run_id = str(uuid.uuid4())
    workflow, selected_playbook = _workflow_review(db, workspace_id, run_id, chunks, body.playbook_id)
    full_text = "\n\n".join(chunk.content for chunk, _document in chunks)
    config = {
        "review_depth": body.review_depth or "standard",
        "instructions": body.instructions or "",
        "playbook_id": selected_playbook.id if selected_playbook else None,
        "playbook_name": selected_playbook.name if selected_playbook else None,
        "mode": "standalone",
    }
    extraction = _extract_fields(full_text, config)
    risks = _risk_matrix(full_text)
    sources = _sources(chunks)
    settings = get_legacy_settings_with_secrets()
    ai_review = _ai_contract_review(full_text, extraction, risks, sources=sources, config=config, settings=settings)
    if ai_review:
        extraction = ai_review.get("extraction", extraction)
        risks = ai_review.get("risk_matrix", risks)
    negotiation_memo = (ai_review or {}).get("negotiation_memo") or _negotiation_memo(extraction, risks)
    client_summary = (ai_review or {}).get("client_summary") or _client_summary(extraction, risks)
    provider = configured_llm_provider(settings)
    payload = {
        "id": run_id,
        "title": body.title or "Contract Review",
        "mode": "standalone",
        "review_depth": config["review_depth"],
        "playbook": _format_playbook(selected_playbook) if selected_playbook else None,
        "extraction": extraction,
        "risk_matrix": risks,
        "negotiation_memo": negotiation_memo,
        "client_summary": client_summary,
        "sources": sources,
        "workflow": workflow,
        "provider": provider,
        "model": settings.get("chat_model") if provider else None,
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
    db.commit()
    return payload
