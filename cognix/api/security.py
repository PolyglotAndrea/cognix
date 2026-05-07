"""Authentication helpers for HTTP endpoints that are not dependency-friendly."""

from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket

from cognix.auth.dependencies import CurrentUser, get_current_user, has_permission


async def authenticate_request(request: Request) -> CurrentUser:
    """Authenticate a plain Request outside FastAPI dependency injection."""
    return await get_current_user(request, credentials=None)


async def authenticate_websocket(websocket: WebSocket) -> CurrentUser:
    """Authenticate a websocket using Authorization, token query, or X-API-Key."""
    token = websocket.query_params.get("token")
    auth = websocket.headers.get("Authorization")
    api_key = websocket.headers.get("X-API-Key") or websocket.query_params.get("api_key")

    if token and not auth:
        websocket.scope["headers"].append((b"authorization", f"Bearer {token}".encode()))
    if api_key and not websocket.headers.get("X-API-Key"):
        websocket.scope["headers"].append((b"x-api-key", api_key.encode()))

    return await get_current_user(websocket, credentials=None)


def ensure_permission(user: CurrentUser, permission: str) -> None:
    """Raise 403 if the user lacks a permission."""
    if not has_permission(user.role.value, permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
