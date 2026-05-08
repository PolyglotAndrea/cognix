"""Workspace management for local-first Cognix data."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome


@dataclass(frozen=True)
class WorkspaceInfo:
    id: str
    name: str
    path: str
    created_at: str
    updated_at: str
    description: str = ""


class WorkspaceManager:
    """Create, open, and list local workspaces under ``~/.cognix/workspaces``."""

    def __init__(self, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()

    def create(
        self,
        name: str,
        *,
        description: str = "",
        workspace_id: str | None = None,
    ) -> WorkspaceInfo:
        workspace_id = workspace_id or self._new_workspace_id(name)
        path = self.workspace_path(workspace_id)
        path.mkdir(parents=True, exist_ok=False)

        for dirname in (
            "agents",
            "attachments",
            "chats",
            "files",
            "mcp",
            "skills",
            "tasks",
        ):
            (path / dirname).mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC).isoformat()
        info = WorkspaceInfo(
            id=workspace_id,
            name=name,
            description=description,
            path=str(path),
            created_at=now,
            updated_at=now,
        )
        self._write_json(path / "workspace.json", asdict(info))
        self._write_json(
            path / "settings.json",
            {
                "default_model": None,
                "enabled_skills": [],
                "context": {
                    "max_history_messages": 20,
                    "include_hot_memory": True,
                    "include_cold_memory": True,
                    "include_skills": True,
                },
            },
        )
        self._write_default(path / "MEMORY.md", f"# {name} Memory\n\n")
        (path / "events.jsonl").touch(exist_ok=True)
        return info

    def get(self, workspace_id: str) -> WorkspaceInfo | None:
        path = self.workspace_path(workspace_id)
        meta = path / "workspace.json"
        if not meta.exists():
            return None
        data = json.loads(meta.read_text(encoding="utf-8"))
        return WorkspaceInfo(**data)

    def list_all(self) -> list[WorkspaceInfo]:
        results = []
        for path in sorted(self.home.workspaces_dir.iterdir()):
            if not path.is_dir():
                continue
            info = self.get(path.name)
            if info:
                results.append(info)
        return results

    def workspace_path(self, workspace_id: str) -> Path:
        return self.home.workspaces_dir / workspace_id

    def append_event(self, workspace_id: str, event: dict[str, Any]) -> None:
        path = self.workspace_path(workspace_id) / "events.jsonl"
        payload = {"timestamp": datetime.now(UTC).isoformat(), **event}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_events(self, workspace_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        path = self.workspace_path(workspace_id) / "events.jsonl"
        if not path.exists():
            return []
        rows = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows[-limit:]

    @staticmethod
    def _new_workspace_id(name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
        slug = slug or "workspace"
        return f"{slug}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def _write_default(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content, encoding="utf-8")
