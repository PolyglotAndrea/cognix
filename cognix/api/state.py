"""Shared API runtime state and helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from cognix.core.agent import Agent
from cognix.core.events import EventBus
from cognix.core.memory import SQLiteBackend
from cognix.core.registry import AgentRegistry
from cognix.scheduler.dispatcher import DistributedTaskDispatcher
from cognix.scheduler.engine import SchedulerEngine
from cognix.scheduler.executor import TaskExecutor
from cognix.scheduler.schedules import parse_schedule
from cognix.scheduler.store import TaskStore
from cognix.storage.models import AgentModel, TaskState

logger = logging.getLogger(__name__)

event_bus = EventBus()
agent_registry = AgentRegistry(event_bus=event_bus)
scheduler_engine: SchedulerEngine | None = None
task_dispatcher: DistributedTaskDispatcher | None = None
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
        permission_mode=getattr(row, "permission_mode", "workspace-write"),
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


async def list_agent_runtimes() -> list[dict[str, Any]]:
    """List persisted agents and hydrate any missing local runtime instances."""
    from sqlalchemy import select

    from cognix.storage.database import get_session

    async with get_session() as session:
        result = await session.execute(select(AgentModel).order_by(AgentModel.created_at.desc()))
        agents = []
        for row in result.scalars():
            agent = agent_registry.get(row.id) or agent_from_model(row)
            if not agent_registry.get(row.id):
                agent_registry.register(agent)
            agents.append(agent.to_dict())
        return agents


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


def schedule_task_in_engine(
    engine: SchedulerEngine,
    task_id: str,
    schedule: str,
    payload: dict[str, Any],
    name: str = "",
) -> None:
    """Register a task with the in-process scheduler."""
    schedule_type, value = parse_schedule(schedule)
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
    from cognix.config import get_settings

    global scheduler_engine, task_dispatcher
    settings = get_settings().scheduler
    engine = SchedulerEngine()
    executor = TaskExecutor(agent_registry=agent_registry)
    engine.retry_base_seconds = settings.retry_base_seconds
    engine.retry_max_seconds = settings.retry_max_seconds
    engine.set_executor(executor)
    await restore_active_tasks(engine)
    engine.start()
    task_dispatcher = DistributedTaskDispatcher(
        executor=executor,
        node_id=engine.node_id,
        poll_interval=settings.dispatcher_poll_interval,
        batch_size=settings.dispatcher_batch_size,
        max_concurrent=settings.dispatcher_max_concurrent,
        lease_ttl_seconds=settings.dispatcher_lease_ttl_seconds,
        retry_base_seconds=settings.retry_base_seconds,
        retry_max_seconds=settings.retry_max_seconds,
    )
    task_dispatcher.start()
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
    import os

    os.environ["COGNIX_RUNTIME_NODE_ID"] = node.id
    runtime_heartbeat_task = asyncio.create_task(_heartbeat_runtime_node(node.id))
    return node.id


async def _heartbeat_runtime_node(node_id: str) -> None:
    from cognix.local.runtime import RuntimeNodeStore

    store = RuntimeNodeStore()
    while True:
        store.heartbeat(node_id, metadata=_runtime_node_metadata())
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


def get_task_dispatcher() -> DistributedTaskDispatcher | None:
    return task_dispatcher


def _runtime_node_metadata() -> dict[str, Any]:
    scheduler = get_scheduler_engine()
    dispatcher = get_task_dispatcher()
    return {
        "scheduler_running": bool(scheduler and scheduler.running),
        "scheduler_jobs": len(scheduler.list_jobs()) if scheduler else 0,
        "dispatcher": dispatcher.status() if dispatcher else None,
    }


def set_scheduler_engine(engine: SchedulerEngine | None) -> None:
    global scheduler_engine
    scheduler_engine = engine


async def shutdown_scheduler() -> None:
    global scheduler_engine, task_dispatcher
    if task_dispatcher:
        await task_dispatcher.stop()
        task_dispatcher = None
    if scheduler_engine:
        scheduler_engine.shutdown()
        scheduler_engine = None
