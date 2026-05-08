"""Workspace-scoped settings for skills and MCP servers."""

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
class MCPServerConfig:
    id: str
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkspaceConfigStore:
    """Read and write local-first workspace runtime configuration."""

    def __init__(self, workspace_id: str, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.mcp_dir.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self._write_json(self.settings_path, self.default_settings())
        if not self.mcp_servers_path.exists():
            self._write_json(self.mcp_servers_path, [])

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def settings_path(self) -> Path:
        return self.workspace_path / "settings.json"

    @property
    def mcp_dir(self) -> Path:
        return self.workspace_path / "mcp"

    @property
    def mcp_servers_path(self) -> Path:
        return self.mcp_dir / "servers.json"

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {
            "default_model": None,
            "enabled_skills": [],
            "context": {
                "max_history_messages": 20,
                "include_hot_memory": True,
                "include_cold_memory": True,
                "include_skills": True,
            },
        }

    def get_settings(self) -> dict[str, Any]:
        settings = self.default_settings()
        settings.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
        settings.setdefault("enabled_skills", [])
        settings.setdefault("context", self.default_settings()["context"])
        return settings

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        settings = self.get_settings()
        for key, value in updates.items():
            if key == "context" and isinstance(value, dict):
                settings["context"] = {**settings.get("context", {}), **value}
            else:
                settings[key] = value
        self._write_json(self.settings_path, settings)
        return settings

    def set_skill_enabled(self, skill_name: str, enabled: bool) -> dict[str, Any]:
        settings = self.get_settings()
        current = list(dict.fromkeys(settings.get("enabled_skills", [])))
        if enabled and skill_name not in current:
            current.append(skill_name)
        if not enabled:
            current = [name for name in current if name != skill_name]
        settings["enabled_skills"] = current
        self._write_json(self.settings_path, settings)
        return settings

    def list_mcp_servers(self) -> list[MCPServerConfig]:
        rows = json.loads(self.mcp_servers_path.read_text(encoding="utf-8"))
        return [MCPServerConfig(**row) for row in rows]

    def upsert_mcp_server(
        self,
        *,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        enabled: bool = True,
        server_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MCPServerConfig:
        servers = self.list_mcp_servers()
        now = datetime.now(UTC).isoformat()
        existing = next((server for server in servers if server.id == server_id), None)
        server = MCPServerConfig(
            id=server_id or uuid.uuid4().hex[:12],
            name=name,
            command=command,
            args=args or [],
            env=env or {},
            enabled=enabled,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata=metadata or (existing.metadata if existing else {}),
        )
        servers = [item for item in servers if item.id != server.id]
        servers.append(server)
        self._write_json(self.mcp_servers_path, [asdict(item) for item in servers])
        return server

    def delete_mcp_server(self, server_id: str) -> bool:
        servers = self.list_mcp_servers()
        remaining = [server for server in servers if server.id != server_id]
        if len(remaining) == len(servers):
            return False
        self._write_json(self.mcp_servers_path, [asdict(item) for item in remaining])
        return True

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
