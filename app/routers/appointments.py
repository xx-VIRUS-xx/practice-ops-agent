"""
Scheduling endpoints: CRUD, conflict check, and slot suggestion.

New appointments are created with status=`proposed` when created via the
AI-assist flow (see /suggest-slots) — an appointment only becomes
`confirmed` via an explicit staff action on /appointments/{id}/confirm.
Direct creation via POST /appointments is treated as staff-initiated and
is created as `confirmed` immediately (staff typing it in IS the human
confirmation); the /suggest-slots endpoint never creates appointments on
its own, it only returns suggestions for staff to act on.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import Appointment, AppointmentStatus, Practice
from app.schemas.schemas import (
    AppointmentConfirm,
    AppointmentCreate,
    AppointmentOut,
    ConflictCheckRequest,
    ConflictCheckResponse,
    SlotOut,
    SlotSuggestionRequest,
)
from app.core.security import get_current_practice
from app.services.audit import log_ai_action
from app.services.scheduling import find_conflicts, suggest_available_slots

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentOut)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> AppointmentOut:
    conflicts = find_conflicts(
        db, practice.id, payload.provider_name, payload.start_time, payload.end_time
    )
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflicts with {len(conflicts)} existing appointment(s) for {payload.provider_name}",
        )

    appt = Appointment(
        practice_id=practice.id,
        patient_id=payload.patient_id,
        provider_name=payload.provider_name,
        start_time=payload.start_time,
        end_time=payload.end_time,
        reason=payload.reason,
        status=AppointmentStatus.confirmed,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> list[Appointment]:
    return db.query(Appointment).filter(Appointment.practice_id == practice.id).all()


@router.post("/check-conflict", response_model=ConflictCheckResponse)
def check_conflict(
    payload: ConflictCheckRequest,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> ConflictCheckResponse:
    conflicts = find_conflicts(
        db,
        practice.id,
        payload.provider_name,
        payload.start_time,
        payload.end_time,
        exclude_appointment_id=payload.exclude_appointment_id,
    )
    return ConflictCheckResponse(has_conflict=len(conflicts) > 0, conflicting_appointments=conflicts)


@router.post("/suggest-slots", response_model=list[SlotOut])
def suggest_slots(
    payload: SlotSuggestionRequest,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> list[dict]:
    slots = suggest_available_slots(
        db,
        practice.id,
        payload.provider_name,
        payload.day_start,
        payload.day_end,
        payload.slot_minutes,
    )
    log_ai_action(
        db,
        practice_id=practice.id,
        action_type="suggest_slots",
        resource_type="appointment",
        details={"provider_name": payload.provider_name, "slots_suggested": len(slots)},
    )
    return slots


@router.post("/{appointment_id}/confirm", response_model=AppointmentOut)
def confirm_appointment(
    appointment_id: str,
    payload: AppointmentConfirm,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> Appointment:
    appt = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id, Appointment.practice_id == practice.id)
        .first()
    )
    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    appt.status = AppointmentStatus.confirmed
    db.commit()
    db.refresh(appt)
    return appt
