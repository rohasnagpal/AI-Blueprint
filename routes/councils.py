import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import database

router = APIRouter()


class CouncilTemplateIn(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any]


class CouncilRunIn(BaseModel):
    template_id: str | None = None
    title: str = ""
    objective: str
    doc_context: str = "all"
    config: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _ollama_endpoint(settings: dict, path: str) -> str:
    base_url = (settings.get("ollama_base_url") or "http://localhost:11434").strip().rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _ollama_headers(settings: dict) -> dict[str, str]:
    api_key = (settings.get("ollama_api_key") or "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _format_template(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "config": _json_loads(row["config_json"], {}),
        "is_builtin": bool(row["is_builtin"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _format_run(row) -> dict:
    return {
        "id": row["id"],
        "template_id": row["template_id"],
        "title": row["title"],
        "objective": row["objective"],
        "doc_context": row["doc_context"],
        "config": _json_loads(row["config_json"], {}),
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def _format_output(row) -> dict:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "phase_id": row["phase_id"],
        "phase_name": row["phase_name"],
        "agent_id": row["agent_id"],
        "role_name": row["role_name"],
        "content": row["content"],
        "sources": _json_loads(row["sources_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
        "created_at": row["created_at"],
    }


def _format_evidence(row) -> dict:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "phase_id": row["phase_id"],
        "phase_name": row["phase_name"],
        "query": row["query"],
        "sources": _json_loads(row["sources_json"], []),
        "created_at": row["created_at"],
    }


def _validate_config(config: dict[str, Any]):
    agents = config.get("agents")
    phases = config.get("phases")
    if not isinstance(agents, list) or not agents:
        raise HTTPException(400, detail="Council config must include at least one AI participant.")
    if not isinstance(phases, list) or not phases:
        raise HTTPException(400, detail="Council config must include at least one phase.")
    agent_ids = set()
    for agent in agents:
        if not agent.get("id") or not agent.get("name"):
            raise HTTPException(400, detail="Each AI participant needs an id and name.")
        if agent["id"] in agent_ids:
            raise HTTPException(400, detail=f"Duplicate AI participant id: {agent['id']}")
        agent_ids.add(agent["id"])
    for phase in phases:
        phase_agents = phase.get("agents")
        if not phase.get("id") or not phase.get("name"):
            raise HTTPException(400, detail="Each phase needs an id and name.")
        if not isinstance(phase_agents, list) or not phase_agents:
            raise HTTPException(400, detail=f"Phase {phase.get('name', '')} needs at least one participant.")
        missing = [agent_id for agent_id in phase_agents if agent_id not in agent_ids]
        if missing:
            raise HTTPException(400, detail=f"Phase {phase.get('name')} references unknown participant(s): {', '.join(missing)}")


def _get_settings_with_secrets() -> dict:
    settings = database.get_all_settings()
    for key in database.API_KEY_FIELDS:
        settings[key] = database.get_setting(key)
    return settings


def _doc_ids_from_context(doc_context: str) -> list[str] | None:
    if not doc_context or doc_context == "all":
        return None
    return [part.strip() for part in doc_context.split(",") if part.strip()]


@router.get("/council/templates")
async def list_templates():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM council_templates ORDER BY is_builtin DESC, updated_at DESC").fetchall()
    conn.close()
    return [_format_template(row) for row in rows]


@router.post("/council/templates")
async def create_template(body: CouncilTemplateIn):
    _validate_config(body.config)
    now = _now()
    template_id = str(uuid.uuid4())
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO council_templates
        (id, name, description, config_json, is_builtin, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        """,
        (template_id, body.name.strip(), body.description.strip(), json.dumps(body.config), now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    return _format_template(row)


@router.get("/council/templates/{template_id}")
async def get_template(template_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, detail="Council template not found")
    return _format_template(row)


@router.put("/council/templates/{template_id}")
async def update_template(template_id: str, body: CouncilTemplateIn):
    _validate_config(body.config)
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Council template not found")
    now = _now()
    conn.execute(
        "UPDATE council_templates SET name = ?, description = ?, config_json = ?, updated_at = ? WHERE id = ?",
        (body.name.strip(), body.description.strip(), json.dumps(body.config), now, template_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    return _format_template(row)


@router.delete("/council/templates/{template_id}")
async def delete_template(template_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Council template not found")
    conn.execute("DELETE FROM council_templates WHERE id = ?", (template_id,))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('council_templates_seeded', 'true')")
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/council/runs")
async def list_runs():
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM council_runs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_format_run(row) for row in rows]


@router.post("/council/runs")
async def create_run(body: CouncilRunIn):
    config = body.config
    template_id = body.template_id
    if not config and template_id:
        conn = database.get_connection()
        template = conn.execute("SELECT * FROM council_templates WHERE id = ?", (template_id,)).fetchone()
        conn.close()
        if not template:
            raise HTTPException(404, detail="Council template not found")
        config = _json_loads(template["config_json"], {})
    if not config:
        raise HTTPException(400, detail="Run needs a template or config.")
    _validate_config(config)
    now = _now()
    run_id = str(uuid.uuid4())
    title = body.title.strip() or config.get("name") or "Council Run"
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO council_runs
        (id, template_id, title, objective, doc_context, config_json, status, error, created_at, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL, NULL)
        """,
        (run_id, template_id, title, body.objective.strip(), body.doc_context, json.dumps(config), now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return _format_run(row)


@router.get("/council/runs/{run_id}")
async def get_run(run_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, detail="Council run not found")
    return _format_run(row)


@router.get("/council/runs/{run_id}/outputs")
async def get_run_outputs(run_id: str):
    conn = database.get_connection()
    run = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        conn.close()
        raise HTTPException(404, detail="Council run not found")
    outputs = conn.execute(
        "SELECT * FROM council_outputs WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    evidence = conn.execute(
        "SELECT * FROM council_evidence WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    conn.close()
    return {"outputs": [_format_output(row) for row in outputs], "evidence": [_format_evidence(row) for row in evidence]}


@router.post("/council/runs/{run_id}/start")
async def start_run(run_id: str, background_tasks: BackgroundTasks):
    conn = database.get_connection()
    run = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not run:
        raise HTTPException(404, detail="Council run not found")
    if run["status"] == "running":
        raise HTTPException(409, detail="Council run is already running")
    _mark_run_running(run_id)
    background_tasks.add_task(_execute_run, run_id, False)
    return await get_run(run_id)


@router.delete("/council/runs/{run_id}")
async def delete_run(run_id: str):
    conn = database.get_connection()
    run = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    if not run:
        conn.close()
        raise HTTPException(404, detail="Council run not found")
    conn.execute("DELETE FROM council_outputs WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM council_evidence WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM council_runs WHERE id = ?", (run_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def _mark_run_running(run_id: str):
    conn = database.get_connection()
    conn.execute("DELETE FROM council_outputs WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM council_evidence WHERE run_id = ?", (run_id,))
    conn.execute(
        "UPDATE council_runs SET status = 'running', error = NULL, started_at = ?, completed_at = NULL WHERE id = ?",
        (_now(), run_id),
    )
    conn.commit()
    conn.close()


async def _execute_run(run_id: str, reset_state: bool = True):
    settings = _get_settings_with_secrets()
    conn = database.get_connection()
    run = conn.execute("SELECT * FROM council_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    if not run:
        raise HTTPException(404, detail="Council run not found")
    config = _json_loads(run["config_json"], {})
    _validate_config(config)
    if reset_state:
        _mark_run_running(run_id)

    try:
        doc_ids = _doc_ids_from_context(run["doc_context"])
        agents = {agent["id"]: agent for agent in config.get("agents", [])}
        prior_outputs: list[dict[str, Any]] = []

        for phase in config.get("phases", []):
            phase_outputs = []
            query = _phase_query(phase, run["objective"], prior_outputs)
            evidence = await _retrieve_phase_evidence(query, doc_ids, settings)
            _save_evidence(run_id, phase, query, evidence)
            phase_agent_ids = phase.get("agents", [])
            if phase.get("mode") == "parallel":
                tasks = [
                    _run_agent(run, config, phase, agents[agent_id], evidence, prior_outputs, settings)
                    for agent_id in phase_agent_ids
                    if agent_id in agents
                ]
                phase_outputs = await asyncio.gather(*tasks)
                for output in phase_outputs:
                    _save_output(run_id, phase, output)
            else:
                for agent_id in phase_agent_ids:
                    if agent_id not in agents:
                        continue
                    output = await _run_agent(run, config, phase, agents[agent_id], evidence, prior_outputs, settings)
                    phase_outputs.append(output)
                    _save_output(run_id, phase, output)
                    prior_outputs.append(output)
                continue
            prior_outputs.extend(phase_outputs)

        conn = database.get_connection()
        conn.execute(
            "UPDATE council_runs SET status = 'completed', completed_at = ? WHERE id = ?",
            (_now(), run_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        conn = database.get_connection()
        conn.execute(
            "UPDATE council_runs SET status = 'error', error = ?, completed_at = ? WHERE id = ?",
            (str(exc), _now(), run_id),
        )
        conn.commit()
        conn.close()
        raise HTTPException(500, detail=str(exc))


def _phase_query(phase: dict[str, Any], objective: str, prior_outputs: list[dict[str, Any]]) -> str:
    mode = phase.get("retrieval_query", "objective")
    if mode == "phase":
        return f"{objective}\n\nPhase: {phase.get('name', '')}\n{phase.get('instructions', '')}"
    if isinstance(mode, str) and mode not in {"objective", "phase"}:
        return mode
    if prior_outputs:
        recent = "\n\n".join(f"{o['role_name']}: {o['content'][:600]}" for o in prior_outputs[-3:])
        return f"{objective}\n\nPrior outputs:\n{recent}"
    return objective


async def _retrieve_phase_evidence(query: str, doc_ids: list[str] | None, settings: dict) -> list[dict[str, Any]]:
    if settings.get("rag_provider") != "llamaindex":
        return []
    try:
        from rag.llamaindex_rag import LlamaIndexRag

        provider = LlamaIndexRag()
        chunks = await provider.retrieve(
            query,
            doc_ids,
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


async def _run_agent(
    run,
    config: dict[str, Any],
    phase: dict[str, Any],
    agent: dict[str, Any],
    evidence: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
    settings: dict,
) -> dict[str, Any]:
    system = _build_agent_system(config, phase, agent, settings)
    user = _build_agent_user(run, phase, agent, evidence, prior_outputs)
    provider = _agent_provider(agent, settings)
    model = _agent_model(agent, settings)
    temperature = float(agent.get("temperature", settings.get("temperature", 0.2)))
    max_tokens = int(agent.get("max_tokens", settings.get("max_tokens", 2048)))

    if provider == "anthropic":
        content = await _complete_anthropic(settings.get("anthropic_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "groq":
        content = await _complete_groq(settings.get("groq_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "ollama":
        content = await _complete_ollama(system, user, model, temperature, max_tokens, settings)
    elif provider == "openrouter":
        content = await _complete_openrouter(settings.get("openrouter_api_key", ""), system, user, model, temperature, max_tokens)
    elif provider == "openai" and settings.get("rag_provider") == "openai" and settings.get("vector_store_id"):
        content = await _complete_openai_file_search(settings.get("openai_api_key", ""), settings["vector_store_id"], system, user, model, temperature, max_tokens)
    else:
        content = await _complete_openai(settings.get("openai_api_key", ""), system, user, model, temperature, max_tokens)

    return {
        "agent_id": agent["id"],
        "role_name": agent["name"],
        "content": content,
        "sources": _visible_sources(evidence),
        "metadata": {
            "provider": provider,
            "model": model,
            "output_type": agent.get("output_type", "custom"),
            "require_citations": bool(agent.get("require_citations")),
        },
    }


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


def _build_agent_user(run, phase: dict[str, Any], agent: dict[str, Any], evidence: list[dict[str, Any]], prior_outputs: list[dict[str, Any]]) -> str:
    access = set(agent.get("context_access") or ["documents", "user_prompt", "prior_outputs"])
    sections = [f"Council objective:\n{run['objective']}"]
    if "documents" in access:
        if evidence:
            evidence_text = "\n\n".join(
                f"[{idx + 1}] {src.get('filename', 'source')} p.{src.get('page')}\n{src.get('content') or src.get('excerpt', '')}"
                for idx, src in enumerate(evidence)
            )
        else:
            evidence_text = "No local evidence bundle is available. If file search is enabled, use the attached vector store evidence."
        sections.append(f"Evidence:\n{evidence_text}")
    if "prior_outputs" in access and prior_outputs:
        sections.append(
            "Prior council outputs:\n"
            + "\n\n".join(f"{out['role_name']}:\n{out['content']}" for out in prior_outputs)
        )
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


def _save_evidence(run_id: str, phase: dict[str, Any], query: str, evidence: list[dict[str, Any]]):
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO council_evidence
        (id, run_id, phase_id, phase_name, query, sources_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), run_id, phase["id"], phase["name"], query, json.dumps(_visible_sources(evidence)), _now()),
    )
    conn.commit()
    conn.close()


def _save_output(run_id: str, phase: dict[str, Any], output: dict[str, Any]):
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO council_outputs
        (id, run_id, phase_id, phase_name, agent_id, role_name, content, sources_json, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            run_id,
            phase["id"],
            phase["name"],
            output["agent_id"],
            output["role_name"],
            output["content"],
            json.dumps(output.get("sources", [])),
            json.dumps(output.get("metadata", {})),
            _now(),
        ),
    )
    conn.commit()
    conn.close()


async def _complete_openai(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("OpenAI API key not configured. Go to Settings → API Keys.")
    import openai

    client = openai.AsyncOpenAI(api_key=key)
    response = await client.chat.completions.create(**_chat_completion_args(model, system, user, temperature, max_tokens))
    return response.choices[0].message.content or ""


async def _complete_openrouter(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("OpenRouter API key not configured. Go to Settings -> API Keys.")
    import openai

    client = openai.AsyncOpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Blueprint",
        },
    )
    response = await client.chat.completions.create(**_chat_completion_args(model or "openrouter/auto", system, user, temperature, max_tokens))
    return response.choices[0].message.content or ""


def _uses_reasoning_chat_params(model: str) -> bool:
    model_id = (model or "").lower()
    return model_id.startswith(("gpt-5", "o1", "o3", "o4"))


def _chat_completion_args(model: str, system: str, user: str, temperature: float, max_tokens: int) -> dict:
    args = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if _uses_reasoning_chat_params(model):
        args["max_completion_tokens"] = max_tokens
        if (model or "").lower().startswith("gpt-5"):
            args["reasoning_effort"] = "none"
    else:
        args["temperature"] = temperature
        args["max_tokens"] = max_tokens
    return args


def _openai_assistants_model() -> str:
    model = database.get_setting("openai_assistants_model") or "gpt-4.1"
    if model.lower().startswith("gpt-5"):
        return "gpt-4.1"
    return model


async def _complete_openai_file_search(
    key: str, vector_store_id: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> str:
    if not key:
        raise RuntimeError("OpenAI API key not configured. Go to Settings → API Keys.")
    import openai

    client = openai.AsyncOpenAI(api_key=key)
    assistant = await client.beta.assistants.create(
        name="AI Blueprint Council Agent",
        model=_openai_assistants_model(),
        instructions=system,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    )
    thread = await client.beta.threads.create(
        messages=[{"role": "user", "content": user}]
    )
    run = await client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    try:
        await client.beta.assistants.delete(assistant.id)
    except Exception:
        pass
    if run.status != "completed":
        raise RuntimeError(f"OpenAI council agent did not complete: {run.status}")
    messages = await client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
    for msg in messages.data:
        if msg.role != "assistant":
            continue
        parts = []
        for block in msg.content or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text.value)
        return "\n".join(parts)
    return ""


async def _complete_groq(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Groq API key not configured.")
    from groq import AsyncGroq

    client = AsyncGroq(api_key=key)
    groq_model = model or "llama-3.1-8b-instant"
    response = await client.chat.completions.create(
        model=groq_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def _complete_anthropic(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Anthropic API key not configured.")
    import httpx

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model or "claude-3-5-sonnet-latest",
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")


async def _complete_ollama(system: str, user: str, model: str, temperature: float, max_tokens: int, settings: dict) -> str:
    import httpx

    chat_url = _ollama_endpoint(settings, "/chat")
    headers = _ollama_headers(settings)
    if "ollama.com" in chat_url and not headers:
        raise RuntimeError("Ollama API key is not configured. Add it in Settings -> API Keys -> Ollama.")

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            chat_url,
            headers=headers,
            json={
                "model": model or "llama3",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
