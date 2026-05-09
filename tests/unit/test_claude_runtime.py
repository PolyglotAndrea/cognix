"""Tests for Claude Agent SDK runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cognix.claude.runtime import ClaudeAgentRunRequest, ClaudeAgentRuntime
from cognix.local.approvals import ApprovalStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import WorkspaceConfigStore


@dataclass
class FakeOptions:
    cwd: str
    model: str | None = None
    system_prompt: str | None = None
    permission_mode: str | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    mcp_servers: dict | None = None
    strict_mcp_config: bool = False
    can_use_tool: Any = None
    max_turns: int | None = None
    resume: str | None = None


@dataclass
class FakePermissionResultDeny:
    message: str
    interrupt: bool = False


class FakeSDK:
    ClaudeAgentOptions = FakeOptions
    PermissionResultDeny = FakePermissionResultDeny

    @staticmethod
    async def query(prompt: str, options: FakeOptions):
        await options.can_use_tool("Write", {"file_path": "README.md"})
        if False:
            yield None


def test_claude_runtime_maps_read_only_workspace_options(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            prompt="review",
            model="claude-sonnet-4-6",
            permission_mode="read-only",
        ),
        sdk=FakeSDK,
    )

    assert options.permission_mode == "dontAsk"
    assert options.allowed_tools == ["Read", "Glob", "Grep"]
    assert options.disallowed_tools == ["Edit", "Write", "Bash"]
    assert options.cwd.endswith(f"{workspace.id}/files")
    assert options.model == "claude-sonnet-4-6"


def test_claude_runtime_maps_workspace_mcp_servers(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    WorkspaceConfigStore(workspace.id, home=home).upsert_mcp_server(
        name="playwright",
        command="npx",
        args=["@playwright/mcp@latest"],
        env={"TOKEN": "x"},
    )
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(workspace_id=workspace.id, prompt="open browser"),
        sdk=FakeSDK,
    )

    assert options.permission_mode == "acceptEdits"
    assert options.mcp_servers == {
        "playwright": {
            "command": "npx",
            "args": ["@playwright/mcp@latest"],
            "env": {"TOKEN": "x"},
        }
    }
    assert options.strict_mcp_config is True


def test_claude_runtime_maps_plan_mode(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            prompt="make a plan",
            permission_mode="plan",
        ),
        sdk=FakeSDK,
    )

    assert options.permission_mode == "plan"
    assert options.allowed_tools == ["Read", "Glob", "Grep", "AskUserQuestion"]
    assert options.can_use_tool is not None


@pytest.mark.asyncio
async def test_claude_runtime_ask_mode_creates_approval_request(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))
    pending = []

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            agent_id="agent-1",
            prompt="edit file",
            permission_mode="ask",
        ),
        sdk=FakeSDK,
        approval_sink=pending.append,
    )

    result = await options.can_use_tool("Write", {"file_path": "README.md"})
    approvals = ApprovalStore(home).list_all(workspace_id=workspace.id)

    assert isinstance(result, FakePermissionResultDeny)
    assert result.interrupt is True
    assert len(approvals) == 1
    assert approvals[0].agent_id == "agent-1"
    assert approvals[0].tool_name == "Write"
    assert approvals[0].access_level == "write"
    assert approvals[0].metadata["runtime"] == "claude-agent-sdk"
    assert pending == approvals


@pytest.mark.asyncio
async def test_claude_runtime_resumes_approved_approval(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))
    store = ApprovalStore(home)
    approval = store.create(
        agent_id=f"claude:{workspace.id}",
        workspace_id=workspace.id,
        tool_name="Write",
        arguments={"file_path": "README.md"},
        access_level="write",
        reason="Needs write access",
        metadata={
            "runtime": "claude-agent-sdk",
            "resume": "session-1",
        },
    )
    store.approve(approval.id)

    result = await ClaudeAgentRuntime().resume_approval(approval.id)

    assert result["runtime"] == "claude-agent-sdk"
    assert result["resume"] == "session-1"
    assert store.get(approval.id).status == "completed"


@pytest.mark.asyncio
async def test_claude_runtime_stream_finishes_waiting_for_approval(
    tmp_path,
    monkeypatch,
) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    import cognix.claude.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_load_sdk", lambda: FakeSDK)

    events = [
        event
        async for event in ClaudeAgentRuntime().stream(
            ClaudeAgentRunRequest(
                workspace_id=workspace.id,
                prompt="edit",
                permission_mode="ask",
            )
        )
    ]

    assert [event.type for event in events] == ["approval_request", "done"]
    assert events[-1].data["finish_reason"] == "waiting_for_approval"
    assert events[-1].data["approval_id"] == events[0].data["id"]
