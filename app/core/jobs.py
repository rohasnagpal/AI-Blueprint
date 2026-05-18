import json
import uuid

from sqlalchemy.orm import Session

from app.core.models import Job, JobEvent, utcnow


def create_job(
    db: Session,
    *,
    workspace_id: str | None,
    created_by_user_id: str,
    job_type: str,
    metadata: dict | None = None,
    message: str = "Job queued",
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        job_type=job_type,
        status="pending",
        progress=0,
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    )
    db.add(job)
    db.flush()
    add_job_event(db, job=job, event_type="status", message=message, metadata={"status": job.status, "progress": job.progress})
    return job


def add_job_event(
    db: Session,
    *,
    job: Job,
    event_type: str,
    message: str | None = None,
    metadata: dict | None = None,
) -> JobEvent:
    event = JobEvent(
        id=str(uuid.uuid4()),
        job_id=job.id,
        workspace_id=job.workspace_id,
        event_type=event_type,
        message=message,
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    )
    db.add(event)
    return event


def update_job_status(
    db: Session,
    *,
    job: Job,
    status: str,
    progress: int | None = None,
    message: str | None = None,
    error: str | None = None,
) -> Job:
    if job.status == "cancelled" and status != "cancelled":
        add_job_event(
            db,
            job=job,
            event_type="status",
            message="Ignored status update after cancellation",
            metadata={"requested_status": status, "progress": job.progress},
        )
        return job
    job.status = status
    if progress is not None:
        job.progress = progress
    if status == "running" and not job.started_at:
        job.started_at = utcnow()
    if status in {"completed", "failed", "cancelled"}:
        job.completed_at = utcnow()
    job.heartbeat_at = utcnow()
    job.error = error
    add_job_event(
        db,
        job=job,
        event_type="status",
        message=message or f"Job {status}",
        metadata={"status": job.status, "progress": job.progress, "error": error},
    )
    return job


def format_job(job: Job) -> dict:
    return {
        "id": job.id,
        "workspace_id": job.workspace_id,
        "created_by_user_id": job.created_by_user_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "metadata": _json_loads(job.metadata_json, {}),
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def format_job_event(event: JobEvent) -> dict:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "workspace_id": event.workspace_id,
        "type": event.event_type,
        "content": event.message or "",
        "metadata": _json_loads(event.metadata_json, {}),
        "created_at": event.created_at.isoformat(),
    }


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback
