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
class ConnectorConfig:
    id: str
    platform: str
    credential_id: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


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
        if not self.connectors_path.exists():
            self._write_json(self.connectors_path, [])

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

    @property
    def connectors_path(self) -> Path:
        return self.workspace_path / "connectors.json"

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {
            "default_model": None,
            "llm": {
                "base_url": None,
                "api_key": None,
                "default_model": None,
            },
            "enabled_skills": [],
            "context": {
                "max_history_messages": 20,
                "include_hot_memory": True,
                "include_cold_memory": True,
                "include_skills": True,
                "include_deep_memory": False,
            },
        }

    def get_settings(self) -> dict[str, Any]:
        settings = self.default_settings()
        settings.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
        settings.setdefault("enabled_skills", [])
        settings.setdefault("context", self.default_settings()["context"])
        settings.setdefault("llm", self.default_settings()["llm"])
        # Decrypt LLM API key if encrypted
        llm = settings.get("llm", {})
        api_key = llm.get("api_key")
        if api_key:
            from cognix.secrets import decrypt_secret

            llm["api_key"] = decrypt_secret(api_key)
        return settings

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        settings = self.get_settings()
        for key, value in updates.items():
            if key in ("context", "llm") and isinstance(value, dict):
                settings[key] = {**settings.get(key, {}), **value}
            else:
                settings[key] = value
        # Encrypt LLM API key before persisting
        llm = settings.get("llm", {})
        api_key = llm.get("api_key")
        if api_key:
            from cognix.secrets import encrypt_secret, is_encrypted

            if not is_encrypted(api_key):
                llm["api_key"] = encrypt_secret(api_key)
        self._write_json(self.settings_path, settings)
        # Return with decrypted key for API response
        return self.get_settings()

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

    def set_mcp_tool_enabled(
        self, server_id: str, tool_name: str, enabled: bool
    ) -> MCPServerConfig | None:
        """Enable or disable a specific tool on an MCP server."""
        servers = self.list_mcp_servers()
        for server in servers:
            if server.id != server_id:
                continue
            disabled = list(server.metadata.get("disabled_tools", []))
            if not enabled and tool_name not in disabled:
                disabled.append(tool_name)
            elif enabled and tool_name in disabled:
                disabled.remove(tool_name)
            else:
                return server  # no change needed
            new_metadata = {**server.metadata, "disabled_tools": disabled}
            updated = MCPServerConfig(
                id=server.id,
                name=server.name,
                command=server.command,
                args=server.args,
                env=server.env,
                enabled=server.enabled,
                created_at=server.created_at,
                updated_at=datetime.now(UTC).isoformat(),
                metadata=new_metadata,
            )
            remaining = [s for s in servers if s.id != server_id]
            remaining.append(updated)
            self._write_json(
                self.mcp_servers_path, [asdict(item) for item in remaining]
            )
            return updated
        return None

    # ── Connector config ───────────────────────────────────────────

    def list_connectors(self) -> list[ConnectorConfig]:
        rows = json.loads(self.connectors_path.read_text(encoding="utf-8"))
        return [ConnectorConfig(**row) for row in rows]

    def upsert_connector(
        self,
        *,
        platform: str,
        credential_id: str,
        enabled: bool = True,
        connector_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorConfig:
        connectors = self.list_connectors()
        now = datetime.now(UTC).isoformat()
        existing = next((c for c in connectors if c.id == connector_id), None)
        connector = ConnectorConfig(
            id=connector_id or uuid.uuid4().hex[:12],
            platform=platform,
            credential_id=credential_id,
            enabled=enabled,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata=metadata or (existing.metadata if existing else {}),
        )
        connectors = [c for c in connectors if c.id != connector.id]
        connectors.append(connector)
        self._write_json(self.connectors_path, [asdict(c) for c in connectors])
        return connector

    def delete_connector(self, connector_id: str) -> bool:
        connectors = self.list_connectors()
        remaining = [c for c in connectors if c.id != connector_id]
        if len(remaining) == len(connectors):
            return False
        self._write_json(self.connectors_path, [asdict(c) for c in remaining])
        return True

    def set_connector_tool_enabled(
        self, connector_id: str, tool_name: str, enabled: bool
    ) -> ConnectorConfig | None:
        connectors = self.list_connectors()
        for conn in connectors:
            if conn.id != connector_id:
                continue
            disabled = list(conn.metadata.get("disabled_tools", []))
            if not enabled and tool_name not in disabled:
                disabled.append(tool_name)
            elif enabled and tool_name in disabled:
                disabled.remove(tool_name)
            else:
                return conn
            new_metadata = {**conn.metadata, "disabled_tools": disabled}
            updated = ConnectorConfig(
                id=conn.id,
                platform=conn.platform,
                credential_id=conn.credential_id,
                enabled=conn.enabled,
                created_at=conn.created_at,
                updated_at=datetime.now(UTC).isoformat(),
                metadata=new_metadata,
            )
            remaining = [c for c in connectors if c.id != connector_id]
            remaining.append(updated)
            self._write_json(self.connectors_path, [asdict(c) for c in remaining])
            return updated
        return None

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
