"""Claude Agent SDK runtime adapter."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from cognix.core.agent import AgentEvent
from cognix.core.permissions import normalize_permission_mode
from cognix.local.files import WorkspaceFileStore
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore


class ClaudeAgentSDKUnavailableError(RuntimeError):
    """Raised when claude-agent-sdk is not installed in the runtime environment."""


@dataclass(frozen=True)
class ClaudeAgentRunRequest:
    workspace_id: str
    prompt: str
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
        options = self.build_options(request, sdk=sdk)
        try:
            async for message in sdk.query(prompt=request.prompt, options=options):
                for event in _message_to_events(message):
                    yield event
        except Exception as exc:
            yield AgentEvent("error", {"message": str(exc), "error": str(exc)})

    def build_options(self, request: ClaudeAgentRunRequest, *, sdk: Any | None = None) -> Any:
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
