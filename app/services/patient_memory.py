"""
Per-practice, per-patient memory store (Qdrant `patient_memory` collection).

Hard requirements enforced here:
- every write and every query carries tenant_id (+ patient_id where
  relevant) so one practice can never read or delete another practice's
  vectors, even by accident;
- text payloads are encrypted at the field level before being sent to
  Qdrant, and decrypted only after being read back for the owning tenant;
- `delete_patient_memory` performs a real, permanent deletion of all
  points for a given (tenant_id, patient_id) pair — not a soft/mark-
  inactive flag — to satisfy GDPR Art. 17 erasure requests.
"""
import uuid

from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.crypto import decrypt_field, encrypt_field
from app.services.embeddings import embed_text
from app.services.qdrant_client import get_qdrant_client


def add_memory(tenant_id: str, patient_id: str, text: str, memory_type: str = "note") -> str:
    """Encrypt + store one memory point, scoped to a tenant and patient."""
    settings = get_settings()
    client = get_qdrant_client()
    point_id = str(uuid.uuid4())
    vector = embed_text(text)
    encrypted_text = encrypt_field(text)

    client.upsert(
        collection_name=settings.qdrant_patient_collection,
        points=[
            qmodels.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "tenant_id": tenant_id,
                    "patient_id": patient_id,
                    "memory_type": memory_type,
                    "encrypted_text": encrypted_text,
                },
            )
        ],
    )
    return point_id


def query_memory(tenant_id: str, patient_id: str, query_text: str, limit: int = 5) -> list[dict]:
    """Retrieve memory points for a SPECIFIC tenant + patient only."""
    settings = get_settings()
    client = get_qdrant_client()
    vector = embed_text(query_text)

    results = client.search(
        collection_name=settings.qdrant_patient_collection,
        query_vector=vector,
        limit=limit,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id)),
                qmodels.FieldCondition(key="patient_id", match=qmodels.MatchValue(value=patient_id)),
            ]
        ),
    )

    out = []
    for r in results:
        payload = r.payload or {}
        out.append(
            {
                "id": r.id,
                "score": r.score,
                "memory_type": payload.get("memory_type"),
                "text": decrypt_field(payload.get("encrypted_text")),
            }
        )
    return out


def delete_patient_memory(tenant_id: str, patient_id: str) -> int:
    """
    Permanently delete ALL memory points for this (tenant_id, patient_id).

    Returns the number of points that matched the filter at delete time
    (best-effort count via a pre-delete scroll, since Qdrant's delete-by-
    filter does not return a count).
    """
    settings = get_settings()
    client = get_qdrant_client()

    delete_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id)),
            qmodels.FieldCondition(key="patient_id", match=qmodels.MatchValue(value=patient_id)),
        ]
    )

    existing, _ = client.scroll(
        collection_name=settings.qdrant_patient_collection,
        scroll_filter=delete_filter,
        limit=10_000,
        with_payload=False,
        with_vectors=False,
    )
    count = len(existing)

    if count > 0:
        client.delete(
            collection_name=settings.qdrant_patient_collection,
            points_selector=qmodels.FilterSelector(filter=delete_filter),
        )
    return count
