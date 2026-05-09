"""Tests for REST/RPC agent listing consistency."""

from __future__ import annotations

import pytest

from cognix.api.state import agent_registry, list_agent_runtimes
from cognix.storage.database import close_db, get_session, init_db
from cognix.storage.models import AgentModel


@pytest.mark.asyncio
async def test_list_agent_runtimes_hydrates_persisted_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    await init_db()
    agent_registry.clear()
    try:
        async with get_session() as session:
            session.add(
                AgentModel(
                    id="agent-1",
                    name="persisted",
                    model="echo",
                    workspace_id="workspace-1",
                    permission_mode="plan",
                )
            )

        agents = await list_agent_runtimes()

        assert [agent["id"] for agent in agents] == ["agent-1"]
        assert agents[0]["permission_mode"] == "plan"
        assert agent_registry.get("agent-1") is not None
    finally:
        agent_registry.clear()
        await close_db()
