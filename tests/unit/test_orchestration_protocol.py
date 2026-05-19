"""Tests for unified orchestration event snapshots."""

from __future__ import annotations

import json

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.orchestrator.protocol import (
    OrchestrationEvent,
    OrchestrationSnapshotStore,
    emit_orchestration_event,
    emit_workspace_event,
)


def test_orchestration_event_updates_workspace_timeline_and_snapshot(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Protocol")

    emit_orchestration_event(
        OrchestrationEvent(
            workspace_id=workspace.id,
            type="plan.proposed",
            stage="plan",
            status="proposed",
            run_id="plan-1",
            plan_id="plan-1",
            data={"summary": "Do the thing"},
        ),
        home=home,
    )
    emit_workspace_event(
        workspace.id,
        {
            "type": "task.success",
            "run_id": "plan-1",
            "plan_id": "plan-1",
            "task_id": "task-1",
            "result": "ok",
        },
        home=home,
    )

    events = WorkspaceManager(home).list_events(workspace.id)
    assert [event["type"] for event in events] == ["plan.proposed", "task.success"]
    assert events[-1]["orchestration"]["stage"] == "execution"
    assert events[-1]["orchestration"]["run_id"] == "plan-1"

    snapshot = OrchestrationSnapshotStore(home=home).get(workspace.id, "plan-1")
    assert snapshot is not None
    assert snapshot.status == "completed"
    assert snapshot.refs["plan_id"] == "plan-1"
    assert snapshot.refs["task_id"] == "task-1"
    assert snapshot.data["result"] == "ok"

    snapshot_path = (
        WorkspaceManager(home).workspace_path(workspace.id)
        / "orchestration"
        / "snapshots"
        / "plan-1.json"
    )
    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["run_id"] == "plan-1"
