import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import database

router = APIRouter()


class PersonaIn(BaseModel):
    name: str
    category: str = "Custom"
    description: str = ""
    system_prompt: str
    constraints: list[str] = Field(default_factory=list)
    output_format: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_enabled: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _json_obj(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def format_persona(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "system_prompt": row["system_prompt"],
        "constraints": _json_list(row["constraints_json"]),
        "output_format": _json_obj(row["output_format_json"]),
        "tags": _json_list(row["tags_json"]),
        "is_builtin": bool(row["is_builtin"]),
        "is_enabled": bool(row["is_enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/personas")
async def list_personas():
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM personas WHERE is_enabled = 1 ORDER BY category, name"
    ).fetchall()
    conn.close()
    return [format_persona(row) for row in rows]


@router.post("/personas", status_code=201)
async def create_persona(body: PersonaIn):
    name = body.name.strip()
    system_prompt = body.system_prompt.strip()
    if not name:
        raise HTTPException(400, detail="Persona name is required")
    if not system_prompt:
        raise HTTPException(400, detail="System prompt is required")

    now = _now()
    persona_id = str(uuid.uuid4())
    conn = database.get_connection()
    conn.execute(
        """
        INSERT INTO personas
        (id, name, category, description, system_prompt, constraints_json, output_format_json, tags_json, is_builtin, is_enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (
            persona_id,
            name,
            body.category.strip() or "Custom",
            body.description.strip(),
            system_prompt,
            json.dumps([c.strip() for c in body.constraints if c.strip()]),
            json.dumps(body.output_format),
            json.dumps([t.strip() for t in body.tags if t.strip()]),
            1 if body.is_enabled else 0,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()
    return format_persona(row)


@router.put("/personas/{persona_id}")
async def update_persona(persona_id: str, body: PersonaIn):
    name = body.name.strip()
    system_prompt = body.system_prompt.strip()
    if not name:
        raise HTTPException(400, detail="Persona name is required")
    if not system_prompt:
        raise HTTPException(400, detail="System prompt is required")

    conn = database.get_connection()
    row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Persona not found")
    if row["is_builtin"]:
        conn.close()
        raise HTTPException(400, detail="Built-in personas cannot be edited")

    now = _now()
    conn.execute(
        """
        UPDATE personas
        SET name = ?, category = ?, description = ?, system_prompt = ?, constraints_json = ?,
            output_format_json = ?, tags_json = ?, is_enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            name,
            body.category.strip() or "Custom",
            body.description.strip(),
            system_prompt,
            json.dumps([c.strip() for c in body.constraints if c.strip()]),
            json.dumps(body.output_format),
            json.dumps([t.strip() for t in body.tags if t.strip()]),
            1 if body.is_enabled else 0,
            now,
            persona_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    conn.close()
    return format_persona(row)


@router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Persona not found")
    if row["is_builtin"]:
        conn.close()
        raise HTTPException(400, detail="Built-in personas cannot be deleted")
    conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
