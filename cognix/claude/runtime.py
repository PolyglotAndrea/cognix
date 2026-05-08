"""Claude Agent SDK runtime adapter."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from cognix.core.agent import AgentEvent
from cognix.core.permissions import normalize_permission_mode
from cognix.local.approvals import ApprovalRequest, ApprovalStore
from cognix.local.files import WorkspaceFileStore
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore


class ClaudeAgentSDKUnavailableError(RuntimeError):
    """Raised when claude-agent-sdk is not installed in the runtime environment."""


@dataclass(frozen=True)
class ClaudeAgentRunRequest:
    workspace_id: str
    prompt: str
    agent_id: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    permission_mode: str = "workspace-write"
    max_turns: int | None = None
    resume: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)


class ClaudeAgentRuntime:
    """Bridge Cognix workspace/runtime settings into Claude Agent SDK options."""

    async def stream(self, request: ClaudeAgentRunRequest) -> AsyncIterator[AgentEvent]:
        sdk = _load_sdk()
        pending_approvals: list[ApprovalRequest] = []
        options = self.build_options(
            request,
            sdk=sdk,
            approval_sink=pending_approvals.append,
        )
        try:
            async for message in sdk.query(prompt=request.prompt, options=options):
                for event in _approval_events(pending_approvals):
                    yield event
                for event in _message_to_events(message):
                    yield event
            for event in _approval_events(pending_approvals):
                yield event
        except Exception as exc:
            for event in _approval_events(pending_approvals):
                yield event
            yield AgentEvent("error", {"message": str(exc), "error": str(exc)})

    def build_options(
        self,
        request: ClaudeAgentRunRequest,
        *,
        sdk: Any | None = None,
        approval_sink: Callable[[ApprovalRequest], None] | None = None,
    ) -> Any:
        sdk = sdk or _load_sdk()
        workspace_files = WorkspaceFileStore(
            request.workspace_id,
            permission_mode=request.permission_mode,
        ).files_dir
        workspace_files.mkdir(parents=True, exist_ok=True)

        return sdk.ClaudeAgentOptions(
            cwd=str(workspace_files),
            model=request.model,
            system_prompt=request.system_prompt,
            permission_mode=_claude_permission_mode(request.permission_mode),
            allowed_tools=request.allowed_tools or _allowed_tools(request.permission_mode),
            disallowed_tools=request.disallowed_tools or _disallowed_tools(request.permission_mode),
            mcp_servers=_mcp_servers(request.workspace_id),
            strict_mcp_config=True,
            can_use_tool=_build_can_use_tool(request, sdk=sdk, approval_sink=approval_sink),
            max_turns=request.max_turns,
            resume=request.resume,
        )


def _load_sdk() -> Any:
    try:
        return importlib.import_module("claude_agent_sdk")
    except ImportError as exc:
        raise ClaudeAgentSDKUnavailableError(
            "claude-agent-sdk is required for Claude Agent mode. "
            "Install project dependencies or run `pip install claude-agent-sdk>=0.2.111`."
        ) from exc


def _claude_permission_mode(mode: str) -> str:
    normalized = normalize_permission_mode(mode)
    return {
        "read-only": "dontAsk",
        "workspace-write": "acceptEdits",
        "ask": "default",
        "unrestricted": "bypassPermissions",
    }[normalized]


def _allowed_tools(mode: str) -> list[str]:
    normalized = normalize_permission_mode(mode)
    if normalized == "read-only":
        return ["Read", "Glob", "Grep"]
    if normalized == "workspace-write":
        return ["Read", "Glob", "Grep", "Edit", "Write"]
    if normalized == "ask":
        return ["Read", "Glob", "Grep", "AskUserQuestion"]
    return ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "WebSearch", "WebFetch"]


def _disallowed_tools(mode: str) -> list[str]:
    normalized = normalize_permission_mode(mode)
    if normalized == "read-only":
        return ["Edit", "Write", "Bash"]
    if normalized == "workspace-write":
        return ["Bash"]
    return []


def _mcp_servers(workspace_id: str) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for server in WorkspaceConfigStore(workspace_id).list_mcp_servers():
        if not server.enabled:
            continue
        servers[server.name] = _mcp_server_config(server)
    return servers


def _mcp_server_config(server: MCPServerConfig) -> dict[str, Any]:
    config: dict[str, Any] = {
        "command": server.command,
        "args": server.args,
    }
    if server.env:
        config["env"] = server.env
    return config


def _build_can_use_tool(
    request: ClaudeAgentRunRequest,
    *,
    sdk: Any,
    approval_sink: Callable[[ApprovalRequest], None] | None = None,
) -> Callable[..., Any] | None:
    if normalize_permission_mode(request.permission_mode) != "ask":
        return None

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        arguments = _normalize_tool_input(tool_input, kwargs)
        approval = ApprovalStore().create(
            agent_id=request.agent_id or f"claude:{request.workspace_id}",
            workspace_id=request.workspace_id,
            tool_name=tool_name,
            arguments=arguments,
            access_level=_claude_tool_access_level(tool_name),
            reason=_claude_tool_reason(tool_name, arguments),
            metadata={
                "runtime": "claude-agent-sdk",
                "permission_mode": request.permission_mode,
                "callback_args": [str(item) for item in args],
            },
        )
        if approval_sink:
            approval_sink(approval)
        return _permission_deny(
            sdk,
            "Waiting for human approval in Cognix. Approve the request and resume the run.",
        )

    return can_use_tool


def _normalize_tool_input(
    tool_input: dict[str, Any] | None,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(tool_input, dict):
        return tool_input
    if "tool_input" in kwargs and isinstance(kwargs["tool_input"], dict):
        return kwargs["tool_input"]
    if "input" in kwargs and isinstance(kwargs["input"], dict):
        return kwargs["input"]
    return {}


def _claude_tool_access_level(tool_name: str) -> str:
    normalized = tool_name.lower()
    if normalized in {"read", "glob", "grep", "ls"}:
        return "read"
    if normalized in {"bash", "webfetch", "websearch"}:
        return "dangerous"
    return "write"


def _claude_tool_reason(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "AskUserQuestion":
        question = str(arguments.get("question") or arguments.get("prompt") or "").strip()
        if question:
            return f"Claude Agent requests user input: {question}"
        return "Claude Agent requests user input."
    return f"Claude Agent requests permission to run {tool_name}."


def _permission_deny(sdk: Any, message: str) -> Any:
    deny = getattr(sdk, "PermissionResultDeny", None)
    if deny is None:
        return {"behavior": "deny", "message": message, "interrupt": True}
    for kwargs in (
        {"message": message, "interrupt": True},
        {"message": message},
    ):
        try:
            return deny(**kwargs)
        except TypeError:
            continue
    return deny(message)


def _approval_events(approvals: list[ApprovalRequest]) -> list[AgentEvent]:
    events = [
        AgentEvent(
            "approval_request",
            {
                "id": approval.id,
                "agent_id": approval.agent_id,
                "workspace_id": approval.workspace_id,
                "tool_name": approval.tool_name,
                "arguments": approval.arguments,
                "access_level": approval.access_level,
                "reason": approval.reason,
                "status": approval.status,
                "metadata": approval.metadata,
            },
        )
        for approval in approvals
    ]
    approvals.clear()
    return events


def _message_to_events(message: Any) -> list[AgentEvent]:
    if hasattr(message, "result"):
        result = str(message.result or "")
        return [
            AgentEvent("delta", {"delta": result}),
            AgentEvent("done", {"finish_reason": "stop"}),
        ]

    events: list[AgentEvent] = []
    content = getattr(message, "content", None)
    if isinstance(content, list):
        for block in content:
            name = getattr(block, "name", None)
            if name:
                events.append(
                    AgentEvent(
                        "tool_call",
                        {
                            "id": getattr(block, "id", ""),
                            "name": name,
                            "arguments": getattr(block, "input", {}),
                            "args": getattr(block, "input", {}),
                        },
                    )
                )
            text = getattr(block, "text", None)
            if text:
                events.append(AgentEvent("delta", {"delta": str(text)}))
    return events
