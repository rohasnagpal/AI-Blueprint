from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin
from app.core.json_utils import json_loads
from app.core.models import AuditEvent, User
from app.core.pagination import page_query_response

router = APIRouter(prefix="/workspaces/{workspace_id}/audit-events", tags=["audit"])


def _format_event(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "workspace_id": event.workspace_id,
        "user_id": event.user_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "metadata": json_loads(event.metadata_json, {}),
        "created_at": event.created_at.isoformat(),
    }


@router.get("")
async def list_audit_events(
    workspace_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    query = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if resource_type:
        query = query.where(AuditEvent.resource_type == resource_type)

    return page_query_response(db, query.order_by(AuditEvent.created_at.desc()), _format_event, page=page, page_size=page_size, scalars=True)
