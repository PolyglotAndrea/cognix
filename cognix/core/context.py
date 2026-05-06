"""Execution context for Agent runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Message:
    role: str  # "user", "assistant", "system", "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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

    def get_history(self, limit: int | None = None) -> list[dict[str, str]]:
        """Return conversation history as list of dicts for LLM APIs."""
        msgs = self.messages[-limit:] if limit else self.messages
        return [{"role": m.role, "content": m.content} for m in msgs]

    def set_variable(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)
