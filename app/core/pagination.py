from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def page_response(items: Sequence[T], formatter: Callable[[T], dict] | None = None, *, page: int = 1, page_size: int = 50) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    selected = items[start:start + page_size]
    if formatter:
        selected_items = [formatter(item) for item in selected]
    else:
        selected_items = list(selected)
    return {"items": selected_items, "total": total, "page": page, "page_size": page_size}
