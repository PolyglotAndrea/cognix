"""Adapters from MCP tools to Cognix core Tools."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from cognix.core.agent import Agent
from cognix.core.tool import Tool
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore
from cognix.mcp.client import MCPClient, MCPToolSpec
from cognix.mcp.manager import MCPRuntimeManager, default_mcp_runtime

MCPClientFactory = Callable[[MCPServerConfig], MCPClient]


async def mcp_server_to_core_tools(
    server: MCPServerConfig,
    *,
    client_factory: MCPClientFactory = MCPClient,
    runtime: MCPRuntimeManager | None = None,
    force_refresh: bool = False,
) -> list[Tool]:
    if not server.enabled:
        return []

    manager = runtime or (
        default_mcp_runtime
        if client_factory is MCPClient
        else MCPRuntimeManager(client_factory=client_factory)
    )
    specs = await manager.list_tools(server, force_refresh=force_refresh)

    disabled_tools = set(_disabled_tools(server))
    return [
        _spec_to_tool(server, spec, client_factory=client_factory, runtime=manager)
        for spec in specs
        if spec.name not in disabled_tools
    ]


async def attach_workspace_mcp_tools(
    agent: Agent,
    workspace_id: str,
    *,
    client_factory: MCPClientFactory = MCPClient,
    runtime: MCPRuntimeManager | None = None,
) -> list[str]:
    """Discover enabled workspace MCP servers and attach their tools to an Agent."""
    attached: list[str] = []
    config = WorkspaceConfigStore(workspace_id)
    for server in config.list_mcp_servers():
        if not server.enabled:
            continue
        for tool in await mcp_server_to_core_tools(
            server,
            client_factory=client_factory,
            runtime=runtime,
        ):
            if tool.name in [existing.name for existing in agent.tools]:
                agent.remove_tool(tool.name)
            agent.add_tool(tool)
            attached.append(tool.name)
    return attached


def _spec_to_tool(
    server: MCPServerConfig,
    spec: MCPToolSpec,
    *,
    client_factory: MCPClientFactory,
    runtime: MCPRuntimeManager | None = None,
) -> Tool:
    tool_name = f"mcp_{_safe_name(server.name)}_{_safe_name(spec.name)}"
    original_name = spec.name

    async def _handler(**kwargs: Any) -> Any:
        # Use persistent connection via runtime manager when available
        if runtime is not None:
            return await runtime.call_tool(server, original_name, kwargs)
        async with client_factory(server) as client:
            return await client.call_tool(original_name, kwargs)

    return Tool(
        name=tool_name,
        description=spec.description or f"MCP tool {original_name} from {server.name}",
        handler=_handler,
        parameters=spec.input_schema or {"type": "object", "properties": {}},
        access_level=_mcp_access_level(server, spec),
    )


def _mcp_access_level(server: MCPServerConfig, spec: MCPToolSpec) -> str:
    tool_access = server.metadata.get("tool_access", {})
    if isinstance(tool_access, dict) and spec.name in tool_access:
        return str(tool_access[spec.name])
    if server.metadata.get("access_level"):
        return str(server.metadata["access_level"])
    if spec.annotations.get("readOnlyHint") is True:
        return "read"
    lowered = spec.name.lower()
    if any(token in lowered for token in ("delete", "remove", "exec", "shell", "run_command")):
        return "dangerous"
    if any(token in lowered for token in ("write", "create", "update", "edit", "save")):
        return "write"
    return "read"


def _disabled_tools(server: MCPServerConfig) -> list[str]:
    disabled = server.metadata.get("disabled_tools", [])
    if isinstance(disabled, list):
        return [str(item) for item in disabled]
    return []


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return safe or "server"
