import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_admin, require_workspace_member
from app.core.json_utils import json_loads
from app.core.models import Persona, User, utcnow
from app.core.pagination import page_query_response

router = APIRouter(tags=["personas"])


class PersonaIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = "Legal"
    description: str = ""
    system_prompt: str = Field(min_length=1)
    constraints: list[str] = []
    output_format: dict = {}
    tags: list[str] = []
    is_enabled: bool = True


def _format_persona(persona: Persona) -> dict:
    return {
        "id": persona.id,
        "workspace_id": persona.workspace_id,
        "name": persona.name,
        "category": persona.category,
        "description": persona.description,
        "system_prompt": persona.system_prompt,
        "constraints": json_loads(persona.constraints_json, []),
        "output_format": json_loads(persona.output_format_json, {}),
        "tags": json_loads(persona.tags_json, []),
        "is_builtin": persona.is_builtin,
        "is_enabled": persona.is_enabled,
        "created_by_user_id": persona.created_by_user_id,
        "created_at": persona.created_at.isoformat(),
        "updated_at": persona.updated_at.isoformat(),
    }


def _persona_visible_query(workspace_id: str):
    return select(Persona).where(
        Persona.is_enabled == True,
        or_(Persona.workspace_id == workspace_id, Persona.workspace_id.is_(None)),
    )


@router.get("/workspaces/{workspace_id}/personas")
async def list_personas(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    personas = _persona_visible_query(workspace_id).order_by(Persona.category, Persona.name)
    return page_query_response(db, personas, _format_persona, page=page, page_size=page_size, scalars=True)


@router.post("/workspaces/{workspace_id}/personas", status_code=status.HTTP_201_CREATED)
async def create_persona(workspace_id: str, body: PersonaIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_admin(workspace_id, user, db)
    name = body.name.strip()
    existing = db.execute(select(Persona).where(Persona.workspace_id == workspace_id, Persona.name == name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Persona already exists")
    persona = Persona(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=name,
        category=body.category.strip() or "Legal",
        description=body.description,
        system_prompt=body.system_prompt,
        constraints_json=json.dumps(body.constraints),
        output_format_json=json.dumps(body.output_format),
        tags_json=json.dumps(body.tags),
        is_builtin=False,
        is_enabled=body.is_enabled,
        created_by_user_id=user.id,
    )
    db.add(persona)
    db.flush()
    record_audit_event(db, action="persona.create", resource_type="persona", resource_id=persona.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(persona)
    return _format_persona(persona)


@router.put("/workspaces/{workspace_id}/personas/{persona_id}")
async def update_persona(workspace_id: str, persona_id: str, body: PersonaIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_admin(workspace_id, user, db)
    persona = db.execute(select(Persona).where(Persona.workspace_id == workspace_id, Persona.id == persona_id)).scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    persona.name = body.name.strip()
    persona.category = body.category.strip() or "Legal"
    persona.description = body.description
    persona.system_prompt = body.system_prompt
    persona.constraints_json = json.dumps(body.constraints)
    persona.output_format_json = json.dumps(body.output_format)
    persona.tags_json = json.dumps(body.tags)
    persona.is_enabled = body.is_enabled
    persona.updated_at = utcnow()
    record_audit_event(db, action="persona.update", resource_type="persona", resource_id=persona.id, user_id=user.id, workspace_id=workspace_id)
    db.commit()
    db.refresh(persona)
    return _format_persona(persona)


@router.delete("/workspaces/{workspace_id}/personas/{persona_id}")
async def delete_persona(workspace_id: str, persona_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_admin(workspace_id, user, db)
    persona = db.execute(select(Persona).where(Persona.workspace_id == workspace_id, Persona.id == persona_id)).scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    db.delete(persona)
    record_audit_event(
        db,
        action="persona.delete",
        resource_type="persona",
        resource_id=persona_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={},
    )
    db.commit()
    return {"ok": True}
