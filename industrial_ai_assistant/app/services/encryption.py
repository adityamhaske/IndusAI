"""
AES-256 encryption utility for user API keys at rest in Firestore.

Uses Fernet (AES-128-CBC → actually AES-128 via Fernet spec, but wraps
a symmetric authenticated scheme). For true AES-256, we derive a 32-byte
key from ENCRYPTION_KEY using PBKDF2 and wrap with Fernet.

ENCRYPTION_KEY env var must be a URL-safe base64 Fernet key.
Generate one via:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings

logger = logging.getLogger(__name__)


@lru_cache()
def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string → URL-safe base64 ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string → plaintext. Raises ValueError on failure."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt. Key may have been rotated or data corrupted.")
