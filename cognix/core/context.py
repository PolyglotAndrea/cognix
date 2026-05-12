"""Execution context for Agent runs."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Message:
    role: str  # "user", "assistant", "system", "tool"
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Context:
    """Carries state through an Agent execution."""

    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> Message:
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        return msg

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return conversation history as list of dicts for LLM APIs."""
        msgs = self.messages[-limit:] if limit else self.messages
        history: list[dict[str, Any]] = []
        for m in msgs:
            item: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.name:
                item["name"] = m.name
            if m.tool_call_id:
                item["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": tc.get("arguments", "{}")
                            if isinstance(tc.get("arguments"), str)
                            else json.dumps(tc.get("arguments", {})),
                        },
                    }
                    if "type" not in tc
                    else tc
                    for tc in m.tool_calls
                ]
            history.append(item)
        return history

    def set_variable(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "conversation_id": self.conversation_id,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "name": m.name,
                    "tool_call_id": m.tool_call_id,
                    "tool_calls": m.tool_calls,
                }
                for m in self.messages
            ],
            "metadata": self.metadata,
            "variables": self.variables,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Context:
        """Deserialize from a dict produced by ``to_dict``."""
        ctx = cls(conversation_id=data.get("conversation_id", ""))
        for m in data.get("messages", []):
            ctx.messages.append(
                Message(
                    role=m["role"],
                    content=m["content"],
                    name=m.get("name"),
                    tool_call_id=m.get("tool_call_id"),
                    tool_calls=m.get("tool_calls"),
                )
            )
        ctx.metadata = data.get("metadata", {})
        ctx.variables = data.get("variables", {})
        return ctx
