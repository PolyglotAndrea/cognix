"""Scheduler engine using APScheduler."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from cognix.scheduler.retry import compute_retry_at
from cognix.scheduler.schedules import next_run_time

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Manages scheduled tasks using APScheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, dict[str, Any]] = {}  # task_id -> job metadata
        self._executor: Any = None  # Set by set_executor
        self.node_id = (
            os.environ.get("COGNIX_RUNTIME_NODE_ID") or f"scheduler-{uuid.uuid4().hex[:8]}"
        )
        self.retry_base_seconds = 30
        self.retry_max_seconds = 3600

    def set_executor(self, executor: Any) -> None:
        """Set the task executor."""
        self._executor = executor

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown")

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def add_cron(
        self,
        task_id: str,
        cron_expr: str,
        payload: dict[str, Any],
        name: str = "",
    ) -> str:
        """Add a cron-scheduled task.

        Args:
            task_id: Unique task identifier
            cron_expr: Cron expression (5-field: minute hour day month day_of_week)
            payload: Task execution payload
            name: Human-readable task name

        Returns:
            The task ID
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression (expected 5 fields): {cron_expr}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )

        return self._add_job(task_id, trigger, payload, name)

    def add_interval(
        self,
        task_id: str,
        seconds: int,
        payload: dict[str, Any],
        name: str = "",
    ) -> str:
        """Add an interval-scheduled task."""
        trigger = IntervalTrigger(seconds=seconds)
        return self._add_job(task_id, trigger, payload, name)

    def add_once(
        self,
        task_id: str,
        run_at: datetime,
        payload: dict[str, Any],
        name: str = "",
    ) -> str:
        """Add a one-shot task to run at a specific time."""
        trigger = DateTrigger(run_date=run_at)
        return self._add_job(task_id, trigger, payload, name)

    def _add_job(self, task_id: str, trigger: Any, payload: dict[str, Any], name: str) -> str:
        """Internal: add a job to the scheduler."""
        job = self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task_id,
            kwargs={"task_id": task_id, "payload": payload},
            name=name or task_id,
            replace_existing=True,
        )

        self._jobs[task_id] = {
            "id": task_id,
            "name": name or task_id,
            "next_run": job.next_run_time,
            "trigger": str(trigger),
        }

        logger.info("Added job %s (next_run=%s)", task_id, job.next_run_time)
        return task_id

    def remove(self, task_id: str) -> bool:
        """Remove a scheduled task."""
        try:
            self._scheduler.remove_job(task_id)
            self._jobs.pop(task_id, None)
            logger.info("Removed job %s", task_id)
            return True
        except Exception:
            return False

    def pause(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        try:
            self._scheduler.pause_job(task_id)
            logger.info("Paused job %s", task_id)
            return True
        except Exception:
            return False

    def resume(self, task_id: str) -> bool:
        """Resume a paused task."""
        try:
            self._scheduler.resume_job(task_id)
            logger.info("Resumed job %s", task_id)
            return True
        except Exception:
            return False

    def get_job_info(self, task_id: str) -> dict[str, Any] | None:
        """Get info about a scheduled job."""
        job = self._scheduler.get_job(task_id)
        if not job:
            return None

        return {
            "id": task_id,
            "name": job.name,
            "next_run": job.next_run_time,
            "trigger": str(job.trigger),
            "pending": job.pending,
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger),
                "pending": job.pending,
            })
        return jobs

    async def _execute_task(self, task_id: str, payload: dict[str, Any]) -> None:
        """Execute a scheduled task."""
        logger.info("Executing task %s", task_id)

        if not self._executor:
            logger.error("No executor set for task %s", task_id)
            return

        from cognix.scheduler.store import TaskStore

        store = TaskStore()
        if not await store.acquire_lease(task_id, owner=self.node_id):
            logger.info("Task %s is leased by another runtime node", task_id)
            return

        task = await store.get(task_id)
        if task:
            idempotency_key = payload.get("idempotency_key") or task.idempotency_key
            if idempotency_key:
                should_execute = await store.check_idempotency(task_id, str(idempotency_key))
                if not should_execute:
                    logger.info(
                        "Skipping task %s; idempotency key %s already executed",
                        task_id,
                        idempotency_key,
                    )
                    await store.complete_lease(
                        task_id,
                        owner=self.node_id,
                        next_run=next_run_time(task.schedule),
                    )
                    return

        try:
            timeout = getattr(task, "max_execution_seconds", 300) if task else 300
            run = await asyncio.wait_for(
                self._executor.execute(task_id, payload),
                timeout=timeout or 300,
            ) or {}
        except TimeoutError:
            logger.exception("Task %s timed out", task_id)
            run = {
                "status": "failure",
                "error": f"Execution timed out after {timeout or 300}s",
            }
        except Exception as e:
            logger.exception("Task %s failed: %s", task_id, e)
            run = {"status": "failure", "error": str(e)}

        task = await store.get(task_id)
        if run.get("status") == "failure" and task:
            attempts = max(task.run_count, 1)
            if attempts <= task.max_retries:
                retry_at = compute_retry_at(
                    attempts, self.retry_base_seconds, self.retry_max_seconds,
                )
                await store.complete_lease(task_id, owner=self.node_id, next_run=retry_at)
                logger.warning(
                    "Task %s failed; scheduler retry %s/%s scheduled at %s",
                    task_id,
                    attempts,
                    task.max_retries,
                    retry_at.isoformat(),
                )
                return

            from cognix.storage.models import TaskState

            await store.complete_lease(
                task_id,
                owner=self.node_id,
                next_run=None,
                state=TaskState.FAILED,
            )
            logger.error("Task %s failed after %s scheduler attempts", task_id, attempts)
            return

        job = self._scheduler.get_job(task_id)
        next_run = job.next_run_time if job else None
        await store.complete_lease(task_id, owner=self.node_id, next_run=next_run)
