"""JWT token creation and verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from cognix.config import get_settings


def create_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT token."""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            hours=settings.auth.token_expire_hours
        )

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm="HS256")


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a JWT token. Returns None if invalid."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def create_access_token(user_id: str, role: str, email: str) -> str:
    """Create an access token for a user."""
    return create_token(
        data={
            "sub": user_id,
            "role": role,
            "email": email,
            "type": "access",
        }
    )


def create_api_key_token(user_id: str, key_id: str, permissions: dict) -> str:
    """Create a token for API key authentication."""
    return create_token(
        data={
            "sub": user_id,
            "key_id": key_id,
            "permissions": permissions,
            "type": "api_key",
        },
        expires_delta=timedelta(days=365),  # API keys last 1 year
    )
