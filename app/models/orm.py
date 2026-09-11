"""
Relational (SQL) models: tenants/practices, API keys, appointments,
billing entries, patients (metadata only — sensitive fields encrypted),
and the audit log.

Design notes:
- Every patient-identifying / clinical field that lives in this relational
  DB is stored encrypted at the field level (see app.core.crypto). This is
  separate from, and in addition to, the encrypted-at-rest Qdrant patient
  memory collection.
- `tenant_id` (the practice) is a mandatory foreign key on every
  patient-scoped table, enforced at the query layer (see app/services) to
  guarantee per-tenant isolation.
- The audit log is append-only from the application's point of view: rows
  are created, never mutated or deleted, and record who/what/when for every
  AI-suggested action plus its human confirm/reject outcome.
"""
import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Practice(Base):
    """A tenant: one medical/dental practice."""

    __tablename__ = "practices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="practice", cascade="all, delete-orphan")
    patients: Mapped[list["Patient"]] = relationship(back_populates="practice", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="practice", cascade="all, delete-orphan")
    billing_entries: Mapped[list["BillingEntry"]] = relationship(back_populates="practice", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    MVP auth stub: one (or more) static API keys per practice.
    Only the SHA-256 hash of the key is stored, never the raw key.
    """

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    practice_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String, default="default")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    practice: Mapped["Practice"] = relationship(back_populates="api_keys")


class Patient(Base):
    """
    Patient metadata for a practice. Direct identifiers (name, DOB, contact)
    are stored encrypted at the field level. This row is the anchor that lets
    us honor a GDPR deletion request cleanly (delete this row + associated
    Qdrant vectors + redact references in appointments/billing).
    """

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    practice_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), nullable=False, index=True)

    # Encrypted fields (ciphertext stored as text)
    encrypted_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_date_of_birth: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_contact_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    practice: Mapped["Practice"] = relationship(back_populates="patients")


class AppointmentStatus(str, enum.Enum):
    proposed = "proposed"  # AI-suggested, not yet confirmed by staff
    confirmed = "confirmed"
    cancelled = "cancelled"


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    practice_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)

    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.proposed
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    practice: Mapped["Practice"] = relationship(back_populates="appointments")


class BillingEntry(Base):
    __tablename__ = "billing_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    practice_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)

    billing_code: Mapped[str] = mapped_column(String, nullable=False)
    claim_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    denial_risk: Mapped[str | None] = mapped_column(String, nullable=True)  # low/medium/high
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft/submitted/confirmed by staff
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    practice: Mapped["Practice"] = relationship(back_populates="billing_entries")


class AuditLog(Base):
    """
    Append-only record of every AI-suggested action and its human outcome.
    Nothing in this system auto-executes (auto-sends a claim, auto-confirms
    an appointment) without a corresponding human confirmation captured here.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    practice_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), nullable=False, index=True)

    actor: Mapped[str] = mapped_column(String, nullable=False)  # "ai" or a staff user identifier
    action_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "suggest_slot", "billing_check", "triage"
    resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded, non-PHI summary where possible

    human_status: Mapped[str] = mapped_column(String, default="pending")  # pending/confirmed/rejected
    human_actor: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
