import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import require_system_admin
from app.core.models import SessionToken, User, Workspace, WorkspaceMember, utcnow
from app.core.security import hash_password
from app.core.validation import normalize_email, validate_choice

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserIn(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=8)
    email: str | None = None
    is_system_admin: bool = False
    is_active: bool = True
    workspace_id: str | None = None
    workspace_role: str = "member"


class AdminUserUpdateIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    display_name: str | None = Field(default=None, min_length=1)
    email: str | None = None
    is_system_admin: bool | None = None
    is_active: bool | None = None
    must_change_credentials: bool | None = None


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=8)
    must_change_credentials: bool = False


class MembershipIn(BaseModel):
    workspace_id: str
    role: str = "member"


def _normalize_username(value: str) -> str:
    return value.strip().lower()


def _validate_role(role: str) -> str:
    return validate_choice(role, {"admin", "member"}, "workspace role")


def _format_user(user: User, memberships: list[WorkspaceMember] | None = None, workspaces: dict[str, Workspace] | None = None) -> dict:
    workspaces = workspaces or {}
    return {
        "id": user.id,
        "username": user.username or user.email,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "is_system_admin": user.is_system_admin,
        "must_change_credentials": user.must_change_credentials,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
        "memberships": [
            {
                "id": membership.id,
                "workspace_id": membership.workspace_id,
                "workspace_name": workspaces.get(membership.workspace_id).name if workspaces.get(membership.workspace_id) else membership.workspace_id,
                "role": membership.role,
                "created_at": membership.created_at.isoformat(),
            }
            for membership in (memberships or [])
        ],
    }


def _user_lookup(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _ensure_unique_identity(db: Session, username: str, email: str, user_id: str | None = None) -> None:
    conditions = [
        User.username == username,
        User.email == username,
        User.email == email,
        User.username == email,
    ]
    query = select(User).where(or_(*conditions))
    if user_id:
        query = query.where(User.id != user_id)
    existing = db.execute(
        query
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists")


def _ensure_not_last_admin(db: Session, user: User) -> None:
    if not user.is_system_admin:
        return
    admin_count = db.execute(select(func.count(User.id)).where(User.is_system_admin == True, User.is_active == True)).scalar_one()
    if admin_count <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last active system admin")


@router.get("/workspaces")
async def list_admin_workspaces(
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.name)).scalars().all()
    return {
        "items": [
            {"id": workspace.id, "name": workspace.name, "slug": workspace.slug}
            for workspace in rows
        ]
    }


@router.get("/users")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    total = db.execute(select(func.count(User.id))).scalar_one()
    users = db.execute(
        select(User)
        .order_by(User.display_name, User.username)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).scalars().all()
    user_ids = [user.id for user in users]
    memberships = []
    workspaces = {}
    if user_ids:
        memberships = db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id.in_(user_ids))).scalars().all()
        workspace_ids = {membership.workspace_id for membership in memberships}
        if workspace_ids:
            workspaces = {
                workspace.id: workspace
                for workspace in db.execute(select(Workspace).where(Workspace.id.in_(workspace_ids))).scalars().all()
            }
    by_user: dict[str, list[WorkspaceMember]] = {}
    for membership in memberships:
        by_user.setdefault(membership.user_id, []).append(membership)
    return {
        "items": [_format_user(user, by_user.get(user.id, []), workspaces) for user in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: AdminUserIn,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    username = _normalize_username(body.username)
    email = normalize_email(body.email) if body.email else username
    _ensure_unique_identity(db, username, email)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        is_active=body.is_active,
        is_system_admin=body.is_system_admin,
        must_change_credentials=False,
    )
    db.add(user)
    db.flush()
    if body.workspace_id:
        workspace = db.get(Workspace, body.workspace_id)
        if not workspace or workspace.deleted_at:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role=_validate_role(body.workspace_role)))
    record_audit_event(db, action="admin.user.create", resource_type="user", resource_id=user.id, user_id=admin.id)
    db.commit()
    return _format_user(user)


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    body: AdminUserUpdateIn,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    user = _user_lookup(db, user_id)
    if body.is_active is False or body.is_system_admin is False:
        _ensure_not_last_admin(db, user)
    if body.username is not None:
        username = _normalize_username(body.username)
        email = normalize_email(body.email) if body.email is not None else user.email
        _ensure_unique_identity(db, username, email, user.id)
        user.username = username
    if body.email is not None:
        email = normalize_email(body.email or user.username or "")
        _ensure_unique_identity(db, user.username or email, email, user.id)
        user.email = email
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.is_system_admin is not None:
        user.is_system_admin = body.is_system_admin
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.must_change_credentials is not None:
        user.must_change_credentials = body.must_change_credentials
    user.updated_at = utcnow()
    record_audit_event(db, action="admin.user.update", resource_type="user", resource_id=user.id, user_id=admin.id)
    db.commit()
    return _format_user(user)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    body: PasswordResetIn,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    user = _user_lookup(db, user_id)
    user.password_hash = hash_password(body.password)
    user.must_change_credentials = body.must_change_credentials
    user.updated_at = utcnow()
    db.query(SessionToken).filter(SessionToken.user_id == user.id).update({SessionToken.revoked_at: func.now()})
    record_audit_event(db, action="admin.user.reset_password", resource_type="user", resource_id=user.id, user_id=admin.id)
    db.commit()
    return {"ok": True, "user": _format_user(user)}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    user = _user_lookup(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own user")
    _ensure_not_last_admin(db, user)
    db.delete(user)
    record_audit_event(db, action="admin.user.delete", resource_type="user", resource_id=user.id, user_id=admin.id)
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/memberships", status_code=status.HTTP_201_CREATED)
async def add_user_membership(
    user_id: str,
    body: MembershipIn,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    user = _user_lookup(db, user_id)
    workspace = db.get(Workspace, body.workspace_id)
    if not workspace or workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    existing = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id, WorkspaceMember.workspace_id == workspace.id)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a workspace member")
    membership = WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role=_validate_role(body.role))
    db.add(membership)
    record_audit_event(db, action="admin.user.membership.add", resource_type="workspace_member", resource_id=membership.id, user_id=admin.id, workspace_id=workspace.id, metadata={"member_user_id": user.id})
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/memberships/{workspace_id}")
async def remove_user_membership(
    user_id: str,
    workspace_id: str,
    admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    membership = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user_id, WorkspaceMember.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace membership not found")
    membership_id = membership.id
    db.delete(membership)
    record_audit_event(db, action="admin.user.membership.remove", resource_type="workspace_member", resource_id=membership_id, user_id=admin.id, workspace_id=workspace_id, metadata={"member_user_id": user_id})
    db.commit()
    return {"ok": True}
