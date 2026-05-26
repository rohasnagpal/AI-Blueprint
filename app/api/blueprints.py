import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member, require_plugin_enabled, require_workspace_member
from app.core.models import (
    BlueprintInstance,
    BlueprintMember,
    BlueprintPersona,
    ContractReviewConfig,
    ContractReviewOutput,
    ContractReviewRun,
    CouncilConfig,
    CouncilEvidence,
    CouncilOutput,
    CouncilRun,
    DocumentLink,
    Escalation,
    LegalResearchConfig,
    LegalResearchOutput,
    LegalResearchRun,
    Matter,
    SkillRun,
    User,
    WorkspaceMember,
    utcnow,
)
from app.core.pagination import page_query_response
from app.core.validation import validate_choice

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints", tags=["blueprints"])


class BlueprintIn(BaseModel):
    name: str = Field(min_length=1)
    plugin_id: str
    matter_id: str | None = None
    description: str | None = None
    status: str = "active"


class BlueprintUpdateIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    status: str = "active"


class BlueprintMemberIn(BaseModel):
    user_id: str
    role: str = "viewer"


class BlueprintMemberRoleIn(BaseModel):
    role: str


def _format_blueprint(blueprint: BlueprintInstance, role: str | None = None) -> dict:
    data = {
        "id": blueprint.id,
        "workspace_id": blueprint.workspace_id,
        "matter_id": blueprint.matter_id,
        "plugin_id": blueprint.plugin_id,
        "name": blueprint.name,
        "description": blueprint.description,
        "status": blueprint.status,
        "created_by_user_id": blueprint.created_by_user_id,
        "created_at": blueprint.created_at.isoformat(),
        "updated_at": blueprint.updated_at.isoformat(),
    }
    if role:
        data["role"] = role
    return data


def _validate_blueprint_role(role: str) -> str:
    return validate_choice(role, {"owner", "editor", "viewer"}, "blueprint role")


def _validate_blueprint_status(status_value: str) -> str:
    return validate_choice(status_value, {"active", "archived"}, "blueprint status")


def _format_blueprint_member(membership: BlueprintMember, member: User) -> dict:
    return {
        "id": membership.id,
        "blueprint_id": membership.blueprint_id,
        "user_id": member.id,
        "email": member.email,
        "display_name": member.display_name,
        "role": membership.role,
        "created_at": membership.created_at.isoformat(),
    }


def _require_blueprint_owner(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, BlueprintMember]:
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if membership.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint owner access required")
    return blueprint, membership


@router.get("")
async def list_blueprints(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    rows = (
        select(BlueprintInstance, BlueprintMember.role)
        .join(BlueprintMember, BlueprintMember.blueprint_id == BlueprintInstance.id)
        .where(
            BlueprintInstance.workspace_id == workspace_id,
            BlueprintMember.user_id == user.id,
        )
        .order_by(BlueprintInstance.updated_at.desc())
    )
    return page_query_response(db, rows, lambda row: _format_blueprint(row[0], row[1]), page=page, page_size=page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_blueprint(
    workspace_id: str,
    body: BlueprintIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    require_plugin_enabled(workspace_id, body.plugin_id, db)
    blueprint_status = _validate_blueprint_status(body.status)
    if body.matter_id:
        matter = db.execute(
            select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == body.matter_id)
        ).scalar_one_or_none()
        if not matter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    blueprint = BlueprintInstance(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        matter_id=body.matter_id,
        plugin_id=body.plugin_id,
        name=body.name.strip(),
        description=body.description,
        status=blueprint_status,
        created_by_user_id=user.id,
    )
    db.add(blueprint)
    db.add(BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint.id, user_id=user.id, role="owner"))
    db.flush()
    record_audit_event(
        db,
        action="blueprint.create",
        resource_type="blueprint",
        resource_id=blueprint.id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"plugin_id": body.plugin_id, "matter_id": body.matter_id},
    )
    db.commit()
    db.refresh(blueprint)
    return _format_blueprint(blueprint, "owner")


@router.get("/{blueprint_id}")
async def get_blueprint(
    workspace_id: str,
    blueprint_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    return _format_blueprint(blueprint, membership.role)


@router.get("/{blueprint_id}/members")
async def list_blueprint_members(
    workspace_id: str,
    blueprint_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_blueprint_member(workspace_id, blueprint_id, user, db)
    rows = (
        select(BlueprintMember, User)
        .join(User, User.id == BlueprintMember.user_id)
        .where(BlueprintMember.blueprint_id == blueprint_id)
        .order_by(User.display_name)
    )
    return page_query_response(db, rows, lambda row: _format_blueprint_member(row[0], row[1]), page=page, page_size=page_size)


@router.post("/{blueprint_id}/members", status_code=status.HTTP_201_CREATED)
async def add_blueprint_member(
    workspace_id: str,
    blueprint_id: str,
    body: BlueprintMemberIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_blueprint_owner(workspace_id, blueprint_id, user, db)
    role = _validate_blueprint_role(body.role)
    member = db.get(User, body.user_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    workspace_membership = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == body.user_id,
        )
    ).scalar_one_or_none()
    if not workspace_membership:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a workspace member")
    existing = db.execute(
        select(BlueprintMember).where(
            BlueprintMember.blueprint_id == blueprint_id,
            BlueprintMember.user_id == body.user_id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a blueprint member")
    membership = BlueprintMember(id=str(uuid.uuid4()), blueprint_id=blueprint_id, user_id=body.user_id, role=role)
    db.add(membership)
    db.flush()
    record_audit_event(db, action="blueprint.member.add", resource_type="blueprint_member", resource_id=membership.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id, "member_user_id": body.user_id, "role": role})
    db.commit()
    db.refresh(membership)
    return _format_blueprint_member(membership, member)


@router.put("/{blueprint_id}/members/{member_user_id}")
async def update_blueprint_member_role(
    workspace_id: str,
    blueprint_id: str,
    member_user_id: str,
    body: BlueprintMemberRoleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_blueprint_owner(workspace_id, blueprint_id, user, db)
    role = _validate_blueprint_role(body.role)
    row = db.execute(
        select(BlueprintMember, User)
        .join(User, User.id == BlueprintMember.user_id)
        .where(
            BlueprintMember.blueprint_id == blueprint_id,
            BlueprintMember.user_id == member_user_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint member not found")
    membership, member = row
    membership.role = role
    record_audit_event(db, action="blueprint.member.role_update", resource_type="blueprint_member", resource_id=membership.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id, "member_user_id": member.id, "role": role})
    db.commit()
    db.refresh(membership)
    return _format_blueprint_member(membership, member)


@router.delete("/{blueprint_id}/members/{member_user_id}")
async def remove_blueprint_member(
    workspace_id: str,
    blueprint_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_blueprint_owner(workspace_id, blueprint_id, user, db)
    membership = db.execute(
        select(BlueprintMember).where(
            BlueprintMember.blueprint_id == blueprint_id,
            BlueprintMember.user_id == member_user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint member not found")
    if member_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owners cannot remove their own blueprint membership")
    membership_id = membership.id
    db.delete(membership)
    record_audit_event(db, action="blueprint.member.remove", resource_type="blueprint_member", resource_id=membership_id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id, "member_user_id": member_user_id})
    db.commit()
    return {"ok": True}


@router.delete("/{blueprint_id}")
async def delete_blueprint(
    workspace_id: str,
    blueprint_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, _membership = _require_blueprint_owner(workspace_id, blueprint_id, user, db)
    metadata = {
        "plugin_id": blueprint.plugin_id,
        "matter_id": blueprint.matter_id,
        "status": blueprint.status,
    }
    for model in (
        CouncilOutput,
        CouncilEvidence,
        CouncilRun,
        CouncilConfig,
        ContractReviewOutput,
        ContractReviewRun,
        ContractReviewConfig,
        LegalResearchOutput,
        LegalResearchRun,
        LegalResearchConfig,
        DocumentLink,
        BlueprintPersona,
        Escalation,
        SkillRun,
        BlueprintMember,
    ):
        db.execute(delete(model).where(model.blueprint_id == blueprint_id))
    db.delete(blueprint)
    record_audit_event(
        db,
        action="blueprint.delete",
        resource_type="blueprint",
        resource_id=blueprint_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata=metadata,
    )
    db.commit()
    return {"ok": True}


@router.put("/{blueprint_id}")
async def update_blueprint(
    workspace_id: str,
    blueprint_id: str,
    body: BlueprintUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if membership.role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    blueprint.name = body.name.strip()
    blueprint.description = body.description
    blueprint.status = _validate_blueprint_status(body.status)
    blueprint.updated_at = utcnow()
    record_audit_event(
        db,
        action="blueprint.update",
        resource_type="blueprint",
        resource_id=blueprint.id,
        user_id=user.id,
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(blueprint)
    return _format_blueprint(blueprint, membership.role)
