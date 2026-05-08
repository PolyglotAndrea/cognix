"""Tests for persisted Agent runtime configuration."""

from __future__ import annotations

from types import SimpleNamespace

from cognix.api.state import agent_from_model
from cognix.core.agent import Agent


def test_agent_to_dict_includes_workspace_and_permission_mode() -> None:
    agent = Agent(
        name="worker",
        workspace_id="workspace-1",
        permission_mode="read-only",
    )

    data = agent.to_dict()

    assert data["workspace_id"] == "workspace-1"
    assert data["permission_mode"] == "read-only"


def test_agent_from_model_hydrates_runtime_config() -> None:
    row = SimpleNamespace(
        id="agent-1",
        name="worker",
        model="echo",
        system_prompt="hi",
        temperature=0.1,
        max_iterations=2,
        description="",
        api_base=None,
        workspace_id="workspace-1",
        permission_mode="ask",
    )

    agent = agent_from_model(row)

    assert agent.workspace_id == "workspace-1"
    assert agent.permission_mode == "ask"
