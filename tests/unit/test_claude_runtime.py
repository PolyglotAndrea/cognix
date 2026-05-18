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


@dataclass
class FakePermissionResultAllow:
    updated_input: dict[str, Any] | None = None


class FakeSDK:
    ClaudeAgentOptions = FakeOptions
    PermissionResultAllow = FakePermissionResultAllow
    PermissionResultDeny = FakePermissionResultDeny

    @staticmethod
    async def query(prompt: str, options: FakeOptions):
        await options.can_use_tool("Write", {"file_path": "README.md"})
        if False:
            yield None


@dataclass
class FakeResultMessage:
    result: str


@dataclass
class FakeContentBlock:
    text: str | None = None
    name: str | None = None
    id: str = ""
    input: dict[str, Any] | None = None


@dataclass
class FakeContentMessage:
    content: list[FakeContentBlock]


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
async def test_claude_runtime_ask_mode_allows_read_tools(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))
    pending = []

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            agent_id="agent-1",
            prompt="inspect files",
            permission_mode="ask",
        ),
        sdk=FakeSDK,
        approval_sink=pending.append,
    )

    result = await options.can_use_tool("Read", {"file_path": "README.md"})

    assert isinstance(result, FakePermissionResultAllow)
    assert result.updated_input == {"file_path": "README.md"}
    assert ApprovalStore(home).list_all(workspace_id=workspace.id) == []
    assert pending == []


@pytest.mark.asyncio
async def test_claude_runtime_ask_mode_flags_unsandboxed_bash_as_dangerous(
    tmp_path,
    monkeypatch,
) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            agent_id="agent-1",
            prompt="run deployment",
            permission_mode="ask",
        ),
        sdk=FakeSDK,
    )

    result = await options.can_use_tool(
        "Bash",
        {"command": "deploy", "dangerouslyDisableSandbox": True},
    )
    approvals = ApprovalStore(home).list_all(workspace_id=workspace.id)

    assert isinstance(result, FakePermissionResultDeny)
    assert approvals[0].tool_name == "Bash"
    assert approvals[0].access_level == "dangerous"


@pytest.mark.asyncio
async def test_claude_runtime_extracts_resume_metadata(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    options = ClaudeAgentRuntime().build_options(
        ClaudeAgentRunRequest(
            workspace_id=workspace.id,
            agent_id="agent-1",
            prompt="edit file",
            permission_mode="ask",
        ),
        sdk=FakeSDK,
    )

    await options.can_use_tool(
        "Write",
        {"file_path": "README.md"},
        {"session_id": "session-2", "tool_use_id": "tool-1"},
        request_id="request-1",
    )
    approvals = ApprovalStore(home).list_all(workspace_id=workspace.id)

    assert approvals[0].metadata["session_id"] == "session-2"
    assert approvals[0].metadata["tool_use_id"] == "tool-1"
    assert approvals[0].metadata["request_id"] == "request-1"


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
    assert result["resume_request"]["resume"] == "session-1"
    assert store.get(approval.id).status == "completed"


@pytest.mark.asyncio
async def test_claude_runtime_resume_stream_uses_resume_token(tmp_path, monkeypatch) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    class ResumeSDK(FakeSDK):
        @staticmethod
        async def query(prompt: str, options: FakeOptions):
            assert prompt == "answered"
            assert options.resume == "session-1"
            yield FakeResultMessage(result="continued")

    import cognix.claude.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_load_sdk", lambda: ResumeSDK)

    store = ApprovalStore(home)
    approval = store.create(
        agent_id=f"claude:{workspace.id}",
        workspace_id=workspace.id,
        tool_name="AskUserQuestion",
        arguments={"question": "Proceed?"},
        access_level="write",
        reason="Need input",
        kind="question",
        metadata={
            "runtime": "claude-agent-sdk",
            "permission_mode": "ask",
            "resume": "session-1",
        },
    )
    store.respond(approval.id, "answered")

    events = [event async for event in ClaudeAgentRuntime().resume_stream(approval.id)]

    assert [event.type for event in events] == ["delta", "done"]
    assert events[0].data["delta"] == "continued"
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


@pytest.mark.asyncio
async def test_claude_runtime_fake_sdk_e2e_approval_then_resume(
    tmp_path,
    monkeypatch,
) -> None:
    home = CognixHome(tmp_path / ".cognix")
    workspace = WorkspaceManager(home).create("Claude")
    WorkspaceConfigStore(workspace.id, home=home).upsert_mcp_server(
        name="notes",
        command="python",
        args=["-m", "notes_mcp"],
        env={},
    )
    monkeypatch.setenv("COGNIX_HOME", str(home.root))

    calls: list[dict[str, Any]] = []

    class E2ESDK(FakeSDK):
        @staticmethod
        async def query(prompt: str, options: FakeOptions):
            calls.append(
                {
                    "prompt": prompt,
                    "cwd": options.cwd,
                    "permission_mode": options.permission_mode,
                    "mcp_servers": options.mcp_servers,
                    "resume": options.resume,
                }
            )
            if options.resume:
                yield FakeContentMessage(content=[FakeContentBlock(text=f"resumed with {prompt}")])
                yield FakeResultMessage(result="final result")
                return

            decision = await options.can_use_tool(
                "Write",
                {"file_path": "notes.md", "content": "hello"},
                {"resume_token": "resume-123", "session_id": "session-123"},
            )
            assert isinstance(decision, FakePermissionResultDeny)
            if False:
                yield None

    import cognix.claude.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "_load_sdk", lambda: E2ESDK)

    events = [
        event
        async for event in ClaudeAgentRuntime().stream(
            ClaudeAgentRunRequest(
                workspace_id=workspace.id,
                agent_id="agent-e2e",
                prompt="edit notes",
                permission_mode="ask",
                system_prompt="be careful",
                model="claude-sonnet-4-6",
            )
        )
    ]

    assert [event.type for event in events] == ["approval_request", "done"]
    approval_id = events[0].data["id"]
    approval = ApprovalStore(home).get(approval_id)
    assert approval is not None
    assert approval.metadata["runtime"] == "claude-agent-sdk"
    assert approval.metadata["resume_token"] == "resume-123"
    assert approval.metadata["session_id"] == "session-123"
    assert calls[0]["permission_mode"] == "default"
    assert calls[0]["mcp_servers"] == {"notes": {"command": "python", "args": ["-m", "notes_mcp"]}}

    ApprovalStore(home).approve(approval_id)
    resumed = [
        event
        async for event in ClaudeAgentRuntime().resume_stream(
            approval_id,
            response="approved, continue",
        )
    ]

    assert [event.type for event in resumed] == ["delta", "delta", "done"]
    assert resumed[0].data["delta"] == "resumed with approved, continue"
    assert resumed[1].data["delta"] == "final result"
    assert calls[1]["resume"] == "resume-123"
    assert ApprovalStore(home).get(approval_id).status == "completed"
