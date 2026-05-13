"""Hermes Agent - the core runtime entity."""

from __future__ import annotations

import enum
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from cognix.core.context import Context
from cognix.core.events import EventBus, Events
from cognix.core.memory import InMemoryBackend, MemoryBackend
from cognix.core.permissions import decide_permission, normalize_permission_mode
from cognix.core.tool import Tool

logger = logging.getLogger(__name__)


class AgentState(enum.StrEnum):
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
class AgentEvent:
    """Structured runtime event using delta/tool_call/tool_result/error/done types."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


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
    workspace_id: str | None = None
    permission_mode: str = "workspace-write"
    use_context_builder: bool = True

    _event_bus: EventBus | None = field(default=None, repr=False)
    _tool_map: dict[str, Tool] = field(default_factory=dict, repr=False)
    _pending_approval_event: dict[str, Any] | None = field(default=None, repr=False)
    _waiting_snapshot: dict[str, Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.permission_mode = normalize_permission_mode(self.permission_mode)
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
        await self._inject_context_pack(ctx, message)
        ctx.add_message("user", self._next_user_content(ctx, message))

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
                    await self._remember_exchange(message, response.content)
                    self.state = AgentState.IDLE
                    return response

                # Execute tool calls
                ctx.add_message("assistant", response.content, tool_calls=response.tool_calls)
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    approval_event = self._consume_pending_approval_event()
                    ctx.add_message(
                        "tool",
                        tool_result,
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )
                    if approval_event:
                        remaining = [
                            t for t in response.tool_calls
                            if t.get("id", "") != tc.get("id", "")
                        ]
                        self._waiting_snapshot = {
                            "context": ctx,
                            "remaining_tool_calls": remaining,
                            "response": response,
                            "message": message,
                        }
                        self._persist_snapshot(approval_event["approval_id"])
                        return AgentResponse(
                            content=tool_result,
                            tool_calls=response.tool_calls,
                            metadata={
                                "finish_reason": "waiting_for_approval",
                                "approval_id": approval_event["approval_id"],
                            },
                            usage=response.usage,
                        )

            # Max iterations reached
            self.state = AgentState.ERROR
            raise RuntimeError(f"Agent {self.name} exceeded max iterations ({self.max_iterations})")

        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            raise

    async def stream(
        self,
        message: str,
        context: Context | None = None,
    ) -> AsyncIterator[AgentChunk]:
        """Stream agent response chunks."""
        ctx = context or Context()
        await self._inject_context_pack(ctx, message)
        ctx.add_message("user", self._next_user_content(ctx, message))

        await self._emit(Events.AGENT_STARTED, {"agent_id": self.id, "message": message})
        self.state = AgentState.RUNNING

        try:
            async for chunk in self._stream_llm(ctx):
                yield chunk

            await self._remember_exchange(message, "")
            self.state = AgentState.IDLE
        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            raise

    async def stream_events(
        self,
        message: str,
        context: Context | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Stream a stable event protocol: delta, tool_call, tool_result, error, done."""
        ctx = context or Context()
        await self._inject_context_pack(ctx, message)
        ctx.add_message("user", self._next_user_content(ctx, message))

        await self._emit(Events.AGENT_STARTED, {"agent_id": self.id, "message": message})
        self.state = AgentState.RUNNING

        try:
            if not self.tools:
                content = ""
                async for chunk in self._stream_llm(ctx):
                    if chunk.delta:
                        content += chunk.delta
                        yield AgentEvent("delta", {"delta": chunk.delta})
                ctx.add_message("assistant", content)
                await self._remember_exchange(message, content)
                await self._emit(Events.AGENT_COMPLETED, {"agent_id": self.id, "response": content})
                self.state = AgentState.IDLE
                yield AgentEvent("done", {"finish_reason": "stop"})
                return

            for _ in range(self.max_iterations):
                response = await self._call_llm(ctx)
                if not response.tool_calls:
                    ctx.add_message("assistant", response.content)
                    if response.content:
                        yield AgentEvent("delta", {"delta": response.content})
                    await self._remember_exchange(message, response.content)
                    await self._emit(
                        Events.AGENT_COMPLETED,
                        {"agent_id": self.id, "response": response.content},
                    )
                    self.state = AgentState.IDLE
                    yield AgentEvent(
                        "done",
                        {"finish_reason": "stop", "usage": response.usage},
                    )
                    return

                ctx.add_message("assistant", response.content, tool_calls=response.tool_calls)
                for tc in response.tool_calls:
                    yield AgentEvent(
                        "tool_call",
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": tc.get("arguments", {}),
                            "args": tc.get("arguments", {}),
                        },
                    )
                    tool_result = await self._execute_tool(tc)
                    approval_event = self._consume_pending_approval_event()
                    ctx.add_message(
                        "tool",
                        tool_result,
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )
                    yield AgentEvent(
                        "tool_result",
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "args": tc.get("arguments", {}),
                            "result": tool_result,
                        },
                    )
                    if approval_event:
                        # Save snapshot for resume_and_continue
                        remaining = [
                            t for t in response.tool_calls
                            if t.get("id", "") != tc.get("id", "")
                        ]
                        self._waiting_snapshot = {
                            "context": ctx,
                            "remaining_tool_calls": remaining,
                            "response": response,
                            "message": message,
                        }
                        self._persist_snapshot(approval_event["approval_id"])
                        yield AgentEvent("approval_request", approval_event)
                        yield AgentEvent(
                            "done",
                            {
                                "finish_reason": "waiting_for_approval",
                                "approval_id": approval_event["approval_id"],
                            },
                        )
                        return

            self.state = AgentState.ERROR
            raise RuntimeError(f"Agent {self.name} exceeded max iterations ({self.max_iterations})")
        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            yield AgentEvent("error", {"message": str(e), "error": str(e)})
        finally:
            if self.state not in (AgentState.ERROR, AgentState.WAITING):
                self.state = AgentState.IDLE

    async def _call_llm(self, ctx: Context) -> AgentResponse:
        """Call the LLM. Override for custom providers."""
        # Fallback for non-LLM models (e.g. "echo" for testing)
        if self.model in ("echo", "noop", "mock"):
            text = self._message_text(ctx.messages[-1].content)
            return AgentResponse(content=f"[{self.name}] Echo: {text}")

        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed, falling back to echo mode")
            text = self._message_text(ctx.messages[-1].content)
            return AgentResponse(content=f"[{self.name}] Echo: {text}")

        messages = [{"role": "system", "content": self.system_prompt}]
        # Use history_window from workspace settings to limit conversation length
        memory_options = self._workspace_memory_options()
        history_window = memory_options.get("max_history_messages", 20)
        token_budget = memory_options.get("token_budget")
        messages.extend(ctx.get_history(
            limit=history_window,
            max_tokens=token_budget,
            model=self.model,
        ))

        tools_schema = [t.to_openai_schema() for t in self.tools] if self.tools else None

        # Fallback to unified provider resolver
        api_base = self.api_base
        api_key = self.api_key
        model = self.model
        if not api_base or not api_key:
            from cognix.providers.resolver import resolve_provider
            provider = resolve_provider(self.workspace_id)
            api_base = api_base or provider.base_url
            api_key = api_key or provider.api_key
            model = model or provider.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
        }

        # Support custom API base URL and key
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key

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
            yield AgentChunk(
                delta=f"[{self.name}] Echo: {self._message_text(ctx.messages[-1].content)}",
                finish_reason="stop",
            )
            return

        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed, falling back to echo mode")
            yield AgentChunk(
                delta=f"[{self.name}] Echo: {self._message_text(ctx.messages[-1].content)}",
                finish_reason="stop",
            )
            return

        messages = [{"role": "system", "content": self.system_prompt}]
        # Use history_window from workspace settings to limit conversation length
        memory_options = self._workspace_memory_options()
        history_window = memory_options.get("max_history_messages", 20)
        token_budget = memory_options.get("token_budget")
        messages.extend(ctx.get_history(
            limit=history_window,
            max_tokens=token_budget,
            model=self.model,
        ))

        tools_schema = [t.to_openai_schema() for t in self.tools] if self.tools else None

        # Fallback to unified provider resolver
        api_base = self.api_base
        api_key = self.api_key
        model = self.model
        if not api_base or not api_key:
            from cognix.providers.resolver import resolve_provider
            provider = resolve_provider(self.workspace_id)
            api_base = api_base or provider.base_url
            api_key = api_key or provider.api_key
            model = model or provider.default_model

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }

        # Support custom API base URL and key
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key

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

        decision = decide_permission(self.permission_mode, tool.access_level, f"tool '{name}'")
        if not decision.allowed:
            approval_id = ""
            if decision.requires_approval:
                approval_id = self._create_approval_request(
                    tool_name=name,
                    arguments=arguments,
                    access_level=tool.access_level,
                    reason=decision.reason,
                )
                self.state = AgentState.WAITING
                await self._emit(
                    Events.APPROVAL_REQUESTED,
                    {
                        "approval_id": approval_id,
                        "agent_id": self.id,
                        "workspace_id": self.workspace_id,
                        "tool": name,
                        "arguments": arguments,
                        "access_level": tool.access_level,
                        "reason": decision.reason,
                    },
                )
                self._pending_approval_event = {
                    "approval_id": approval_id,
                    "id": approval_id,
                    "agent_id": self.id,
                    "workspace_id": self.workspace_id,
                    "tool": name,
                    "name": name,
                    "tool_name": name,
                    "arguments": arguments,
                    "args": arguments,
                    "access_level": tool.access_level,
                    "reason": decision.reason,
                    "kind": "plan_confirmation"
                    if self.permission_mode == "plan"
                    else "tool_permission",
                    "permission_mode": self.permission_mode,
                }
                await self._emit(
                    Events.AGENT_WAITING,
                    {"agent_id": self.id, "approval_id": approval_id, "reason": decision.reason},
                )
            error_msg = (
                f"Permission denied: {decision.reason}"
                if not decision.requires_approval
                else f"Approval required [{approval_id}]: {decision.reason}"
            )
            await self._emit(
                Events.TOOL_ERROR,
                {
                    "tool": name,
                    "error": error_msg,
                    "permission_mode": self.permission_mode,
                    "access_level": tool.access_level,
                    "requires_approval": decision.requires_approval,
                },
            )
            return error_msg

        return await self._execute_tool_unchecked(tool_call, tool)

    async def resume_approval(self, approval_id: str) -> str:
        """Execute a previously approved tool call."""
        from cognix.local.approvals import ApprovalStore

        store = ApprovalStore()
        approval = store.get(approval_id)
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")
        if approval.agent_id != self.id:
            raise ValueError(f"Approval '{approval_id}' does not belong to agent '{self.id}'")
        if approval.status != "approved":
            raise ValueError(f"Approval '{approval_id}' is not approved")

        tool = self._tool_map.get(approval.tool_name)
        if not tool:
            raise ValueError(f"Tool '{approval.tool_name}' not found")

        result = await self._execute_tool_unchecked(
            {"name": approval.tool_name, "arguments": approval.arguments},
            tool,
        )
        store.complete(approval_id, result)
        await self._emit(
            Events.APPROVAL_COMPLETED,
            {"approval_id": approval_id, "agent_id": self.id, "result": result},
        )
        self.state = AgentState.IDLE
        return result

    async def resume_and_continue(
        self,
        approval_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """Resume after approval, execute the tool, and continue the LLM loop.

        Unlike ``resume_approval`` which only returns the tool result, this
        method restores the full conversation context and re-enters the
        iteration loop so the agent can produce a final response — including
        handling additional tool calls or further approval gates.
        """
        from cognix.local.approvals import ApprovalStore

        store = ApprovalStore()
        approval = store.get(approval_id)
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")
        if approval.agent_id != self.id:
            raise ValueError(f"Approval '{approval_id}' does not belong to agent '{self.id}'")
        if approval.status != "approved":
            raise ValueError(f"Approval '{approval_id}' is not approved")

        tool = self._tool_map.get(approval.tool_name)
        if not tool:
            raise ValueError(f"Tool '{approval.tool_name}' not found")

        snapshot = self._waiting_snapshot
        if not snapshot:
            # Try to restore from persisted approval metadata (survives restart)
            persisted = approval.metadata.get("waiting_snapshot")
            if persisted:
                try:
                    snapshot = self.deserialize_snapshot(persisted)
                    logger.info(
                        "Restored waiting snapshot from approval metadata for %s",
                        approval_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to deserialize snapshot from approval %s",
                        approval_id,
                    )

        if not snapshot:
            # Fallback: no snapshot, just execute tool and return
            result = await self.resume_approval(approval_id)
            yield AgentEvent("tool_result", {"name": approval.tool_name, "result": result})
            yield AgentEvent("done", {"finish_reason": "stop"})
            return

        self._waiting_snapshot = None
        ctx: Context = snapshot["context"]
        remaining_tool_calls: list[dict[str, Any]] = snapshot["remaining_tool_calls"]
        original_message: str = snapshot["message"]

        # Replace the placeholder "Approval required" tool result with the real one
        result = await self._execute_tool_unchecked(
            {"name": approval.tool_name, "arguments": approval.arguments},
            tool,
        )
        store.complete(approval_id, result)
        await self._emit(
            Events.APPROVAL_COMPLETED,
            {"approval_id": approval_id, "agent_id": self.id, "result": result},
        )

        # Fix the context: replace placeholder tool result with real result
        self._replace_last_tool_result(ctx, approval.tool_name, result)

        yield AgentEvent(
            "tool_result",
            {
                "name": approval.tool_name,
                "result": result,
            },
        )

        # Execute remaining tool calls from the same LLM response
        for tc in remaining_tool_calls:
            tc_name = tc.get("name", "")
            yield AgentEvent(
                "tool_call",
                {
                    "id": tc.get("id", ""),
                    "name": tc_name,
                    "arguments": tc.get("arguments", {}),
                    "args": tc.get("arguments", {}),
                },
            )
            tc_result = await self._execute_tool(tc)
            tc_approval = self._consume_pending_approval_event()
            ctx.add_message(
                "tool",
                tc_result,
                tool_call_id=tc.get("id", ""),
                name=tc_name,
            )
            yield AgentEvent(
                "tool_result",
                {
                    "id": tc.get("id", ""),
                    "name": tc_name,
                    "args": tc.get("arguments", {}),
                    "result": tc_result,
                },
            )
            if tc_approval:
                # Another approval needed — save snapshot and pause again
                later_remaining = [
                    t for t in remaining_tool_calls
                    if t.get("id", "") != tc.get("id", "")
                ]
                self._waiting_snapshot = {
                    "context": ctx,
                    "remaining_tool_calls": later_remaining,
                    "response": snapshot["response"],
                    "message": original_message,
                }
                self._persist_snapshot(tc_approval["approval_id"])
                yield AgentEvent("approval_request", tc_approval)
                yield AgentEvent(
                    "done",
                    {
                        "finish_reason": "waiting_for_approval",
                        "approval_id": tc_approval["approval_id"],
                    },
                )
                return

        # Continue the LLM iteration loop
        self.state = AgentState.RUNNING

        try:
            for _ in range(self.max_iterations):
                response = await self._call_llm(ctx)
                if not response.tool_calls:
                    ctx.add_message("assistant", response.content)
                    if response.content:
                        yield AgentEvent("delta", {"delta": response.content})
                    await self._remember_exchange(original_message, response.content)
                    await self._emit(
                        Events.AGENT_COMPLETED,
                        {"agent_id": self.id, "response": response.content},
                    )
                    self.state = AgentState.IDLE
                    yield AgentEvent(
                        "done",
                        {"finish_reason": "stop", "usage": response.usage},
                    )
                    return

                ctx.add_message("assistant", response.content, tool_calls=response.tool_calls)
                for tc in response.tool_calls:
                    yield AgentEvent(
                        "tool_call",
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": tc.get("arguments", {}),
                            "args": tc.get("arguments", {}),
                        },
                    )
                    tool_result = await self._execute_tool(tc)
                    approval_event = self._consume_pending_approval_event()
                    ctx.add_message(
                        "tool",
                        tool_result,
                        tool_call_id=tc.get("id", ""),
                        name=tc.get("name", ""),
                    )
                    yield AgentEvent(
                        "tool_result",
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "args": tc.get("arguments", {}),
                            "result": tool_result,
                        },
                    )
                    if approval_event:
                        later_remaining = [
                            t for t in response.tool_calls
                            if t.get("id", "") != tc.get("id", "")
                        ]
                        self._waiting_snapshot = {
                            "context": ctx,
                            "remaining_tool_calls": later_remaining,
                            "response": response,
                            "message": original_message,
                        }
                        self._persist_snapshot(approval_event["approval_id"])
                        yield AgentEvent("approval_request", approval_event)
                        yield AgentEvent(
                            "done",
                            {
                                "finish_reason": "waiting_for_approval",
                                "approval_id": approval_event["approval_id"],
                            },
                        )
                        return

            self.state = AgentState.ERROR
            raise RuntimeError(f"Agent {self.name} exceeded max iterations ({self.max_iterations})")
        except Exception as e:
            self.state = AgentState.ERROR
            await self._emit(Events.AGENT_ERROR, {"agent_id": self.id, "error": str(e)})
            yield AgentEvent("error", {"message": str(e), "error": str(e)})
        finally:
            if self.state not in (AgentState.ERROR, AgentState.WAITING):
                self.state = AgentState.IDLE

    @staticmethod
    def _replace_last_tool_result(ctx: Context, tool_name: str, new_result: str) -> None:
        """Replace the most recent tool result message for *tool_name*."""
        for msg in reversed(ctx.messages):
            if msg.role == "tool" and msg.name == tool_name:
                msg.content = new_result
                return

    async def _execute_tool_unchecked(self, tool_call: dict[str, Any], tool: Tool) -> str:
        name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})
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

    def _create_approval_request(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        access_level: str,
        reason: str,
    ) -> str:
        from cognix.local.approvals import ApprovalStore

        request = ApprovalStore().create(
            agent_id=self.id,
            workspace_id=self.workspace_id,
            tool_name=tool_name,
            arguments=arguments,
            access_level=access_level,
            reason=reason,
            kind="plan_confirmation" if self.permission_mode == "plan" else "tool_permission",
        )
        return request.id

    def _consume_pending_approval_event(self) -> dict[str, Any] | None:
        event = self._pending_approval_event
        self._pending_approval_event = None
        return event

    def _persist_snapshot(self, approval_id: str) -> None:
        """Serialize and persist the current waiting snapshot to approval metadata."""
        if not self._waiting_snapshot:
            return
        try:
            from cognix.local.approvals import ApprovalStore

            serialized = self.serialize_snapshot(self._waiting_snapshot)
            ApprovalStore().update_metadata(
                approval_id,
                {"runtime": "hermes-agent", "waiting_snapshot": serialized},
            )
        except Exception:
            logger.exception(
                "Failed to persist waiting snapshot for approval %s",
                approval_id,
            )

    def _next_user_content(self, ctx: Context, message: str) -> Any:
        return ctx.metadata.get("next_user_content", message)

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part).strip()
        return str(content)

    async def _inject_context_pack(self, ctx: Context, message: str) -> None:
        """Inject routed Cognix memory context, falling back to backend search."""
        if self.use_context_builder:
            try:
                from cognix.memory.pipeline import ContextBuilder

                memory_options = self._workspace_memory_options()

                pack = await ContextBuilder().build(
                    message,
                    workspace_id=self.workspace_id,
                    include_hot_memory=memory_options.get("include_hot_memory", True),
                    include_cold_memory=memory_options.get("include_cold_memory", True),
                    include_skills=memory_options.get("include_skills", True),
                    include_deep_memory=memory_options.get("include_deep_memory", False),
                    token_budget=memory_options.get("token_budget", 8000),
                    routing_strategy=memory_options.get("routing_strategy", "priority"),
                    model=self.model,
                )
                rendered = pack.render_system_context(model=self.model)
                if rendered:
                    ctx.add_message("system", rendered)
                    ctx.metadata["context_token_usage"] = pack.token_usage
                    return
            except Exception:
                logger.exception("ContextBuilder failed for agent %s", self.id)

        await self._inject_relevant_memory(ctx, message)

    def _workspace_memory_options(self) -> dict[str, Any]:
        if not self.workspace_id:
            return {}
        try:
            from cognix.local.workspace_config import WorkspaceConfigStore

            settings = WorkspaceConfigStore(self.workspace_id).get_settings()
            return settings.get("context", {})
        except Exception:
            logger.exception("Workspace memory settings failed for agent %s", self.id)
            return {}

    async def _inject_relevant_memory(self, ctx: Context, message: str) -> None:
        """Inject a compact long-term memory recall into the context."""
        try:
            memories = await self.memory.search(message, limit=5)
        except Exception:
            logger.exception("Memory search failed for agent %s", self.id)
            return

        if not memories:
            return

        lines = []
        for entry in memories:
            value = entry.value
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            lines.append(f"- {entry.key}: {value[:500]}")

        ctx.add_message(
            "system",
            "Relevant long-term memory:\n" + "\n".join(lines),
        )

    async def _remember_exchange(self, user_message: str, assistant_message: str) -> None:
        """Persist a summarized exchange in the configured memory backend."""
        if not user_message.strip():
            return
        key = f"conversation:{uuid.uuid4().hex[:12]}"
        value = {
            "user": user_message,
            "assistant": assistant_message,
        }
        try:
            await self.memory.set(key, value)
        except Exception:
            logger.exception("Memory write failed for agent %s", self.id)

        try:
            from cognix.local.home import CognixHome
            from cognix.memory.pipeline import ColdMemoryStore

            content = f"User: {user_message}\nAssistant: {assistant_message}"
            await ColdMemoryStore(CognixHome.default().ensure().state_db).remember(
                content,
                workspace_id=self.workspace_id,
                scope="agent",
                kind="conversation",
                summary=content[:700],
                metadata={"agent_id": self.id, "agent_name": self.name},
            )
        except Exception:
            logger.exception("Cold memory write failed for agent %s", self.id)

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
            "workspace_id": self.workspace_id,
            "permission_mode": self.permission_mode,
            "tools": [t.name for t in self.tools],
        }

    # ── Snapshot persistence ────────────────────────────────────────

    @staticmethod
    def serialize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        """Serialize a waiting snapshot to a JSON-compatible dict.

        The snapshot contains a ``Context``, an ``AgentResponse``, tool call
        lists, and the original user message.  This method converts it to a
        plain dict that can be stored in approval metadata.
        """
        ctx: Context = snapshot["context"]
        response: AgentResponse = snapshot["response"]
        return {
            "context": ctx.to_dict(),
            "remaining_tool_calls": snapshot["remaining_tool_calls"],
            "message": snapshot["message"],
            "response": {
                "content": response.content,
                "tool_calls": response.tool_calls,
                "usage": response.usage,
                "metadata": response.metadata,
            },
        }

    @staticmethod
    def deserialize_snapshot(data: dict[str, Any]) -> dict[str, Any]:
        """Deserialize a snapshot dict back into live objects."""
        ctx = Context.from_dict(data["context"])
        resp_data = data.get("response", {})
        response = AgentResponse(
            content=resp_data.get("content", ""),
            tool_calls=resp_data.get("tool_calls", []),
            usage=resp_data.get("usage", {}),
            metadata=resp_data.get("metadata", {}),
        )
        return {
            "context": ctx,
            "remaining_tool_calls": data.get("remaining_tool_calls", []),
            "message": data.get("message", ""),
            "response": response,
        }
