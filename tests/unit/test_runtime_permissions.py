"""Tests for runtime permission enforcement."""

from __future__ import annotations

import pytest

from cognix.core.agent import Agent, AgentState
from cognix.core.permissions import PermissionDeniedError, decide_permission
from cognix.core.tool import tool
from cognix.local.files import WorkspaceFileStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


def test_decide_permission_modes() -> None:
    assert decide_permission("read-only", "read", "read file").allowed is True
    assert decide_permission("read-only", "write", "write file").allowed is False

    ask_decision = decide_permission("ask", "write", "write file")
    assert ask_decision.allowed is False
    assert ask_decision.requires_approval is True

    plan_decision = decide_permission("plan", "write", "write file")
    assert plan_decision.allowed is False
    assert plan_decision.requires_approval is True
    assert "plan confirmation" in plan_decision.reason

    dangerous = decide_permission("workspace-write", "dangerous", "shell")
    assert dangerous.allowed is False
    assert dangerous.requires_approval is True


@pytest.mark.asyncio
async def test_agent_blocks_write_tool_in_read_only_mode() -> None:
    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    agent = Agent(name="guarded", model="echo", tools=[write_note], permission_mode="read-only")
    result = await agent._execute_tool({"name": "write_note", "arguments": {"content": "x"}})

    assert result.startswith("Permission denied:")


@pytest.mark.asyncio
async def test_agent_marks_write_tool_as_approval_required_in_ask_mode(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))

    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    agent = Agent(name="guarded", model="echo", tools=[write_note], permission_mode="ask")
    result = await agent._execute_tool({"name": "write_note", "arguments": {"content": "x"}})

    assert result.startswith("Approval required [")
    assert agent.state == AgentState.WAITING


def test_workspace_file_store_respects_permission_mode(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Files")
    store = WorkspaceFileStore(workspace.id, home=home, permission_mode="read-only")

    with pytest.raises(PermissionDeniedError):
        store.write_text("note.md", "hello")


@pytest.mark.asyncio
async def test_agent_resumes_approved_tool(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))

    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    agent = Agent(name="guarded", model="echo", tools=[write_note], permission_mode="ask")
    blocked = await agent._execute_tool({"name": "write_note", "arguments": {"content": "x"}})
    approval_id = blocked.split("[", 1)[1].split("]", 1)[0]

    from cognix.local.approvals import ApprovalStore

    ApprovalStore().approve(approval_id)
    result = await agent.resume_approval(approval_id)

    assert result == "wrote x"
    assert ApprovalStore().get(approval_id).status == "completed"
    assert agent.state == AgentState.IDLE


@pytest.mark.asyncio
async def test_agent_streams_approval_request_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))

    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    class ApprovalAgent(Agent):
        async def _call_llm(self, ctx):
            from cognix.core.agent import AgentResponse

            return AgentResponse(
                content="",
                tool_calls=[
                    {
                        "id": "tc-1",
                        "name": "write_note",
                        "arguments": {"content": "x"},
                    }
                ],
            )

    agent = ApprovalAgent(
        name="guarded",
        model="mock",
        tools=[write_note],
        permission_mode="ask",
        max_iterations=1,
    )
    events = [event async for event in agent.stream_events("write")]

    approval = next(event for event in events if event.type == "approval_request")
    done = events[-1]
    assert approval.data["tool"] == "write_note"
    assert approval.data["approval_id"]
    assert done.type == "done"
    assert done.data["finish_reason"] == "waiting_for_approval"
    assert agent.state == AgentState.WAITING


@pytest.mark.asyncio
async def test_agent_run_stops_when_tool_needs_approval(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))

    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    class ApprovalAgent(Agent):
        async def _call_llm(self, ctx):
            from cognix.core.agent import AgentResponse

            return AgentResponse(
                content="",
                tool_calls=[
                    {
                        "id": "tc-1",
                        "name": "write_note",
                        "arguments": {"content": "x"},
                    }
                ],
            )

    agent = ApprovalAgent(
        name="guarded",
        model="mock",
        tools=[write_note],
        permission_mode="ask",
    )

    response = await agent.run("write")

    assert response.metadata["finish_reason"] == "waiting_for_approval"
    assert response.metadata["approval_id"]
    assert response.content.startswith("Approval required [")
    assert agent.state == AgentState.WAITING
