import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.models import Secret, User, utcnow
from app.core.pagination import page_query_response
from app.core.secrets import encrypt_secret
from app.core.validation import validate_choice

router = APIRouter(prefix="/workspaces/{workspace_id}/secrets", tags=["secrets"])


class SecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1)
    scope: str = "workspace"


class SecretRotateIn(BaseModel):
    value: str = Field(min_length=1)


def _format_secret(secret: Secret) -> dict:
    return {
        "id": secret.id,
        "workspace_id": secret.workspace_id,
        "owner_user_id": secret.owner_user_id,
        "name": secret.name,
        "scope": secret.scope,
        "status": secret.status,
        "created_by_user_id": secret.created_by_user_id,
        "created_at": secret.created_at.isoformat(),
        "updated_at": secret.updated_at.isoformat(),
        "revoked_at": secret.revoked_at.isoformat() if secret.revoked_at else None,
        "has_value": bool(secret.encrypted_value),
    }


def _validate_scope(scope: str) -> str:
    return validate_choice(scope, {"user", "workspace", "admin"}, "secret scope")


def _authorize_scope(workspace_id: str, scope: str, user: User, db: Session) -> None:
    if scope in {"workspace", "admin"}:
        require_workspace_admin(workspace_id, user, db)
    else:
        require_workspace_member(workspace_id, user, db)


def _query_visible(workspace_id: str, user: User, db: Session):
    require_workspace_member(workspace_id, user, db)
    query = select(Secret).where(Secret.workspace_id == workspace_id)
    if not user.is_system_admin:
        query = query.where(
            (Secret.scope == "workspace")
            | ((Secret.scope == "user") & (Secret.owner_user_id == user.id))
        )
    return query


@router.get("")
async def list_secrets(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secrets = _query_visible(workspace_id, user, db).order_by(Secret.name)
    return page_query_response(db, secrets, _format_secret, page=page, page_size=page_size, scalars=True)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_secret(workspace_id: str, body: SecretIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = _validate_scope(body.scope)
    _authorize_scope(workspace_id, scope, user, db)
    owner_user_id = user.id if scope == "user" else None
    existing = db.execute(
        select(Secret).where(
            Secret.workspace_id == workspace_id,
            Secret.owner_user_id == owner_user_id,
            Secret.name == body.name.strip(),
            Secret.scope == scope,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Secret already exists")
    secret = Secret(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        name=body.name.strip(),
        encrypted_value=encrypt_secret(body.value),
        scope=scope,
        status="active",
        created_by_user_id=user.id,
    )
    db.add(secret)
    db.flush()
    record_audit_event(db, action="secret.create", resource_type="secret", resource_id=secret.id, user_id=user.id, workspace_id=workspace_id, metadata={"scope": scope, "name": secret.name})
    db.commit()
    db.refresh(secret)
    return _format_secret(secret)


@router.put("/{secret_id}/rotate")
async def rotate_secret(workspace_id: str, secret_id: str, body: SecretRotateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = db.execute(_query_visible(workspace_id, user, db).where(Secret.id == secret_id)).scalar_one_or_none()
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    _authorize_scope(workspace_id, secret.scope, user, db)
    secret.encrypted_value = encrypt_secret(body.value)
    secret.status = "active"
    secret.revoked_at = None
    secret.updated_at = utcnow()
    record_audit_event(db, action="secret.rotate", resource_type="secret", resource_id=secret.id, user_id=user.id, workspace_id=workspace_id, metadata={"scope": secret.scope, "name": secret.name})
    db.commit()
    db.refresh(secret)
    return _format_secret(secret)


@router.delete("/{secret_id}")
async def revoke_secret(workspace_id: str, secret_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = db.execute(_query_visible(workspace_id, user, db).where(Secret.id == secret_id)).scalar_one_or_none()
    if not secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    _authorize_scope(workspace_id, secret.scope, user, db)
    secret.status = "revoked"
    secret.revoked_at = utcnow()
    secret.updated_at = utcnow()
    record_audit_event(db, action="secret.revoke", resource_type="secret", resource_id=secret.id, user_id=user.id, workspace_id=workspace_id, metadata={"scope": secret.scope, "name": secret.name})
    db.commit()
    return {"ok": True}
