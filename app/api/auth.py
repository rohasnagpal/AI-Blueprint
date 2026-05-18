import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.models import SessionToken, User, WorkspaceMember
from app.core.security import hash_password, hash_session_token, new_session_token, session_expiry, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupIn(BaseModel):
    email: str
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=12)


class LoginIn(BaseModel):
    email: str
    password: str


def _format_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "is_system_admin": user.is_system_admin,
        "created_at": user.created_at.isoformat(),
    }


def _issue_session(db: Session, response: Response, user: User) -> None:
    raw_token = new_session_token()
    db.add(
        SessionToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=session_expiry(),
        )
    )
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )


@router.get("/setup-state", include_in_schema=False)
async def setup_state(db: Session = Depends(get_db)):
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    return {"setup_required": user_count == 0}


@router.post("/setup")
async def setup_admin(body: SetupIn, response: Response, db: Session = Depends(get_db)):
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    if user_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup has already been completed")
    user = User(
        id=str(uuid.uuid4()),
        email=body.email.strip().lower(),
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        is_system_admin=True,
    )
    db.add(user)
    db.flush()
    record_audit_event(db, action="auth.setup_admin", resource_type="user", resource_id=user.id, user_id=user.id)
    _issue_session(db, response, user)
    db.commit()
    return {"user": _format_user(user)}


@router.post("/login")
async def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.strip().lower())).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    _issue_session(db, response, user)
    record_audit_event(db, action="auth.login", resource_type="user", resource_id=user.id, user_id=user.id)
    db.commit()
    return {"user": _format_user(user)}


@router.post("/logout")
async def logout(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(SessionToken).filter(SessionToken.user_id == user.id).update({SessionToken.revoked_at: func.now()})
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    record_audit_event(db, action="auth.logout", resource_type="user", resource_id=user.id, user_id=user.id)
    db.commit()
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).scalars().all()
    return {
        "user": _format_user(user),
        "workspace_memberships": [
            {"workspace_id": membership.workspace_id, "role": membership.role}
            for membership in memberships
        ],
    }
