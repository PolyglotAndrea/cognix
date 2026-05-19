"""Obsidian-compatible memory vault projection."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.memory.pipeline import ColdMemoryRecord


class MemoryVault:
    """Writes durable Markdown projections of memory records for review.

    SQLite remains the machine index. The vault is the human-readable layer:
    it lets users inspect memory sources, summaries, and raw content in an
    Obsidian-compatible folder without coupling retrieval to Markdown parsing.
    """

    def __init__(self, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_manager = WorkspaceManager(self.home)

    def append_record(self, record: ColdMemoryRecord) -> Path:
        path = self.record_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        block = self.render_record(record)
        if f"id: {record.id}" in existing:
            return path
        with path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n\n"):
                f.write("\n\n")
            f.write(block)
        return path

    def record_path(self, record: ColdMemoryRecord) -> Path:
        base = self.base_dir(record.workspace_id)
        scope = self._safe_segment(record.scope or "global")
        kind = self._safe_segment(record.kind or "message")
        return base / "tree" / scope / f"{kind}.md"

    def base_dir(self, workspace_id: str | None = None) -> Path:
        if workspace_id:
            return self.workspace_manager.workspace_path(workspace_id) / "memory"
        return self.home.root / "memory"

    @staticmethod
    def render_record(record: ColdMemoryRecord) -> str:
        title = record.summary.strip() or record.content.strip().splitlines()[0][:80] or record.id
        source = record.metadata.get("source") or record.metadata.get("agent_id") or "unknown"
        metadata = json.dumps(record.metadata, ensure_ascii=False, sort_keys=True)
        return "\n".join(
            [
                f"## {title}",
                "",
                f"- id: {record.id}",
                f"- created_at: {record.created_at}",
                f"- workspace_id: {record.workspace_id or ''}",
                f"- scope: {record.scope}",
                f"- kind: {record.kind}",
                f"- source: {source}",
                f"- metadata: `{metadata}`",
                "",
                record.content.strip(),
                "",
            ]
        )

    @staticmethod
    def _safe_segment(value: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
        return safe or "default"
