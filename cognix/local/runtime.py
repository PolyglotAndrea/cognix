"""Local-first runtime node registry."""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome


@dataclass(frozen=True)
class RuntimeNode:
    id: str
    role: str
    host: str
    pid: int
    status: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    last_seen: str = ""


class RuntimeNodeStore:
    """Stores runtime node presence under ``~/.cognix/runtime``."""

    def __init__(self, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @property
    def runtime_dir(self) -> Path:
        return self.home.root / "runtime"

    @property
    def nodes_file(self) -> Path:
        return self.runtime_dir / "nodes.json"

    def register_current(
        self,
        *,
        role: str,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> RuntimeNode:
        now = _now()
        node = RuntimeNode(
            id=node_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}",
            role=role,
            host=socket.gethostname(),
            pid=os.getpid(),
            status="online",
            capabilities=capabilities or [],
            metadata=metadata or {},
            started_at=now,
            last_seen=now,
        )
        nodes = {existing.id: existing for existing in self.list_all(include_stale=True)}
        nodes[node.id] = node
        self._write_nodes(nodes.values())
        return node

    def heartbeat(
        self,
        node_id: str,
        *,
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeNode | None:
        nodes = {node.id: node for node in self.list_all(include_stale=True)}
        node = nodes.get(node_id)
        if not node:
            return None

        node_data = asdict(node)
        if metadata:
            node_data["metadata"] = {**node.metadata, **metadata}
        updated = RuntimeNode(**{**node_data, "status": status, "last_seen": _now()})
        nodes[node_id] = updated
        self._write_nodes(nodes.values())
        return updated

    def mark_status(self, node_id: str, status: str) -> RuntimeNode | None:
        nodes = {node.id: node for node in self.list_all(include_stale=True)}
        node = nodes.get(node_id)
        if not node:
            return None

        updated = RuntimeNode(**{**asdict(node), "status": status, "last_seen": _now()})
        nodes[node_id] = updated
        self._write_nodes(nodes.values())
        return updated

    def list_all(
        self,
        *,
        include_stale: bool = False,
        stale_after_seconds: int = 90,
    ) -> list[RuntimeNode]:
        if not self.nodes_file.exists():
            return []

        raw = json.loads(self.nodes_file.read_text(encoding="utf-8") or "[]")
        nodes = [RuntimeNode(**item) for item in raw if isinstance(item, dict)]
        if include_stale:
            return nodes
        return [self._with_stale_status(node, stale_after_seconds) for node in nodes]

    def _with_stale_status(self, node: RuntimeNode, stale_after_seconds: int) -> RuntimeNode:
        if node.status != "online":
            return node
        try:
            last_seen = datetime.fromisoformat(node.last_seen)
        except ValueError:
            return RuntimeNode(**{**asdict(node), "status": "stale"})
        if datetime.now(UTC) - last_seen > timedelta(seconds=stale_after_seconds):
            return RuntimeNode(**{**asdict(node), "status": "stale"})
        return node

    def _write_nodes(self, nodes: Any) -> None:
        data = [asdict(node) for node in sorted(nodes, key=lambda item: item.id)]
        self.nodes_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()
