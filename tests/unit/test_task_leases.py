"""Tests for distributed task lease helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


@pytest.mark.asyncio
async def test_task_store_claims_due_tasks_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    try:
        store = TaskStore()
        now = datetime.now(UTC)
        await store.create(
            task_id="due",
            name="Due",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"task_type": "agent_call"},
        )
        await store.create(
            task_id="future",
            name="Future",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"task_type": "agent_call"},
        )
        await store.set_next_run("due", now - timedelta(seconds=1))
        await store.set_next_run("future", now + timedelta(minutes=5))

        claimed = await store.claim_due_tasks(owner="node-a", now=now)
        assert [task.id for task in claimed] == ["due"]
        assert claimed[0].lease_owner == "node-a"
        assert await store.extend_lease("due", owner="node-a") is True
        assert await store.extend_lease("due", owner="node-b") is False

        assert await store.claim_due_tasks(owner="node-b", now=now) == []
        assert await store.release_lease("due", owner="node-a") is True
        claimed_again = await store.claim_due_tasks(owner="node-b", now=now)
        assert [task.id for task in claimed_again] == ["due"]
    finally:
        await close_db()
