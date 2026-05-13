"""Generic secret encryption for API keys stored at rest.

Reuses the same Fernet (AES-128-CBC + HMAC) approach as connector token
encryption but with a separate PBKDF2 salt so the two domains are isolated.
The encryption key is derived from ``settings.auth.secret_key`` (or a
dedicated ``COGNIX_SECRETS__ENCRYPTION_KEY`` env var if set).
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "gAAAAA"
_SALT = b"cognix-secrets-v1"

_fernet: Fernet | None = None


def _derive_key(secret: str) -> bytes:
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), _SALT, 480_000)
    return base64.urlsafe_b64encode(dk)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    from cognix.config import get_settings

    settings = get_settings()
    raw = getattr(settings, "secrets", None)
    encryption_key = getattr(raw, "encryption_key", None) if raw else None
    if not encryption_key:
        encryption_key = settings.auth.secret_key
    key = (
        encryption_key.encode()
        if len(encryption_key) == 44
        else _derive_key(encryption_key)
    )
    _fernet = Fernet(key)
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string, returning a URL-safe base64 ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a previously encrypted secret string.

    Returns the ciphertext unchanged if it is not a valid Fernet token
    (i.e. it was stored as plaintext before encryption was enabled).
    """
    if not ciphertext.startswith(_FERNET_PREFIX):
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        logger.debug("Failed to decrypt secret — returning as plaintext")
        return ciphertext


def is_encrypted(value: str | None) -> bool:
    """Return True if *value* looks like a Fernet ciphertext."""
    return bool(value) and value.startswith(_FERNET_PREFIX)
