"""
Patient records + the GDPR Art. 17 delete-on-request endpoint.

The delete endpoint performs a REAL deletion:
- the `patients` SQL row is deleted (not soft-deleted / marked inactive),
- all Qdrant `patient_memory` points for that (tenant_id, patient_id) are
  permanently deleted,
- appointments/billing rows referencing the patient have their
  `patient_id` foreign key nulled out (the operational record of "an
  appointment happened" is not itself special-category data once
  unlinked from patient identity, but if a practice wants full
  cascading deletion of those too, that is a straightforward extension
  — documented as a current limitation in the README).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_field
from app.db.session import get_db
from app.models.orm import Appointment, BillingEntry, Patient, Practice
from app.schemas.schemas import PatientCreate, PatientDeleteResult, PatientOut
from app.core.security import get_current_practice
from app.services.audit import log_ai_action
from app.services.patient_memory import delete_patient_memory

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut)
def create_patient(
    payload: PatientCreate,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> PatientOut:
    patient = Patient(
        practice_id=practice.id,
        encrypted_full_name=encrypt_field(payload.full_name),
        encrypted_date_of_birth=encrypt_field(payload.date_of_birth),
        encrypted_contact_info=encrypt_field(payload.contact_info),
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return PatientOut(id=patient.id, practice_id=patient.practice_id, created_at=patient.created_at)


def _get_patient_or_404(db: Session, practice_id: str, patient_id: str) -> Patient:
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.practice_id == practice_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.delete("/{patient_id}", response_model=PatientDeleteResult)
def delete_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    practice: Practice = Depends(get_current_practice),
) -> PatientDeleteResult:
    """
    Permanently erase a patient's data on request (GDPR Art. 17), scoped
    strictly to the requesting practice's tenant_id.
    """
    patient = _get_patient_or_404(db, practice.id, patient_id)

    # 1. Permanently delete all vector memory for this patient.
    vector_deleted_count = delete_patient_memory(tenant_id=practice.id, patient_id=patient_id)

    # 2. Unlink (not cascade-delete) operational records so appointment/
    #    billing history for the practice's own operations remains, but
    #    with no link back to patient identity.
    db.query(Appointment).filter(
        Appointment.practice_id == practice.id, Appointment.patient_id == patient_id
    ).update({"patient_id": None})
    db.query(BillingEntry).filter(
        BillingEntry.practice_id == practice.id, BillingEntry.patient_id == patient_id
    ).update({"patient_id": None})

    # 3. Permanently delete the patient row itself (real delete, not a flag).
    db.delete(patient)
    db.commit()

    log_ai_action(
        db,
        practice_id=practice.id,
        action_type="patient_data_deletion",
        resource_type="patient",
        resource_id=patient_id,
        details={"vector_points_deleted": vector_deleted_count},
    )

    return PatientDeleteResult(
        patient_id=patient_id,
        sql_record_deleted=True,
        vector_points_deleted=vector_deleted_count,
        message="Patient record and all associated vector memory permanently deleted.",
    )
