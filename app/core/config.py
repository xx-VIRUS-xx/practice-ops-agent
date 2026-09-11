"""
Application configuration.

All settings are read from environment variables (see .env.example).
Nothing sensitive is hard-coded here.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "practice-ops-agent"
    environment: str = "development"

    # Relational DB (structured records: appointments, billing, audit log)
    database_url: str = "sqlite:///./practice_ops.db"

    # Qdrant vector store
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_domain_collection: str = "domain_knowledge"
    qdrant_patient_collection: str = "patient_memory"

    # Field-level encryption key for patient-memory payloads (Art. 9 data).
    # MUST be a urlsafe base64-encoded 32-byte key, e.g. generated via
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
    # In production this should come from a secrets manager / KMS, never committed.
    field_encryption_key: str = "REPLACE_ME_WITH_A_GENERATED_FERNET_KEY_BASE64=="

    # API key auth (MVP stub: one static key per practice, stored hashed in DB)
    admin_bootstrap_key: str = "dev-admin-bootstrap-key-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
