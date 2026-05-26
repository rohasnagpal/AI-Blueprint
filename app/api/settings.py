import json
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.json_utils import json_loads
from app.core.models import RuntimeSetting, User, utcnow
from app.core.pagination import page_response

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    value_type: str
    default: Any
    description: str


SETTING_DEFINITIONS = {
    "default_jurisdiction": SettingDefinition("default_jurisdiction", "string", "unspecified", "Default jurisdiction label for legal workflows."),
    "citation_style": SettingDefinition("citation_style", "string", "neutral", "Citation style label used in generated legal outputs."),
    "client_output_tone": SettingDefinition("client_output_tone", "string", "plain_english", "Default tone for client-facing summaries."),
    "require_human_approval_for_external_send": SettingDefinition("require_human_approval_for_external_send", "boolean", True, "Require approval before external communication."),
    "max_upload_size_mb": SettingDefinition("max_upload_size_mb", "integer", 25, "Workspace upload size limit in megabytes."),
}


class SettingUpdateIn(BaseModel):
    value: Any


def _coerce_value(definition: SettingDefinition, value: Any) -> Any:
    if definition.value_type == "string":
        if not isinstance(value, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setting value must be a string")
        return value
    if definition.value_type == "boolean":
        if not isinstance(value, bool):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setting value must be a boolean")
        return value
    if definition.value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setting value must be an integer")
        return value
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported setting type")


def _format_setting(key: str, setting: RuntimeSetting | None = None) -> dict:
    definition = SETTING_DEFINITIONS[key]
    value = json_loads(setting.value_json, definition.default) if setting else definition.default
    return {
        "key": key,
        "value": value,
        "value_type": definition.value_type,
        "description": definition.description,
        "is_default": setting is None,
        "updated_by_user_id": setting.updated_by_user_id if setting else None,
        "updated_at": setting.updated_at.isoformat() if setting else None,
    }


@router.get("")
async def list_settings(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    rows = db.execute(select(RuntimeSetting).where(RuntimeSetting.workspace_id == workspace_id)).scalars().all()
    by_key = {row.key: row for row in rows}
    items = [_format_setting(key, by_key.get(key)) for key in SETTING_DEFINITIONS]
    return page_response(items, page=page, page_size=page_size)


@router.put("/{key}")
async def update_setting(
    workspace_id: str,
    key: str,
    body: SettingUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    definition = SETTING_DEFINITIONS.get(key)
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting is not allowlisted")
    value = _coerce_value(definition, body.value)
    setting = db.execute(
        select(RuntimeSetting).where(RuntimeSetting.workspace_id == workspace_id, RuntimeSetting.key == key)
    ).scalar_one_or_none()
    if not setting:
        setting = RuntimeSetting(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            key=key,
            value_json=json.dumps(value),
            value_type=definition.value_type,
            updated_by_user_id=user.id,
        )
        db.add(setting)
    else:
        setting.value_json = json.dumps(value)
        setting.value_type = definition.value_type
        setting.updated_by_user_id = user.id
        setting.updated_at = utcnow()
    record_audit_event(db, action="setting.update", resource_type="runtime_setting", resource_id=key, user_id=user.id, workspace_id=workspace_id, metadata={"key": key})
    db.commit()
    db.refresh(setting)
    return _format_setting(key, setting)
