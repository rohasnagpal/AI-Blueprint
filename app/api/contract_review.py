import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.contract_review_runner import execute_contract_review
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member
from app.core.json_utils import json_loads
from app.core.jobs import create_job, format_job
from app.core.models import (
    BlueprintInstance,
    ContractReviewConfig,
    ContractReviewOutput,
    ContractReviewRun,
    User,
    utcnow,
)
from app.core.pagination import page_query_response
from app.core.task_control import run_background_job

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review", tags=["contract-review"])


class ContractReviewConfigIn(BaseModel):
    config: dict[str, Any] = {}


class ContractReviewRunIn(BaseModel):
    title: str = ""
    config: dict[str, Any] | None = None


def _require_contract_blueprint(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, str]:
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if blueprint.plugin_id != "contract_review":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review blueprint not found")
    return blueprint, membership.role


def _format_config(config: ContractReviewConfig) -> dict:
    return {
        "id": config.id,
        "workspace_id": config.workspace_id,
        "blueprint_id": config.blueprint_id,
        "config": json_loads(config.config_json, {}),
        "created_by_user_id": config.created_by_user_id,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


def _format_run(run: ContractReviewRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "blueprint_id": run.blueprint_id,
        "title": run.title,
        "status": run.status,
        "config_snapshot": json_loads(run.config_snapshot_json, {}),
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _format_output(output: ContractReviewOutput) -> dict:
    return {
        "id": output.id,
        "run_id": output.run_id,
        "extraction": json_loads(output.extraction_json, {}),
        "risk_matrix": json_loads(output.risk_matrix_json, []),
        "negotiation_memo": output.negotiation_memo,
        "client_summary": output.client_summary,
        "sources": json_loads(output.sources_json, []),
        "metadata": json_loads(output.metadata_json, {}),
        "created_at": output.created_at.isoformat(),
    }


def _contract_export_markdown(run: ContractReviewRun, output: ContractReviewOutput) -> str:
    extraction = json_loads(output.extraction_json, {})
    risk_matrix = json_loads(output.risk_matrix_json, [])
    sources = json_loads(output.sources_json, [])
    lines = [
        f"# {run.title}",
        "",
        "## Client Summary",
        output.client_summary,
        "",
        "## Structured Extraction",
    ]
    for key, value in extraction.items():
        lines.append(f"- **{key}**: {value.get('value') or 'Unsupported'}")
    lines.extend(["", "## Risk Matrix"])
    for risk in risk_matrix:
        lines.append(f"- **{risk.get('issue')}** ({risk.get('severity')}): {risk.get('finding')}")
    lines.extend(["", "## Negotiation Memo", output.negotiation_memo, "", "## Sources"])
    for source in sources:
        locator = f"chunk {source.get('chunk')}" if source.get("chunk") else "indexed excerpt"
        lines.append(f"- {source.get('filename')} {locator}: {source.get('excerpt')}")
    lines.extend(["", "## Review Status", "Human legal review required before external delivery."])
    return "\n".join(lines).strip() + "\n"


@router.get("/config")
async def get_config(workspace_id: str, blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    config = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review config not found")
    return _format_config(config)


@router.put("/config")
async def upsert_config(
    workspace_id: str,
    blueprint_id: str,
    body: ContractReviewConfigIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config_json = json.dumps(body.config, sort_keys=True)
    config = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
    if config:
        config.config_json = config_json
        config.updated_at = utcnow()
        action = "contract_review.config.update"
    else:
        config = ContractReviewConfig(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            config_json=config_json,
            created_by_user_id=user.id,
        )
        db.add(config)
        action = "contract_review.config.create"
    db.flush()
    record_audit_event(db, action=action, resource_type="contract_review_config", resource_id=config.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(config)
    return _format_config(config)


@router.get("/runs")
async def list_runs(workspace_id: str, blueprint_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    runs = (
        select(ContractReviewRun)
        .where(ContractReviewRun.workspace_id == workspace_id, ContractReviewRun.blueprint_id == blueprint_id)
        .order_by(ContractReviewRun.created_at.desc())
    )
    return page_query_response(db, runs, _format_run, page=page, page_size=page_size, scalars=True)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    workspace_id: str,
    blueprint_id: str,
    background_tasks: BackgroundTasks,
    body: ContractReviewRunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    config = body.config
    if config is None:
        saved = db.execute(select(ContractReviewConfig).where(ContractReviewConfig.blueprint_id == blueprint_id)).scalar_one_or_none()
        config = json_loads(saved.config_json, {}) if saved else {}
    run = ContractReviewRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        title=body.title.strip() or "Contract Review",
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
        job_type="contract_review.run",
        metadata={"blueprint_id": blueprint_id, "run_id": run.id},
        message="Contract review queued",
    )
    record_audit_event(
        db,
        action="contract_review.run.create",
        resource_type="contract_review_run",
        resource_id=run.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"blueprint_id": blueprint_id, "job_id": job.id},
    )
    db.commit()
    db.refresh(run)
    db.refresh(job)
    background_tasks.add_task(run_background_job, job.id, execute_contract_review, job.id, run.id)
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
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    return {"run": _format_run(run), "output": _format_output(output) if output else None}


@router.delete("/runs/{run_id}")
async def delete_run(
    workspace_id: str,
    blueprint_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _blueprint, role = _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    if role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    db.execute(delete(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id))
    db.delete(run)
    record_audit_event(db, action="contract_review.run.delete", resource_type="contract_review_run", resource_id=run_id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
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
    _require_contract_blueprint(workspace_id, blueprint_id, user, db)
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review output not found")
    record_audit_event(db, action="contract_review.run.export", resource_type="contract_review_run", resource_id=run.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id})
    db.commit()
    return Response(content=_contract_export_markdown(run, output), media_type="text/markdown")


def _get_run_output(db: Session, workspace_id: str, blueprint_id: str, run_id: str) -> tuple[ContractReviewRun, ContractReviewOutput]:
    run = db.execute(
        select(ContractReviewRun).where(
            ContractReviewRun.workspace_id == workspace_id,
            ContractReviewRun.blueprint_id == blueprint_id,
            ContractReviewRun.id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review run not found")
    output = db.execute(select(ContractReviewOutput).where(ContractReviewOutput.run_id == run_id)).scalar_one_or_none()
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract Review output not found")
    return run, output
