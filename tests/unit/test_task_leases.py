"""Tests for distributed task lease helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from cognix.scheduler.dispatcher import DistributedTaskDispatcher
from cognix.scheduler.store import TaskStore
from cognix.storage.database import close_db, get_session, init_db
from cognix.storage.models import ScheduledTaskModel, TaskState, TaskType


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


@pytest.mark.asyncio
async def test_distributed_dispatcher_executes_claimed_due_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    try:
        store = TaskStore()
        await store.create(
            task_id="dispatch-task-1",
            name="Task",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"message": "hi"},
        )
        await store.set_next_run("dispatch-task-1", datetime.now(UTC) - timedelta(seconds=1))
        calls = []

        class FakeExecutor:
            async def execute(self, task_id, payload):
                calls.append((task_id, payload))

        dispatcher = DistributedTaskDispatcher(
            executor=FakeExecutor(),
            store=store,
            node_id="node-a",
        )

        assert await dispatcher.dispatch_once() == 1
        assert calls == [("dispatch-task-1", {"message": "hi", "task_type": "agent_call"})]
        assert dispatcher.status()["metrics"]["claimed_total"] == 1
        assert dispatcher.status()["metrics"]["success_total"] == 1
        task = await store.get("dispatch-task-1")
        assert task.lease_owner is None
        assert task.next_run is not None
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_distributed_dispatcher_retries_failed_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    try:
        store = TaskStore()
        await store.create(
            task_id="retry-task",
            name="Retry",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"message": "hi"},
            max_retries=2,
        )
        due_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        await store.set_next_run("retry-task", due_at)

        class FailingExecutor:
            async def execute(self, task_id, payload):
                async with get_session() as session:
                    await session.execute(
                        update(ScheduledTaskModel)
                        .where(ScheduledTaskModel.id == task_id)
                        .values(run_count=ScheduledTaskModel.run_count + 1)
                    )
                return {"status": "failure", "error": "boom"}

        dispatcher = DistributedTaskDispatcher(
            executor=FailingExecutor(),
            store=store,
            node_id="node-a",
            retry_base_seconds=5,
        )

        assert await dispatcher.dispatch_once() == 1
        assert dispatcher.status()["metrics"]["failure_total"] == 1
        assert dispatcher.status()["metrics"]["retry_scheduled_total"] == 1
        task = await store.get("retry-task")
        assert task.state == TaskState.ACTIVE
        assert task.lease_owner is None
        assert task.next_run is not None
        assert task.next_run > due_at
        assert task.run_count == 1
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_distributed_dispatcher_marks_exhausted_retry_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    try:
        store = TaskStore()
        await store.create(
            task_id="exhausted-task",
            name="Exhausted",
            task_type=TaskType.AGENT_CALL,
            schedule="every 1m",
            payload={"message": "hi"},
            max_retries=0,
        )
        await store.set_next_run("exhausted-task", datetime.now(UTC) - timedelta(seconds=1))

        class FailingExecutor:
            async def execute(self, task_id, payload):
                async with get_session() as session:
                    await session.execute(
                        update(ScheduledTaskModel)
                        .where(ScheduledTaskModel.id == task_id)
                        .values(run_count=ScheduledTaskModel.run_count + 1)
                    )
                return {"status": "failure", "error": "boom"}

        dispatcher = DistributedTaskDispatcher(
            executor=FailingExecutor(),
            store=store,
            node_id="node-a",
        )

        assert await dispatcher.dispatch_once() == 1
        assert dispatcher.status()["metrics"]["exhausted_failure_total"] == 1
        task = await store.get("exhausted-task")
        assert task.state == TaskState.FAILED
        assert task.lease_owner is None
        assert task.next_run is None
        assert task.run_count == 1
    finally:
        await close_db()
