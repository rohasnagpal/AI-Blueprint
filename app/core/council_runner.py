import asyncio
import json
import uuid
from typing import Any

from app.core.database import SessionLocal
from app.core.json_utils import json_loads
from app.core.llm import complete_async, get_legacy_settings_with_secrets, run_async
from app.core.jobs import JobCancelled, add_job_event, ensure_job_not_cancelled, update_job_status
from app.core.retrieval import retrieve_scoped_evidence

from app.core.models import CouncilEvidence, CouncilOutput, CouncilRun, Job, utcnow


def execute_council_run(job_id: str, run_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run = db.get(CouncilRun, run_id)
        if not job or not run:
            return
        try:
            ensure_job_not_cancelled(db, job)
            config = json_loads(run.config_snapshot_json, {})
            phases = config.get("phases") or []
            agents = {agent["id"]: agent for agent in config.get("agents") or [] if isinstance(agent, dict) and agent.get("id")}
            settings = get_legacy_settings_with_secrets()
            prior_outputs: list[dict[str, Any]] = []

            run.status = "running"
            run.started_at = utcnow()
            update_job_status(db, job=job, status="running", progress=5, message="Council run started")
            db.commit()
            ensure_job_not_cancelled(db, job)

            total_steps = max(1, sum(len(phase.get("agents") or []) for phase in phases if isinstance(phase, dict)))
            completed_steps = 0

            for phase in phases:
                ensure_job_not_cancelled(db, job)
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
                evidence = retrieve_scoped_evidence(
                    db,
                    workspace_id=run.workspace_id,
                    blueprint_id=run.blueprint_id,
                    query=query,
                    top_k=int(settings.get("top_k", 5) or 5),
                )
                if not evidence:
                    evidence = run_async(_retrieve_phase_evidence(query, settings))
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
                ensure_job_not_cancelled(db, job)

                phase_agent_ids = [agent_id for agent_id in phase.get("agents") or [] if agent_id in agents]
                phase_outputs = run_async(_run_phase_agents(run, config, phase, phase_agent_ids, agents, evidence, prior_outputs, settings))
                ensure_job_not_cancelled(db, job)

                for result in phase_outputs:
                    ensure_job_not_cancelled(db, job)
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
        except JobCancelled:
            run.status = "cancelled"
            run.completed_at = utcnow()
            update_job_status(db, job=job, status="cancelled", progress=job.progress, message="Council run cancelled")
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
    elif provider == "openai" and settings.get("rag_provider") == "openai" and settings.get("vector_store_id"):
        content = await complete_async(settings, "openai_file_search", system, user, model=model, temperature=temperature, max_tokens=max_tokens)
    else:
        content = await complete_async(settings, provider, system, user, model=model, temperature=temperature, max_tokens=max_tokens)

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

