"""
Qdrant client setup and collection bootstrap for the two collections:

1. `domain_knowledge` — generic, non-patient-specific reference material:
   billing code explanations, scheduling policy templates, generic triage
   routing guidance. Safe to seed with static content; contains no PHI.

2. `patient_memory` — per-practice, per-patient memory. Every point:
   - carries a mandatory `tenant_id` (practice id) payload field used as a
     hard filter on every query (defense against cross-tenant leakage);
   - carries a mandatory `patient_id` payload field so a single patient's
     vectors can be located and deleted on request (GDPR Art. 17 / Art. 9
     special-category data);
   - stores any human-readable payload text in encrypted form (see
     app.core.crypto) — the payload is not stored as cleartext PHI even
     though Qdrant's on-disk storage should also live on an encrypted
     volume in production (see README for the full documented approach).
"""
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.services.embeddings import VECTOR_SIZE

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return _client


def ensure_collections() -> None:
    """Idempotently create both collections if they don't already exist."""
    settings = get_settings()
    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}

    for name in (settings.qdrant_domain_collection, settings.qdrant_patient_collection):
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
            )

    # Index tenant_id / patient_id for fast + safe filtering on patient_memory
    patient_collection = settings.qdrant_patient_collection
    try:
        client.create_payload_index(
            collection_name=patient_collection, field_name="tenant_id", field_schema="keyword"
        )
        client.create_payload_index(
            collection_name=patient_collection, field_name="patient_id", field_schema="keyword"
        )
    except Exception:  # noqa: BLE001 - index may already exist; Qdrant raises on duplicate
        pass
