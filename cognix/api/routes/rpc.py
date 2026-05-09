"""Authenticated JSON-RPC route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket

from cognix.api.security import authenticate_websocket
from cognix.api.state import agent_registry
from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.rpc.server import handle_rpc

router = APIRouter(tags=["rpc"])


@router.post("/rpc")
async def rpc_endpoint(
    body: Annotated[dict | list, Body()],
    user: CurrentUser = Depends(get_current_user),
) -> dict | list:
    return await handle_rpc(body, agent_registry, user=user)


@router.websocket("/rpc/ws")
async def rpc_websocket(websocket: WebSocket) -> None:
    """Authenticated JSON-RPC 2.0 WebSocket transport."""
    try:
        user = await authenticate_websocket(websocket)
    except HTTPException as exc:
        await websocket.accept()
        await websocket.send_json(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32003, "message": exc.detail},
                "id": None,
            }
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        while True:
            body = await websocket.receive_json()
            response = await handle_rpc(body, agent_registry, user=user)
            if response:
                await websocket.send_json(response)
    except Exception:
        await websocket.close()
