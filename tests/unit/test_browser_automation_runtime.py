from __future__ import annotations

import pytest

from cognix.browser.service import (
    BrowserAutomationRun,
    BrowserAutomationService,
    BrowserObservation,
)
from cognix.local.approvals import ApprovalStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.planner.capabilities import CapabilityResolver
from cognix.storage.database import close_db, get_session, init_db
from cognix.storage.models import ArtifactModel


def test_browser_mcp_preset_and_profile_are_workspace_scoped(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Browser")
    service = BrowserAutomationService(workspace.id, home=home)

    server = service.ensure_mcp_preset(profile="operator")
    profile = service.profile_status("operator")

    assert server.id == "browser_playwright"
    assert server.metadata["capability"] == "browser_automation"
    assert server.metadata["profile"] == "operator"
    assert "--user-data-dir" in server.args
    assert profile["exists"] is True
    assert profile["path"].endswith("/browser/profiles/operator")


@pytest.mark.asyncio
async def test_browser_run_requests_approval_when_network_policy_asks(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    home = CognixHome.default().ensure()
    workspace = WorkspaceManager(home).create("Browser")
    service = BrowserAutomationService(workspace.id, home=home)

    result = await service.run(
        BrowserAutomationRun(
            objective="Collect authorized page data",
            url="https://example.test/report",
            permission_mode="ask",
        ),
        user_id="user-1",
    )

    assert result["status"] == "approval_required"
    approval = ApprovalStore(home).get(result["approval_id"])
    assert approval is not None
    assert approval.tool_name == "browser_automation"
    assert approval.arguments["url"] == "https://example.test/report"


@pytest.mark.asyncio
async def test_browser_result_is_persisted_as_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/state.db")
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    await init_db()
    home = CognixHome.default().ensure()
    workspace = WorkspaceManager(home).create("Browser")
    service = BrowserAutomationService(workspace.id, home=home)

    try:
        artifact_id = await service.create_artifact(
            request=BrowserAutomationRun(
                objective="Collect authorized page data",
                url="https://example.test/report",
                task_id="task-1",
                agent_id="agent-1",
            ),
            observation=BrowserObservation(
                title="Report",
                url="https://example.test/report",
                text="coupon code A1",
                links=[{"text": "source", "href": "https://example.test/source"}],
            ),
            result={"status": "completed"},
            user_id="user-1",
        )

        async with get_session() as session:
            artifact = await session.get(ArtifactModel, artifact_id)

        assert artifact is not None
        assert artifact.source == "browser_automation"
        assert artifact.context_type == "browser"
        assert "coupon code A1" in artifact.content
        assert artifact.metadata_json["task_id"] == "task-1"
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_capability_resolver_includes_browser_automation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COGNIX_HOME", str(tmp_path / ".cognix"))
    home = CognixHome.default().ensure()
    workspace = WorkspaceManager(home).create("Browser")
    service = BrowserAutomationService(workspace.id, home=home)
    service.ensure_mcp_preset(profile="default")

    snapshot = await CapabilityResolver(home=home).resolve(workspace.id, user_id="user-1")

    browser = snapshot["browser_automation"]
    assert browser["kind"] == "browser_automation"
    assert browser["mcp_preset_configured"] is True
    assert browser["mcp_server_id"] == "browser_playwright"
