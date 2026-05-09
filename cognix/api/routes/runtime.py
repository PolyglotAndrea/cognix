"""Runtime node REST routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cognix.api.state import get_scheduler_engine, get_task_dispatcher, runtime_node_id
from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.local.runtime import RuntimeNodeStore

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


@router.get("/nodes")
async def list_runtime_nodes(
    include_stale: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return [node.__dict__ for node in RuntimeNodeStore().list_all(include_stale=include_stale)]


@router.get("/status")
async def get_runtime_status(user: CurrentUser = Depends(get_current_user)) -> dict:
    scheduler = get_scheduler_engine()
    dispatcher = get_task_dispatcher()
    return {
        "node_id": runtime_node_id,
        "scheduler": {
            "running": bool(scheduler and scheduler.running),
            "node_id": scheduler.node_id if scheduler else None,
            "jobs": scheduler.list_jobs() if scheduler else [],
        },
        "dispatcher": {
            "running": bool(dispatcher and dispatcher.running),
            "node_id": dispatcher.node_id if dispatcher else None,
            "poll_interval": dispatcher.poll_interval if dispatcher else None,
            "batch_size": dispatcher.batch_size if dispatcher else None,
            "lease_ttl_seconds": dispatcher.lease_ttl_seconds if dispatcher else None,
        },
    }
