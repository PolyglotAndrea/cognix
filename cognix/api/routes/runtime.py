"""Runtime node REST routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cognix.api.state import get_scheduler_engine, get_task_dispatcher, runtime_node_id
from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.local.runtime import RuntimeNodeStore
from cognix.scheduler.store import TaskStore
from cognix.storage.models import TaskState

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
        "dispatcher": dispatcher.status() if dispatcher else None,
    }


@router.get("/active-tasks")
async def list_active_tasks(user: CurrentUser = Depends(get_current_user)) -> dict:
    """List currently leased (running) tasks across all nodes."""
    store = TaskStore()
    tasks = await store.list_all(state=TaskState.ACTIVE)
    leased = [
        {
            "id": t.id,
            "name": t.name,
            "task_type": t.task_type.value if t.task_type else None,
            "lease_owner": t.lease_owner,
            "lease_expires_at": t.lease_expires_at.isoformat() if t.lease_expires_at else None,
            "run_count": t.run_count,
            "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        }
        for t in tasks
        if t.lease_owner
    ]
    return {
        "leased_count": len(leased),
        "tasks": leased,
    }


@router.get("/cluster-capacity")
async def cluster_capacity(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Aggregate capacity across all registered runtime nodes."""
    nodes = RuntimeNodeStore().list_all(include_stale=True)
    dispatcher = get_task_dispatcher()
    local_status = dispatcher.status() if dispatcher else {}
    return {
        "nodes": [
            {
                "node_id": n.id,
                "status": n.status,
                "last_seen": (
                    n.last_seen.isoformat() if hasattr(n, "last_seen") and n.last_seen else None
                ),
                "metadata": n.metadata if hasattr(n, "metadata") else {},
            }
            for n in nodes
        ],
        "local_node": {
            "node_id": runtime_node_id,
            "max_concurrent": local_status.get("max_concurrent", 0),
            "active_count": local_status.get("active_count", 0),
            "active_task_ids": local_status.get("active_task_ids", []),
            "metrics": local_status.get("metrics", {}),
        },
    }


# ── Worker node management ─────────────────────────────────────


@router.get("/workers")
async def list_workers(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List registered worker nodes with their load and status."""
    from cognix.scheduler.registry import WorkerRegistry

    registry = WorkerRegistry()
    return await registry.list_all()


@router.post("/workers/{node_id}/drain")
async def drain_worker(
    node_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Gracefully drain a worker node (stop receiving new tasks)."""
    from cognix.scheduler.registry import WorkerRegistry

    registry = WorkerRegistry()
    await registry.drain_node(node_id)
    return {"node_id": node_id, "status": "draining"}
