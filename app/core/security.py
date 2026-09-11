"""
MVP auth stub: one API key per practice (tenant), passed via the
`X-API-Key` header. Keys are stored hashed (SHA-256) — never in plaintext.

This is intentionally simple for MVP scope. It is NOT a substitute for
OAuth2/OIDC or per-user RBAC in a production multi-user practice setting,
but it does give us a real tenant boundary from day one, which is the
important part architecturally: every request is resolved to exactly one
Practice, and all data access is filtered by that practice's tenant_id.
"""
import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import ApiKey, Practice


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"poa_{secrets.token_urlsafe(32)}"


def get_current_practice(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Practice:
    key_hash = hash_key(x_api_key)
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.revoked.is_(False))
        .first()
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    practice = db.query(Practice).filter(Practice.id == api_key.practice_id).first()
    if practice is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Practice not found for API key")
    return practice
