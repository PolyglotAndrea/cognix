"""Unified orchestration event and snapshot protocol."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


@dataclass(frozen=True)
class OrchestrationEvent:
    """A normalized lifecycle event across planning, approval, execution, and outputs."""

    workspace_id: str
    type: str
    stage: str = ""
    status: str = ""
    run_id: str = ""
    plan_id: str = ""
    step_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    approval_id: str = ""
    artifact_id: str = ""
    playbook_id: str = ""
    memory_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_workspace_event(self) -> dict[str, Any]:
        payload = asdict(self)
        data = payload.pop("data", {}) or {}
        payload["orchestration"] = {
            "event_id": payload.pop("event_id"),
            "stage": payload.get("stage"),
            "status": payload.get("status"),
            "run_id": payload.get("run_id"),
        }
        payload.update(data)
        return payload


@dataclass
class OrchestrationSnapshot:
    """Latest known state for a single orchestration run."""

    workspace_id: str
    run_id: str
    stage: str
    status: str
    refs: dict[str, str] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class OrchestrationSnapshotStore:
    """Stores run snapshots under each workspace."""

    def __init__(self, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_manager = WorkspaceManager(self.home)

    def upsert(self, event: OrchestrationEvent) -> OrchestrationSnapshot | None:
        if not event.workspace_id or not event.run_id:
            return None
        current = self.get(event.workspace_id, event.run_id)
        refs = dict(current.refs if current else {})
        refs.update(
            {
                key: value
                for key, value in {
                    "plan_id": event.plan_id,
                    "step_id": event.step_id,
                    "task_id": event.task_id,
                    "agent_id": event.agent_id,
                    "approval_id": event.approval_id,
                    "artifact_id": event.artifact_id,
                    "playbook_id": event.playbook_id,
                    "memory_id": event.memory_id,
                }.items()
                if value
            }
        )
        data = dict(current.data if current else {})
        data.update(event.data)
        snapshot = OrchestrationSnapshot(
            workspace_id=event.workspace_id,
            run_id=event.run_id,
            stage=event.stage,
            status=event.status,
            refs=refs,
            data=data,
        )
        path = self._path(event.workspace_id, event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(snapshot), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return snapshot

    def get(self, workspace_id: str, run_id: str) -> OrchestrationSnapshot | None:
        path = self._path(workspace_id, run_id)
        if not path.exists():
            return None
        return OrchestrationSnapshot(**json.loads(path.read_text(encoding="utf-8")))

    def list(self, workspace_id: str, *, limit: int = 50) -> list[OrchestrationSnapshot]:
        directory = self._path(workspace_id, "placeholder").parent
        if not directory.exists():
            return []
        paths = sorted(
            directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True
        )
        snapshots = []
        for path in paths[:limit]:
            try:
                snapshots.append(
                    OrchestrationSnapshot(**json.loads(path.read_text(encoding="utf-8")))
                )
            except Exception:
                continue
        return snapshots

    def _path(self, workspace_id: str, run_id: str) -> Path:
        return (
            self.workspace_manager.workspace_path(workspace_id)
            / "orchestration"
            / "snapshots"
            / f"{run_id}.json"
        )


_orchestration_listeners: list[Any] = []


def register_orchestration_listener(listener: Any) -> None:
    """Register a callback for all emitted orchestration events."""
    _orchestration_listeners.append(listener)


def unregister_orchestration_listener(listener: Any) -> None:
    """Unregister a callback for orchestration events."""
    if listener in _orchestration_listeners:
        _orchestration_listeners.remove(listener)


def emit_orchestration_event(
    event: OrchestrationEvent,
    *,
    home: CognixHome | None = None,
    snapshot: bool = True,
) -> None:
    """Append a normalized event and update the run snapshot."""
    manager = WorkspaceManager(home)
    manager.append_event(event.workspace_id, event.to_workspace_event())
    if snapshot:
        OrchestrationSnapshotStore(home=home).upsert(event)

    for listener in list(_orchestration_listeners):
        try:
            listener(event)
        except Exception:
            pass



def emit_workspace_event(
    workspace_id: str | None,
    event: dict[str, Any],
    *,
    home: CognixHome | None = None,
    snapshot: bool = True,
) -> None:
    """Normalize and append an existing workspace event dict."""
    if not workspace_id:
        return
    orchestration_event = from_workspace_event(workspace_id, event)
    emit_orchestration_event(orchestration_event, home=home, snapshot=snapshot)


def from_workspace_event(workspace_id: str, event: dict[str, Any]) -> OrchestrationEvent:
    event_type = str(event.get("type", "event"))
    stage = _stage_for_type(event_type)
    status = _status_for_type(event_type, event)
    plan_id = str(event.get("plan_id") or "")
    task_id = str(event.get("task_id") or "")
    approval_id = str(event.get("approval_id") or event.get("id") or "")
    artifact_id = str(event.get("artifact_id") or "")
    playbook_id = str(event.get("playbook_id") or "")
    memory_id = str(event.get("memory_id") or "")
    run_id = str(
        event.get("run_id")
        or plan_id
        or task_id
        or approval_id
        or artifact_id
        or playbook_id
        or memory_id
        or uuid.uuid4().hex[:12]
    )
    return OrchestrationEvent(
        workspace_id=workspace_id,
        type=event_type,
        stage=stage,
        status=status,
        run_id=run_id,
        plan_id=plan_id,
        step_id=str(event.get("step_id") or ""),
        task_id=task_id,
        agent_id=str(event.get("agent_id") or ""),
        approval_id=approval_id,
        artifact_id=artifact_id,
        playbook_id=playbook_id,
        memory_id=memory_id,
        data=dict(event),
    )


def _stage_for_type(event_type: str) -> str:
    prefix = event_type.split(".", 1)[0]
    return {
        "intent": "intent",
        "plan": "plan",
        "approval": "approval",
        "execution": "execution",
        "task": "execution",
        "artifact": "artifact",
        "memory": "memory",
        "playbook": "playbook",
        "skill": "playbook",
    }.get(prefix, prefix or "event")


def _status_for_type(event_type: str, event: dict[str, Any]) -> str:
    if event.get("status"):
        return str(event["status"])
    suffix = event_type.split(".")[-1]
    return {
        "started": "running",
        "executing": "running",
        "success": "completed",
        "completed": "completed",
        "applied": "completed",
        "failed": "failed",
        "failure": "failed",
        "rejected": "rejected",
        "approved": "approved",
        "responded": "approved",
        "queued": "queued",
        "created": "created",
        "proposed": "proposed",
        "confirmed": "confirmed",
        "published": "published",
        "archived": "archived",
        "promoted": "promoted",
    }.get(suffix, "")
