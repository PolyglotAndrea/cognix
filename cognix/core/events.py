"""Event bus for inter-module communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Async publish-subscribe event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Emit an event to all registered handlers."""
        data = data or {}
        handlers = self._handlers.get(event, [])
        if not handlers:
            logger.debug("No handlers for event: %s", event)
            return

        tasks = [self._safe_call(handler, event, data) for handler in handlers]
        await asyncio.gather(*tasks)

    def on(self, event: str, handler: EventHandler) -> None:
        """Register an event handler."""
        self._handlers[event].append(handler)

    def off(self, event: str, handler: EventHandler) -> None:
        """Unregister an event handler."""
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def clear(self, event: str | None = None) -> None:
        """Clear handlers for a specific event or all events."""
        if event:
            self._handlers.pop(event, None)
        else:
            self._handlers.clear()

    @staticmethod
    async def _safe_call(handler: EventHandler, event: str, data: dict[str, Any]) -> None:
        try:
            await handler(event=event, **data)
        except Exception:
            logger.exception("Handler error for event %s", event)


# Well-known event names
class Events:
    AGENT_CREATED = "agent.created"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    AGENT_WAITING = "agent.waiting"

    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_COMPLETED = "approval.completed"

    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    TOOL_ERROR = "tool.error"

    TASK_SCHEDULED = "task.scheduled"
    TASK_EXECUTED = "task.executed"
    TASK_FAILED = "task.failed"

    SKILL_LOADED = "skill.loaded"
    SKILL_UNLOADED = "skill.unloaded"

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_ERROR = "workflow.error"
