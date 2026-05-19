import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.database import get_db
from app.core.deps import get_current_user, require_blueprint_member, require_workspace_admin, require_workspace_member
from app.core.models import BlueprintPersona, Persona, User, utcnow
from app.core.pagination import page_response

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


class BlueprintPersonaIn(BaseModel):
    persona_id: str
    role: str = "participant"


def _json_loads(value: str, fallback):
    try:
        data = json.loads(value)
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback


def _format_persona(persona: Persona) -> dict:
    return {
        "id": persona.id,
        "workspace_id": persona.workspace_id,
        "name": persona.name,
        "category": persona.category,
        "description": persona.description,
        "system_prompt": persona.system_prompt,
        "constraints": _json_loads(persona.constraints_json, []),
        "output_format": _json_loads(persona.output_format_json, {}),
        "tags": _json_loads(persona.tags_json, []),
        "is_builtin": persona.is_builtin,
        "is_enabled": persona.is_enabled,
        "created_by_user_id": persona.created_by_user_id,
        "created_at": persona.created_at.isoformat(),
        "updated_at": persona.updated_at.isoformat(),
    }


def _format_blueprint_persona(link: BlueprintPersona, persona: Persona) -> dict:
    return {
        "id": link.id,
        "workspace_id": link.workspace_id,
        "blueprint_id": link.blueprint_id,
        "persona_id": link.persona_id,
        "role": link.role,
        "created_by_user_id": link.created_by_user_id,
        "created_at": link.created_at.isoformat(),
        "persona": _format_persona(persona),
    }


def _persona_visible_query(workspace_id: str):
    return select(Persona).where(
        Persona.is_enabled == True,
        or_(Persona.workspace_id == workspace_id, Persona.workspace_id.is_(None)),
    )


def _get_visible_persona(db: Session, workspace_id: str, persona_id: str) -> Persona:
    persona = db.execute(_persona_visible_query(workspace_id).where(Persona.id == persona_id)).scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    return persona


def _require_blueprint_editor(workspace_id: str, blueprint_id: str, user: User, db: Session):
    blueprint, membership = require_blueprint_member(workspace_id, blueprint_id, user, db)
    if membership.role not in {"owner", "editor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blueprint edit access required")
    return blueprint, membership


@router.get("/workspaces/{workspace_id}/personas")
async def list_personas(workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace_member(workspace_id, user, db)
    personas = db.execute(_persona_visible_query(workspace_id).order_by(Persona.category, Persona.name)).scalars().all()
    return page_response(personas, _format_persona, page=page, page_size=page_size)


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
    links = db.execute(select(BlueprintPersona).where(BlueprintPersona.workspace_id == workspace_id, BlueprintPersona.persona_id == persona_id)).scalars().all()
    for link in links:
        db.delete(link)
    db.delete(persona)
    record_audit_event(
        db,
        action="persona.delete",
        resource_type="persona",
        resource_id=persona_id,
        user_id=user.id,
        workspace_id=workspace_id,
        metadata={"link_count": len(links)},
    )
    db.commit()
    return {"ok": True}


@router.get("/workspaces/{workspace_id}/blueprints/{blueprint_id}/personas")
async def list_blueprint_personas(workspace_id: str, blueprint_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_blueprint_member(workspace_id, blueprint_id, user, db)
    rows = db.execute(
        select(BlueprintPersona, Persona)
        .join(Persona, Persona.id == BlueprintPersona.persona_id)
        .where(BlueprintPersona.workspace_id == workspace_id, BlueprintPersona.blueprint_id == blueprint_id)
        .order_by(BlueprintPersona.role, Persona.name)
    ).all()
    return page_response(rows, lambda row: _format_blueprint_persona(row[0], row[1]), page=page, page_size=page_size)


@router.post("/workspaces/{workspace_id}/blueprints/{blueprint_id}/personas", status_code=status.HTTP_201_CREATED)
async def link_blueprint_persona(
    workspace_id: str,
    blueprint_id: str,
    body: BlueprintPersonaIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_blueprint_editor(workspace_id, blueprint_id, user, db)
    persona = _get_visible_persona(db, workspace_id, body.persona_id)
    role = body.role.strip() or "participant"
    existing = db.execute(
        select(BlueprintPersona).where(
            BlueprintPersona.workspace_id == workspace_id,
            BlueprintPersona.blueprint_id == blueprint_id,
            BlueprintPersona.persona_id == body.persona_id,
            BlueprintPersona.role == role,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Persona is already linked to this blueprint role")
    link = BlueprintPersona(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        persona_id=persona.id,
        role=role,
        created_by_user_id=user.id,
    )
    db.add(link)
    db.flush()
    record_audit_event(db, action="blueprint.persona.link", resource_type="blueprint_persona", resource_id=link.id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id, "persona_id": persona.id, "role": role})
    db.commit()
    db.refresh(link)
    return _format_blueprint_persona(link, persona)


@router.delete("/workspaces/{workspace_id}/blueprints/{blueprint_id}/personas/{link_id}")
async def unlink_blueprint_persona(
    workspace_id: str,
    blueprint_id: str,
    link_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_blueprint_editor(workspace_id, blueprint_id, user, db)
    link = db.execute(
        select(BlueprintPersona).where(
            BlueprintPersona.workspace_id == workspace_id,
            BlueprintPersona.blueprint_id == blueprint_id,
            BlueprintPersona.id == link_id,
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint persona link not found")
    db.delete(link)
    record_audit_event(db, action="blueprint.persona.unlink", resource_type="blueprint_persona", resource_id=link_id, user_id=user.id, workspace_id=workspace_id, metadata={"blueprint_id": blueprint_id, "persona_id": link.persona_id})
    db.commit()
    return {"ok": True}
