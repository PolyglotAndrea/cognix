"""Stable runtime stream event protocol helpers."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from cognix.core.agent import AgentEvent


class StreamEventType(StrEnum):
    DELTA = "delta"
    STATUS = "status"
    TODO = "todo"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    ERROR = "error"
    DONE = "done"


STREAM_EVENT_TYPES = {event_type.value for event_type in StreamEventType}


def stream_payload(
    event: AgentEvent,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the canonical JSON payload for SSE/WebSocket stream events."""
    if event.type not in STREAM_EVENT_TYPES:
        raise ValueError(f"Unsupported stream event type: {event.type}")

    data = dict(event.data)
    if event.type == StreamEventType.ERROR and "error" not in data:
        data["error"] = data.get("message", "")

    return {"type": event.type, **(extra or {}), **data}


def encode_sse_event(
    event: AgentEvent,
    *,
    extra: dict[str, Any] | None = None,
) -> str:
    """Serialize a runtime event as a data-only SSE frame.

    The `type` field is kept in the JSON body so fetch-stream consumers and
    WebSocket clients can share exactly the same payload shape.
    """
    return f"data: {json.dumps(stream_payload(event, extra=extra), ensure_ascii=False)}\n\n"
