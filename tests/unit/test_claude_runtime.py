"""Tests for Claude Agent SDK runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass

from cognix.claude.runtime import ClaudeAgentRunRequest, ClaudeAgentRuntime
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
    max_turns: int | None = None
    resume: str | None = None


class FakeSDK:
    ClaudeAgentOptions = FakeOptions


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
