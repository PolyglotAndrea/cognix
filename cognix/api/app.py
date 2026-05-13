"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cognix import __version__
from cognix.api.routes.agents import agent_chat_ws
from cognix.api.routes.agents import router as agents_router
from cognix.api.routes.approvals import router as approvals_router
from cognix.api.routes.artifacts import router as artifacts_router
from cognix.api.routes.auth import router as auth_router
from cognix.api.routes.billing import router as billing_router
from cognix.api.routes.bots import router as bots_router
from cognix.api.routes.connectors import router as connectors_router
from cognix.api.routes.memory import router as memory_router
from cognix.api.routes.planner import router as planner_router
from cognix.api.routes.rpc import router as rpc_router
from cognix.api.routes.runtime import router as runtime_router
from cognix.api.routes.settings import router as settings_router
from cognix.api.routes.skills import router as skills_router
from cognix.api.routes.tasks import router as tasks_router
from cognix.api.routes.workspaces import router as workspaces_router
from cognix.api.state import (
    agent_registry,
    event_bus,
    load_agents_from_db,
    set_scheduler_engine,
    shutdown_runtime_node,
    shutdown_scheduler,
    start_runtime_node,
    start_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: database, runtime registry, and scheduler."""
    import asyncio
    import logging

    from cognix.storage.database import close_db, init_db

    logger = logging.getLogger(__name__)

    await init_db()
    await load_agents_from_db()
    await start_runtime_node()
    await start_scheduler()

    # Auto-compress memory background task
    compress_task: asyncio.Task | None = None

    async def _auto_compress_loop() -> None:
        from cognix.config import get_settings
        from cognix.local.home import CognixHome
        from cognix.memory.pipeline import ColdMemoryStore

        settings = get_settings().memory
        if not settings.auto_compress_enabled:
            return
        interval = settings.auto_compress_interval_hours * 3600
        while True:
            await asyncio.sleep(interval)
            try:
                store = ColdMemoryStore(CognixHome.default().ensure().state_db)
                compressed = await store.compress()
                if compressed:
                    logger.info("Auto-compressed %d cold memories", len(compressed))
            except Exception:
                logger.exception("Auto-compress failed")

    compress_task = asyncio.create_task(_auto_compress_loop())

    try:
        yield
    finally:
        if compress_task:
            compress_task.cancel()
            try:
                await compress_task
            except asyncio.CancelledError:
                pass
        await shutdown_runtime_node()
        await shutdown_scheduler()
        await close_db()


app = FastAPI(
    title="Cognix",
    description="Hermes Agent-based multi-agent collaboration platform",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(approvals_router)
app.include_router(artifacts_router)
app.include_router(billing_router)
app.include_router(connectors_router)
app.include_router(bots_router)
app.include_router(memory_router)
app.include_router(settings_router)
app.include_router(planner_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(skills_router)
app.include_router(workspaces_router)
app.include_router(rpc_router)
app.include_router(runtime_router)
app.websocket("/ws/agents/{agent_id}/chat")(agent_chat_ws)


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


__all__ = ["app", "agent_registry", "event_bus", "set_scheduler_engine"]
