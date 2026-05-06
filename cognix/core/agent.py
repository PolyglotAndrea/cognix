"""Hermes Agent - the core runtime entity."""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from cognix.core.context import Context, Message
from cognix.core.events import EventBus, Events
from cognix.core.memory import InMemoryBackend, MemoryBackend
from cognix.core.tool import Tool

logger = logging.getLogger(__name__)


class AgentState(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"


@dataclass
class AgentResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class AgentChunk:
    """Streaming response chunk."""

    delta: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None


@dataclass
class Agent:
    """Hermes Agent - an LLM-powered autonomous entity."""

    name: str
    model: str = "gpt-4o"
    system_prompt: str = "You are a helpful assistant."
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    tools: list[Tool] = field(default_factory=list)
    memory: MemoryBackend = field(default_factory=InMemoryBackend)
    state: AgentState = AgentState.IDLE
    max_iterations: int = 10
    temperature: float = 0.7
    api_base: str | None = None
    api_key: str | None = None

    _event_bus: EventBus | None = field(default=None, repr=False)
    _tool_map: dict[str, Tool] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._tool_map = {t.name: t for t in self.tools}

    def set_event_bus(self, bus: EventBus) -> None:
        self._event_bus = bus

    def add_tool(self, tool: Tool) -> None:
        self.tools.append(tool)
        self._tool_map[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        self.tools = [t for t in self.tools if t.name != name]
        self._tool_map.pop(name, None)

    async def run(self, message: str, context: Context | None = None) -> AgentResponse:
        """Run the agent with a user message. Handles tool-call loops."""
        ctx = context or Context()
        ctx.add_message("user", message)

        await self._emit(Events.AGENT_STARTED, {"agent_id": self.id, "message": message})
        self.state = AgentState.RUNNING

        try:
            for _ in range(self.max_iterations):
                response = await self._call_llm(ctx)

                if not response.tool_calls:
                    # Final response, no more tool calls
                    ctx.add_message("assistant", response.content)
                    await self._emit(
                        Events.AGENT_COMPLETED,
                        {"agent_id": self.id, "response": response.content},
                    )
                    self.state = AgentState.IDLE
                    return response

                # Execute tool calls
                ctx.add_message("assistant", response.content, tool_calls=response.tool_calls)
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    ctx.add_message(
                        "tool",
                        tool_result,
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )

            # Max iterations reached
            self.state = AgentState.ERROR
            raise RuntimeError(f"Agent {self.name} exceeded max iterations ({self.max_iterations})")

        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            raise

    async def stream(self, message: str, context: Context | None = None) -> AsyncIterator[AgentChunk]:
        """Stream agent response chunks."""
        ctx = context or Context()
        ctx.add_message("user", message)

        await self._emit(Events.AGENT_STARTED, {"agent_id": self.id, "message": message})
        self.state = AgentState.RUNNING

        try:
            async for chunk in self._stream_llm(ctx):
                yield chunk

            self.state = AgentState.IDLE
        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            raise

    async def _call_llm(self, ctx: Context) -> AgentResponse:
        """Call the LLM. Override for custom providers."""
        # Fallback for non-LLM models (e.g. "echo" for testing)
        if self.model in ("echo", "noop", "mock"):
            return AgentResponse(content=f"[{self.name}] Echo: {ctx.messages[-1].content}")

        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed, falling back to echo mode")
            return AgentResponse(content=f"[{self.name}] Echo: {ctx.messages[-1].content}")

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(ctx.get_history())

        tools_schema = [t.to_openai_schema() for t in self.tools] if self.tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        # Support custom API base URL and key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        if tools_schema:
            kwargs["tools"] = tools_schema

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise RuntimeError(f"LLM call failed for model '{self.model}': {e}") from e

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls: list[dict[str, Any]] = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                import json

                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                )

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return AgentResponse(content=content, tool_calls=tool_calls, usage=usage)

    async def _stream_llm(self, ctx: Context) -> AsyncIterator[AgentChunk]:
        """Stream from LLM. Override for custom providers."""
        # Fallback for non-LLM models (e.g. "echo" for testing)
        if self.model in ("echo", "noop", "mock"):
            yield AgentChunk(delta=f"[{self.name}] Echo: {ctx.messages[-1].content}", finish_reason="stop")
            return

        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed, falling back to echo mode")
            yield AgentChunk(delta=f"[{self.name}] Echo: {ctx.messages[-1].content}", finish_reason="stop")
            return

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(ctx.get_history())

        tools_schema = [t.to_openai_schema() for t in self.tools] if self.tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }

        # Support custom API base URL and key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        if tools_schema:
            kwargs["tools"] = tools_schema

        try:
            async for chunk in await litellm.acompletion(**kwargs):
                delta = chunk.choices[0].delta
                yield AgentChunk(
                    delta=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                )
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            raise RuntimeError(f"LLM stream failed for model '{self.model}': {e}") from e

    async def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a tool call and return the result as string."""
        name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        tool = self._tool_map.get(name)
        if not tool:
            error_msg = f"Tool '{name}' not found"
            await self._emit(Events.TOOL_ERROR, {"tool": name, "error": error_msg})
            return error_msg

        await self._emit(Events.TOOL_CALLED, {"tool": name, "arguments": arguments})
        try:
            result = await tool.execute(**arguments)
            result_str = str(result)
            await self._emit(Events.TOOL_RESULT, {"tool": name, "result": result_str})
            return result_str
        except Exception as e:
            error_msg = f"Tool '{name}' error: {e}"
            await self._emit(Events.TOOL_ERROR, {"tool": name, "error": error_msg})
            return error_msg

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        if self._event_bus:
            await self._event_bus.emit(event, data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize agent config (excluding runtime state)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_iterations": self.max_iterations,
            "api_base": self.api_base,
            "tools": [t.name for t in self.tools],
        }
