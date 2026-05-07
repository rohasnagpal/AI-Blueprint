import json

from fastapi import APIRouter

import database

router = APIRouter()


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
