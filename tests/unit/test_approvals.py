"""Tests for local approval store."""

from __future__ import annotations

from cognix.local.approvals import ApprovalStore
from cognix.local.home import CognixHome


def test_approval_store_lifecycle(tmp_path) -> None:
    store = ApprovalStore(CognixHome(tmp_path / ".cognix"))

    request = store.create(
        agent_id="agent-1",
        workspace_id="workspace-1",
        tool_name="write_note",
        arguments={"content": "hello"},
        access_level="write",
        reason="needs write",
    )

    assert store.list_all(workspace_id="workspace-1") == [request]
    assert store.approve(request.id).status == "approved"
    assert store.list_all() == []
    assert store.complete(request.id, "ok").status == "completed"
    assert store.get(request.id).result == "ok"


def test_approval_store_records_question_response(tmp_path) -> None:
    store = ApprovalStore(CognixHome(tmp_path / ".cognix"))

    request = store.create(
        agent_id="agent-1",
        workspace_id="workspace-1",
        tool_name="AskUserQuestion",
        arguments={"question": "Continue?"},
        access_level="read",
        reason="question",
        kind="question",
    )

    approval = store.respond(request.id, "Yes, continue")

    assert approval.status == "approved"
    assert approval.kind == "question"
    assert approval.response == "Yes, continue"
