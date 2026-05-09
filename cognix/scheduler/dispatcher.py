"""DB-backed distributed task dispatcher."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cognix.scheduler.executor import TaskExecutor
from cognix.scheduler.schedules import next_run_time
from cognix.scheduler.store import TaskStore
from cognix.storage.models import ScheduledTaskModel, TaskState

logger = logging.getLogger(__name__)


class DistributedTaskDispatcher:
    """Polls the task table, leases due tasks, and executes claimed work."""

    def __init__(
        self,
        *,
        executor: TaskExecutor,
        store: TaskStore | None = None,
        node_id: str | None = None,
        poll_interval: float = 5.0,
        batch_size: int = 10,
        lease_ttl_seconds: int = 120,
        retry_base_seconds: int = 30,
        retry_max_seconds: int = 3600,
    ) -> None:
        self.executor = executor
        self.store = store or TaskStore()
        self.node_id = (
            node_id
            or os.environ.get("COGNIX_RUNTIME_NODE_ID")
            or f"dispatcher-{uuid.uuid4().hex[:8]}"
        )
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.lease_ttl_seconds = lease_ttl_seconds
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.metrics: dict[str, Any] = {
            "claimed_total": 0,
            "success_total": 0,
            "failure_total": 0,
            "retry_scheduled_total": 0,
            "exhausted_failure_total": 0,
            "last_dispatch_at": None,
            "last_error": "",
        }
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def dispatch_once(self) -> int:
        claimed = await self.store.claim_due_tasks(
            owner=self.node_id,
            limit=self.batch_size,
            ttl_seconds=self.lease_ttl_seconds,
            now=datetime.now(UTC),
        )
        if not claimed:
            return 0
        self.metrics["claimed_total"] += len(claimed)
        self.metrics["last_dispatch_at"] = datetime.now(UTC).isoformat()
        await asyncio.gather(*(self._run_claimed(task) for task in claimed))
        return len(claimed)

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.dispatch_once()
            except Exception:
                logger.exception("Distributed task dispatch cycle failed")
            await asyncio.sleep(self.poll_interval)

    async def _run_claimed(self, task: ScheduledTaskModel) -> None:
        payload = _payload_dict(task.payload)
        if task.task_type and "task_type" not in payload:
            payload["task_type"] = task.task_type.value
        try:
            run = await self.executor.execute(task.id, payload) or {}
        except Exception as exc:
            logger.exception("Task %s executor raised outside normal failure handling", task.id)
            self.metrics["last_error"] = str(exc)
            run = {"status": "failure", "error": str(exc)}
        task_after_run = await self.store.get(task.id)
        if run.get("status") == "failure" and task_after_run:
            self.metrics["failure_total"] += 1
            self.metrics["last_error"] = str(run.get("error", ""))
            await self._complete_failed_run(task_after_run)
            return

        self.metrics["success_total"] += 1
        await self.store.complete_lease(
            task.id,
            owner=self.node_id,
            next_run=next_run_time(task.schedule),
        )

    async def _complete_failed_run(self, task: ScheduledTaskModel) -> None:
        attempts = max(task.run_count, 1)
        if attempts <= task.max_retries:
            delay_seconds = min(
                self.retry_base_seconds * (2 ** (attempts - 1)),
                self.retry_max_seconds,
            )
            retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
            await self.store.complete_lease(
                task.id,
                owner=self.node_id,
                next_run=retry_at,
            )
            self.metrics["retry_scheduled_total"] += 1
            logger.warning(
                "Task %s failed; retry %s/%s scheduled in %ss",
                task.id,
                attempts,
                task.max_retries,
                delay_seconds,
            )
            return

        await self.store.complete_lease(
            task.id,
            owner=self.node_id,
            next_run=None,
            state=TaskState.FAILED,
        )
        self.metrics["exhausted_failure_total"] += 1
        logger.error("Task %s failed after %s attempts", task.id, attempts)

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "node_id": self.node_id,
            "poll_interval": self.poll_interval,
            "batch_size": self.batch_size,
            "lease_ttl_seconds": self.lease_ttl_seconds,
            "retry_base_seconds": self.retry_base_seconds,
            "retry_max_seconds": self.retry_max_seconds,
            "metrics": dict(self.metrics),
        }


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload or {}
