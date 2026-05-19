"""Message routing from external channels into Cognix orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from cognix.channels.base import ChannelDispatchResult, ChannelEvent, ChannelRouteTarget
from cognix.core.context import Context
from cognix.local.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

DispatchMode = Literal["direct", "task", "async_task"]


class MessageRouter:
    """Route normalized channel events into Agents or one-shot Tasks."""

    async def route(
        self,
        event: ChannelEvent,
        target: ChannelRouteTarget,
        *,
        dispatch_mode: DispatchMode = "direct",
    ) -> ChannelDispatchResult:
        mode = dispatch_mode.lower()
        if mode in {"task", "async_task"}:
            task_id = await self.enqueue_task(event, target)
            return ChannelDispatchResult(
                status="queued",
                response=f"Task queued: {task_id}",
                task_id=task_id,
                session_key=event.session_key,
            )

        response = await self.dispatch_direct(event, target)
        return ChannelDispatchResult(
            status="success",
            response=response,
            session_key=event.session_key,
        )

    async def enqueue_task(self, event: ChannelEvent, target: ChannelRouteTarget) -> str:
        """Queue a channel event as a one-shot Agent task."""
        from cognix.api.state import get_scheduler_engine, schedule_task_in_engine
        from cognix.scheduler.store import TaskStore
        from cognix.storage.models import TaskType

        run_at = datetime.now(UTC) + timedelta(seconds=1)
        task_id = f"channel-{uuid.uuid4().hex[:12]}"
        payload = self.task_payload(event, target)
        schedule = run_at.isoformat()
        await TaskStore().create(
            task_id=task_id,
            name=f"{event.channel}:{target.name or target.target_id or target.agent_id}",
            task_type=TaskType.AGENT_CALL,
            schedule=schedule,
            payload=payload,
            max_retries=int(target.metadata.get("task_max_retries", 1)),
        )
        engine = get_scheduler_engine()
        if engine:
            schedule_task_in_engine(
                engine,
                task_id,
                schedule,
                payload,
                name=f"{event.channel}:{target.name or target.agent_id}",
            )

        self._append_event(
            event.workspace_id,
            target.event_prefix,
            {
                "type": f"{target.event_prefix}.task_queued",
                "channel": event.channel,
                "target_id": target.target_id,
                "agent_id": target.agent_id,
                "task_id": task_id,
                "sender": event.sender_id,
                "thread_id": event.thread_id,
                "session_key": event.session_key,
                "message": event.text,
                **self._compat_event_fields(event),
            },
        )
        return task_id

    async def dispatch_direct(self, event: ChannelEvent, target: ChannelRouteTarget) -> str:
        """Run a channel event against an Agent immediately."""
        from cognix.api.state import get_agent_runtime
        from cognix.core.mounts import attach_workspace_runtime_tools

        agent = await get_agent_runtime(target.agent_id)
        if not agent:
            raise ValueError(f"Agent '{target.agent_id}' not found")
        agent.workspace_id = target.workspace_id
        await attach_workspace_runtime_tools(agent)
        context = Context(
            conversation_id=event.session_key,
            metadata={
                "channel_event": event.to_dict(),
                "next_user_content": event.user_content(),
                **self._compat_context_metadata(event),
            },
        )
        response = await agent.run(event.text, context=context)
        self._append_event(
            event.workspace_id,
            target.event_prefix,
            {
                "type": f"{target.event_prefix}.message",
                "channel": event.channel,
                "target_id": target.target_id,
                "agent_id": target.agent_id,
                "sender": event.sender_id,
                "thread_id": event.thread_id,
                "session_key": event.session_key,
                "message": event.text,
                "response": response.content,
                **self._compat_event_fields(event),
            },
        )
        return response.content

    @staticmethod
    def task_payload(event: ChannelEvent, target: ChannelRouteTarget) -> dict:
        payload = {
            "task_type": "agent_call",
            "agent_id": target.agent_id,
            "workspace_id": target.workspace_id,
            "message": event.text,
            "channel_event": event.to_dict(),
        }
        payload.update(MessageRouter._compat_task_payload(event))
        return payload

    @staticmethod
    def _compat_context_metadata(event: ChannelEvent) -> dict:
        if "remote_bot" in event.metadata:
            return {"remote_bot": event.metadata["remote_bot"]}
        return {}

    @staticmethod
    def _compat_task_payload(event: ChannelEvent) -> dict:
        if "remote_bot" in event.metadata:
            return {"remote_bot": event.metadata["remote_bot"]}
        return {}

    @staticmethod
    def _compat_event_fields(event: ChannelEvent) -> dict:
        remote_bot = event.metadata.get("remote_bot")
        if not isinstance(remote_bot, dict):
            return {}
        return {
            "provider": remote_bot.get("provider", event.channel),
            "bot_id": remote_bot.get("bot_id", event.metadata.get("bot_id", "")),
            "chat_id": remote_bot.get("chat_id", event.thread_id),
        }

    @staticmethod
    def _append_event(workspace_id: str, event_prefix: str, event: dict) -> None:
        try:
            WorkspaceManager().append_event(workspace_id, event)
        except Exception:
            logger.exception("Failed to append %s event", event_prefix)
