import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member
from app.core.jobs import create_job, format_job
from app.core.legal_research_runner import execute_legal_research
from app.core.models import BlueprintInstance, LegalResearchConfig, LegalResearchOutput, LegalResearchRun, User, utcnow
from app.core.pagination import page_response

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints/{blueprint_id}/legal-research", tags=["legal-research"])


class LegalResearchConfigIn(BaseModel):
    config: dict[str, Any] = {}


class LegalResearchRunIn(BaseModel):
    title: str = ""
    question: str = Field(min_length=1)
    config: dict[str, Any] | None = None


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _require_research_blueprint(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, str]:
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if blueprint.plugin_id != "legal_research":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal Research blueprint not found")
    return blueprint, membership.role


def _format_config(config: LegalResearchConfig) -> dict:
    return {
        "id": config.id,
        "workspace_id": config.workspace_id,
        "blueprint_id": config.blueprint_id,
        "config": _json_loads(config.config_json, {}),
        "created_by_user_id": config.created_by_user_id,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


def _format_run(run: LegalResearchRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "blueprint_id": run.blueprint_id,
        "title": run.title,
        "question": run.question,
        "status": run.status,
        "config_snapshot": _json_loads(run.config_snapshot_json, {}),
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _format_output(output: LegalResearchOutput) -> dict:
    return {
        "id": output.id,
        "run_id": output.run_id,
        "authority_matrix": _json_loads(output.authority_matrix_json, []),
        "legal_tests": _json_loads(output.legal_tests_json, []),
        "citation_pack": _json_loads(output.citation_pack_json, []),
        "research_memo": output.research_memo,
        "limitations": output.limitations,
        "sources": _json_loads(output.sources_json, []),
        "metadata": _json_loads(output.metadata_json, {}),
        "created_at": output.created_at.isoformat(),
    }


def _research_export_markdown(run: LegalResearchRun, output: LegalResearchOutput) -> str:
    authority_matrix = _json_loads(output.authority_matrix_json, [])
    legal_tests = _json_loads(output.legal_tests_json, [])
    citation_pack = _json_loads(output.citation_pack_json, [])
    lines = [
        f"# {run.title}",
        "",
        "## Research Question",
        run.question,
        "",
        "## Research Memo",
        output.research_memo,
        "",
        "## Authority Matrix",
    ]
    for item in authority_matrix:
        lines.append(f"- **{item.get('authority')}** ({item.get('type')}): {item.get('proposition')} [{item.get('treatment')}]")
    lines.extend(["", "## Legal Tests"])
    for test in legal_tests:
        elements = ", ".join(test.get("elements") or []) or "Unsupported"
        lines.append(f"- **{test.get('label')}**: {elements}")
    lines.extend(["", "## Citation Pack"])
    for citation in citation_pack:
        lines.append(f"- {citation.get('citation')}: {citation.get('excerpt')}")
    lines.extend(["", "## Limitations", output.limitations])
    return "\n".join(lines).strip() + "\n"


@router.get("/config")
async def get_config(workspace_id: str, blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_research_blueprint(workspace_id, blueprint_id, user, db)
    config = db.execute(select(LegalResearchConfig).where(LegalResearchConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal Research config not found")
    return _format_config(config)


@router.put("/config")
async def upsert_config(workspace_id: str, blueprint_id: str, body: LegalResearchConfigIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _blueprint, role = _require_research_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config_json = json.dumps(body.config, sort_keys=True)
    config = db.execute(select(LegalResearchConfig).where(LegalResearchConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if config:
        config.config_json = config_json
        config.updated_at = utcnow()
        action = "legal_research.config.update"
    else:
        config = LegalResearchConfig(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            config_json=config_json,
            created_by_user_id=user.id,
        )
        db.add(config)
        action = "legal_research.config.create"
    db.flush()
    record_audit_event(db, action=action, resource_type="legal_research_config", resource_id=config.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(config)
    return _format_config(config)


@router.get("/runs")
async def list_runs(workspace_id: str, blueprint_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_research_blueprint(workspace_id, blueprint_id, user, db)
    runs = db.execute(
        select(LegalResearchRun)
        .where(LegalResearchRun.workspace_id == workspace_id, LegalResearchRun.blueprint_id == blueprint_id)
        .order_by(LegalResearchRun.created_at.desc())
    ).scalars().all()
    return page_response(runs, _format_run, page=page, page_size=page_size)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    workspace_id: str,
    blueprint_id: str,
    background_tasks: BackgroundTasks,
    body: LegalResearchRunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_research_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config = body.config
    if config is None:
        saved = db.execute(select(LegalResearchConfig).where(LegalResearchConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
        config = _json_loads(saved.config_json, {}) if saved else {}
    run = LegalResearchRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        title=body.title.strip() or "Legal Research",
        question=body.question.strip(),
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
        job_type="legal_research.run",
        metadata={"blueprint_id": blueprint_id, "run_id": run.id},
        message="Legal research queued",
    )
    record_audit_event(
        db,
        action="legal_research.run.create",
        resource_type="legal_research_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "job_id": job.id},
    )
    db.commit()
    db.refresh(run)
    db.refresh(job)
    background_tasks.add_task(execute_legal_research, job.id, run.id)
    data = _format_run(run)
    data["job"] = format_job(job)
    return data


@router.get("/runs/{run_id}")
async def get_run(workspace_id: str, blueprint_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_research_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(LegalResearchRun).where(
            LegalResearchRun.workspace_id == workspace_id,
            LegalResearchRun.blueprint_id == blueprint_id,
            LegalResearchRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal Research run not found")
    output = db.execute(select(LegalResearchOutput).where(LegalResearchOutput.run_id == run_id)).scalar_one_or_none()
    return {"run": _format_run(run), "output": _format_output(output) if output else None}


@router.get("/runs/{run_id}/export")
async def export_run(workspace_id: str, blueprint_id: str, run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_research_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(LegalResearchRun).where(
            LegalResearchRun.workspace_id == workspace_id,
            LegalResearchRun.blueprint_id == blueprint_id,
            LegalResearchRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal Research run not found")
    output = db.execute(select(LegalResearchOutput).where(LegalResearchOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal Research output not found")
    record_audit_event(db, action="legal_research.run.export", resource_type="legal_research_run", resource_id=run.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    return Response(content=_research_export_markdown(run, output), media_type="text/markdown")
