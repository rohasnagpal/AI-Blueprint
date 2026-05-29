from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.models import User, Workspace, WorkspaceMember
from app.core.pagination import page_query_response

router = APIRouter(prefix="/me", tags=["navigation"])


def _workspace_nav(workspace: Workspace, role: str) -> dict:
    items = [
        {"id": "matters", "label": "Matters", "href": f"/workspaces/{workspace.id}/matters"},
        {"id": "knowledge", "label": "Knowledge", "href": f"/workspaces/{workspace.id}/documents"},
        {"id": "skills", "label": "Skills", "href": f"/workspaces/{workspace.id}/skills"},
    ]
    if role == "admin":
        items.extend(
            [
                {"id": "personas", "label": "Personas", "href": f"/workspaces/{workspace.id}/personas"},
                {"id": "admin", "label": "Admin", "href": f"/workspaces/{workspace.id}/admin"},
            ]
        )
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "role": role,
        "items": items,
    }


@router.get("/navigation")
async def navigation(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id, Workspace.deleted_at.is_(None))
        .order_by(Workspace.name)
    )
    return page_query_response(db, rows, lambda row: _workspace_nav(row[0], row[1]), page=page, page_size=page_size)
