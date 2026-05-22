"""Local-first conversation run loop storage."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


RUN_STATES = {
    "intent_received",
    "intent_confirming",
    "context_resolving",
    "needs_input",
    "plan_proposed",
    "plan_revision_requested",
    "approved",
    "running",
    "blocked",
    "completed",
    "failed",
    "reviewing_output",
    "promoted_to_task",
    "promoted_to_source",
    "promoted_to_skill",
    "memory_write_pending",
    "closed",
}


@dataclass(frozen=True)
class ConversationRunEvent:
    id: str
    type: str
    state: str
    created_at: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationRun:
    id: str
    workspace_id: str
    chat_id: str
    user_id: str
    state: str
    created_at: str
    updated_at: str
    locale: str = ""
    timezone: str = ""
    intent: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    requirements: list[dict[str, Any]] = field(default_factory=list)
    plan_id: str = ""
    execution_id: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    promotion_candidates: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[ConversationRunEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["events"] = [asdict(event) for event in self.events]
        return data


class ConversationRunStore:
    """Stores durable conversation run state under a workspace."""

    def __init__(
        self,
        workspace_id: str,
        *,
        home: CognixHome | None = None,
    ) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def runs_dir(self) -> Path:
        return self.workspace_path / "runs"

    def create(
        self,
        *,
        chat_id: str,
        user_id: str,
        raw_intent: str,
        locale: str = "",
        timezone: str = "",
        sources: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        state: str = "intent_received",
    ) -> ConversationRun:
        state = self._normalize_state(state)
        now = datetime.now(UTC).isoformat()
        run = ConversationRun(
            id=uuid.uuid4().hex[:12],
            workspace_id=self.workspace_id,
            chat_id=chat_id,
            user_id=user_id,
            state=state,
            locale=locale,
            timezone=timezone,
            intent={"raw": raw_intent, "confirmed": False},
            sources=sources or [],
            metadata=metadata or {},
            events=[
                ConversationRunEvent(
                    id=uuid.uuid4().hex[:12],
                    type="run.intent_received",
                    state=state,
                    created_at=now,
                    data={"raw": raw_intent},
                )
            ],
            created_at=now,
            updated_at=now,
        )
        self._write(run)
        return run

    def get(self, run_id: str) -> ConversationRun | None:
        path = self._run_path(run_id)
        if not path.exists():
            return None
        return self._from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_all(
        self,
        *,
        chat_id: str | None = None,
        limit: int | None = None,
    ) -> list[ConversationRun]:
        runs: list[ConversationRun] = []
        paths = sorted(
            self.runs_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in paths:
            run = self.get(path.stem)
            if not run:
                continue
            if chat_id and run.chat_id != chat_id:
                continue
            runs.append(run)
            if limit and len(runs) >= limit:
                break
        return runs

    def latest(self, *, chat_id: str | None = None) -> ConversationRun | None:
        rows = self.list_all(chat_id=chat_id, limit=1)
        return rows[0] if rows else None

    def update(
        self,
        run_id: str,
        *,
        state: str | None = None,
        intent: dict[str, Any] | None = None,
        sources: list[dict[str, Any]] | None = None,
        capabilities: list[dict[str, Any]] | None = None,
        requirements: list[dict[str, Any]] | None = None,
        plan_id: str | None = None,
        execution_id: str | None = None,
        artifact_ids: list[str] | None = None,
        promotion_candidates: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        event_type: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> ConversationRun:
        run = self.get(run_id)
        if not run:
            raise FileNotFoundError(f"Conversation run not found: {run_id}")
        next_state = self._normalize_state(state or run.state)
        now = datetime.now(UTC).isoformat()
        events = list(run.events)
        if event_type or next_state != run.state:
            events.append(
                ConversationRunEvent(
                    id=uuid.uuid4().hex[:12],
                    type=event_type or f"run.{next_state}",
                    state=next_state,
                    created_at=now,
                    data=event_data or {},
                )
            )
        updated = ConversationRun(
            id=run.id,
            workspace_id=run.workspace_id,
            chat_id=run.chat_id,
            user_id=run.user_id,
            state=next_state,
            locale=run.locale,
            timezone=run.timezone,
            intent={**run.intent, **intent} if intent is not None else run.intent,
            sources=sources if sources is not None else run.sources,
            capabilities=capabilities if capabilities is not None else run.capabilities,
            requirements=requirements if requirements is not None else run.requirements,
            plan_id=plan_id if plan_id is not None else run.plan_id,
            execution_id=execution_id if execution_id is not None else run.execution_id,
            artifact_ids=artifact_ids if artifact_ids is not None else run.artifact_ids,
            promotion_candidates=(
                promotion_candidates
                if promotion_candidates is not None
                else run.promotion_candidates
            ),
            metadata={**run.metadata, **metadata} if metadata is not None else run.metadata,
            events=events[-200:],
            created_at=run.created_at,
            updated_at=now,
        )
        self._write(updated)
        return updated

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _write(self, run: ConversationRun) -> None:
        self._run_path(run.id).write_text(
            json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_state(state: str) -> str:
        state = (state or "intent_received").strip()
        if state not in RUN_STATES:
            raise ValueError(f"Invalid conversation run state: {state}")
        return state

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> ConversationRun:
        events = [
            ConversationRunEvent(**event)
            for event in data.get("events", [])
            if isinstance(event, dict)
        ]
        return ConversationRun(
            **{
                **data,
                "events": events,
            }
        )
