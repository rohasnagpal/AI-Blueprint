from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.models import BlueprintInstance, BlueprintMember, Plugin, PluginEnablement, SessionToken, User, Workspace, WorkspaceMember
from app.core.security import hash_session_token


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> User:
    public = getattr(request.scope.get("route"), "include_in_schema", True) is False
    if public:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    row = db.execute(
        select(SessionToken, User)
        .join(User, User.id == SessionToken.user_id)
        .where(SessionToken.token_hash == hash_session_token(session_cookie))
    ).first()
    now = datetime.now(timezone.utc)
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    session, user = row
    if session.revoked_at or _as_aware(session.expires_at) <= now or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    if user.must_change_credentials and request.url.path not in {
        "/api/v2/auth/me",
        "/api/v2/auth/logout",
        "/api/v2/auth/change-initial-credentials",
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Credential reset required")
    return user


def require_system_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_system_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System admin access required")
    return user


def require_workspace_member(workspace_id: str, user: User, db: Session) -> WorkspaceMember:
    row = db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    membership, workspace = row
    if workspace.deleted_at:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return membership


def require_workspace_admin(workspace_id: str, user: User, db: Session) -> WorkspaceMember:
    membership = require_workspace_member(workspace_id, user, db)
    if membership.role != "admin" and not user.is_system_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace admin access required")
    return membership


def require_plugin_enabled(workspace_id: str, plugin_id: str, db: Session) -> Plugin:
    row = db.execute(
        select(Plugin, PluginEnablement)
        .join(PluginEnablement, PluginEnablement.plugin_id == Plugin.id)
        .where(
            Plugin.id == plugin_id,
            Plugin.is_enabled == True,
            PluginEnablement.workspace_id == workspace_id,
            PluginEnablement.is_enabled == True,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Plugin is not enabled for this workspace")
    plugin, _enablement = row
    return plugin


def require_blueprint_member(workspace_id: str, blueprint_id: str, user: User, db: Session) -> tuple[BlueprintInstance, BlueprintMember]:
    row = db.execute(
        select(BlueprintInstance, BlueprintMember)
        .join(BlueprintMember, BlueprintMember.blueprint_id == BlueprintInstance.id)
        .where(
            BlueprintInstance.workspace_id == workspace_id,
            BlueprintInstance.id == blueprint_id,
            BlueprintMember.user_id == user.id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint access denied")
    return row
