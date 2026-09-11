"""
Tests for the GDPR Art. 17 delete-on-request endpoint.

Qdrant is mocked out at the router's import point so these tests run fully
offline / without a live Qdrant instance, while still verifying:
- the SQL patient row is actually deleted (not soft-deleted),
- the vector-memory deletion function is invoked with the correct
  tenant_id + patient_id (proving tenant-scoped deletion, not a global wipe),
- appointments/billing referencing the patient are unlinked rather than
  left dangling,
- an audit log entry is created for the deletion action,
- a request for a patient belonging to a DIFFERENT practice's API key is
  rejected (tenant isolation on delete).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import generate_api_key, hash_key
from app.db.session import Base, get_db
from app.main import app
from app.models.orm import Appointment, ApiKey, AuditLog, Patient, Practice
import app.routers.patients as patients_router


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Mock the vector-store delete so tests don't require a live Qdrant.
    deleted_calls = []

    def fake_delete_patient_memory(tenant_id: str, patient_id: str) -> int:
        deleted_calls.append((tenant_id, patient_id))
        return 3  # pretend 3 points existed

    monkeypatch.setattr(patients_router, "delete_patient_memory", fake_delete_patient_memory)

    with TestClient(app) as c:
        c.deleted_calls = deleted_calls
        c.SessionLocal = TestingSessionLocal
        yield c

    app.dependency_overrides.clear()


def _create_practice_with_key(session_local) -> tuple[str, str]:
    db = session_local()
    practice = Practice(id=str(uuid.uuid4()), name="Delete Test Practice")
    db.add(practice)
    db.commit()

    raw_key = generate_api_key()
    db.add(ApiKey(practice_id=practice.id, key_hash=hash_key(raw_key)))
    db.commit()
    practice_id = practice.id
    db.close()
    return practice_id, raw_key


def test_delete_patient_removes_sql_row_and_vector_memory(client):
    practice_id, api_key = _create_practice_with_key(client.SessionLocal)
    headers = {"X-API-Key": api_key}

    create_resp = client.post(
        "/patients",
        json={"full_name": "Jane Doe", "date_of_birth": "1990-01-01", "contact_info": "jane@example.com"},
        headers=headers,
    )
    assert create_resp.status_code == 200
    patient_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/patients/{patient_id}", headers=headers)
    assert delete_resp.status_code == 200
    body = delete_resp.json()
    assert body["sql_record_deleted"] is True
    assert body["vector_points_deleted"] == 3
    assert body["patient_id"] == patient_id

    # Vector deletion was called scoped to this exact tenant + patient.
    assert client.deleted_calls == [(practice_id, patient_id)]

    # The SQL row is REALLY gone, not soft-deleted.
    db = client.SessionLocal()
    remaining = db.query(Patient).filter(Patient.id == patient_id).first()
    assert remaining is None
    db.close()


def test_delete_patient_unlinks_appointments_instead_of_leaving_dangling_fk(client):
    practice_id, api_key = _create_practice_with_key(client.SessionLocal)
    headers = {"X-API-Key": api_key}

    patient_id = client.post(
        "/patients", json={"full_name": "John Roe"}, headers=headers
    ).json()["id"]

    appt_resp = client.post(
        "/appointments",
        json={
            "provider_name": "Dr. Smith",
            "start_time": "2026-09-15T09:00:00Z",
            "end_time": "2026-09-15T09:30:00Z",
            "patient_id": patient_id,
        },
        headers=headers,
    )
    assert appt_resp.status_code == 200
    appt_id = appt_resp.json()["id"]

    client.delete(f"/patients/{patient_id}", headers=headers)

    db = client.SessionLocal()
    appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
    assert appt is not None  # appointment record itself is retained
    assert appt.patient_id is None  # but unlinked from the deleted patient
    db.close()


def test_delete_patient_creates_audit_log_entry(client):
    practice_id, api_key = _create_practice_with_key(client.SessionLocal)
    headers = {"X-API-Key": api_key}

    patient_id = client.post(
        "/patients", json={"full_name": "Audit Test"}, headers=headers
    ).json()["id"]

    client.delete(f"/patients/{patient_id}", headers=headers)

    db = client.SessionLocal()
    audit_entries = (
        db.query(AuditLog)
        .filter(AuditLog.practice_id == practice_id, AuditLog.action_type == "patient_data_deletion")
        .all()
    )
    assert len(audit_entries) == 1
    assert audit_entries[0].resource_id == patient_id
    db.close()


def test_delete_patient_rejects_cross_tenant_request(client):
    practice_a_id, api_key_a = _create_practice_with_key(client.SessionLocal)
    practice_b_id, api_key_b = _create_practice_with_key(client.SessionLocal)

    patient_id = client.post(
        "/patients", json={"full_name": "Tenant A Patient"}, headers={"X-API-Key": api_key_a}
    ).json()["id"]

    # Practice B tries to delete Practice A's patient using its own valid key.
    resp = client.delete(f"/patients/{patient_id}", headers={"X-API-Key": api_key_b})

    assert resp.status_code == 404

    # The patient must still exist for its real owner (Practice A).
    db = client.SessionLocal()
    still_there = db.query(Patient).filter(Patient.id == patient_id).first()
    assert still_there is not None
    db.close()


def test_delete_patient_requires_valid_api_key(client):
    resp = client.delete(f"/patients/{uuid.uuid4()}", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401
