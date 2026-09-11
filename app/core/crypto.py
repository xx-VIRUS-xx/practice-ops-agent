"""
Field-level encryption helpers for patient-related data (GDPR Art. 9).

MVP approach: symmetric encryption (Fernet / AES-128-CBC + HMAC) of individual
sensitive fields before they are persisted (in Postgres columns or in the
Qdrant payload of the per-patient memory collection). The encryption key is
provided via configuration (env var / secrets manager in production) and is
never stored alongside the ciphertext.

This is documented explicitly as an MVP-level control in the README. It is
NOT a substitute for full disk/volume encryption, KMS-backed key rotation,
or an HSM — see README "GDPR & Health Data Handling" section for the honest
limitations list.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionError(Exception):
    pass


def _get_fernet() -> Fernet:
    key = get_settings().field_encryption_key
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # noqa: BLE001
        raise EncryptionError(
            "Invalid FIELD_ENCRYPTION_KEY. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc


def encrypt_field(plaintext: str | None) -> str | None:
    """Encrypt a single string field. Returns None for None input."""
    if plaintext is None:
        return None
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: str | None) -> str | None:
    """Decrypt a single string field. Returns None for None input."""
    if ciphertext is None:
        return None
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError("Failed to decrypt field: invalid token or wrong key") from exc
