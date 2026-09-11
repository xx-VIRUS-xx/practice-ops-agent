from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import Practice
from app.schemas.schemas import TriageRequest, TriageResponse
from app.core.security import get_current_practice
from app.services.audit import log_ai_action
from app.services.triage import suggest_routing

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("/intake", response_model=TriageResponse)
def intake_triage(
    payload: TriageRequest,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> TriageResponse:
    result = suggest_routing(
        reason_for_visit=payload.reason_for_visit,
        symptom_flags=payload.symptom_flags,
        duration_days=payload.duration_days,
        pain_level=payload.pain_level,
    )

    log_ai_action(
        db,
        practice_id=practice.id,
        action_type="triage_routing",
        resource_type="patient" if payload.patient_id else None,
        resource_id=payload.patient_id,
        details={"urgency": result["urgency"], "matched_flags": result["matched_flags"]},
    )

    return TriageResponse(**result)
