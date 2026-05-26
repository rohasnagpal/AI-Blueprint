from collections.abc import Callable, Sequence
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


def page_response(items: Sequence[T], formatter: Callable[[T], dict] | None = None, *, page: int = 1, page_size: int = 50) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    selected = items[start:start + page_size]
    if formatter:
        selected_items = [formatter(item) for item in selected]
    else:
        selected_items = list(selected)
    return _page_payload(selected_items, total=total, page=page, page_size=page_size)


def page_query_response(db: Session, statement: Select, formatter: Callable[[T], dict] | None = None, *, page: int = 1, page_size: int = 50, scalars: bool = False) -> dict:
    total = db.execute(select(func.count()).select_from(statement.order_by(None).subquery())).scalar_one()
    paged = statement.limit(page_size).offset((page - 1) * page_size)
    result = db.execute(paged)
    selected = result.scalars().all() if scalars else result.all()
    if formatter:
        selected_items = [formatter(item) for item in selected]
    else:
        selected_items = list(selected)
    return _page_payload(selected_items, total=total, page=page, page_size=page_size)


def _page_payload(items: list[dict] | list[T], *, total: int, page: int, page_size: int) -> dict:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1 and pages > 0,
    }
