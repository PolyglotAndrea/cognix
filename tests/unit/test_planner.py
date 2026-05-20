"""Tests for planner service robustness and dependency propagation."""

from __future__ import annotations

import pytest

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.planner.schema import PlanStep, WorkspacePlan
from cognix.planner.service import PlannerService
from cognix.storage.database import close_db, get_session, init_db
from cognix.storage.models import AgentModel


@pytest.mark.asyncio
async def test_agent_name_reuse_and_deduplication(tmp_path, monkeypatch) -> None:
    # Setup test DB and home directory environment variables
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path))
    await init_db()

    # Configure PlannerService with mock home
    home = CognixHome(root=tmp_path).ensure()
    workspace = WorkspaceManager(home).create("TestWorkspace")
    planner = PlannerService(home=home)

    try:
        # Create an agent for the first time
        agent_id_1 = await planner._apply_create_agent(
            workspace_id=workspace.id,
            params={"name": "test-agent", "model": "gpt-4o", "system_prompt": "Hello"}
        )

        # Create/apply again with the same name
        agent_id_2 = await planner._apply_create_agent(
            workspace_id=workspace.id,
            params={"name": "test-agent", "model": "gpt-4o", "system_prompt": "Hello again"}
        )

        # Verify both executions returned the same agent ID (de-duplication/reuse)
        assert agent_id_1 == agent_id_2

        # Verify there is exactly one agent in the DB
        async with get_session() as session:
            from sqlalchemy import select
            res = await session.execute(select(AgentModel))
            agents = res.scalars().all()
            assert len(agents) == 1
            assert agents[0].id == agent_id_1
            assert agents[0].name == "test-agent"

    finally:
        await close_db()


@pytest.mark.asyncio
async def test_agent_name_collision_is_unique_across_workspaces(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path))
    await init_db()

    home = CognixHome(root=tmp_path).ensure()
    manager = WorkspaceManager(home)
    ws1 = manager.create("Workspace One")
    ws2 = manager.create("Workspace Two")
    planner = PlannerService(home=home)

    try:
        first = await planner._apply_create_agent(
            workspace_id=ws1.id,
            params={"name": "task-agent", "model": "gpt-4o"},
        )
        second_params = {"name": "task-agent", "model": "gpt-4o"}
        second = await planner._apply_create_agent(
            workspace_id=ws2.id,
            params=second_params,
        )

        assert first != second
        assert second_params["_resolved_agent_name"].startswith("task-agent-")

        async with get_session() as session:
            from sqlalchemy import select

            res = await session.execute(select(AgentModel).order_by(AgentModel.created_at))
            agents = res.scalars().all()
            assert len(agents) == 2
            assert {agent.workspace_id for agent in agents} == {ws1.id, ws2.id}
            assert len({agent.name for agent in agents}) == 2
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_create_task_rejects_empty_agent_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path))
    await init_db()

    home = CognixHome(root=tmp_path).ensure()
    workspace = WorkspaceManager(home).create("TestWorkspace")
    planner = PlannerService(home=home)

    try:
        with pytest.raises(ValueError, match="no agent_id was resolved"):
            await planner._apply_create_task(
                workspace_id=workspace.id,
                params={
                    "name": "bad-task",
                    "agent_name": "missing-agent",
                    "schedule_type": "once",
                    "input": "run",
                },
                agent_name_to_id={},
                user_id="test-user",
            )
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_planner_dependency_failure_propagation(tmp_path, monkeypatch) -> None:
    # Setup test DB and home directory environment variables
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path))
    await init_db()

    home = CognixHome(root=tmp_path).ensure()
    workspace = WorkspaceManager(home).create("TestWorkspace")
    planner = PlannerService(home=home)

    try:
        # Construct a plan with dependencies:
        # step_1: invalid action that fails
        # step_2: create task depending on step_1
        step_1 = PlanStep(
            id="step_1",
            action="invalid_action",
            description="Failing step",
            params={},
            depends_on=[]
        )
        step_2 = PlanStep(
            id="step_2",
            action="create_task",
            description="Step depending on failed agent creation",
            params={
                "name": "dependent-task",
                "agent_name": "non-existent-agent",
                "schedule_type": "once",
                "input": "Execute task",
            },
            depends_on=["step_1"]
        )

        plan = WorkspacePlan(
            id="test-plan-id",
            workspace_id=workspace.id,
            summary="Test plan",
            steps=[step_1, step_2],
            status="confirmed"
        )

        # Save plan to disk so apply_plan can load it
        planner._save_plan(plan)

        # Apply plan
        result = await planner.apply_plan(
            workspace_id=workspace.id,
            plan_id="test-plan-id",
            user_id="test-user"
        )

        # Check result
        assert result["status"] == "failed"
        assert "step_1" in result["plan"]["step_statuses"]
        assert result["plan"]["step_statuses"]["step_1"] == "failed"
        assert "step_2" in result["plan"]["step_statuses"]
        assert result["plan"]["step_statuses"]["step_2"] == "failed"

        # Verify no task was created in the DB since it depends on the failed step_1
        from cognix.storage.models import ScheduledTaskModel
        async with get_session() as session:
            from sqlalchemy import select
            res = await session.execute(select(ScheduledTaskModel))
            tasks = res.scalars().all()
            assert len(tasks) == 0

    finally:
        await close_db()


def test_orchestration_listener_streaming(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path))
    from cognix.local.home import CognixHome
    from cognix.local.workspace import WorkspaceManager
    from cognix.orchestrator.protocol import (
        OrchestrationEvent,
        emit_orchestration_event,
        register_orchestration_listener,
        unregister_orchestration_listener,
    )

    home = CognixHome(root=tmp_path).ensure()
    workspace = WorkspaceManager(home).create("test-ws")

    events_received = []

    def listener(event):
        events_received.append(event)

    register_orchestration_listener(listener)
    try:
        event = OrchestrationEvent(
            workspace_id=workspace.id,
            type="agent.created",
            stage="execution",
            status="created",
            plan_id="test-plan",
            agent_id="test-agent",
        )
        emit_orchestration_event(event, home=home, snapshot=False)

        assert len(events_received) == 1
        assert events_received[0].agent_id == "test-agent"
        assert events_received[0].plan_id == "test-plan"
    finally:
        unregister_orchestration_listener(listener)
