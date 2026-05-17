"""Claude Agent SDK runtime adapter."""

from __future__ import annotations

import importlib
import logging
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cognix.core.agent import AgentEvent
from cognix.core.permissions import decide_permission, normalize_permission_mode
from cognix.local.approvals import ApprovalRequest, ApprovalStore
from cognix.local.files import WorkspaceFileStore
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore

logger = logging.getLogger(__name__)


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
        waiting_approval_id = ""
        done_emitted = False
        options = self.build_options(
            request,
            sdk=sdk,
            approval_sink=pending_approvals.append,
        )
        try:
            async for message in sdk.query(prompt=request.prompt, options=options):
                for event in _approval_events(pending_approvals):
                    waiting_approval_id = str(event.data.get("id") or "")
                    yield event
                for event in _message_to_events(message):
                    done_emitted = done_emitted or event.type == "done"
                    yield event
            for event in _approval_events(pending_approvals):
                waiting_approval_id = str(event.data.get("id") or "")
                yield event
            if waiting_approval_id and not done_emitted:
                yield AgentEvent(
                    "done",
                    {
                        "finish_reason": "waiting_for_approval",
                        "approval_id": waiting_approval_id,
                    },
                )
        except Exception as exc:
            for event in _approval_events(pending_approvals):
                waiting_approval_id = str(event.data.get("id") or "")
                yield event
            if waiting_approval_id:
                yield AgentEvent(
                    "done",
                    {
                        "finish_reason": "waiting_for_approval",
                        "approval_id": waiting_approval_id,
                    },
                )
                return
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

    async def resume_approval(self, approval_id: str) -> dict[str, Any]:
        """Complete an approved Claude SDK permission request in Cognix."""
        store = ApprovalStore()
        approval = store.get(approval_id)
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")
        if approval.metadata.get("runtime") != "claude-agent-sdk":
            raise ValueError(f"Approval '{approval_id}' is not a Claude Agent SDK request")
        if approval.status != "approved":
            raise ValueError(f"Approval '{approval_id}' is not approved")

        resume_token = _approval_resume_token(approval)
        result = (
            f"Claude Agent SDK approval acknowledged for {approval.tool_name}."
            if not resume_token
            else (
                f"Claude Agent SDK approval acknowledged for {approval.tool_name}. "
                f"Resume token: {resume_token}"
            )
        )
        completed = store.complete(approval_id, result)
        return {
            "approval_id": approval_id,
            "runtime": "claude-agent-sdk",
            "result": result,
            "resume": resume_token,
            "resume_request": _run_request_dict(self.resume_request(approval)),
            "status": completed.status if completed else "completed",
        }

    def resume_request(
        self,
        approval: ApprovalRequest,
        *,
        prompt: str | None = None,
    ) -> ClaudeAgentRunRequest:
        """Build a Claude Agent SDK run request from a stored approval."""
        return ClaudeAgentRunRequest(
            workspace_id=approval.workspace_id,
            prompt=prompt or _approval_resume_prompt(approval),
            agent_id=approval.agent_id,
            permission_mode=str(approval.metadata.get("permission_mode", "ask")),
            resume=_approval_resume_token(approval) or None,
        )

    async def resume_stream(
        self,
        approval_id: str,
        *,
        response: str = "",
    ) -> AsyncIterator[AgentEvent]:
        """Stream a resumed Claude Agent SDK run for an approved Cognix approval."""
        store = ApprovalStore()
        if response:
            store.respond(approval_id, response)
        approval = store.get(approval_id)
        if not approval:
            yield AgentEvent("error", {"message": f"Approval '{approval_id}' not found"})
            return
        if approval.metadata.get("runtime") != "claude-agent-sdk":
            yield AgentEvent(
                "error",
                {"message": f"Approval '{approval_id}' is not a Claude Agent SDK request"},
            )
            return
        if approval.status != "approved":
            yield AgentEvent("error", {"message": f"Approval '{approval_id}' is not approved"})
            return

        prompt = response or approval.response or _approval_resume_prompt(approval)
        saw_error = False
        async for event in self.stream(self.resume_request(approval, prompt=prompt)):
            saw_error = saw_error or event.type == "error"
            yield event
        if not saw_error:
            store.complete(approval_id, "Claude Agent SDK approval resumed.")


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
        "plan": "plan",
        "unrestricted": "bypassPermissions",
    }[normalized]


def _allowed_tools(mode: str) -> list[str]:
    normalized = normalize_permission_mode(mode)
    if normalized == "read-only":
        return ["Read", "Glob", "Grep"]
    if normalized == "workspace-write":
        return ["Read", "Glob", "Grep", "Edit", "Write"]
    if normalized in ("ask", "plan"):
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
        _validate_mcp_server(server)
        servers[server.name] = _mcp_server_config(server)
    return servers


def _validate_mcp_server(server: MCPServerConfig) -> None:
    """Validate an MCP server config for basic safety.

    Logs warnings for potentially dangerous configurations. Does not block
    (the workspace admin is trusted), but makes issues visible.
    """
    cmd = server.command
    if not cmd:
        return

    # Warn if command is a relative path that doesn't resolve in PATH
    cmd_path = Path(cmd)
    if not cmd_path.is_absolute():
        resolved = shutil.which(cmd)
        if not resolved:
            logger.warning(
                "MCP server '%s' command '%s' not found in PATH",
                server.name,
                cmd,
            )
    elif not cmd_path.exists():
        logger.warning(
            "MCP server '%s' command path does not exist: %s",
            server.name,
            cmd,
        )

    # Warn on suspicious env var names
    if server.env:
        sensitive_keys = {
            "AWS_SECRET_ACCESS_KEY",
            "DATABASE_URL",
            "PRIVATE_KEY",
            "SECRET_KEY",
            "TOKEN",
            "PASSWORD",
        }
        for key in server.env:
            upper = key.upper()
            for pattern in sensitive_keys:
                if pattern in upper:
                    logger.warning(
                        "MCP server '%s' env var '%s' may contain secrets",
                        server.name,
                        key,
                    )
                    break


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
    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        *args,
        **kwargs,
    ):
        arguments = _normalize_tool_input(tool_input, kwargs)
        access_level = _claude_tool_access_level(tool_name, arguments)
        decision = decide_permission(
            request.permission_mode,
            access_level,
            f"Claude Agent SDK tool '{tool_name}'",
        )
        policy_decision = await _claude_policy_decision(
            request,
            tool_name,
            arguments,
            access_level,
        )
        if not policy_decision.allowed and not policy_decision.requires_approval:
            return _permission_deny(
                sdk,
                policy_decision.reason or "Denied by Cognix workspace policy.",
            )

        if decision.allowed and policy_decision.allowed:
            return _permission_allow(sdk, arguments)

        approval = ApprovalStore().create(
            agent_id=request.agent_id or f"claude:{request.workspace_id}",
            workspace_id=request.workspace_id,
            tool_name=tool_name,
            arguments=arguments,
            access_level=access_level,
            reason=(
                policy_decision.reason
                or decision.reason
                or _claude_tool_reason(tool_name, arguments)
            ),
            kind=_claude_approval_kind(tool_name, request.permission_mode),
            metadata={
                "runtime": "claude-agent-sdk",
                "permission_mode": request.permission_mode,
                "callback_args": [str(item) for item in args],
                **_extract_callback_metadata(args, kwargs),
            },
        )
        if approval_sink:
            approval_sink(approval)
        return _permission_deny(
            sdk,
            "Waiting for human approval in Cognix. Approve the request and resume the run.",
        )

    return can_use_tool


async def _claude_policy_decision(
    request: ClaudeAgentRunRequest,
    tool_name: str,
    arguments: dict[str, Any],
    access_level: str,
):
    from cognix.core.policy import PolicyResult, WorkspacePolicyService

    policy = WorkspacePolicyService(request.workspace_id)
    normalized = tool_name.lower()
    if normalized in {"bash", "shell"}:
        command = str(arguments.get("command") or arguments.get("cmd") or "")
        return await policy.check_command(
            command,
            permission_mode=request.permission_mode,
            agent_id=request.agent_id,
        )
    if normalized in {"write", "edit", "multiedit"}:
        path = str(arguments.get("file_path") or arguments.get("path") or "")
        return await policy.check_file_access(
            path,
            "write",
            permission_mode=request.permission_mode,
            agent_id=request.agent_id,
        )
    if normalized in {"read", "glob", "grep"}:
        path = str(arguments.get("file_path") or arguments.get("path") or arguments.get("pattern") or "")
        return await policy.check_file_access(
            path,
            "read",
            permission_mode=request.permission_mode,
            agent_id=request.agent_id,
        )
    if normalized in {"webfetch", "websearch"}:
        url = str(arguments.get("url") or arguments.get("query") or "")
        return await policy.check_network_access(
            url,
            permission_mode=request.permission_mode,
            agent_id=request.agent_id,
        )
    if tool_name.startswith("mcp__"):
        return await policy.check_mcp_tool(
            tool_name,
            access_level,
            permission_mode=request.permission_mode,
            agent_id=request.agent_id,
        )
    return PolicyResult(allowed=True)


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


def _claude_tool_access_level(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    arguments = arguments or {}
    normalized = tool_name.lower()
    if normalized in {"read", "glob", "grep", "ls"}:
        return "read"
    if normalized in {"bash", "webfetch", "websearch"} or arguments.get(
        "dangerouslyDisableSandbox"
    ):
        return "dangerous"
    return "write"


def _claude_tool_reason(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "AskUserQuestion":
        question = str(arguments.get("question") or arguments.get("prompt") or "").strip()
        if question:
            return f"Claude Agent requests user input: {question}"
        return "Claude Agent requests user input."
    return f"Claude Agent requests permission to run {tool_name}."


def _claude_approval_kind(tool_name: str, permission_mode: str) -> str:
    if tool_name == "AskUserQuestion":
        return "question"
    if normalize_permission_mode(permission_mode) == "plan":
        return "plan_confirmation"
    return "tool_permission"


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


def _permission_allow(sdk: Any, arguments: dict[str, Any]) -> Any:
    allow = getattr(sdk, "PermissionResultAllow", None)
    if allow is None:
        return {"behavior": "allow", "updatedInput": arguments}
    for kwargs in (
        {"updated_input": arguments},
        {"updatedInput": arguments},
        {},
    ):
        try:
            return allow(**kwargs)
        except TypeError:
            continue
    return allow()


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
                "kind": approval.kind,
                "response": approval.response,
                "metadata": approval.metadata,
            },
        )
        for approval in approvals
    ]
    approvals.clear()
    return events


def _approval_resume_token(approval: ApprovalRequest) -> str:
    for key in ("resume", "resume_token", "session_id", "conversation_id"):
        value = approval.metadata.get(key)
        if value:
            return str(value)
    return ""


def _approval_resume_prompt(approval: ApprovalRequest) -> str:
    if approval.kind == "question" and approval.response:
        return approval.response
    if approval.kind == "plan_confirmation":
        return "The plan has been confirmed by the user. Continue the run."
    if approval.status == "approved":
        return f"The user approved {approval.tool_name}. Continue the run."
    return "Continue the run."


def _run_request_dict(request: ClaudeAgentRunRequest) -> dict[str, Any]:
    return {
        "workspace_id": request.workspace_id,
        "prompt": request.prompt,
        "agent_id": request.agent_id,
        "model": request.model,
        "system_prompt": request.system_prompt,
        "permission_mode": request.permission_mode,
        "max_turns": request.max_turns,
        "resume": request.resume,
        "allowed_tools": request.allowed_tools,
        "disallowed_tools": request.disallowed_tools,
    }


def _extract_callback_metadata(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for item in (*args, kwargs):
        _collect_resume_metadata(item, metadata, depth=0)
    return metadata


def _collect_resume_metadata(value: Any, metadata: dict[str, Any], *, depth: int) -> None:
    if value is None or depth > 3:
        return
    keys = ("resume", "resume_token", "session_id", "conversation_id", "tool_use_id", "request_id")
    if isinstance(value, dict):
        for key in keys:
            if key in value and key not in metadata and _is_metadata_scalar(value[key]):
                metadata[key] = value[key]
        for nested in value.values():
            if isinstance(nested, dict) or hasattr(nested, "__dict__"):
                _collect_resume_metadata(nested, metadata, depth=depth + 1)
        return
    for key in keys:
        if key in metadata or not hasattr(value, key):
            continue
        item = getattr(value, key)
        if _is_metadata_scalar(item):
            metadata[key] = item


def _is_metadata_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


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
