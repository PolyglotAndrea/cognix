"""Shared API runtime state and helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from cognix.core.agent import Agent
from cognix.core.events import EventBus
from cognix.core.memory import SQLiteBackend
from cognix.core.registry import AgentRegistry
from cognix.scheduler.engine import SchedulerEngine
from cognix.scheduler.executor import TaskExecutor
from cognix.scheduler.store import TaskStore
from cognix.storage.models import AgentModel, TaskState

logger = logging.getLogger(__name__)

event_bus = EventBus()
agent_registry = AgentRegistry(event_bus=event_bus)
scheduler_engine: SchedulerEngine | None = None
runtime_node_id: str | None = None
runtime_heartbeat_task: asyncio.Task | None = None


def agent_from_model(row: AgentModel) -> Agent:
    """Build a runtime Agent from persisted configuration."""
    return Agent(
        id=row.id,
        name=row.name,
        model=row.model,
        system_prompt=row.system_prompt,
        temperature=row.temperature,
        max_iterations=row.max_iterations,
        description=row.description,
        api_base=row.api_base,
        workspace_id=getattr(row, "workspace_id", None),
        memory=SQLiteBackend(agent_id=row.id),
    )


async def load_agents_from_db() -> None:
    """Load persisted agents into the local process registry."""
    from sqlalchemy import select

    from cognix.storage.database import get_session

    async with get_session() as session:
        result = await session.execute(select(AgentModel))
        for row in result.scalars():
            agent_registry.register(agent_from_model(row))


async def get_agent_runtime(agent_id: str) -> Agent | None:
    """Get an agent from this process or lazily hydrate it from the DB.

    This keeps REST/RPC calls workable across multiple server workers, where each
    process has its own in-memory registry.
    """
    agent = agent_registry.get(agent_id) or agent_registry.get_by_name(agent_id)
    if agent:
        return agent

    from sqlalchemy import or_, select

    from cognix.storage.database import get_session

    async with get_session() as session:
        result = await session.execute(
            select(AgentModel).where(or_(AgentModel.id == agent_id, AgentModel.name == agent_id))
        )
        row = result.scalar_one_or_none()

    if not row:
        return None

    agent = agent_from_model(row)
    agent_registry.register(agent)
    return agent


def _parse_schedule(schedule: str) -> tuple[str, Any]:
    """Parse a persisted schedule into an engine schedule type and value."""
    schedule = schedule.strip()
    if " " in schedule and len(schedule.split()) == 5:
        return "cron", schedule
    if schedule.startswith("every "):
        parts = schedule.split()
        val = int(parts[1][:-1])
        unit = parts[1][-1]
        seconds = val * {"s": 1, "m": 60, "h": 3600}.get(unit, 1)
        return "interval", seconds
    return "once", datetime.fromisoformat(schedule)


def schedule_task_in_engine(
    engine: SchedulerEngine,
    task_id: str,
    schedule: str,
    payload: dict[str, Any],
    name: str = "",
) -> None:
    """Register a task with the in-process scheduler."""
    schedule_type, value = _parse_schedule(schedule)
    if schedule_type == "cron":
        engine.add_cron(task_id, value, payload, name=name)
    elif schedule_type == "interval":
        engine.add_interval(task_id, value, payload, name=name)
    else:
        engine.add_once(task_id, value, payload, name=name)


async def restore_active_tasks(engine: SchedulerEngine) -> None:
    """Register active persisted tasks with the scheduler on server startup."""
    store = TaskStore()
    tasks = await store.list_all(state=TaskState.ACTIVE)
    for task in tasks:
        try:
            payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload
            if task.task_type and "task_type" not in payload:
                payload["task_type"] = task.task_type.value
            schedule_task_in_engine(engine, task.id, task.schedule, payload, name=task.name)
        except Exception as exc:
            logger.warning("Failed to restore scheduled task %s: %s", task.id, exc)


async def start_scheduler() -> SchedulerEngine:
    """Create, configure, restore, and start the process scheduler."""
    global scheduler_engine
    engine = SchedulerEngine()
    engine.set_executor(TaskExecutor(agent_registry=agent_registry))
    await restore_active_tasks(engine)
    engine.start()
    scheduler_engine = engine
    return engine


async def start_runtime_node() -> str:
    """Register this API process in the local runtime node registry."""
    global runtime_node_id, runtime_heartbeat_task

    from cognix.local.runtime import RuntimeNodeStore

    store = RuntimeNodeStore()
    node = store.register_current(
        role="api",
        capabilities=["rest", "rpc", "websocket", "scheduler", "agent-runtime"],
    )
    runtime_node_id = node.id
    runtime_heartbeat_task = asyncio.create_task(_heartbeat_runtime_node(node.id))
    return node.id


async def _heartbeat_runtime_node(node_id: str) -> None:
    from cognix.local.runtime import RuntimeNodeStore

    store = RuntimeNodeStore()
    while True:
        store.heartbeat(node_id)
        await asyncio.sleep(30)


async def shutdown_runtime_node() -> None:
    global runtime_node_id, runtime_heartbeat_task

    if runtime_heartbeat_task:
        runtime_heartbeat_task.cancel()
        try:
            await runtime_heartbeat_task
        except asyncio.CancelledError:
            pass
        runtime_heartbeat_task = None

    if runtime_node_id:
        from cognix.local.runtime import RuntimeNodeStore

        RuntimeNodeStore().mark_status(runtime_node_id, "offline")
        runtime_node_id = None


def get_scheduler_engine() -> SchedulerEngine | None:
    return scheduler_engine


def set_scheduler_engine(engine: SchedulerEngine | None) -> None:
    global scheduler_engine
    scheduler_engine = engine


async def shutdown_scheduler() -> None:
    global scheduler_engine
    if scheduler_engine:
        scheduler_engine.shutdown()
        scheduler_engine = None
