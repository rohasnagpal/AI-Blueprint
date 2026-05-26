import json
from typing import TypeVar

T = TypeVar("T")


def json_loads(value: str | None, fallback: T) -> T:
    if not value:
        return fallback
    try:
        data = json.loads(value)
    except Exception:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback
