import asyncio
import json
import re
import uuid
from typing import Any

import database
from app.core.database import SessionLocal
from app.core.jobs import add_job_event, update_job_status
from sqlalchemy import select

from app.core.models import CouncilEvidence, CouncilOutput, CouncilRun, DocumentLink, Job, KnowledgeChunk, KnowledgeDocument, utcnow
from routes import councils as legacy_councils


def execute_council_run(job_id: str, run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run = db.get(CouncilRun, run_id)
        if not job or not run:
            return
        try:
            config = _json_loads(run.config_snapshot_json, {})
            phases = config.get("phases") or []
            agents = {agent["id"]: agent for agent in config.get("agents") or [] if isinstance(agent, dict) and agent.get("id")}
            settings = _get_settings_with_secrets()
            prior_outputs: list[dict[str, Any]] = []

            run.status = "running"
            run.started_at = utcnow()
            update_job_status(db, job=job, status="running", progress=5, message="Council run started")
            db.commit()

            total_steps = max(1, sum(len(phase.get("agents") or []) for phase in phases if isinstance(phase, dict)))
            completed_steps = 0

            for phase in phases:
                phase_id = phase.get("id")
                phase_name = phase.get("name")
                add_job_event(
                    db,
                    job=job,
                    event_type="progress",
                    message=f"Starting phase: {phase_name}",
                    metadata={"phase_id": phase_id, "phase_name": phase_name},
                )
                query = _phase_query(phase, run.objective, prior_outputs)
                evidence = _retrieve_scoped_evidence(db, run, query, int(settings.get("top_k", 5) or 5))
                if not evidence:
                    evidence = asyncio.run(_retrieve_phase_evidence(query, settings))
                evidence_row = CouncilEvidence(
                    id=str(uuid.uuid4()),
                    workspace_id=run.workspace_id,
                    blueprint_id=run.blueprint_id,
                    run_id=run.id,
                    phase_id=phase_id,
                    phase_name=phase_name,
                    query=query,
                    sources_json=json.dumps(_visible_sources(evidence), sort_keys=True),
                )
                db.add(evidence_row)
                db.commit()

                phase_agent_ids = [agent_id for agent_id in phase.get("agents") or [] if agent_id in agents]
                phase_outputs = asyncio.run(_run_phase_agents(run, config, phase, phase_agent_ids, agents, evidence, prior_outputs, settings))

                for result in phase_outputs:
                    output = CouncilOutput(
                        id=str(uuid.uuid4()),
                        workspace_id=run.workspace_id,
                        blueprint_id=run.blueprint_id,
                        run_id=run.id,
                        phase_id=phase_id,
                        phase_name=phase_name,
                        agent_id=result["agent_id"],
                        role_name=result["role_name"],
                        content=result["content"],
                        sources_json=json.dumps(result.get("sources", []), sort_keys=True),
                        metadata_json=json.dumps(result.get("metadata", {}), sort_keys=True),
                    )
                    db.add(output)
                    completed_steps += 1
                    progress = min(95, 5 + int((completed_steps / total_steps) * 90))
                    job.progress = progress
                    job.heartbeat_at = utcnow()
                    add_job_event(
                        db,
                        job=job,
                        event_type="progress",
                        message=f"Completed {result['role_name']} in {phase_name}",
                        metadata={"phase_id": phase_id, "agent_id": result["agent_id"], "progress": progress},
                    )
                    db.commit()
                prior_outputs.extend(phase_outputs)

            run.status = "completed"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="completed", progress=100, message="Council run completed")
            db.commit()
        except Exception as exc:
            if run:
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = utcnow()
            if job:
                update_job_status(db, job=job, status="failed", progress=job.progress, message="Council run failed", error=str(exc))
            db.commit()


async def _run_phase_agents(
    run: CouncilRun,
    config: dict[str, Any],
    phase: dict[str, Any],
    phase_agent_ids: list[str],
    agents: dict[str, dict[str, Any]],
    evidence: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict,
) -> list[dict[str, Any]]:
    if phase.get("mode") == "parallel":
        tasks = [
            _run_agent(run, config, phase, agents[agent_id], evidence, prior_outputs, settings)
            for agent_id in phase_agent_ids
        ]
        return await asyncio.gather(*tasks)
    outputs = []
    local_prior_outputs = list(prior_outputs)
    for agent_id in phase_agent_ids:
        output = await _run_agent(run, config, phase, agents[agent_id], evidence, local_prior_outputs, settings)
        outputs.append(output)
        local_prior_outputs.append(output)
    return outputs


async def _run_agent(
    run: CouncilRun,
    config: dict[str, Any],
    phase: dict[str, Any],
    agent: dict[str, Any],
    evidence: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict,
) -> dict[str, Any]:
    provider = _agent_provider(agent, settings)
    model = _agent_model(agent, settings)
    temperature = float(agent.get("temperature", settings.get("temperature", 0.2)))
    max_tokens = int(agent.get("max_tokens", settings.get("max_tokens", 2048)))
    system = _build_agent_system(config, phase, agent, settings)
    user = _build_agent_user(run, phase, agent, evidence, prior_outputs)

    if provider == "mock":
        content = _mock_output(run, phase, agent)
    elif provider == "anthropic":
        content = await legacy_councils._complete_anthropic(settings.get("anthropic_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "groq":
        content = await legacy_councils._complete_groq(settings.get("groq_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "ollama":
        content = await legacy_councils._complete_ollama(system, user, model, temperature, max_tokens, settings)
    elif provider == "openrouter":
        content = await legacy_councils._complete_openrouter(settings.get("openrouter_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "openai" and settings.get("rag_provider") == "openai" and settings.get("vector_store_id"):
        content = await legacy_councils._complete_openai_file_search(settings.get("openai_api_key", ""), settings["vector_store_id"], system, user, model, temperature, max_tokens)
    else:
        content = await legacy_councils._complete_openai(settings.get("openai_api_key", ""), system, user, model, temperature, max_tokens)

    return {
        "agent_id": agent["id"],
        "role_name": agent["name"],
        "content": content,
        "sources": _visible_sources(evidence),
        "metadata": {
            "provider": provider,
            "model": model,
            "runner": "v2_council_runner",
            "output_type": agent.get("output_type", "custom"),
            "require_citations": bool(agent.get("require_citations")),
        },
    }


async def _retrieve_phase_evidence(query: str, settings: dict) -> list[dict[str, Any]]:
    if settings.get("rag_provider") != "llamaindex":
        return []
    try:
        from rag.llamaindex_rag import LlamaIndexRag

        provider = LlamaIndexRag()
        chunks = await provider.retrieve(
            query,
            None,
            int(settings.get("top_k", 5)),
            float(settings.get("similarity_threshold", 0.72)),
        )
        return [
            {
                "filename": chunk.get("source", "unknown"),
                "doc_id": chunk.get("doc_id", ""),
                "page": chunk.get("page"),
                "excerpt": chunk.get("content", "")[:800],
                "content": chunk.get("content", ""),
            }
            for chunk in chunks
        ]
    except Exception as exc:
        return [{"filename": "retrieval-error", "page": None, "excerpt": str(exc), "content": ""}]


def _retrieve_scoped_evidence(db, run: CouncilRun, query: str, top_k: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(DocumentLink, DocumentLink.document_id == KnowledgeDocument.id)
        .where(
            DocumentLink.workspace_id == run.workspace_id,
            DocumentLink.blueprint_id == run.blueprint_id,
            KnowledgeDocument.status == "indexed",
        )
        .order_by(KnowledgeChunk.chunk_index)
    ).all()
    if not rows:
        return []
    terms = _query_terms(query)
    scored = []
    for chunk, document in rows:
        content_lower = chunk.content.lower()
        score = sum(1 for term in terms if term in content_lower)
        scored.append((score, chunk, document))
    scored.sort(key=lambda item: (item[0], -item[1].chunk_index), reverse=True)
    evidence = []
    for score, chunk, document in scored[: max(1, top_k)]:
        evidence.append(
            {
                "filename": document.original_name,
                "doc_id": document.id,
                "page": chunk.chunk_index + 1,
                "excerpt": chunk.content[:800],
                "content": chunk.content,
                "score": score,
                "retrieval": "v2_scoped_chunks",
            }
        )
    return evidence


def _query_terms(query: str) -> set[str]:
    return {part.lower() for part in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query or "")}


def _phase_query(phase: dict[str, Any], objective: str, prior_outputs: list[dict[str, Any]]) -> str:
    mode = phase.get("retrieval_query", "objective")
    if mode == "phase":
        return f"{objective}\n\nPhase: {phase.get('name', '')}\n{phase.get('instructions', '')}"
    if isinstance(mode, str) and mode not in {"objective", "phase"}:
        return mode
    if prior_outputs:
        recent = "\n\n".join(f"{output['role_name']}: {output['content'][:600]}" for output in prior_outputs[-3:])
        return f"{objective}\n\nPrior outputs:\n{recent}"
    return objective


def _build_agent_system(config: dict[str, Any], phase: dict[str, Any], agent: dict[str, Any], settings: dict) -> str:
    lang = settings.get("response_language", "English")
    citation_rule = "Include source references when evidence is provided." if agent.get("require_citations") else "Use evidence carefully; citations are optional."
    return (
        f"You are {agent.get('name')}, a participant in an AI council named {config.get('name', 'Council')}.\n"
        f"Role instructions:\n{agent.get('instructions', '')}\n\n"
        f"Current phase: {phase.get('name', '')}.\n"
        f"Phase instructions: {phase.get('instructions', '')}\n"
        f"Respond in {lang}. {citation_rule}\n"
        "Do not invent facts that are not supported by the provided evidence or user objective."
    )


def _build_agent_user(run: CouncilRun, phase: dict[str, Any], agent: dict[str, Any], evidence: list[dict[str, Any]], prior_outputs: list[dict[str, Any]]) -> str:
    access = set(agent.get("context_access") or ["documents", "user_prompt", "prior_outputs"])
    sections = [f"Council objective:\n{run.objective}"]
    if "documents" in access:
        if evidence:
            evidence_text = "\n\n".join(
                f"[{idx + 1}] {src.get('filename', 'source')} p.{src.get('page')}\n{src.get('content') or src.get('excerpt', '')}"
                for idx, src in enumerate(evidence)
            )
        else:
            evidence_text = "No local evidence bundle is available."
        sections.append(f"Evidence:\n{evidence_text}")
    if "prior_outputs" in access and prior_outputs:
        sections.append("Prior council outputs:\n" + "\n\n".join(f"{out['role_name']}:\n{out['content']}" for out in prior_outputs))
    sections.append(f"Your task in this phase:\n{phase.get('instructions', '')}")
    return "\n\n---\n\n".join(sections)


def _agent_provider(agent: dict[str, Any], settings: dict) -> str:
    provider = agent.get("provider", "default")
    if provider and provider != "default":
        return provider
    return settings.get("local_llm_provider", "openai")


def _agent_model(agent: dict[str, Any], settings: dict) -> str:
    model = agent.get("model", "default")
    return settings.get("chat_model", "gpt-4o") if not model or model == "default" else model


def _visible_sources(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "filename": src.get("filename"),
            "doc_id": src.get("doc_id"),
            "page": src.get("page"),
            "excerpt": src.get("excerpt"),
        }
        for src in evidence
    ]


def _mock_output(run: CouncilRun, phase: dict[str, Any], agent: dict[str, Any]) -> str:
    return (
        f"{agent.get('name')} completed mock execution for {phase.get('name') or 'Phase'}.\n\n"
        f"Objective: {run.objective}\n\n"
        f"Phase instructions: {phase.get('instructions') or 'No phase instructions were provided.'}"
    )


def _get_settings_with_secrets() -> dict:
    settings = database.get_all_settings()
    for key in database.API_KEY_FIELDS:
        settings[key] = database.get_setting(key)
    return settings


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback
