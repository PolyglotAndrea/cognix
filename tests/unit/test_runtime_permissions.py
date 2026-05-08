"""Tests for runtime permission enforcement."""

from __future__ import annotations

import pytest

from cognix.core.agent import Agent
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
async def test_agent_marks_write_tool_as_approval_required_in_ask_mode() -> None:
    @tool(name="write_note", description="Write a note", access_level="write")
    async def write_note(content: str) -> str:
        return f"wrote {content}"

    agent = Agent(name="guarded", model="echo", tools=[write_note], permission_mode="ask")
    result = await agent._execute_tool({"name": "write_note", "arguments": {"content": "x"}})

    assert result.startswith("Approval required:")


def test_workspace_file_store_respects_permission_mode(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Files")
    store = WorkspaceFileStore(workspace.id, home=home, permission_mode="read-only")

    with pytest.raises(PermissionDeniedError):
        store.write_text("note.md", "hello")
