"""Task store for managing scheduled tasks in the database."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from cognix.scheduler.schedules import next_run_time
from cognix.storage.database import get_session
from cognix.storage.models import ScheduledTaskModel, TaskRunModel, TaskState, TaskType

logger = logging.getLogger(__name__)


class TaskStore:
    """Manages scheduled task persistence."""

    async def create(
        self,
        task_id: str,
        name: str,
        task_type: TaskType,
        schedule: str,
        payload: dict[str, Any],
        max_retries: int = 3,
    ) -> ScheduledTaskModel:
        """Create a new scheduled task."""
        async with get_session() as session:
            task = ScheduledTaskModel(
                id=task_id,
                name=name,
                task_type=task_type,
                schedule=schedule,
                payload=json.dumps(payload),
                state=TaskState.ACTIVE,
                max_retries=max_retries,
                next_run=next_run_time(schedule),
            )
            session.add(task)
            logger.info("Created task %s: %s", task_id, name)
            return task

    async def get(self, task_id: str) -> ScheduledTaskModel | None:
        """Get a task by ID."""
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
            )
            return result.scalar_one_or_none()

    async def list_all(self, state: TaskState | None = None) -> list[ScheduledTaskModel]:
        """List all tasks, optionally filtered by state."""
        async with get_session() as session:
            query = select(ScheduledTaskModel)
            if state:
                query = query.where(ScheduledTaskModel.state == state)
            result = await session.execute(query.order_by(ScheduledTaskModel.created_at.desc()))
            return list(result.scalars().all())

    async def update_state(self, task_id: str, state: TaskState) -> bool:
        """Update a task's state."""
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(ScheduledTaskModel.id == task_id)
                .values(state=state)
            )
            return result.rowcount > 0

    async def set_next_run(self, task_id: str, next_run: datetime | None) -> bool:
        """Persist the next expected run time for distributed dispatchers."""
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(ScheduledTaskModel.id == task_id)
                .values(next_run=next_run)
            )
            return result.rowcount > 0

    async def claim_due_tasks(
        self,
        *,
        owner: str,
        limit: int = 10,
        ttl_seconds: int = 120,
        now: datetime | None = None,
    ) -> list[ScheduledTaskModel]:
        """Claim active tasks whose ``next_run`` is due.

        Candidate selection is intentionally separate from ``acquire_lease`` so
        each claim still goes through an atomic conditional update. Multiple
        workers can safely race this method; only one owner wins each task lease.
        """
        now = now or datetime.now(UTC)
        async with get_session() as session:
            result = await session.execute(
                select(ScheduledTaskModel)
                .where(
                    and_(
                        ScheduledTaskModel.state == TaskState.ACTIVE,
                        ScheduledTaskModel.next_run.is_not(None),
                        ScheduledTaskModel.next_run <= now,
                        or_(
                            ScheduledTaskModel.lease_owner.is_(None),
                            ScheduledTaskModel.lease_expires_at.is_(None),
                            ScheduledTaskModel.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(ScheduledTaskModel.next_run.asc())
                .limit(limit)
            )
            candidates = list(result.scalars().all())

        claimed: list[ScheduledTaskModel] = []
        for candidate in candidates:
            if await self.acquire_lease(
                candidate.id,
                owner=owner,
                ttl_seconds=ttl_seconds,
            ):
                task = await self.get(candidate.id)
                if task:
                    claimed.append(task)
        return claimed

    async def acquire_lease(
        self,
        task_id: str,
        *,
        owner: str,
        ttl_seconds: int = 120,
    ) -> bool:
        """Acquire a task execution lease if it is free or expired."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(
                    and_(
                        ScheduledTaskModel.id == task_id,
                        ScheduledTaskModel.state == TaskState.ACTIVE,
                        or_(
                            ScheduledTaskModel.lease_owner.is_(None),
                            ScheduledTaskModel.lease_owner == owner,
                            ScheduledTaskModel.lease_expires_at.is_(None),
                            ScheduledTaskModel.lease_expires_at < now,
                        ),
                    )
                )
                .values(lease_owner=owner, lease_expires_at=expires_at)
            )
            return result.rowcount > 0

    async def extend_lease(
        self,
        task_id: str,
        *,
        owner: str,
        ttl_seconds: int = 120,
    ) -> bool:
        """Extend an owned task lease for long-running executions."""
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(
                    and_(
                        ScheduledTaskModel.id == task_id,
                        ScheduledTaskModel.lease_owner == owner,
                    )
                )
                .values(lease_expires_at=expires_at)
            )
            return result.rowcount > 0

    async def release_lease(self, task_id: str, *, owner: str) -> bool:
        """Release a task execution lease owned by this runtime node."""
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(
                    and_(
                        ScheduledTaskModel.id == task_id,
                        ScheduledTaskModel.lease_owner == owner,
                    )
                )
                .values(lease_owner=None, lease_expires_at=None)
            )
            return result.rowcount > 0

    async def complete_lease(
        self,
        task_id: str,
        *,
        owner: str,
        next_run: datetime | None,
    ) -> bool:
        """Release an owned lease and advance the persisted next run time."""
        async with get_session() as session:
            result = await session.execute(
                update(ScheduledTaskModel)
                .where(
                    and_(
                        ScheduledTaskModel.id == task_id,
                        ScheduledTaskModel.lease_owner == owner,
                    )
                )
                .values(
                    lease_owner=None,
                    lease_expires_at=None,
                    next_run=next_run,
                )
            )
            return result.rowcount > 0

    async def delete(self, task_id: str) -> bool:
        """Delete a task."""
        from sqlalchemy import delete

        async with get_session() as session:
            result = await session.execute(
                delete(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
            )
            return result.rowcount > 0

    async def get_runs(self, task_id: str, limit: int = 20) -> list[TaskRunModel]:
        """Get execution history for a task."""
        async with get_session() as session:
            result = await session.execute(
                select(TaskRunModel)
                .where(TaskRunModel.task_id == task_id)
                .order_by(TaskRunModel.started_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
