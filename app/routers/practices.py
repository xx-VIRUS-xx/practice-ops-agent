"""
Practice (tenant) onboarding.

MVP note: creating a new practice + its first API key is gated by a static
`admin_bootstrap_key` (see app.core.config) rather than open self-signup,
since this is out-of-scope MVP territory for real billing/account
management. In production this would sit behind a proper signup/billing
flow.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_api_key, hash_key
from app.db.session import get_db
from app.models.orm import ApiKey, Practice
from app.schemas.schemas import PracticeCreate, PracticeCreated

router = APIRouter(prefix="/practices", tags=["practices"])


def _require_bootstrap_key(x_bootstrap_key: str = Header(..., alias="X-Bootstrap-Key")) -> None:
    settings = get_settings()
    if x_bootstrap_key != settings.admin_bootstrap_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bootstrap key")


@router.post("", response_model=PracticeCreated, dependencies=[Depends(_require_bootstrap_key)])
def create_practice(payload: PracticeCreate, db: Session = Depends(get_db)) -> PracticeCreated:
    practice = Practice(name=payload.name)
    db.add(practice)
    db.commit()
    db.refresh(practice)

    raw_key = generate_api_key()
    api_key = ApiKey(practice_id=practice.id, key_hash=hash_key(raw_key), label="default")
    db.add(api_key)
    db.commit()

    return PracticeCreated(practice_id=practice.id, name=practice.name, api_key=raw_key)
