"""Runtime node REST routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.local.runtime import RuntimeNodeStore

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


@router.get("/nodes")
async def list_runtime_nodes(
    include_stale: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return [node.__dict__ for node in RuntimeNodeStore().list_all(include_stale=include_stale)]
