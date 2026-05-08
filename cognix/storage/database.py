"""Database connection management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cognix.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_engine():
    """Get or create the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database.url,
            echo=settings.database.echo,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Context manager for a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize the database (create tables)."""
    from cognix.storage.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_agent_runtime_columns(conn)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def _ensure_agent_runtime_columns(conn) -> None:
    """Add lightweight Agent runtime columns for existing local databases."""

    def _columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("agents")}

    columns = await conn.run_sync(_columns)
    additions = {
        "workspace_id": "VARCHAR(64)",
        "permission_mode": "VARCHAR(32) DEFAULT 'workspace-write'",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            await conn.execute(text(f"ALTER TABLE agents ADD COLUMN {column} {ddl_type}"))
