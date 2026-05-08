"""Tests for workspace-scoped skills and MCP configuration."""

from __future__ import annotations

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import WorkspaceConfigStore


def test_workspace_config_updates_skills_and_context(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Config")
    store = WorkspaceConfigStore(workspace.id, home=home)

    settings = store.set_skill_enabled("web_search", True)
    assert settings["enabled_skills"] == ["web_search"]

    settings = store.update_settings({"context": {"max_history_messages": 8}})
    assert settings["context"]["max_history_messages"] == 8
    assert settings["context"]["include_cold_memory"] is True

    settings = store.set_skill_enabled("web_search", False)
    assert settings["enabled_skills"] == []


def test_workspace_config_manages_mcp_servers(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Config")
    store = WorkspaceConfigStore(workspace.id, home=home)

    server = store.upsert_mcp_server(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        env={"ROOT": "/tmp"},
    )

    assert server.name == "filesystem"
    assert store.list_mcp_servers() == [server]

    updated = store.upsert_mcp_server(
        server_id=server.id,
        name="filesystem",
        command="npx",
        args=["server-filesystem"],
        enabled=False,
    )

    assert updated.id == server.id
    assert updated.created_at == server.created_at
    assert updated.enabled is False
    assert store.delete_mcp_server(server.id) is True
    assert store.list_mcp_servers() == []
