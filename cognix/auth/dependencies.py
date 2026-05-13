"""FastAPI dependencies for authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cognix.auth.jwt import verify_token
from cognix.storage.database import get_session
from cognix.storage.models import APIKeyModel, UserModel, UserRole

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Authenticated user context."""

    id: str
    email: str
    role: UserRole
    name: str = ""
    auth_method: str = "jwt"  # jwt or api_key


# Permission definitions
PERMISSIONS = {
    "agents:read": "View agents",
    "agents:write": "Create/edit agents",
    "agents:delete": "Delete agents",
    "tasks:read": "View tasks",
    "tasks:write": "Create/edit tasks",
    "tasks:delete": "Delete tasks",
    "skills:read": "View skills",
    "skills:write": "Install/uninstall skills",
    "connectors:read": "View connectors",
    "connectors:write": "Connect/disconnect platforms",
    "settings:read": "View settings",
    "settings:write": "Modify settings",
    "admin": "Full admin access",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["*"],
    "user": [
        "agents:read", "agents:write",
        "tasks:read", "tasks:write",
        "skills:read", "skills:write",
        "connectors:read", "connectors:write",
        "settings:read", "settings:write",
    ],
    "viewer": [
        "agents:read",
        "tasks:read",
        "skills:read",
        "connectors:read",
        "settings:read",
    ],
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    perms = ROLE_PERMISSIONS.get(role, [])
    if "*" in perms:
        return True
    return permission in perms


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> CurrentUser:
    """Get the current authenticated user from JWT or API Key."""

    # Try JWT from Authorization header
    token = credentials.credentials if credentials and credentials.credentials else None
    if not token:
        authorization = request.headers.get("Authorization")
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()

    if token:
        payload = verify_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                # Load user from DB
                from sqlalchemy import select

                async with get_session() as session:
                    result = await session.execute(
                        select(UserModel).where(UserModel.id == user_id)
                    )
                    user = result.scalar_one_or_none()

                if user and user.is_active:
                    return CurrentUser(
                        id=user.id,
                        email=user.email,
                        role=user.role,
                        name=user.name,
                        auth_method="jwt",
                    )

    # Try API Key from X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(select(APIKeyModel))
            for key_model in result.scalars():
                from cognix.auth.api_key import verify_api_key

                if verify_api_key(api_key, key_model.key_hash):
                    # Update last_used_at
                    key_model.last_used_at = datetime.now(UTC)

                    # Load user
                    user_result = await session.execute(
                        select(UserModel).where(UserModel.id == key_model.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user and user.is_active:
                        return CurrentUser(
                            id=user.id,
                            email=user.email,
                            role=user.role,
                            name=user.name,
                            auth_method="api_key",
                        )

    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_permission(permission: str):
    """Create a dependency that requires a specific permission."""

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(user.role.value, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission required: {permission}",
            )
        return user

    return _check


# Convenience dependencies
require_agents_read = require_permission("agents:read")
require_agents_write = require_permission("agents:write")
require_agents_delete = require_permission("agents:delete")
require_tasks_read = require_permission("tasks:read")
require_tasks_write = require_permission("tasks:write")
require_skills_read = require_permission("skills:read")
require_skills_write = require_permission("skills:write")
require_connectors_read = require_permission("connectors:read")
require_connectors_write = require_permission("connectors:write")
require_settings_read = require_permission("settings:read")
require_settings_write = require_permission("settings:write")
