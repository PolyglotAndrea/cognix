"""Tests for local-first workspace storage and memory pipeline."""

from __future__ import annotations

import pytest

from cognix.core.agent import Agent
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.memory.pipeline import ColdMemoryStore, ContextBuilder


def test_cognix_home_ensure_creates_layout(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()

    assert home.user_file.exists()
    assert home.memory_file.exists()
    assert home.events_file.exists()
    assert home.workspaces_dir.exists()
    assert home.skills_dir.exists()


def test_workspace_manager_create_and_list(tmp_path):
    manager = WorkspaceManager(CognixHome(tmp_path / ".cognix"))
    workspace = manager.create("Demo Workspace", description="Test")

    assert workspace.name == "Demo Workspace"
    assert (manager.workspace_path(workspace.id) / "workspace.json").exists()
    assert (manager.workspace_path(workspace.id) / "MEMORY.md").exists()
    assert manager.get(workspace.id) == workspace
    assert manager.list_all() == [workspace]


@pytest.mark.asyncio
async def test_context_builder_loads_hot_cold_and_procedural_memory(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    home.user_file.write_text("Name: Alice", encoding="utf-8")
    home.memory_file.write_text("Prefers concise answers.", encoding="utf-8")
    (home.skills_dir / "python.md").write_text("Use pytest for Python tests.", encoding="utf-8")

    manager = WorkspaceManager(home)
    workspace = manager.create("Code")
    (manager.workspace_path(workspace.id) / "MEMORY.md").write_text(
        "Current project is Cognix.",
        encoding="utf-8",
    )

    store = ColdMemoryStore(home.state_db)
    await store.remember(
        "We discussed Python test strategy yesterday.",
        workspace_id=workspace.id,
        summary="Python testing strategy",
    )

    pack = await ContextBuilder(home).build("python tests", workspace_id=workspace.id)
    rendered = pack.render_system_context()

    assert "Alice" in rendered
    assert "Current project is Cognix" in rendered
    assert "Python testing strategy" in rendered
    assert "Use pytest" in rendered


@pytest.mark.asyncio
async def test_agent_writes_cold_memory_under_cognix_home(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    agent = Agent(name="test", model="echo", workspace_id="ws-test")

    response = await agent.run("remember this")

    assert "remember this" in response.content
    store = ColdMemoryStore(CognixHome.default().ensure().state_db)
    results = await store.search("remember", workspace_id="ws-test")
    assert results
