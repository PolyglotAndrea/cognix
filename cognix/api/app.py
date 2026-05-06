"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from cognix import __version__
from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.core.events import EventBus
from cognix.core.registry import AgentRegistry

# Shared state
event_bus = EventBus()
agent_registry = AgentRegistry(event_bus=event_bus)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown."""
    from cognix.storage.database import init_db

    await init_db()
    # Load persisted agents from DB
    await _load_agents_from_db()
    yield
    from cognix.storage.database import close_db

    await close_db()


async def _load_agents_from_db() -> None:
    """Load agents from database into the registry on startup."""
    from sqlalchemy import select

    from cognix.core.agent import Agent
    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    async with get_session() as session:
        result = await session.execute(select(AgentModel))
        for row in result.scalars():
            agent = Agent(
                id=row.id,
                name=row.name,
                model=row.model,
                system_prompt=row.system_prompt,
                temperature=row.temperature,
                max_iterations=row.max_iterations,
                description=row.description,
            )
            agent_registry.register(agent)


app = FastAPI(
    title="Cognix",
    description="Hermes Agent-based multi-agent collaboration platform",
    version=__version__,
    lifespan=lifespan,
)

# Include auth routes
from cognix.api.routes.auth import router as auth_router
from cognix.api.routes.billing import router as billing_router

app.include_router(auth_router)
app.include_router(billing_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "cognix",
        "version": __version__,
        "docs": "/docs",
    }


# ── Schemas ─────────────────────────────────────────────────────────


class CreateAgentRequest(BaseModel):
    name: str
    model: str = "gpt-4o"
    system_prompt: str = "You are a helpful assistant."
    description: str = ""
    temperature: float = 0.7
    max_iterations: int = 10
    api_base: str | None = None


class ChatRequest(BaseModel):
    message: str


# ── Agent routes ────────────────────────────────────────────────────


@app.get("/api/v1/agents")
async def list_agents(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return agent_registry.list_all()


@app.post("/api/v1/agents", status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.core.agent import Agent
    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    agent = Agent(
        name=body.name,
        model=body.model,
        system_prompt=body.system_prompt,
        description=body.description,
        temperature=body.temperature,
        max_iterations=body.max_iterations,
        api_base=body.api_base,
    )
    agent_registry.register(agent)

    # Persist to DB
    async with get_session() as session:
        db_agent = AgentModel(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            model=agent.model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            max_iterations=agent.max_iterations,
            api_base=body.api_base,
        )
        session.add(db_agent)

    return agent.to_dict()


@app.get("/api/v1/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent.to_dict()


@app.delete("/api/v1/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    if not agent_registry.unregister(agent_id):
        raise HTTPException(404, "Agent not found")

    # Remove from DB
    from sqlalchemy import delete

    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    async with get_session() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent_id))

    return {"deleted": agent_id}


@app.post("/api/v1/agents/{agent_id}/chat")
async def agent_chat(
    agent_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    response = await agent.run(body.message)
    return {"content": response.content, "usage": response.usage}


@app.post("/api/v1/agents/{agent_id}/chat/stream")
async def agent_chat_stream(
    agent_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """SSE streaming endpoint for agent chat."""
    from starlette.responses import StreamingResponse

    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    async def event_generator():
        async for chunk in agent.stream(body.message):
            import json

            data = json.dumps({"delta": chunk.delta, "finish_reason": chunk.finish_reason})
            yield f"data: {data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.websocket("/ws/agents/{agent_id}/chat")
async def agent_chat_ws(websocket: WebSocket, agent_id: str) -> None:
    """WebSocket endpoint for agent chat with streaming."""
    await websocket.accept()

    agent = agent_registry.get(agent_id)
    if not agent:
        await websocket.send_json({"error": "Agent not found"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            async for chunk in agent.stream(message):
                await websocket.send_json(
                    {"delta": chunk.delta, "finish_reason": chunk.finish_reason}
                )

            await websocket.send_json({"type": "done"})
    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()


# ── Task schemas ────────────────────────────────────────────────────


class CreateTaskRequest(BaseModel):
    name: str
    task_type: str = "agent_call"  # agent_call, rpc_call, http_webhook, workflow
    schedule: str  # cron expression or ISO datetime
    payload: dict = {}
    max_retries: int = 3


# ── Task routes ─────────────────────────────────────────────────────


@app.post("/api/v1/tasks", status_code=201)
async def create_task(
    body: CreateTaskRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a scheduled task."""
    import uuid

    from cognix.scheduler.engine import SchedulerEngine
    from cognix.scheduler.store import TaskStore
    from cognix.storage.models import TaskType

    task_id = uuid.uuid4().hex[:12]
    store = TaskStore()

    # Parse schedule type
    schedule = body.schedule.strip()
    payload = {**body.payload, "task_type": body.task_type}

    # Create in DB
    task_type = TaskType(body.task_type)
    await store.create(
        task_id=task_id,
        name=body.name,
        task_type=task_type,
        schedule=schedule,
        payload=payload,
        max_retries=body.max_retries,
    )

    # Register with scheduler engine if available
    engine = _get_scheduler_engine()
    if engine:
        try:
            # Detect schedule type
            if " " in schedule and len(schedule.split()) == 5:
                engine.add_cron(task_id, schedule, payload, name=body.name)
            elif schedule.startswith("every "):
                # Simple interval parsing: "every 30s", "every 5m", "every 1h"
                parts = schedule.split()
                val = int(parts[1][:-1])
                unit = parts[1][-1]
                seconds = val * {"s": 1, "m": 60, "h": 3600}.get(unit, 1)
                engine.add_interval(task_id, seconds, payload, name=body.name)
            else:
                # Try ISO datetime
                from datetime import datetime

                run_at = datetime.fromisoformat(schedule)
                engine.add_once(task_id, run_at, payload, name=body.name)
        except Exception as e:
            logger.warning("Failed to schedule task in engine: %s", e)

    return {
        "id": task_id,
        "name": body.name,
        "task_type": body.task_type,
        "schedule": schedule,
        "state": "active",
    }


@app.get("/api/v1/tasks")
async def list_tasks(
    state: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List scheduled tasks."""
    from cognix.scheduler.store import TaskStore
    from cognix.storage.models import TaskState

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
            "last_run": t.last_run.isoformat() if t.last_run else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@app.get("/api/v1/tasks/{task_id}")
async def get_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get task details."""
    from cognix.scheduler.store import TaskStore

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
        "state": task.state.value,
        "run_count": task.run_count,
        "max_retries": task.max_retries,
        "last_run": task.last_run.isoformat() if task.last_run else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@app.delete("/api/v1/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Delete a scheduled task."""
    from cognix.scheduler.store import TaskStore

    store = TaskStore()

    # Remove from scheduler engine
    engine = _get_scheduler_engine()
    if engine:
        engine.remove(task_id)

    # Remove from DB
    if not await store.delete(task_id):
        raise HTTPException(404, "Task not found")

    return {"deleted": task_id}


@app.post("/api/v1/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Pause a scheduled task."""
    from cognix.scheduler.store import TaskStore

    store = TaskStore()
    if not await store.update_state(task_id, "paused"):
        raise HTTPException(404, "Task not found")

    engine = _get_scheduler_engine()
    if engine:
        engine.pause(task_id)

    return {"id": task_id, "state": "paused"}


@app.post("/api/v1/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Resume a paused task."""
    from cognix.scheduler.store import TaskStore

    store = TaskStore()
    if not await store.update_state(task_id, "active"):
        raise HTTPException(404, "Task not found")

    engine = _get_scheduler_engine()
    if engine:
        engine.resume(task_id)

    return {"id": task_id, "state": "active"}


@app.post("/api/v1/tasks/{task_id}/trigger")
async def trigger_task(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Immediately trigger a task."""
    from cognix.scheduler.executor import TaskExecutor
    from cognix.scheduler.store import TaskStore

    store = TaskStore()
    task = await store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    import json

    payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload
    executor = TaskExecutor(agent_registry=agent_registry)
    result = await executor.execute(task_id, payload)

    return result


@app.get("/api/v1/tasks/{task_id}/runs")
async def get_task_runs(
    task_id: str,
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Get task execution history."""
    from cognix.scheduler.store import TaskStore

    store = TaskStore()
    runs = await store.get_runs(task_id, limit=limit)

    return [
        {
            "id": r.id,
            "status": r.status,
            "result": r.result[:200] if r.result else "",
            "error": r.error,
            "duration_ms": r.duration_ms,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in runs
    ]


# ── Helpers ─────────────────────────────────────────────────────────

_scheduler_engine = None


def _get_scheduler_engine():
    """Get or create the global scheduler engine."""
    global _scheduler_engine
    return _scheduler_engine


def set_scheduler_engine(engine):
    """Set the global scheduler engine."""
    global _scheduler_engine
    _scheduler_engine = engine


# ── RPC endpoint ────────────────────────────────────────────────────


@app.post("/rpc")
async def rpc_endpoint(body: dict) -> dict:
    """JSON-RPC 2.0 endpoint."""
    from cognix.rpc.server import handle_rpc

    return await handle_rpc(body, agent_registry)
