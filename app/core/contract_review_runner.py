import json
import re
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.json_utils import json_loads
from app.core.jobs import JobCancelled, add_job_event, ensure_job_not_cancelled, update_job_status
from app.core.llm import complete_with_configured_llm, get_legacy_settings_with_secrets
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
            ensure_job_not_cancelled(db, job)
            config = json_loads(run.config_snapshot_json, {})
            run.status = "running"
            run.started_at = utcnow()
            update_job_status(db, job=job, status="running", progress=10, message="Contract review started")
            db.commit()
            ensure_job_not_cancelled(db, job)

            chunks = _linked_chunks(db, run)
            if not chunks:
                raise RuntimeError("No indexed documents are linked to this Contract Review blueprint")
            add_job_event(db, job=job, event_type="progress", message="Loaded linked contract evidence", metadata={"chunks": len(chunks)})
            job.progress = 35
            job.heartbeat_at = utcnow()
            db.commit()
            ensure_job_not_cancelled(db, job)

            full_text = "\n\n".join(chunk.content for chunk, _document in chunks)
            add_job_event(db, job=job, event_type="progress", message="Classifying document and extracting contract fields", metadata={"text_chars": len(full_text), "progress": 45})
            job.progress = 45
            job.heartbeat_at = utcnow()
            db.commit()
            ensure_job_not_cancelled(db, job)
            extraction = _extract_fields(full_text, config)
            settings = get_legacy_settings_with_secrets()
            ai_review = _ai_contract_review(full_text, extraction, _risk_matrix(full_text), sources=_sources(chunks), config=config, settings=settings)
            runner_name = "ai_contract_review" if ai_review else "deterministic_contract_review"
            if ai_review:
                extraction = ai_review.get("extraction", extraction)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.extract_fields",
                created_by_user_id=run.created_by_user_id,
                input_data={"fields": config.get("fields"), "text_chars": len(full_text)},
                output_data=extraction,
                sources=_sources(chunks),
                metadata={"runner": runner_name},
            )
            add_job_event(db, job=job, event_type="progress", message="Building risk analysis", metadata={"progress": 60})
            job.progress = 60
            job.heartbeat_at = utcnow()
            db.commit()
            ensure_job_not_cancelled(db, job)
            risk_matrix = ai_review.get("risk_matrix", _risk_matrix(full_text)) if ai_review else _risk_matrix(full_text)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.risk_matrix",
                created_by_user_id=run.created_by_user_id,
                input_data={"risk_terms": list(RISK_TERMS.keys())},
                output_data=risk_matrix,
                sources=_sources(chunks),
                metadata={"runner": runner_name},
            )
            sources = _sources(chunks)
            negotiation_memo = ai_review.get("negotiation_memo") if ai_review else None
            negotiation_memo = negotiation_memo or _negotiation_memo(extraction, risk_matrix)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.negotiation_memo",
                created_by_user_id=run.created_by_user_id,
                input_data={"extraction_keys": list(extraction.keys()), "risk_count": len(risk_matrix)},
                output_data={"negotiation_memo": negotiation_memo},
                sources=sources,
                metadata={"runner": runner_name},
            )
            client_summary = ai_review.get("client_summary") if ai_review else None
            client_summary = client_summary or _client_summary(extraction, risk_matrix)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="contract.client_summary",
                created_by_user_id=run.created_by_user_id,
                input_data={"extraction_keys": list(extraction.keys()), "risk_count": len(risk_matrix)},
                output_data={"client_summary": client_summary},
                sources=sources,
                metadata={"runner": runner_name},
            )
            add_job_event(db, job=job, event_type="progress", message="Saving contract review output", metadata={"progress": 90})
            job.progress = 90
            job.heartbeat_at = utcnow()
            db.commit()

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
                metadata_json=json.dumps(
                    {
                        "runner": runner_name,
                        "review_depth": config.get("review_depth", "standard"),
                    },
                    sort_keys=True,
                ),
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
        except JobCancelled:
            run.status = "cancelled"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="cancelled", progress=job.progress, message="Contract review cancelled")
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
            "chunk": chunk.chunk_index + 1,
            "excerpt": chunk.content[:500],
        }
        for chunk, document in chunks[:10]
    ]


def _ai_contract_review(text: str, extraction: dict, risk_matrix: list[dict], *, sources: list[dict], config: dict, settings: dict) -> dict | None:
    system = (
        "You are a careful contract review assistant. Return only valid JSON with keys "
        "extraction, risk_matrix, negotiation_memo, client_summary. Do not provide legal advice or recommend signing."
    )
    source_text = "\n\n".join(f"[{source['filename']} chunk {source['chunk']}]\n{source['excerpt']}" for source in sources[:8])
    user = (
        "Review this indexed contract evidence. Use the provided deterministic draft as a starting point, "
        "but improve it where the evidence supports a better analysis.\n\n"
        f"Config: {json.dumps(config, sort_keys=True)}\n\n"
        f"Deterministic extraction: {json.dumps(extraction, sort_keys=True)}\n\n"
        f"Deterministic risk matrix: {json.dumps(risk_matrix, sort_keys=True)}\n\n"
        f"Evidence excerpts:\n{source_text}\n\n"
        f"Full indexed text, truncated:\n{text[:12000]}"
    )
    try:
        content = complete_with_configured_llm(
            settings,
            system,
            user,
            model=config.get("model"),
            temperature=float(config.get("temperature", 0.2)),
            max_tokens=int(config.get("max_tokens", 3000)),
        )
    except Exception:
        return None
    data = json_loads(_extract_json_object(content), {}) if content else {}
    if not isinstance(data.get("extraction"), dict) or not isinstance(data.get("risk_matrix"), list):
        return None
    return data


def _extract_json_object(value: str | None) -> str | None:
    if not value:
        return None
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return value
    return value[start:end + 1]
