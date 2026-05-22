"""Tests for local-first workspace storage and memory pipeline."""

from __future__ import annotations

import pytest

from cognix.core.agent import Agent
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.memory.extractor import MemoryExtractor
from cognix.memory.facts import AtomicFactStore
from cognix.memory.pipeline import ColdMemoryStore, ContextBuilder
from cognix.memory.vault import MemoryVault


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

    manager.append_event(workspace.id, {"type": "test.event", "message": "hello"})
    events = manager.list_events(workspace.id)
    assert events[-1]["type"] == "test.event"
    assert events[-1]["message"] == "hello"


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
    await AtomicFactStore(home.state_db).upsert(
        workspace_id=workspace.id,
        entity_type="workspace",
        entity_id="default",
        key="output_format",
        value="markdown-report",
        confidence=0.9,
        source="test",
    )

    pack = await ContextBuilder(home).build("python tests", workspace_id=workspace.id)
    rendered = pack.render_system_context()

    assert "Alice" in rendered
    assert "Current project is Cognix" in rendered
    assert "markdown-report" in rendered
    assert "Python testing strategy" in rendered
    assert "Use pytest" in rendered

    cold_only = await ContextBuilder(home).build(
        "python tests",
        workspace_id=workspace.id,
        include_hot_memory=False,
        include_skills=False,
    )
    cold_rendered = cold_only.render_system_context()
    assert "Python testing strategy" in cold_rendered
    assert "Alice" not in cold_rendered
    assert "Use pytest" not in cold_rendered


def test_memory_extractor_returns_atomic_facts():
    facts = MemoryExtractor().extract(
        "默认输出格式是 markdown-report。林客入口：https://example.com/tickets 我喜欢简洁输出"
    )

    keys = {fact.key for fact in facts}
    assert "output_format" in keys
    assert "entry_url" in keys
    assert "preference" in keys


@pytest.mark.asyncio
async def test_memory_vault_projects_cold_memory_to_markdown(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Vault")
    store = ColdMemoryStore(home.state_db)

    record = await store.remember(
        "We decided to keep provider keys encrypted and never save masked values.",
        workspace_id=workspace.id,
        scope="workspace",
        kind="decision",
        summary="Provider key safety decision",
        metadata={"source": "test", "artifact_id": "artifact-1"},
    )

    path = MemoryVault(home).record_path(record)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Provider key safety decision" in content
    assert f"id: {record.id}" in content
    assert "artifact-1" in content


@pytest.mark.asyncio
async def test_context_builder_balanced_strategy_uses_router_and_budget(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    (home.skills_dir / "testing.md").write_text(
        "Use pytest and keep tests focused.",
        encoding="utf-8",
    )
    workspace = WorkspaceManager(home).create("Code")
    store = ColdMemoryStore(home.state_db)
    await store.remember(
        "Yesterday we discussed deployment logs.",
        workspace_id=workspace.id,
        summary="Deployment logs discussion",
    )

    pack = await ContextBuilder(home).build(
        "how to run testing workflow steps",
        workspace_id=workspace.id,
        routing_strategy="balanced",
        token_budget=400,
    )
    rendered = pack.render_system_context()

    assert "Use pytest" in rendered
    assert "Deployment logs discussion" not in rendered
    assert any(source["source"] == "memory_router" for source in pack.source_details)
    assert any(source["source"] == "context_budget" for source in pack.source_details)


@pytest.mark.asyncio
async def test_agent_writes_cold_memory_under_cognix_home(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    agent = Agent(name="test", model="echo", workspace_id="ws-test")

    response = await agent.run("remember this")

    assert "remember this" in response.content
    store = ColdMemoryStore(CognixHome.default().ensure().state_db)
    results = await store.search("remember", workspace_id="ws-test")
    assert results


@pytest.mark.asyncio
async def test_agent_memory_write_approval_blocks_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    agent = Agent(name="test", model="echo", workspace_id="ws-test", permission_mode="ask")

    response = await agent.run("remember my default output format is markdown-report")

    assert "markdown-report" in response.content
    store = ColdMemoryStore(CognixHome.default().ensure().state_db)
    results = await store.search("markdown-report", workspace_id="ws-test")
    assert results == []
