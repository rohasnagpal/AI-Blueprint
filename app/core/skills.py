import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.json_utils import json_loads
from app.core.models import Skill, SkillRun, SkillVersion, utcnow


def record_skill_run(
    db: Session,
    *,
    workspace_id: str,
    blueprint_id: str | None,
    skill_id: str,
    created_by_user_id: str,
    input_data: dict | None = None,
    output_data: dict | list | str | None = None,
    sources: list | None = None,
    metadata: dict | None = None,
    status: str = "completed",
    error: str | None = None,
) -> SkillRun:
    skill = db.get(Skill, skill_id)
    if not skill:
        skill = Skill(
            id=skill_id,
            name=skill_id,
            description="Auto-registered skill placeholder created by a runner.",
            category="runner",
            owner="system",
            is_enabled=False,
        )
        db.add(skill)
        db.flush()
    version = db.execute(
        select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(SkillVersion.created_at.desc())
    ).scalars().first()
    run = SkillRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        skill_id=skill_id,
        skill_version_id=version.id if version else None,
        status=status,
        input_json=json.dumps(input_data or {}, sort_keys=True),
        output_json=json.dumps(output_data if output_data is not None else {}, sort_keys=True),
        sources_json=json.dumps(sources or [], sort_keys=True),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
        error=error,
        created_by_user_id=created_by_user_id,
        completed_at=utcnow() if status in {"completed", "failed"} else None,
    )
    db.add(run)
    return run

