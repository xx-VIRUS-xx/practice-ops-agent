from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import BillingEntry, Practice
from app.schemas.schemas import BillingCheckRequest, BillingCheckResponse, BillingConfirm
from app.core.security import get_current_practice
from app.services.audit import log_ai_action
from app.services.billing import explain_billing_code

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/check", response_model=BillingCheckResponse)
def check_billing_code(
    payload: BillingCheckRequest,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> BillingCheckResponse:
    result = explain_billing_code(payload.billing_code, payload.claim_context)

    entry = BillingEntry(
        practice_id=practice.id,
        patient_id=payload.patient_id,
        billing_code=payload.billing_code,
        claim_context=payload.claim_context,
        denial_risk=result["denial_risk"],
        explanation=result["explanation"],
        status="draft",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    log_ai_action(
        db,
        practice_id=practice.id,
        action_type="billing_check",
        resource_type="billing_entry",
        resource_id=entry.id,
        details={"billing_code": payload.billing_code, "denial_risk": result["denial_risk"]},
    )

    return BillingCheckResponse(billing_entry_id=entry.id, **result)


@router.post("/{billing_entry_id}/confirm")
def confirm_billing_entry(
    billing_entry_id: str,
    payload: BillingConfirm,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> dict:
    """
    Human confirmation gate: a billing suggestion is never auto-submitted.
    Staff explicitly approves or rejects it here.
    """
    entry = (
        db.query(BillingEntry)
        .filter(BillingEntry.id == billing_entry_id, BillingEntry.practice_id == practice.id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing entry not found")

    entry.status = "confirmed" if payload.approved else "rejected"
    db.commit()

    return {"billing_entry_id": entry.id, "status": entry.status, "confirmed_by": payload.confirmed_by}
