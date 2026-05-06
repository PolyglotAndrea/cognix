"""Task store for managing scheduled tasks in the database."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

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
