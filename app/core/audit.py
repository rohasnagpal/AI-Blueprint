import json
import uuid

from sqlalchemy.orm import Session

from app.core.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )
