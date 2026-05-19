"""Shared channel event models.

The channel layer normalizes webhook/chat inputs before they enter Cognix
orchestration. Provider-specific bridges should translate into these models,
then let ``MessageRouter`` decide whether to run an Agent directly or queue a
Task.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


@dataclass(frozen=True)
class ChannelAttachment:
    """A normalized attachment received from an external channel."""

    id: str = ""
    name: str = ""
    content_type: str = ""
    url: str = ""
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelEvent:
    """Provider-neutral message event for WeChat, Telegram, Lark, web, API, etc."""

    channel: str
    workspace_id: str
    text: str = ""
    sender_id: str = ""
    thread_id: str = ""
    message_type: str = "text"
    attachments: list[ChannelAttachment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    received_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def session_key(self) -> str:
        remote_id = self.thread_id or self.sender_id or "direct"
        source_id = str(self.metadata.get("source_id") or self.metadata.get("bot_id") or "default")
        return f"{self.channel}:{source_id}:{remote_id}"

    def user_content(self) -> str:
        """Build the message content seen by an Agent, including remote context."""
        return "\n".join(
            [
                f"[channel={self.channel}]",
                f"[session_key={self.session_key}]",
                f"[sender={self.sender_id or 'unknown'} thread_id={self.thread_id or 'direct'}]",
                self.text,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChannelRouteTarget:
    """Where a channel event should be routed."""

    workspace_id: str
    agent_id: str
    target_id: str = ""
    name: str = ""
    event_prefix: str = "channel"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelDispatchResult:
    """Result of routing a channel event."""

    status: Literal["success", "queued"]
    response: str = ""
    task_id: str = ""
    session_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
