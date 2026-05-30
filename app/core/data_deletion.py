import sqlite3
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import database as legacy_database
from app.core.database import Base
from app.core.models import KnowledgeDocument, Matter, Workspace
from app.core.storage import delete_stored_file


def _storage_keys_to_delete(db: Session, documents: Iterable[KnowledgeDocument]) -> list[str]:
    document_list = list(documents)
    document_ids = {document.id for document in document_list}
    storage_keys = {document.storage_key for document in document_list if document.storage_key}
    unreferenced: list[str] = []
    for storage_key in storage_keys:
        remaining = db.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.storage_key == storage_key,
                KnowledgeDocument.id.notin_(document_ids),
            )
        ).scalar_one()
        if remaining == 0:
            unreferenced.append(storage_key)
    return unreferenced


def _delete_legacy_chats(*, workspace_id: str, matter_id: str | None = None) -> int:
    conn = legacy_database.get_connection()
    try:
        try:
            if matter_id:
                rows = conn.execute(
                    "SELECT id FROM chats WHERE v2_workspace_id = ? AND v2_matter_id = ?",
                    (workspace_id, matter_id),
                ).fetchall()
            else:
                rows = conn.execute("SELECT id FROM chats WHERE v2_workspace_id = ?", (workspace_id,)).fetchall()
        except sqlite3.OperationalError:
            return 0
        chat_ids = [row["id"] for row in rows]
        if chat_ids:
            placeholders = ",".join("?" for _ in chat_ids)
            conn.execute(f"DELETE FROM messages WHERE chat_id IN ({placeholders})", chat_ids)
            conn.execute(f"DELETE FROM chats WHERE id IN ({placeholders})", chat_ids)
            conn.commit()
        return len(chat_ids)
    finally:
        conn.close()


def _delete_rows_with_column(db: Session, column_name: str, value: str, *, exclude_tables: set[str]) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in exclude_tables or column_name not in table.c:
            continue
        db.execute(table.delete().where(table.c[column_name] == value))


def hard_delete_matter(db: Session, matter: Matter) -> dict:
    documents = db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.workspace_id == matter.workspace_id,
            KnowledgeDocument.matter_id == matter.id,
        )
    ).scalars().all()
    storage_keys = _storage_keys_to_delete(db, documents)
    legacy_chat_count = _delete_legacy_chats(workspace_id=matter.workspace_id, matter_id=matter.id)
    _delete_rows_with_column(db, "matter_id", matter.id, exclude_tables={"matters"})
    db.delete(matter)
    db.flush()
    return {
        "documents": len(documents),
        "storage_keys": storage_keys,
        "legacy_chats": legacy_chat_count,
    }


def hard_delete_workspace(db: Session, workspace: Workspace) -> dict:
    documents = db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.workspace_id == workspace.id)
    ).scalars().all()
    storage_keys = _storage_keys_to_delete(db, documents)
    legacy_chat_count = _delete_legacy_chats(workspace_id=workspace.id)
    _delete_rows_with_column(db, "workspace_id", workspace.id, exclude_tables={"workspaces"})
    db.delete(workspace)
    db.flush()
    return {
        "documents": len(documents),
        "storage_keys": storage_keys,
        "legacy_chats": legacy_chat_count,
    }


def delete_storage_keys(storage_keys: Iterable[str]) -> None:
    for storage_key in storage_keys:
        delete_stored_file(storage_key)
