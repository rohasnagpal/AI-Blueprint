import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.council_runner import execute_council_run
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member
from app.core.jobs import create_job, format_job
from app.core.models import BlueprintInstance, CouncilConfig, CouncilEvidence, CouncilOutput, CouncilRun, User, utcnow
from app.core.pagination import page_response

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints/{blueprint_id}/council", tags=["council"])


class CouncilConfigIn(BaseModel):
    config: dict[str, Any]


class CouncilRunIn(BaseModel):
    title: str = ""
    objective: str = Field(min_length=1)
    config: dict[str, Any] | None = None


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _validate_config(config: dict[str, Any]) -> None:
    agents = config.get("agents")
    phases = config.get("phases")
    if not isinstance(agents, list) or not agents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Council config must include at least one AI participant")
    if not isinstance(phases, list) or not phases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Council config must include at least one phase")
    agent_ids = set()
    for agent in agents:
        if not isinstance(agent, dict) or not agent.get("id") or not agent.get("name"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each AI participant needs an id and name")
        if agent["id"] in agent_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Duplicate AI participant id: {agent['id']}")
        agent_ids.add(agent["id"])
    for phase in phases:
        phase_agents = phase.get("agents") if isinstance(phase, dict) else None
        if not isinstance(phase, dict) or not phase.get("id") or not phase.get("name"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each phase needs an id and name")
        if not isinstance(phase_agents, list) or not phase_agents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Phase {phase.get('name', '')} needs at least one participant")
        missing = [agent_id for agent_id in phase_agents if agent_id not in agent_ids]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Phase {phase.get('name')} references unknown participant(s): {', '.join(missing)}")


def _require_council_blueprint(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, str]:
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if blueprint.plugin_id != "ai_council":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI Council blueprint not found")
    return blueprint, membership.role


def _format_config(config: CouncilConfig) -> dict:
    return {
        "id": config.id,
        "workspace_id": config.workspace_id,
        "blueprint_id": config.blueprint_id,
        "config": _json_loads(config.config_json, {}),
        "created_by_user_id": config.created_by_user_id,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


def _format_run(run: CouncilRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "blueprint_id": run.blueprint_id,
        "title": run.title,
        "objective": run.objective,
        "status": run.status,
        "config_snapshot": _json_loads(run.config_snapshot_json, {}),
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _format_output(output: CouncilOutput) -> dict:
    return {
        "id": output.id,
        "run_id": output.run_id,
        "phase_id": output.phase_id,
        "phase_name": output.phase_name,
        "agent_id": output.agent_id,
        "role_name": output.role_name,
        "content": output.content,
        "sources": _json_loads(output.sources_json, []),
        "metadata": _json_loads(output.metadata_json, {}),
        "created_at": output.created_at.isoformat(),
    }


def _format_evidence(evidence: CouncilEvidence) -> dict:
    return {
        "id": evidence.id,
        "run_id": evidence.run_id,
        "phase_id": evidence.phase_id,
        "phase_name": evidence.phase_name,
        "query": evidence.query,
        "sources": _json_loads(evidence.sources_json, []),
        "created_at": evidence.created_at.isoformat(),
    }


def _council_export_markdown(run: CouncilRun, outputs: list[CouncilOutput], evidence: list[CouncilEvidence]) -> str:
    lines = [
        f"# {run.title}",
        "",
        "## Objective",
        run.objective,
        "",
        "## Outputs",
    ]
    if not outputs:
        lines.append("No council outputs are available yet.")
    for output in outputs:
        lines.extend(
            [
                "",
                f"### {output.phase_name} - {output.role_name}",
                output.content,
            ]
        )
        sources = _json_loads(output.sources_json, [])
        if sources:
            lines.append("")
            lines.append("Sources:")
            for source in sources:
                lines.append(f"- {source.get('filename')} p. {source.get('page')}: {source.get('excerpt')}")
    lines.extend(["", "## Evidence"])
    if not evidence:
        lines.append("No retrieval evidence was recorded.")
    for item in evidence:
        lines.append("")
        lines.append(f"### {item.phase_name}")
        lines.append(f"Query: {item.query}")
        sources = _json_loads(item.sources_json, [])
        for source in sources:
            lines.append(f"- {source.get('filename')} p. {source.get('page')}: {source.get('excerpt')}")
    lines.extend(["", "## Review Status", "Human review required before external delivery."])
    return "\n".join(lines).strip() + "\n"


@router.get("/config")
async def get_config(
    workspace_id: str,
    blueprint_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_council_blueprint(workspace_id, blueprint_id, user, db)
    config = db.execute(select(CouncilConfig).where(CouncilConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Council config not found")
    return _format_config(config)


@router.put("/config")
async def upsert_config(
    workspace_id: str,
    blueprint_id: str,
    body: CouncilConfigIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_council_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    _validate_config(body.config)
    config_json = json.dumps(body.config, sort_keys=True)
    config = db.execute(select(CouncilConfig).where(CouncilConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if config:
        config.config_json = config_json
        config.updated_at = utcnow()
        action = "council.config.update"
    else:
        config = CouncilConfig(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            config_json=config_json,
            created_by_user_id=user.id,
        )
        db.add(config)
        action = "council.config.create"
    db.flush()
    record_audit_event(db, action=action, resource_type="council_config", resource_id=config.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(config)
    return _format_config(config)


@router.get("/runs")
async def list_runs(
    workspace_id: str,
    blueprint_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_council_blueprint(workspace_id, blueprint_id, user, db)
    runs = db.execute(
        select(CouncilRun)
        .where(CouncilRun.workspace_id == workspace_id, CouncilRun.blueprint_id == blueprint_id)
        .order_by(CouncilRun.created_at.desc())
    ).scalars().all()
    return page_response(runs, _format_run, page=page, page_size=page_size)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    workspace_id: str,
    blueprint_id: str,
    background_tasks: BackgroundTasks,
    body: CouncilRunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_council_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config = body.config
    if not config:
        saved_config = db.execute(select(CouncilConfig).where(CouncilConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
        if not saved_config:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Council run needs a saved config or inline config")
        config = _json_loads(saved_config.config_json, {})
    _validate_config(config)
    title = body.title.strip() or config.get("name") or "Council Run"
    run = CouncilRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        title=title,
        objective=body.objective.strip(),
        status="pending",
        config_snapshot_json=json.dumps(config, sort_keys=True),
        created_by_user_id=user.id,
    )
    db.add(run)
    db.flush()
    job = create_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
        job_type="council.run",
        metadata={"blueprint_id": blueprint_id, "run_id": run.id},
        message="Council run queued",
    )
    record_audit_event(
        db,
        action="council.run.create",
        resource_type="council_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "job_id": job.id},
    )
    db.commit()
    db.refresh(run)
    db.refresh(job)
    background_tasks.add_task(execute_council_run, job.id, run.id)
    data = _format_run(run)
    data["job"] = format_job(job)
    return data


@router.get("/runs/{run_id}")
async def get_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_council_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(CouncilRun).where(
            CouncilRun.workspace_id == workspace_id,
            CouncilRun.blueprint_id == blueprint_id,
            CouncilRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Council run not found")
    outputs = db.execute(select(CouncilOutput).where(CouncilOutput.run_id == run_id).order_by(CouncilOutput.created_at)).scalars().all()
    evidence = db.execute(select(CouncilEvidence).where(CouncilEvidence.run_id == run_id).order_by(CouncilEvidence.created_at)).scalars().all()
    return {
        "run": _format_run(run),
        "outputs": [_format_output(output) for output in outputs],
        "evidence": [_format_evidence(item) for item in evidence],
    }


@router.delete("/runs/{run_id}")
async def delete_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_council_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    run = db.execute(
        select(CouncilRun).where(
            CouncilRun.workspace_id == workspace_id,
            CouncilRun.blueprint_id == blueprint_id,
            CouncilRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Council run not found")
    db.execute(delete(CouncilOutput).where(CouncilOutput.run_id == run_id))
    db.execute(delete(CouncilEvidence).where(CouncilEvidence.run_id == run_id))
    db.delete(run)
    record_audit_event(db, action="council.run.delete", resource_type="council_run", resource_id=run_id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    return {"ok": True}


@router.get("/runs/{run_id}/export")
async def export_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_council_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(CouncilRun).where(
            CouncilRun.workspace_id == workspace_id,
            CouncilRun.blueprint_id == blueprint_id,
            CouncilRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Council run not found")
    outputs = db.execute(select(CouncilOutput).where(CouncilOutput.run_id == run_id).order_by(CouncilOutput.created_at)).scalars().all()
    evidence = db.execute(select(CouncilEvidence).where(CouncilEvidence.run_id == run_id).order_by(CouncilEvidence.created_at)).scalars().all()
    record_audit_event(db, action="council.run.export", resource_type="council_run", resource_id=run.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    return Response(content=_council_export_markdown(run, outputs, evidence), media_type="text/markdown")
