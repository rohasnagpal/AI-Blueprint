import json
import re
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.jobs import add_job_event, update_job_status
from app.core.skills import record_skill_run
from app.core.models import (
    ContractReviewOutput,
    ContractReviewRun,
    DocumentLink,
    Escalation,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    utcnow,
)


RISK_TERMS = {
    "termination": "Termination rights",
    "liability": "Liability exposure",
    "indemn": "Indemnity",
    "confidential": "Confidentiality",
    "governing law": "Governing law",
    "jurisdiction": "Jurisdiction",
    "assignment": "Assignment",
    "payment": "Payment obligations",
}


def execute_contract_review(job_id: str, run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run = db.get(ContractReviewRun, run_id)
        if not job or not run:
            return
        try:
            config = _json_loads(run.config_snapshot_json, {})
            run.status = "running"
            run.started_at = utcnow()
            update_job_status(db, job=job, status="running", progress=10, message="Contract review started")
            db.commit()

            chunks = _linked_chunks(db, run)
            if not chunks:
                raise RuntimeError("No indexed documents are linked to this Contract Review blueprint")
            add_job_event(db, job=job, event_type="progress", message="Loaded linked contract evidence", metadata={"chunks": len(chunks)})
            job.progress = 35
            job.heartbeat_at = utcnow()
            db.commit()

            full_text = "\n\n".join(chunk.content for chunk, _document in chunks)
            extraction = _extract_fields(full_text, config)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.extract_fields",
                created_by_user_id=run.created_by_user_id,
                input_data={"fields": config.get("fields"), "text_chars": len(full_text)},
                output_data=extraction,
                sources=_sources(chunks),
                metadata={"runner": "deterministic_contract_review"},
            )
            risk_matrix = _risk_matrix(full_text)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.risk_matrix",
                created_by_user_id=run.created_by_user_id,
                input_data={"risk_terms": list(RISK_TERMS.keys())},
                output_data=risk_matrix,
                sources=_sources(chunks),
                metadata={"runner": "deterministic_contract_review"},
            )
            sources = _sources(chunks)
            negotiation_memo = _negotiation_memo(extraction, risk_matrix)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.negotiation_memo",
                created_by_user_id=run.created_by_user_id,
                input_data={"extraction_keys": list(extraction.keys()), "risk_count": len(risk_matrix)},
                output_data={"negotiation_memo": negotiation_memo},
                sources=sources,
                metadata={"runner": "deterministic_contract_review"},
            )
            client_summary = _client_summary(extraction, risk_matrix)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.client_summary",
                created_by_user_id=run.created_by_user_id,
                input_data={"extraction_keys": list(extraction.keys()), "risk_count": len(risk_matrix)},
                output_data={"client_summary": client_summary},
                sources=sources,
                metadata={"runner": "deterministic_contract_review"},
            )

            output = ContractReviewOutput(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                extraction_json=json.dumps(extraction, sort_keys=True),
                risk_matrix_json=json.dumps(risk_matrix, sort_keys=True),
                negotiation_memo=negotiation_memo,
                client_summary=client_summary,
                sources_json=json.dumps(sources, sort_keys=True),
                metadata_json=json.dumps({"runner": "deterministic_contract_review", "review_depth": config.get("review_depth", "standard")}, sort_keys=True),
            )
            db.add(output)
            for risk in risk_matrix:
                if risk.get("requires_review"):
                    db.add(
                        Escalation(
                            id=str(uuid.uuid4()),
                            workspace_id=run.workspace_id,
                            blueprint_id=run.blueprint_id,
                            source_type="contract_review_run",
                            source_id=run.id,
                            severity=risk["severity"],
                            status="open",
                            reason=f"{risk['issue']}: {risk['finding']}",
                            required_action="Lawyer review required before client delivery.",
                            metadata_json=json.dumps({"issue": risk["issue"]}, sort_keys=True),
                            created_by_user_id=run.created_by_user_id,
                        )
                    )
            run.status = "completed"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="completed", progress=100, message="Contract review completed")
            db.commit()
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Contract review failed", error=str(exc))
            db.commit()


def _linked_chunks(db, run: ContractReviewRun):
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


def _extract_fields(text: str, config: dict) -> dict:
    fields = config.get("fields") or ["parties", "effective_date", "governing_law", "term", "payment"]
    extraction = {}
    for field in fields:
        label = str(field)
        pattern = label.replace("_", r"[\s_-]+")
        match = re.search(rf"{pattern}\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE)
        extraction[label] = {
            "value": match.group(1).strip()[:300] if match else None,
            "supported": bool(match),
        }
    return extraction


def _risk_matrix(text: str) -> list[dict]:
    lower = text.lower()
    risks = []
    for needle, label in RISK_TERMS.items():
        present = needle in lower
        risks.append(
            {
                "issue": label,
                "severity": "medium" if present else "low",
                "finding": "Relevant language found for review." if present else "No obvious language found in indexed text.",
                "requires_review": present,
            }
        )
    return risks


def _negotiation_memo(extraction: dict, risk_matrix: list[dict]) -> str:
    flagged = [risk["issue"] for risk in risk_matrix if risk["requires_review"]]
    missing = [key for key, value in extraction.items() if not value["supported"]]
    return (
        "Negotiation memo\n\n"
        f"Flagged issues: {', '.join(flagged) if flagged else 'None from indexed text'}.\n"
        f"Missing structured fields: {', '.join(missing) if missing else 'None'}.\n"
        "Review flagged clauses against the firm's playbook before client delivery."
    )


def _client_summary(extraction: dict, risk_matrix: list[dict]) -> str:
    review_count = sum(1 for risk in risk_matrix if risk["requires_review"])
    supported = sum(1 for value in extraction.values() if value["supported"])
    return f"Indexed review found {review_count} issue area(s) requiring lawyer review and {supported} structured field(s) with apparent support."


def _sources(chunks) -> list[dict]:
    return [
        {
            "filename": document.original_name,
            "doc_id": document.id,
            "page": chunk.chunk_index + 1,
            "excerpt": chunk.content[:500],
        }
        for chunk, document in chunks[:10]
    ]


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback
