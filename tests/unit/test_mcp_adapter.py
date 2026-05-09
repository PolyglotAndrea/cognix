"""Tests for MCP tool adapter."""

from __future__ import annotations

from typing import Any

import pytest

from cognix.core.agent import Agent
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore
from cognix.mcp.adapter import attach_workspace_mcp_tools, mcp_server_to_core_tools
from cognix.mcp.client import MCPToolSpec
from cognix.mcp.manager import MCPRuntimeManager


class FakeMCPClient:
    list_calls = 0

    def __init__(self, server: MCPServerConfig) -> None:
        self.server = server

    async def __aenter__(self) -> FakeMCPClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def list_tools(self) -> list[MCPToolSpec]:
        FakeMCPClient.list_calls += 1
        return [
            MCPToolSpec(
                name="search",
                description="Search docs",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                annotations={"readOnlyHint": True},
            ),
            MCPToolSpec(name="write_file", description="Write file"),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return f"{name}:{arguments}"


class FailingMCPClient:
    def __init__(self, server: MCPServerConfig) -> None:
        self.server = server
        self.stderr_tail = "server failed to start"

    async def __aenter__(self) -> FailingMCPClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def list_tools(self) -> list[MCPToolSpec]:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_mcp_server_to_core_tools_maps_specs_and_access_levels() -> None:
    server = MCPServerConfig(id="mcp1", name="Docs Server", command="fake")

    tools = await mcp_server_to_core_tools(server, client_factory=FakeMCPClient)

    assert [tool.name for tool in tools] == ["mcp_docs_server_search", "mcp_docs_server_write_file"]
    assert tools[0].access_level == "read"
    assert tools[1].access_level == "write"
    assert await tools[0].execute(query="cognix") == "search:{'query': 'cognix'}"


@pytest.mark.asyncio
async def test_attach_workspace_mcp_tools_adds_tools_to_agent(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("MCP")
    WorkspaceConfigStore(workspace.id, home=home).upsert_mcp_server(
        name="Docs",
        command="fake",
        enabled=True,
    )
    monkeypatch.setenv("COGNIX_HOME", str(home.root))
    agent = Agent(name="worker", model="echo", workspace_id=workspace.id)

    attached = await attach_workspace_mcp_tools(agent, workspace.id, client_factory=FakeMCPClient)

    assert attached == ["mcp_docs_search", "mcp_docs_write_file"]
    assert "mcp_docs_search" in [tool.name for tool in agent.tools]


@pytest.mark.asyncio
async def test_mcp_runtime_manager_caches_discovery() -> None:
    FakeMCPClient.list_calls = 0
    server = MCPServerConfig(id="mcp1", name="Docs Server", command="fake")
    manager = MCPRuntimeManager(client_factory=FakeMCPClient, cache_ttl_seconds=60)

    first = await manager.list_tools(server)
    second = await manager.list_tools(server)
    status = manager.status(server)

    assert first == second
    assert FakeMCPClient.list_calls == 1
    assert status.status == "ready"
    assert status.tool_count == 2


@pytest.mark.asyncio
async def test_mcp_runtime_manager_tracks_errors_and_stop_restart() -> None:
    server = MCPServerConfig(id="mcp1", name="Docs Server", command="fake")
    manager = MCPRuntimeManager(client_factory=FailingMCPClient, cache_ttl_seconds=60)

    status = await manager.probe(server)

    assert status.status == "error"
    assert status.error == "boom"
    assert status.stderr == "server failed to start"

    stopped = manager.stop(server)
    assert stopped.status == "stopped"
    assert manager.status(server).status == "stopped"

    restarted = await manager.restart(server)
    assert restarted.status == "error"
