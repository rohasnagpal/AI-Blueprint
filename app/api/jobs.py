import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_member
from app.core.json_utils import json_loads
from app.core.jobs import format_job, format_job_event, update_job_status
from app.core.models import Job, JobEvent, User
from app.core.pagination import page_query_response
from app.core.task_control import is_job_running, request_job_cancel

router = APIRouter(prefix="/workspaces/{workspace_id}/jobs", tags=["jobs"])


def _require_job_access(workspace_id: str, job_id: str, user: User, db: Session) -> Job:
    require_workspace_member(workspace_id, user, db)
    job = db.execute(select(Job).where(Job.workspace_id == workspace_id, Job.id == job_id)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"


@router.get("")
async def list_jobs(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    jobs = (
        select(Job)
        .where(Job.workspace_id == workspace_id)
        .order_by(Job.created_at.desc())
    )
    return page_query_response(db, jobs, format_job, page=page, page_size=page_size, scalars=True)


@router.get("/{job_id}")
async def get_job(workspace_id: str, job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _require_job_access(workspace_id, job_id, user, db)
    events = db.execute(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at)).scalars().all()
    return {"job": format_job(job), "events": [format_job_event(event) for event in events]}


@router.put("/{job_id}/cancel")
async def cancel_job(workspace_id: str, job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _require_job_access(workspace_id, job_id, user, db)
    membership = require_workspace_member(workspace_id, user, db)
    if job.created_by_user_id != user.id and membership.role != "admin" and not user.is_system_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the job creator or a workspace admin can cancel this job")
    if job.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel a {job.status} job")
    was_running = request_job_cancel(job.id)
    update_job_status(db, job=job, status="cancelled", progress=job.progress, message="Job cancelled by user")
    record_audit_event(db, action="job.cancel", resource_type="job", resource_id=job.id, user_id=user.id, workspace_id=workspace_id, metadata={"job_type": job.job_type})
    db.commit()
    db.refresh(job)
    events = db.execute(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at)).scalars().all()
    payload = format_job(job)
    payload["running_in_process_at_cancel"] = was_running
    return {"job": payload, "events": [format_job_event(event) for event in events]}


@router.get("/{job_id}/events")
async def stream_job_events(workspace_id: str, job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _require_job_access(workspace_id, job_id, user, db)
    user_id = user.id
    initial_job_id = job.id

    async def stream():
        seen_event_ids: set[str] = set()
        max_polls = max(1, get_settings().job_stream_max_seconds)
        for _ in range(max_polls):
            with SessionLocal() as poll_db:
                poll_user = poll_db.get(User, user_id)
                if not poll_user:
                    yield _sse_event({"type": "error", "content": "User no longer exists", "metadata": {}})
                    return
                try:
                    current_job = _require_job_access(workspace_id, initial_job_id, poll_user, poll_db)
                except HTTPException as exc:
                    yield _sse_event({"type": "error", "content": str(exc.detail), "metadata": {"status_code": exc.status_code}})
                    return
                metadata = format_job(current_job)
                metadata["running_in_process"] = is_job_running(current_job.id)
                yield _sse_event({"type": "status", "content": current_job.status, "metadata": metadata})
                events = poll_db.execute(
                    select(JobEvent).where(JobEvent.job_id == initial_job_id).order_by(JobEvent.created_at)
                ).scalars().all()
                for event in events:
                    if event.id in seen_event_ids:
                        continue
                    seen_event_ids.add(event.id)
                    yield _sse_event(format_job_event(event))
                if current_job.status in {"completed", "failed", "cancelled"}:
                    yield _sse_event({"type": "done", "content": current_job.status, "metadata": format_job(current_job)})
                    return
            await asyncio.sleep(1)
        yield _sse_event({"type": "done", "content": "stream_timeout", "metadata": {"job_id": initial_job_id}})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
