"""Scheduled task REST routes."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cognix.api.state import agent_registry, get_scheduler_engine, schedule_task_in_engine
from cognix.auth.dependencies import (
    CurrentUser,
    require_tasks_read,
    require_tasks_write,
)
from cognix.scheduler.store import TaskStore
from cognix.storage.models import TaskState, TaskType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    name: str
    task_type: str = "agent_call"
    schedule: str
    payload: dict = Field(default_factory=dict)
    max_retries: int = 3
    max_execution_seconds: int = 300
    idempotency_key: str | None = None


@router.post("", status_code=201)
async def create_task(
    body: CreateTaskRequest,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    task_id = uuid.uuid4().hex[:12]
    store = TaskStore()
    schedule = body.schedule.strip()
    payload = {**body.payload, "task_type": body.task_type}
    task_type = TaskType(body.task_type)

    await store.create(
        task_id=task_id,
        name=body.name,
        task_type=task_type,
        schedule=schedule,
        payload=payload,
        max_retries=body.max_retries,
        max_execution_seconds=body.max_execution_seconds,
        idempotency_key=body.idempotency_key or payload.get("idempotency_key"),
    )

    engine = get_scheduler_engine()
    if engine:
        try:
            schedule_task_in_engine(engine, task_id, schedule, payload, name=body.name)
        except Exception as e:
            logger.warning("Failed to schedule task in engine: %s", e)

    return {
        "id": task_id,
        "name": body.name,
        "task_type": body.task_type,
        "schedule": schedule,
        "state": "active",
    }


@router.get("")
async def list_tasks(
    state: str | None = None,
    user: CurrentUser = Depends(require_tasks_read),
) -> list[dict]:
    store = TaskStore()
    filter_state = TaskState(state) if state else None
    tasks = await store.list_all(state=filter_state)

    return [
        {
            "id": t.id,
            "name": t.name,
            "task_type": t.task_type.value,
            "schedule": t.schedule,
            "state": t.state.value,
            "run_count": t.run_count,
            "max_execution_seconds": t.max_execution_seconds,
            "workspace_id": _payload_dict(t.payload).get("workspace_id"),
            "last_run": t.last_run.isoformat() if t.last_run else None,
            "lease_owner": t.lease_owner,
            "lease_expires_at": t.lease_expires_at.isoformat() if t.lease_expires_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_read),
) -> dict:
    store = TaskStore()
    task = await store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    return {
        "id": task.id,
        "name": task.name,
        "task_type": task.task_type.value,
        "schedule": task.schedule,
        "payload": task.payload,
        "payload_json": _payload_dict(task.payload),
        "state": task.state.value,
        "run_count": task.run_count,
        "max_retries": task.max_retries,
        "max_execution_seconds": task.max_execution_seconds,
        "idempotency_key": task.idempotency_key,
        "last_run": task.last_run.isoformat() if task.last_run else None,
        "lease_owner": task.lease_owner,
        "lease_expires_at": task.lease_expires_at.isoformat() if task.lease_expires_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    store = TaskStore()
    engine = get_scheduler_engine()
    if engine:
        engine.remove(task_id)

    if not await store.delete(task_id):
        raise HTTPException(404, "Task not found")

    return {"deleted": task_id}


@router.post("/{task_id}/pause")
async def pause_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    store = TaskStore()
    if not await store.update_state(task_id, TaskState.PAUSED):
        raise HTTPException(404, "Task not found")

    engine = get_scheduler_engine()
    if engine:
        engine.pause(task_id)

    return {"id": task_id, "state": "paused"}


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    store = TaskStore()
    if not await store.update_state(task_id, TaskState.ACTIVE):
        raise HTTPException(404, "Task not found")

    task = await store.get(task_id)
    engine = get_scheduler_engine()
    if engine and task:
        payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload
        schedule_task_in_engine(engine, task.id, task.schedule, payload, name=task.name)
        engine.resume(task_id)

    return {"id": task_id, "state": "active"}


@router.post("/{task_id}/replay")
async def replay_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    """Replay a failed task — reset it to ACTIVE for immediate re-execution."""
    store = TaskStore()
    task = await store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.state != TaskState.FAILED:
        raise HTTPException(400, f"Task is {task.state.value}, not FAILED")

    if not await store.replay_failed(task_id):
        raise HTTPException(500, "Failed to replay task")

    engine = get_scheduler_engine()
    if engine:
        payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload
        try:
            schedule_task_in_engine(engine, task_id, task.schedule, payload, name=task.name)
        except Exception as e:
            logger.warning("Failed to reschedule replayed task in engine: %s", e)

    return {"id": task_id, "state": "active", "replayed": True}


@router.post("/{task_id}/trigger")
async def trigger_task(
    task_id: str,
    user: CurrentUser = Depends(require_tasks_write),
) -> dict:
    from cognix.scheduler.executor import TaskExecutor

    store = TaskStore()
    task = await store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload
    executor = TaskExecutor(agent_registry=agent_registry)
    return await executor.execute(task_id, payload)


@router.get("/{task_id}/runs")
async def get_task_runs(
    task_id: str,
    limit: int = 20,
    user: CurrentUser = Depends(require_tasks_read),
) -> list[dict]:
    store = TaskStore()
    runs = await store.get_runs(task_id, limit=limit)

    return [
        {
            "id": r.id,
            "status": r.status,
            "result": r.result[:2000] if r.result else "",
            "error": r.error,
            "duration_ms": r.duration_ms,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]


def _payload_dict(payload) -> dict:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload or {}
