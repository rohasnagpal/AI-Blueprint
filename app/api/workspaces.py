import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.models import BlueprintInstance, KnowledgeDocument, Matter, User, Workspace, WorkspaceMember, utcnow
from app.core.pagination import page_query_response
from app.core.security import hash_password
from app.core.validation import normalize_email, validate_choice

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None


class MatterIn(BaseModel):
    name: str = Field(min_length=1)
    client_name: str | None = None
    description: str | None = None
    status: str = "active"


class WorkspaceMemberIn(BaseModel):
    email: str
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=12)
    role: str = "member"


class WorkspaceMemberRoleIn(BaseModel):
    role: str


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or f"workspace-{uuid.uuid4().hex[:8]}"


def _format_workspace(workspace: Workspace, role: str | None = None) -> dict:
    data = {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "created_by_user_id": workspace.created_by_user_id,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
        "deleted_at": workspace.deleted_at.isoformat() if workspace.deleted_at else None,
    }
    if role:
        data["role"] = role
    return data


def _format_matter(matter: Matter) -> dict:
    return {
        "id": matter.id,
        "workspace_id": matter.workspace_id,
        "name": matter.name,
        "client_name": matter.client_name,
        "description": matter.description,
        "status": matter.status,
        "created_by_user_id": matter.created_by_user_id,
        "created_at": matter.created_at.isoformat(),
        "updated_at": matter.updated_at.isoformat(),
    }


def _validate_workspace_role(role: str) -> str:
    return validate_choice(role, {"admin", "member"}, "workspace role")


def _validate_matter_status(status_value: str) -> str:
    return validate_choice(status_value, {"active", "paused", "closed"}, "matter status")


def _format_workspace_member(membership: WorkspaceMember, member: User) -> dict:
    return {
        "id": membership.id,
        "workspace_id": membership.workspace_id,
        "user_id": member.id,
        "email": member.email,
        "display_name": member.display_name,
        "role": membership.role,
        "is_active": member.is_active,
        "is_system_admin": member.is_system_admin,
        "created_at": membership.created_at.isoformat(),
    }


@router.get("")
async def list_workspaces(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name)
    )
    return page_query_response(db, rows, lambda row: _format_workspace(row[0], row[1]), page=page, page_size=page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    slug = _slugify(body.slug or body.name)
    if db.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workspace slug already exists")
    workspace = Workspace(id=str(uuid.uuid4()), name=body.name.strip(), slug=slug, created_by_user_id=user.id)
    db.add(workspace)
    db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.flush()
    record_audit_event(db, action="workspace.create", resource_type="workspace", resource_id=workspace.id, user_id=user.id, workspace_id=workspace.id)
    db.commit()
    db.refresh(workspace)
    return _format_workspace(workspace, "admin")


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    membership = require_workspace_member(workspace_id, user, db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _format_workspace(workspace, membership.role)


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    body: WorkspaceIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = require_workspace_admin(workspace_id, user, db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    slug = _slugify(body.slug or body.name)
    existing = db.execute(select(Workspace).where(Workspace.slug == slug, Workspace.id != workspace_id)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workspace slug already exists")
    workspace.name = body.name.strip()
    workspace.slug = slug
    workspace.updated_at = utcnow()
    record_audit_event(db, action="workspace.update", resource_type="workspace", resource_id=workspace.id, user_id=user.id, workspace_id=workspace.id)
    db.commit()
    db.refresh(workspace)
    return _format_workspace(workspace, membership.role)


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_admin(workspace_id, user, db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    now = utcnow()
    workspace.deleted_at = now
    workspace.updated_at = now
    record_audit_event(db, action="workspace.delete", resource_type="workspace", resource_id=workspace.id, user_id=user.id, workspace_id=workspace.id)
    db.commit()
    return {"ok": True}


@router.get("/{workspace_id}/members")
async def list_workspace_members(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_admin(workspace_id, user, db)
    rows = (
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.display_name)
    )
    return page_query_response(db, rows, lambda row: _format_workspace_member(row[0], row[1]), page=page, page_size=page_size)


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_workspace_member(
    workspace_id: str,
    body: WorkspaceMemberIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    role = _validate_workspace_role(body.role)
    email = normalize_email(body.email)
    member = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not member:
        if not body.password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is required for new users")
        member = User(
            id=str(uuid.uuid4()),
            email=email,
            display_name=(body.display_name or email).strip(),
            password_hash=hash_password(body.password),
        )
        db.add(member)
        db.flush()
        record_audit_event(db, action="user.create", resource_type="user", resource_id=member.id, user_id=user.id, workspace_id=workspace_id)
    existing = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member.id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a workspace member")
    membership = WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace_id, user_id=member.id, role=role)
    db.add(membership)
    db.flush()
    record_audit_event(db, action="workspace.member.add", resource_type="workspace_member", resource_id=membership.id, user_id=user.id, workspace_id=workspace_id, metadata={"member_user_id": member.id, "role": role})
    db.commit()
    db.refresh(membership)
    db.refresh(member)
    return _format_workspace_member(membership, member)


@router.put("/{workspace_id}/members/{member_user_id}")
async def update_workspace_member_role(
    workspace_id: str,
    member_user_id: str,
    body: WorkspaceMemberRoleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    role = _validate_workspace_role(body.role)
    row = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member_user_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace member not found")
    membership, member = row
    membership.role = role
    record_audit_event(db, action="workspace.member.role_update", resource_type="workspace_member", resource_id=membership.id, user_id=user.id, workspace_id=workspace_id, metadata={"member_user_id": member.id, "role": role})
    db.commit()
    db.refresh(membership)
    return _format_workspace_member(membership, member)


@router.delete("/{workspace_id}/members/{member_user_id}")
async def remove_workspace_member(
    workspace_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    membership = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member_user_id,
        )
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace member not found")
    if member_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot remove their own workspace membership")
    membership_id = membership.id
    db.delete(membership)
    record_audit_event(db, action="workspace.member.remove", resource_type="workspace_member", resource_id=membership_id, user_id=user.id, workspace_id=workspace_id, metadata={"member_user_id": member_user_id})
    db.commit()
    return {"ok": True}


@router.get("/{workspace_id}/matters")
async def list_matters(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    matters = (
        select(Matter).where(Matter.workspace_id == workspace_id).order_by(Matter.updated_at.desc())
    )
    return page_query_response(db, matters, _format_matter, page=page, page_size=page_size, scalars=True)


@router.post("/{workspace_id}/matters", status_code=status.HTTP_201_CREATED)
async def create_matter(
    workspace_id: str,
    body: MatterIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    matter_status = _validate_matter_status(body.status)
    matter = Matter(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name.strip(),
        client_name=body.client_name.strip() if body.client_name else None,
        description=body.description,
        status=matter_status,
        created_by_user_id=user.id,
    )
    db.add(matter)
    db.flush()
    record_audit_event(db, action="matter.create", resource_type="matter", resource_id=matter.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(matter)
    return _format_matter(matter)


@router.get("/{workspace_id}/matters/{matter_id}")
async def get_matter(
    workspace_id: str,
    matter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return _format_matter(matter)


@router.put("/{workspace_id}/matters/{matter_id}")
async def update_matter(
    workspace_id: str,
    matter_id: str,
    body: MatterIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    matter.name = body.name.strip()
    matter.client_name = body.client_name.strip() if body.client_name else None
    matter.description = body.description
    matter.status = _validate_matter_status(body.status)
    matter.updated_at = utcnow()
    record_audit_event(db, action="matter.update", resource_type="matter", resource_id=matter.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(matter)
    return _format_matter(matter)


@router.delete("/{workspace_id}/matters/{matter_id}")
async def delete_matter(
    workspace_id: str,
    matter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    matter = db.execute(select(Matter).where(Matter.workspace_id == workspace_id, Matter.id == matter_id)).scalar_one_or_none()
    if not matter:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    db.execute(
        update(BlueprintInstance)
        .where(BlueprintInstance.workspace_id == workspace_id, BlueprintInstance.matter_id == matter_id)
        .values(matter_id=None, updated_at=utcnow())
    )
    db.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.workspace_id == workspace_id, KnowledgeDocument.matter_id == matter_id)
        .values(matter_id=None, updated_at=utcnow())
    )
    db.delete(matter)
    record_audit_event(db, action="matter.delete", resource_type="matter", resource_id=matter_id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    return {"ok": True}
