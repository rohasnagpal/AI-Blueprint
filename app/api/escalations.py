from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member, require_workspace_admin, require_workspace_member
from app.core.json_utils import json_loads
from app.core.models import BlueprintMember, Escalation, User, utcnow
from app.core.pagination import page_query_response
from app.core.validation import validate_choice

router = APIRouter(prefix="/workspaces/{workspace_id}/escalations", tags=["escalations"])


def _format_escalation(escalation: Escalation) -> dict:
    return {
        "id": escalation.id,
        "workspace_id": escalation.workspace_id,
        "blueprint_id": escalation.blueprint_id,
        "source_type": escalation.source_type,
        "source_id": escalation.source_id,
        "severity": escalation.severity,
        "status": escalation.status,
        "reason": escalation.reason,
        "required_action": escalation.required_action,
        "metadata": json_loads(escalation.metadata_json, {}),
        "created_by_user_id": escalation.created_by_user_id,
        "resolved_by_user_id": escalation.resolved_by_user_id,
        "created_at": escalation.created_at.isoformat(),
        "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
    }


@router.get("")
async def list_escalations(
    workspace_id: str,
    status_filter: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_member(workspace_id, user, db)
    permitted_blueprint_ids = db.execute(
        select(BlueprintMember.blueprint_id).where(BlueprintMember.user_id == user.id)
    ).scalars().all()
    query = select(Escalation).where(Escalation.workspace_id == workspace_id)
    if status_filter:
        status_filter = validate_choice(status_filter, {"open", "resolved", "dismissed"}, "escalation status")
        query = query.where(Escalation.status == status_filter)
    visibility_filters = [Escalation.blueprint_id.is_(None)]
    if permitted_blueprint_ids:
        visibility_filters.append(Escalation.blueprint_id.in_(permitted_blueprint_ids))
    query = query.where(or_(*visibility_filters)).order_by(Escalation.created_at.desc())
    return page_query_response(db, query, _format_escalation, page=page, page_size=page_size, scalars=True)


@router.get("/blueprints/{blueprint_id}")
async def list_blueprint_escalations(
    workspace_id: str,
    blueprint_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_blueprint_member(workspace_id, blueprint_id, user, db)
    escalations = (
        select(Escalation)
        .where(Escalation.workspace_id == workspace_id, Escalation.blueprint_id == blueprint_id)
        .order_by(Escalation.created_at.desc())
    )
    return page_query_response(db, escalations, _format_escalation, page=page, page_size=page_size, scalars=True)


@router.put("/{escalation_id}/resolve")
async def resolve_escalation(
    workspace_id: str,
    escalation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    escalation = db.execute(
        select(Escalation).where(Escalation.workspace_id == workspace_id, Escalation.id == escalation_id)
    ).scalar_one_or_none()
    if not escalation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found")
    if escalation.status == "resolved":
        return _format_escalation(escalation)
    escalation.status = "resolved"
    escalation.resolved_by_user_id = user.id
    escalation.resolved_at = utcnow()
    record_audit_event(db, action="escalation.resolve", resource_type="escalation", resource_id=escalation.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": escalation.blueprint_id})
    db.commit()
    db.refresh(escalation)
    return _format_escalation(escalation)


@router.put("/{escalation_id}/dismiss")
async def dismiss_escalation(
    workspace_id: str,
    escalation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_admin(workspace_id, user, db)
    escalation = db.execute(
        select(Escalation).where(Escalation.workspace_id == workspace_id, Escalation.id == escalation_id)
    ).scalar_one_or_none()
    if not escalation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found")
    if escalation.status == "dismissed":
        return _format_escalation(escalation)
    escalation.status = "dismissed"
    escalation.resolved_by_user_id = user.id
    escalation.resolved_at = utcnow()
    record_audit_event(db, action="escalation.dismiss", resource_type="escalation", resource_id=escalation.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": escalation.blueprint_id})
    db.commit()
    db.refresh(escalation)
    return _format_escalation(escalation)
