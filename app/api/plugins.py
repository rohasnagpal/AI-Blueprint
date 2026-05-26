import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.models import Plugin, PluginEnablement, User
from app.core.pagination import page_query_response

router = APIRouter(tags=["plugins"])


class PluginEnablementIn(BaseModel):
    enabled: bool = True


def _format_plugin(plugin: Plugin, workspace_enabled: bool | None = None) -> dict:
    try:
        manifest = json.loads(plugin.manifest_json)
    except Exception:
        manifest = {}
    data = {
        "id": plugin.id,
        "name": plugin.name,
        "description": plugin.description,
        "version": plugin.version,
        "is_enabled": plugin.is_enabled,
        "manifest": manifest,
    }
    if workspace_enabled is not None:
        data["workspace_enabled"] = workspace_enabled
    return data


@router.get("/plugins")
async def list_global_plugins(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_system_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System admin access required")
    plugins = select(Plugin).order_by(Plugin.name)
    return page_query_response(db, plugins, _format_plugin, page=page, page_size=page_size, scalars=True)


@router.get("/workspaces/{workspace_id}/plugins")
async def list_workspace_plugins(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    rows = (
        select(Plugin, PluginEnablement)
        .outerjoin(
            PluginEnablement,
            (PluginEnablement.plugin_id == Plugin.id) & (PluginEnablement.workspace_id == workspace_id),
        )
        .where(Plugin.is_enabled == True)
        .order_by(Plugin.name)
    )
    return page_query_response(
        db,
        rows,
        lambda row: _format_plugin(row[0], bool(row[1] and row[1].is_enabled)),
        page=page,
        page_size=page_size,
    )


@router.put("/workspaces/{workspace_id}/plugins/{plugin_id}")
async def set_workspace_plugin(
    workspace_id: str,
    plugin_id: str,
    body: PluginEnablementIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    plugin = db.get(Plugin, plugin_id)
    if not plugin or not plugin.is_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    enablement = db.execute(
        select(PluginEnablement).where(
            PluginEnablement.workspace_id == workspace_id,
            PluginEnablement.plugin_id == plugin_id,
        )
    ).scalar_one_or_none()
    if not enablement:
        enablement = PluginEnablement(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            plugin_id=plugin_id,
            enabled_by_user_id=user.id,
            is_enabled=body.enabled,
        )
        db.add(enablement)
    else:
        enablement.is_enabled = body.enabled
        enablement.enabled_by_user_id = user.id
    db.flush()
    action = "plugin.enable" if body.enabled else "plugin.disable"
    record_audit_event(db, action=action, resource_type="plugin", resource_id=plugin_id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    return _format_plugin(plugin, enablement.is_enabled)
