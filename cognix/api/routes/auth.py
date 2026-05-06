"""Authentication API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.auth.jwt import create_access_token
from cognix.auth.oauth import get_provider
from cognix.storage.database import get_session
from cognix.storage.models import APIKeyModel, UserModel, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ─────────────────────────────────────────────────────────


class CreateAPIKeyRequest(BaseModel):
    name: str = "default"


class APIKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: str | None = None
    last_used_at: str | None = None


class APIKeyCreatedResponse(APIKeyResponse):
    key: str  # Only returned on creation


# ── OAuth Login ─────────────────────────────────────────────────────


@router.get("/login/{provider}")
async def oauth_login(provider: str, request: Request) -> RedirectResponse:
    """Redirect to OAuth provider for login."""
    oauth_provider = get_provider(provider)
    if not oauth_provider:
        raise HTTPException(400, f"Unknown provider: {provider}")

    # Build callback URL from request
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/callback/{provider}"

    authorize_url = oauth_provider.get_authorize_url(redirect_uri)
    return RedirectResponse(authorize_url)


@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str,
    request: Request,
) -> RedirectResponse:
    """Handle OAuth callback, create/update user, return JWT."""
    from cognix.config import get_settings

    oauth_provider = get_provider(provider)
    if not oauth_provider:
        raise HTTPException(400, f"Unknown provider: {provider}")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/callback/{provider}"

    # Exchange code for user info
    user_info = await oauth_provider.get_user_info(code, redirect_uri)
    if not user_info.get("email"):
        raise HTTPException(400, "Could not get email from OAuth provider")

    # Find or create user
    async with get_session() as session:
        result = await session.execute(
            select(UserModel).where(
                UserModel.oauth_provider == provider,
                UserModel.oauth_id == user_info["oauth_id"],
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            # Check if email already exists with different provider
            email_result = await session.execute(
                select(UserModel).where(UserModel.email == user_info["email"])
            )
            existing = email_result.scalar_one_or_none()
            if existing:
                # Link OAuth to existing user
                existing.oauth_provider = provider
                existing.oauth_id = user_info["oauth_id"]
                existing.name = user_info.get("name", existing.name)
                existing.avatar_url = user_info.get("avatar_url", existing.avatar_url)
                user = existing
            else:
                # Create new user
                user = UserModel(
                    id=uuid.uuid4().hex,
                    email=user_info["email"],
                    name=user_info.get("name", ""),
                    avatar_url=user_info.get("avatar_url"),
                    oauth_provider=provider,
                    oauth_id=user_info["oauth_id"],
                    role=UserRole.USER,
                    is_active=True,
                )
                session.add(user)

        # Generate JWT
        token = create_access_token(
            user_id=user.id,
            role=user.role.value,
            email=user.email,
        )

    # Redirect to frontend with token
    settings = get_settings()
    frontend_url = f"http://localhost:5173"  # TODO: configurable
    return RedirectResponse(f"{frontend_url}/auth/callback?token={token}")


# ── Current User ────────────────────────────────────────────────────


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Get current authenticated user info."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "auth_method": user.auth_method,
    }


# ── API Key Management ──────────────────────────────────────────────


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: CreateAPIKeyRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a new API key for the current user."""
    from cognix.auth.api_key import generate_api_key

    full_key, key_hash, prefix = generate_api_key()

    async with get_session() as session:
        key_model = APIKeyModel(
            id=uuid.uuid4().hex,
            user_id=user.id,
            name=body.name,
            key_hash=key_hash,
            prefix=prefix,
            permissions={},
            created_at=datetime.now(timezone.utc),
        )
        session.add(key_model)
        await session.flush()

        return {
            "id": key_model.id,
            "name": key_model.name,
            "prefix": key_model.prefix,
            "key": full_key,
            "created_at": key_model.created_at.isoformat() if key_model.created_at else None,
            "last_used_at": None,
        }


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List API keys for the current user."""
    async with get_session() as session:
        result = await session.execute(
            select(APIKeyModel).where(APIKeyModel.user_id == user.id)
        )
        keys = result.scalars().all()

    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Delete an API key."""
    from sqlalchemy import delete

    async with get_session() as session:
        result = await session.execute(
            delete(APIKeyModel).where(
                APIKeyModel.id == key_id,
                APIKeyModel.user_id == user.id,
            )
        )
        if result.rowcount == 0:
            raise HTTPException(404, "API key not found")

    return {"deleted": key_id}
