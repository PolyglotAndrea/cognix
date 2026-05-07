"""Authenticated JSON-RPC route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from cognix.api.state import agent_registry
from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.rpc.server import handle_rpc

router = APIRouter(tags=["rpc"])


@router.post("/rpc")
async def rpc_endpoint(
    body: Annotated[dict | list, Body()],
    user: CurrentUser = Depends(get_current_user),
) -> dict | list:
    return await handle_rpc(body, agent_registry)
