"""Tests for JSON-RPC method-level RBAC."""

from __future__ import annotations

import pytest

from cognix.auth.dependencies import CurrentUser
from cognix.core.agent import Agent
from cognix.core.registry import AgentRegistry
from cognix.rpc.server import handle_rpc, rpc_permission
from cognix.storage.models import UserRole


@pytest.mark.asyncio
async def test_rpc_rejects_write_method_for_viewer() -> None:
    viewer = CurrentUser(id="u1", email="viewer@example.com", role=UserRole.VIEWER)

    response = await handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "agent.create",
            "params": {"name": "blocked"},
            "id": 1,
        },
        AgentRegistry(),
        user=viewer,
    )

    assert response["error"]["code"] == -32003
    assert response["error"]["message"] == "Permission required: agents:write"


@pytest.mark.asyncio
async def test_rpc_allows_unrestricted_system_methods_for_viewer() -> None:
    viewer = CurrentUser(id="u1", email="viewer@example.com", role=UserRole.VIEWER)

    response = await handle_rpc(
        {"jsonrpc": "2.0", "method": "system.ping", "params": {}, "id": 2},
        AgentRegistry(),
        user=viewer,
    )

    assert response["result"] == "pong"


def test_rpc_permission_mapping_documents_mutating_methods() -> None:
    assert rpc_permission("agent.create") == "agents:write"
    assert rpc_permission("task.pause") == "tasks:write"
    assert rpc_permission("task.runs") == "tasks:read"
    assert rpc_permission("task.trigger") == "tasks:write"
    assert rpc_permission("system.ping") is None


@pytest.mark.asyncio
async def test_rpc_agent_chat_attaches_workspace_mcp_tools(monkeypatch) -> None:
    calls = []
    registry = AgentRegistry()
    agent = Agent(id="agent-1", name="worker", model="echo", workspace_id="workspace-1")
    registry.register(agent)

    async def fake_get_agent_runtime(agent_id):
        return agent if agent_id == "agent-1" else None

    async def fake_attach(agent_arg):
        calls.append(agent_arg.id)

    monkeypatch.setattr("cognix.api.state.get_agent_runtime", fake_get_agent_runtime)
    monkeypatch.setattr("cognix.rpc.server._attach_runtime_mcp_tools", fake_attach)

    response = await handle_rpc(
        {
            "jsonrpc": "2.0",
            "method": "agent.chat",
            "params": {"agent_id": "agent-1", "message": "hi"},
            "id": 3,
        },
        registry,
    )

    assert calls == ["agent-1"]
    assert "Echo: hi" in response["result"]["content"]
