"""
Audit log service.

Every AI-suggested action (slot suggestion, billing denial-risk flag,
triage routing suggestion) is recorded here with a `pending` human_status.
Only an explicit staff confirmation or rejection (via the confirm/reject
endpoint) updates that status. Nothing in this system transitions an
audit entry to "confirmed" on its own.
"""
import json

from sqlalchemy.orm import Session

from app.models.orm import AuditLog


def log_ai_action(
    db: Session,
    practice_id: str,
    action_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        practice_id=practice_id,
        actor="ai",
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details is not None else None,
        human_status="pending",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
