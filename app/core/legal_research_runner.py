import json
import re
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.jobs import add_job_event, update_job_status
from app.core.models import (
    DocumentLink,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    LegalResearchOutput,
    LegalResearchRun,
    utcnow,
)
from app.core.skills import record_skill_run


AUTHORITY_RE = re.compile(r"\b([A-Z][A-Za-z.&' ]+\s+v\.?\s+[A-Z][A-Za-z.&' ]+)\b")
STATUTE_RE = re.compile(r"\b([A-Z][A-Za-z ]+(?:Act|Code|Rules|Regulation)s?(?:,?\s+\d{4})?)\b")


def execute_legal_research(job_id: str, run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run = db.get(LegalResearchRun, run_id)
        if not job or not run:
            return
        try:
            config = _json_loads(run.config_snapshot_json, {})
            run.status = "running"
            run.started_at = utcnow()
            update_job_status(db, job=job, status="running", progress=10, message="Legal research started")
            db.commit()

            chunks = _linked_chunks(db, run)
            if not chunks:
                raise RuntimeError("No indexed documents are linked to this Legal Research blueprint")
            add_job_event(db, job=job, event_type="progress", message="Loaded linked research sources", metadata={"chunks": len(chunks)})
            job.progress = 35
            job.heartbeat_at = utcnow()
            db.commit()

            sources = _sources(chunks)
            full_text = "\n\n".join(chunk.content for chunk, _document in chunks)
            authority_matrix = _authority_matrix(full_text, chunks)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="research.authority_finder",
                created_by_user_id=run.created_by_user_id,
                input_data={"question": run.question, "text_chars": len(full_text)},
                output_data={"authority_matrix": authority_matrix},
                sources=sources,
                metadata={"runner": "deterministic_legal_research"},
            )

            legal_tests = _legal_tests(full_text)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="research.legal_test",
                created_by_user_id=run.created_by_user_id,
                input_data={"question": run.question},
                output_data={"legal_tests": legal_tests},
                sources=sources,
                metadata={"runner": "deterministic_legal_research"},
            )

            citation_pack = _citation_pack(sources)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="research.citation_pack",
                created_by_user_id=run.created_by_user_id,
                input_data={"source_count": len(sources)},
                output_data={"citation_pack": citation_pack},
                sources=sources,
                metadata={"runner": "deterministic_legal_research"},
            )

            memo = _research_memo(run.question, authority_matrix, legal_tests, citation_pack, config)
            limitations = _limitations(authority_matrix, legal_tests)
            record_skill_run(
                db,
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                skill_id="research.memo",
                created_by_user_id=run.created_by_user_id,
                input_data={"question": run.question},
                output_data={"research_memo": memo, "limitations": limitations},
                sources=sources,
                metadata={"runner": "deterministic_legal_research"},
            )

            output = LegalResearchOutput(
                id=str(uuid.uuid4()),
                workspace_id=run.workspace_id,
                blueprint_id=run.blueprint_id,
                run_id=run.id,
                authority_matrix_json=json.dumps(authority_matrix, sort_keys=True),
                legal_tests_json=json.dumps(legal_tests, sort_keys=True),
                citation_pack_json=json.dumps(citation_pack, sort_keys=True),
                research_memo=memo,
                limitations=limitations,
                sources_json=json.dumps(sources, sort_keys=True),
                metadata_json=json.dumps({"runner": "deterministic_legal_research", "jurisdiction": config.get("jurisdiction")}, sort_keys=True),
            )
            db.add(output)
            run.status = "completed"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="completed", progress=100, message="Legal research completed")
            db.commit()
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="failed", progress=job.progress, message="Legal research failed", error=str(exc))
            db.commit()


def _linked_chunks(db, run: LegalResearchRun):
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


def _authority_matrix(text: str, chunks) -> list[dict]:
    candidates = []
    for name in AUTHORITY_RE.findall(text):
        candidates.append({"authority": name.strip(), "type": "case", "treatment": "mentioned", "proposition": "Candidate authority found in linked material."})
    for name in STATUTE_RE.findall(text):
        if name.lower() in {"the act", "this act"}:
            continue
        candidates.append({"authority": name.strip(), "type": "statute_or_rule", "treatment": "mentioned", "proposition": "Candidate legislation or rule found in linked material."})
    if not candidates and chunks:
        _chunk, document = chunks[0]
        candidates.append({"authority": document.original_name, "type": "source", "treatment": "source_only", "proposition": "No formal authority pattern found; linked source requires lawyer review."})
    return candidates[:20]


def _legal_tests(text: str) -> list[dict]:
    tests = []
    patterns = [
        ("must establish", r"must establish\s+([^.;]+)"),
        ("test is", r"test is\s+([^.;]+)"),
        ("elements", r"elements(?: are| include)?\s+([^.;]+)"),
    ]
    for label, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            tests.append({"label": label, "elements": [part.strip() for part in re.split(r",| and ", match.group(1)) if part.strip()], "supported": True})
    if not tests:
        tests.append({"label": "unsupported", "elements": [], "supported": False})
    return tests


def _citation_pack(sources: list[dict]) -> list[dict]:
    return [
        {
            "source_id": source["doc_id"],
            "citation": f"{source['filename']} p. {source['page']}",
            "excerpt": source["excerpt"],
            "verified": True,
        }
        for source in sources
    ]


def _research_memo(question: str, authorities: list[dict], tests: list[dict], citations: list[dict], config: dict) -> str:
    jurisdiction = config.get("jurisdiction") or "unspecified jurisdiction"
    authority_names = ", ".join(item["authority"] for item in authorities[:5]) or "No formal authorities identified"
    supported_tests = [test for test in tests if test.get("supported")]
    test_text = "; ".join(", ".join(test["elements"]) for test in supported_tests) or "No supported legal test extracted from linked sources"
    citation_text = ", ".join(item["citation"] for item in citations[:5]) or "No citations available"
    return (
        "Research memo\n\n"
        f"Issue: {question}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Authorities: {authority_names}.\n"
        f"Rule/test: {test_text}.\n"
        "Application: Apply the extracted authorities and tests to the matter facts only after lawyer review of the cited source excerpts.\n"
        f"Citations: {citation_text}.\n"
        "Conclusion: Preliminary research pack prepared; final legal conclusion requires human review."
    )


def _limitations(authorities: list[dict], tests: list[dict]) -> str:
    limits = []
    if not authorities:
        limits.append("No candidate authorities were extracted from linked sources.")
    if not any(test.get("supported") for test in tests):
        limits.append("No supported legal test was extracted from linked sources.")
    limits.append("This deterministic run does not verify current law or external treatment.")
    return " ".join(limits)


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
