"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cognix import __version__
from cognix.api.routes.agents import agent_chat_ws
from cognix.api.routes.agents import router as agents_router
from cognix.api.routes.auth import router as auth_router
from cognix.api.routes.billing import router as billing_router
from cognix.api.routes.bots import router as bots_router
from cognix.api.routes.rpc import router as rpc_router
from cognix.api.routes.skills import router as skills_router
from cognix.api.routes.tasks import router as tasks_router
from cognix.api.routes.workspaces import router as workspaces_router
from cognix.api.state import (
    agent_registry,
    event_bus,
    load_agents_from_db,
    set_scheduler_engine,
    shutdown_scheduler,
    start_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: database, runtime registry, and scheduler."""
    from cognix.storage.database import close_db, init_db

    await init_db()
    await load_agents_from_db()
    await start_scheduler()
    try:
        yield
    finally:
        await shutdown_scheduler()
        await close_db()


app = FastAPI(
    title="Cognix",
    description="Hermes Agent-based multi-agent collaboration platform",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(bots_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(skills_router)
app.include_router(workspaces_router)
app.include_router(rpc_router)
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
