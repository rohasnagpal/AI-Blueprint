import uuid
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.bootstrap import DEFAULT_ADMIN_USERNAME
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.models import SessionToken, User, WorkspaceMember
from app.core.security import hash_password, hash_session_token, new_session_token, session_expiry, verify_password
router = APIRouter(prefix="/auth", tags=["auth"])


class SetupIn(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    email: str | None = None
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=12)


class LoginIn(BaseModel):
    identifier: str | None = None
    email: str | None = None
    password: str


class InitialCredentialsIn(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=12)


def _format_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username or user.email,
        "email": user.email,
        "display_name": user.display_name,
        "is_system_admin": user.is_system_admin,
        "must_change_credentials": user.must_change_credentials,
        "created_at": user.created_at.isoformat(),
    }


def _normalize_username(value: str) -> str:
    username = value.strip().lower()
    if len(username) < 3 or len(username) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be between 3 and 100 characters")
    if any(char.isspace() for char in username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username cannot contain spaces")
    return username


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


def _client_key(request: Request, identifier: str = "") -> str:
    settings = get_settings()
    forwarded_for = request.headers.get("x-forwarded-for", "") if settings.trust_proxy_headers else ""
    ip = forwarded_for.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
    return f"{ip}:{identifier.strip().lower()}"


def _ensure_auth_rate_limit_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS auth_rate_limit_attempts (
                client_key TEXT NOT NULL,
                attempted_at REAL NOT NULL
            )
            """
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_auth_rate_limit_attempts_key_time "
            "ON auth_rate_limit_attempts (client_key, attempted_at)"
        )
    )


def _check_auth_rate_limit(db: Session, request: Request, identifier: str = "") -> None:
    settings = get_settings()
    if settings.auth_rate_limit_attempts <= 0:
        return
    now = monotonic()
    window_start = now - settings.auth_rate_limit_window_seconds
    client_key = _client_key(request, identifier)
    _ensure_auth_rate_limit_table(db)
    db.execute(text("DELETE FROM auth_rate_limit_attempts WHERE attempted_at < :window_start"), {"window_start": window_start})
    attempt_count = db.execute(
        text(
            "SELECT COUNT(*) FROM auth_rate_limit_attempts "
            "WHERE client_key = :client_key AND attempted_at >= :window_start"
        ),
        {"client_key": client_key, "window_start": window_start},
    ).scalar_one()
    if attempt_count >= settings.auth_rate_limit_attempts:
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many authentication attempts")
    db.execute(
        text("INSERT INTO auth_rate_limit_attempts (client_key, attempted_at) VALUES (:client_key, :attempted_at)"),
        {"client_key": client_key, "attempted_at": now},
    )
    db.commit()


@router.get("/setup-state", include_in_schema=False)
async def setup_state(db: Session = Depends(get_db)):
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    return {"setup_required": user_count == 0}


@router.post("/setup")
async def setup_admin(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = body.username or body.email or ""
    username = _normalize_username(identifier)
    _check_auth_rate_limit(db, request, username)
    user_count = db.execute(select(func.count(User.id))).scalar_one()
    if user_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup has already been completed")
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=username,
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
async def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = (body.identifier or body.email or "").strip().lower()
    if not identifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or email is required")
    _check_auth_rate_limit(db, request, identifier)
    user = db.execute(select(User).where(or_(User.username == identifier, User.email == identifier))).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    _issue_session(db, response, user)
    record_audit_event(db, action="auth.login", resource_type="user", resource_id=user.id, user_id=user.id)
    db.commit()
    return {"user": _format_user(user)}


@router.post("/change-initial-credentials")
async def change_initial_credentials(
    body: InitialCredentialsIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    username = body.username.strip().lower()
    bootstrap_username = (get_settings().bootstrap_admin_username or DEFAULT_ADMIN_USERNAME).strip().lower()
    if username == bootstrap_username or body.password.strip().lower() == bootstrap_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose credentials different from the bootstrap defaults")
    existing = db.execute(select(User).where(User.username == username, User.id != user.id)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    email_existing = db.execute(select(User).where(User.email == username, User.id != user.id)).scalar_one_or_none()
    if email_existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username conflicts with an existing email")
    user.username = username
    if user.email == bootstrap_username:
        user.email = username
    user.display_name = body.display_name.strip()
    user.password_hash = hash_password(body.password)
    user.must_change_credentials = False
    db.query(SessionToken).filter(SessionToken.user_id == user.id).update({SessionToken.revoked_at: func.now()})
    _issue_session(db, response, user)
    record_audit_event(db, action="auth.change_initial_credentials", resource_type="user", resource_id=user.id, user_id=user.id)
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
