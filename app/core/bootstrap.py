import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import SessionLocal
from app.core.models import User
from app.core.security import hash_password


DEFAULT_ADMIN_USERNAME = "rohas"
DEFAULT_ADMIN_PASSWORD = "rohas"


def ensure_default_admin() -> None:
    with SessionLocal() as db:
        _ensure_default_admin(db)


def _ensure_default_admin(db: Session) -> None:
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    system_admin_count = db.execute(select(func.count(User.id)).where(User.is_system_admin == True)).scalar_one()
    if user_count and system_admin_count:
        return

    existing = db.execute(select(User).where(User.username == DEFAULT_ADMIN_USERNAME)).scalar_one_or_none()
    if existing:
        existing.is_system_admin = True
        existing.is_active = True
        existing.must_change_credentials = True
        db.commit()
        return

    user = User(
        id=str(uuid.uuid4()),
        username=DEFAULT_ADMIN_USERNAME,
        email=DEFAULT_ADMIN_USERNAME,
        display_name="Default Admin",
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        is_system_admin=True,
        must_change_credentials=True,
    )
    db.add(user)
    db.flush()
    record_audit_event(db, action="auth.bootstrap_default_admin", resource_type="user", resource_id=user.id, user_id=user.id)
    db.commit()
