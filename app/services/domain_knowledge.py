"""
Domain knowledge retrieval (Qdrant `domain_knowledge` collection).

This collection holds only generic, non-patient-specific reference material
(billing code explanations, scheduling policy templates, generic triage
routing guidance) — see scripts/seed_domain_knowledge.py for the seed set.
No tenant filter is needed here since nothing patient-specific is stored.
"""
import uuid

from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.services.embeddings import embed_text
from app.services.qdrant_client import get_qdrant_client


def upsert_knowledge(doc_id: str, text: str, category: str, metadata: dict | None = None) -> None:
    settings = get_settings()
    client = get_qdrant_client()
    vector = embed_text(text)
    payload = {"category": category, "text": text, **(metadata or {})}
    client.upsert(
        collection_name=settings.qdrant_domain_collection,
        points=[qmodels.PointStruct(id=doc_id, vector=vector, payload=payload)],
    )


def search_knowledge(query_text: str, category: str | None = None, limit: int = 3) -> list[dict]:
    settings = get_settings()
    client = get_qdrant_client()
    vector = embed_text(query_text)

    query_filter = None
    if category:
        query_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="category", match=qmodels.MatchValue(value=category))]
        )

    results = client.search(
        collection_name=settings.qdrant_domain_collection,
        query_vector=vector,
        limit=limit,
        query_filter=query_filter,
    )
    return [
        {"id": r.id, "score": r.score, "category": (r.payload or {}).get("category"), "text": (r.payload or {}).get("text")}
        for r in results
    ]


def stable_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))
