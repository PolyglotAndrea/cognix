"""Tests for scheduler workspace events."""

from __future__ import annotations

import pytest

from cognix.core.agent import Agent
from cognix.core.registry import AgentRegistry
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.scheduler.executor import TaskExecutor


@pytest.mark.asyncio
async def test_task_executor_appends_workspace_events(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    home = CognixHome.default().ensure()
    workspace = WorkspaceManager(home).create("Events")
    registry = AgentRegistry()
    agent = Agent(id="agent-1", name="worker", model="echo", workspace_id=workspace.id)
    registry.register(agent)

    executor = TaskExecutor(agent_registry=registry)

    async def persist_noop(run):
        return None

    monkeypatch.setattr(executor, "_persist_run", persist_noop)

    run = await executor.execute(
        "task-1",
        {
            "task_type": "agent_call",
            "agent_id": "agent-1",
            "message": "hello",
            "workspace_id": workspace.id,
            "api_key": "secret",
        },
    )

    assert run["status"] == "success"
    events = WorkspaceManager(home).list_events(workspace.id)
    assert [event["type"] for event in events] == ["task.started", "task.success"]
    assert events[0]["payload"]["api_key"] == "***"
    assert "hello" in events[1]["result"]
