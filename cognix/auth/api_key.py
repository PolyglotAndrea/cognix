"""API Key generation and verification."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import bcrypt

PREFIX = "cnx"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (full_key, key_hash, prefix)
        - full_key: The full API key to show to user (cnx_xxxxx...)
        - key_hash: bcrypt hash to store in DB
        - prefix: First 8 chars for display (cnx_xxxx...)
    """
    random_part = secrets.token_hex(24)
    full_key = f"{PREFIX}_{random_part}"
    key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt()).decode()
    prefix = full_key[:12] + "..."

    return full_key, key_hash, prefix


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Verify an API key against its stored hash."""
    return bcrypt.checkpw(provided_key.encode(), stored_hash.encode())


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()
