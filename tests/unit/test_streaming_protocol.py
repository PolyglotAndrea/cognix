"""Tests for the canonical runtime stream event protocol."""

from __future__ import annotations

import json

import pytest

from cognix.core.agent import AgentEvent
from cognix.core.streaming import STREAM_EVENT_TYPES, encode_sse_event, stream_payload


def test_stream_payload_keeps_canonical_event_types() -> None:
    assert STREAM_EVENT_TYPES == {"delta", "tool_call", "tool_result", "error", "done"}

    payload = stream_payload(AgentEvent("delta", {"delta": "hello"}), extra={"model": "echo"})

    assert payload == {"type": "delta", "model": "echo", "delta": "hello"}


def test_stream_payload_normalizes_error_field() -> None:
    payload = stream_payload(AgentEvent("error", {"message": "boom"}))

    assert payload == {"type": "error", "message": "boom", "error": "boom"}


def test_encode_sse_event_uses_data_only_json_frame() -> None:
    frame = encode_sse_event(AgentEvent("done", {"finish_reason": "stop"}))

    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    body = json.loads(frame.removeprefix("data: ").strip())
    assert body == {"type": "done", "finish_reason": "stop"}


def test_stream_payload_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError):
        stream_payload(AgentEvent("custom", {}))
