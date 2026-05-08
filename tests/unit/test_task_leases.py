"""Tests for distributed task lease helpers."""

from __future__ import annotations

import pytest

from cognix.scheduler.store import TaskStore
from cognix.storage.database import close_db, init_db
from cognix.storage.models import TaskType


@pytest.mark.asyncio
async def test_task_store_acquires_and_releases_leases(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    try:
        store = TaskStore()
        await store.create(
            task_id="task-1",
            name="Task",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"task_type": "agent_call"},
        )

        assert await store.acquire_lease("task-1", owner="node-a") is True
        assert await store.acquire_lease("task-1", owner="node-b") is False
        assert await store.release_lease("task-1", owner="node-b") is False
        assert await store.release_lease("task-1", owner="node-a") is True
        assert await store.acquire_lease("task-1", owner="node-b") is True
    finally:
        await close_db()
