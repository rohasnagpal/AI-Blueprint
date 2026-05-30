import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.models import Matter, User, Workspace, WorkspaceMember, utcnow
from app.core.security import hash_password


DEFAULT_ADMIN_USERNAME = "rohas"


def ensure_default_admin() -> None:
    with SessionLocal() as db:
        _ensure_default_admin(db)


def _ensure_default_admin(db: Session) -> None:
    settings = get_settings()
    username = (settings.bootstrap_admin_username or DEFAULT_ADMIN_USERNAME).strip().lower()
    if not settings.bootstrap_admin_password:
        raise RuntimeError("Bootstrap admin password is not configured")
    password = settings.bootstrap_admin_password
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    system_admin_count = db.execute(select(func.count(User.id)).where(User.is_system_admin == True)).scalar_one()
    if user_count and system_admin_count:
        admins = db.execute(select(User).where(User.is_system_admin == True, User.is_active == True)).scalars().all()
        for admin in admins:
            _ensure_default_workspace_and_matter(db, admin)
        db.commit()
        return

    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing:
        existing.is_system_admin = True
        existing.is_active = True
        existing.must_change_credentials = True
        _ensure_default_workspace_and_matter(db, existing)
        db.commit()
        return

    user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=username,
        display_name="Default Admin",
        password_hash=hash_password(password),
        is_system_admin=True,
        must_change_credentials=True,
    )
    db.add(user)
    db.flush()
    record_audit_event(db, action="auth.bootstrap_default_admin", resource_type="user", resource_id=user.id, user_id=user.id)
    _ensure_default_workspace_and_matter(db, user)
    db.commit()


def _ensure_default_workspace_and_matter(db: Session, user: User) -> None:
    workspace = db.execute(
        select(Workspace).where(
            Workspace.slug == "default-workspace",
            Workspace.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    membership = (
        db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id,
            )
        ).scalar_one_or_none()
        if workspace
        else None
    )
    now = utcnow()
    if not workspace:
        workspace = Workspace(
            id=str(uuid.uuid4()),
            name="Default Workspace",
            slug="default-workspace",
            created_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role="admin"))
        record_audit_event(
            db,
            action="workspace.create_default",
            resource_type="workspace",
            resource_id=workspace.id,
            user_id=user.id,
            workspace_id=workspace.id,
        )
    elif not membership:
        db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role="admin"))
    matter = db.execute(
        select(Matter).where(Matter.workspace_id == workspace.id, Matter.name == "Default Matter")
    ).scalar_one_or_none()
    if not matter:
        matter = Matter(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            name="Default Matter",
            status="active",
            created_by_user_id=user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(matter)
        db.flush()
        record_audit_event(
            db,
            action="matter.create_default",
            resource_type="matter",
            resource_id=matter.id,
            user_id=user.id,
            workspace_id=workspace.id,
        )
