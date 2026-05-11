"""Fernet-based symmetric encryption for connector OAuth tokens."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from a secret string via PBKDF2."""
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), b"cognix-connectors", 480_000)
    return base64.urlsafe_b64encode(dk)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    from cognix.config import get_settings

    settings = get_settings()
    raw = settings.connectors.encryption_key
    if raw:
        key = raw.encode() if len(raw) == 44 else _derive_key(raw)
    else:
        key = _derive_key(settings.auth.secret_key)
    _fernet = Fernet(key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string, returning a URL-safe base64 string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a previously encrypted token string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
