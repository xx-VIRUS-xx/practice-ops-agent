import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import AuditLog, Practice
from app.schemas.schemas import AuditDecision, AuditLogOut
from app.core.security import get_current_practice

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.practice_id == practice.id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )


@router.post("/{audit_id}/decision", response_model=AuditLogOut)
def record_decision(
    audit_id: str,
    payload: AuditDecision,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> AuditLog:
    entry = (
        db.query(AuditLog)
        .filter(AuditLog.id == audit_id, AuditLog.practice_id == practice.id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit entry not found")

    entry.human_status = "confirmed" if payload.approve else "rejected"
    entry.human_actor = payload.human_actor
    entry.decided_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(entry)
    return entry
