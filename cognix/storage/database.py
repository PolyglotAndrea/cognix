"""Database connection management."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cognix.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_engine_url: str | None = None
_session_factory = None


def _configured_database_url() -> str:
    """Resolve the current database URL, honoring test/runtime env overrides."""
    return os.environ.get("COGNIX_DATABASE__URL") or get_settings().database.url


def get_engine():
    """Get or create the async SQLAlchemy engine."""
    global _engine, _engine_url, _session_factory
    database_url = _configured_database_url()
    if _engine is None or _engine_url != database_url:
        settings = get_settings()
        _engine = create_async_engine(
            database_url,
            echo=settings.database.echo,
        )
        _engine_url = database_url
        _session_factory = None
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
        await _ensure_task_lease_columns(conn)
        await _ensure_task_run_columns(conn)
        await _ensure_connector_credentials_table(conn)
        await _ensure_artifact_columns(conn)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close database connections."""
    global _engine, _engine_url, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _engine_url = None
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


async def _ensure_task_lease_columns(conn) -> None:
    """Add lightweight distributed scheduling lease columns for existing DBs."""

    def _columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("scheduled_tasks")}

    columns = await conn.run_sync(_columns)
    additions = {
        "user_id": "VARCHAR(36)",
        "lease_owner": "VARCHAR(128)",
        "lease_expires_at": "DATETIME",
        "max_execution_seconds": "INTEGER DEFAULT 300",
        "idempotency_key": "VARCHAR(64)",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            await conn.execute(text(f"ALTER TABLE scheduled_tasks ADD COLUMN {column} {ddl_type}"))


async def _ensure_task_run_columns(conn) -> None:
    """Add lightweight task run columns for existing DBs."""

    def _columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("task_runs")}

    columns = await conn.run_sync(_columns)
    additions = {
        "user_id": "VARCHAR(36)",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            await conn.execute(text(f"ALTER TABLE task_runs ADD COLUMN {column} {ddl_type}"))


async def _ensure_connector_credentials_table(conn) -> None:
    """Create the connector_credentials table if it doesn't exist (handled by create_all),
    and add any lightweight schema migrations for existing databases."""

    def _table_exists(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        return "connector_credentials" in inspector.get_table_names()

    exists = await conn.run_sync(_table_exists)
    if not exists:
        # Table will be created by Base.metadata.create_all above
        return

    def _columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("connector_credentials")}

    columns = await conn.run_sync(_columns)
    additions = {
        "workspace_id": "VARCHAR(64)",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            sql = (
                f"ALTER TABLE connector_credentials"
                f" ADD COLUMN {column} {ddl_type}"
            )
            await conn.execute(text(sql))


async def _ensure_artifact_columns(conn) -> None:
    """Add versioning, status, source columns to artifacts table."""

    def _columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        return {column["name"] for column in inspector.get_columns("artifacts")}

    columns = await conn.run_sync(_columns)
    additions = {
        "version": "INTEGER DEFAULT 1",
        "parent_id": "VARCHAR(32)",
        "status": "VARCHAR(32) DEFAULT 'draft'",
        "source": "VARCHAR(32) DEFAULT 'manual'",
        "context_type": "VARCHAR(32)",
    }
    for column, ddl_type in additions.items():
        if column not in columns:
            await conn.execute(
                text(f"ALTER TABLE artifacts ADD COLUMN {column} {ddl_type}")
            )
