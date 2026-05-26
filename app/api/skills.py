from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member, require_workspace_member
from app.core.models import BlueprintMember, Skill, SkillRun, SkillVersion, User
from app.core.pagination import page_query_response
from app.core.skills import json_loads

router = APIRouter(tags=["skills"])


def _format_skill(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "owner": skill.owner,
        "input_schema": json_loads(skill.input_schema_json, {}),
        "output_schema": json_loads(skill.output_schema_json, {}),
        "is_enabled": skill.is_enabled,
        "created_at": skill.created_at.isoformat(),
        "updated_at": skill.updated_at.isoformat(),
    }


def _format_version(version: SkillVersion) -> dict:
    return {
        "id": version.id,
        "skill_id": version.skill_id,
        "version": version.version,
        "prompt_template": version.prompt_template,
        "validation": json_loads(version.validation_json, {}),
        "created_at": version.created_at.isoformat(),
    }


def _format_run(run: SkillRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "blueprint_id": run.blueprint_id,
        "skill_id": run.skill_id,
        "skill_version_id": run.skill_version_id,
        "status": run.status,
        "input": json_loads(run.input_json, {}),
        "output": json_loads(run.output_json, {}),
        "sources": json_loads(run.sources_json, []),
        "metadata": json_loads(run.metadata_json, {}),
        "error": run.error,
        "created_by_user_id": run.created_by_user_id,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/skills")
async def list_skills(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    skills = select(Skill).where(Skill.is_enabled == True).order_by(Skill.owner, Skill.name)
    return page_query_response(db, skills, _format_skill, page=page, page_size=page_size, scalars=True)


@router.get("/skills/{skill_id}/versions")
async def list_skill_versions(skill_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    versions = select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(SkillVersion.created_at.desc())
    return page_query_response(db, versions, _format_version, page=page, page_size=page_size, scalars=True)


@router.get("/workspaces/{workspace_id}/skill-runs")
async def list_workspace_skill_runs(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    permitted_blueprint_ids = db.execute(
        select(BlueprintMember.blueprint_id).where(BlueprintMember.user_id == user.id)
    ).scalars().all()
    visibility_filters = [SkillRun.blueprint_id.is_(None)]
    if permitted_blueprint_ids:
        visibility_filters.append(SkillRun.blueprint_id.in_(permitted_blueprint_ids))
    runs = (
        select(SkillRun)
        .where(SkillRun.workspace_id == workspace_id, or_(*visibility_filters))
        .order_by(SkillRun.created_at.desc())
    )
    return page_query_response(db, runs, _format_run, page=page, page_size=page_size, scalars=True)


@router.get("/workspaces/{workspace_id}/blueprints/{blueprint_id}/skill-runs")
async def list_blueprint_skill_runs(workspace_id: str, blueprint_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_blueprint_member(workspace_id, blueprint_id, user, db)
    runs = (
        select(SkillRun)
        .where(SkillRun.workspace_id == workspace_id, SkillRun.blueprint_id == blueprint_id)
        .order_by(SkillRun.created_at.desc())
    )
    return page_query_response(db, runs, _format_run, page=page, page_size=page_size, scalars=True)
