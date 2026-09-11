import datetime

from pydantic import BaseModel, Field


# ---- Practice / auth ----

class PracticeCreate(BaseModel):
    name: str


class PracticeCreated(BaseModel):
    practice_id: str
    name: str
    api_key: str = Field(description="Raw API key — shown only once, store it securely.")


# ---- Patients ----

class PatientCreate(BaseModel):
    full_name: str
    date_of_birth: str | None = None
    contact_info: str | None = None


class PatientOut(BaseModel):
    id: str
    practice_id: str
    created_at: datetime.datetime


class PatientDeleteResult(BaseModel):
    patient_id: str
    sql_record_deleted: bool
    vector_points_deleted: int
    message: str


# ---- Appointments ----

class AppointmentCreate(BaseModel):
    provider_name: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    reason: str | None = None
    patient_id: str | None = None


class AppointmentOut(BaseModel):
    id: str
    practice_id: str
    patient_id: str | None
    provider_name: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    reason: str | None
    status: str

    class Config:
        from_attributes = True


class ConflictCheckRequest(BaseModel):
    provider_name: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    exclude_appointment_id: str | None = None


class ConflictCheckResponse(BaseModel):
    has_conflict: bool
    conflicting_appointments: list[AppointmentOut]


class SlotSuggestionRequest(BaseModel):
    provider_name: str
    day_start: datetime.datetime
    day_end: datetime.datetime
    slot_minutes: int = 30


class SlotOut(BaseModel):
    start_time: datetime.datetime
    end_time: datetime.datetime


class AppointmentConfirm(BaseModel):
    confirmed_by: str


# ---- Billing ----

class BillingCheckRequest(BaseModel):
    billing_code: str
    claim_context: str | None = None
    patient_id: str | None = None


class BillingCheckResponse(BaseModel):
    billing_entry_id: str
    billing_code: str
    explanation: str
    grounding_used: bool
    sources: list[dict]
    denial_risk: str
    denial_risk_signals: list[str]
    disclaimer: str


class BillingConfirm(BaseModel):
    confirmed_by: str
    approved: bool


# ---- Triage ----

class TriageRequest(BaseModel):
    reason_for_visit: str
    symptom_flags: list[str] = Field(default_factory=list)
    duration_days: int | None = None
    pain_level: int | None = Field(default=None, ge=0, le=10)
    patient_id: str | None = None


class TriageResponse(BaseModel):
    urgency: str
    routing_suggestion: str
    matched_flags: list[str]
    sources: list[dict]
    disclaimer: str
    not_medical_advice: bool


# ---- Audit ----

class AuditLogOut(BaseModel):
    id: str
    practice_id: str
    actor: str
    action_type: str
    resource_type: str | None
    resource_id: str | None
    details: str | None
    human_status: str
    human_actor: str | None
    decided_at: datetime.datetime | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class AuditDecision(BaseModel):
    human_actor: str
    approve: bool
