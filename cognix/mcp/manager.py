"""MCP server lifecycle and discovery helpers."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from cognix.local.workspace_config import MCPServerConfig
from cognix.mcp.client import MCPClient, MCPError, MCPToolSpec


@dataclass(frozen=True)
class MCPServerStatus:
    server_id: str
    name: str
    enabled: bool
    status: str
    tool_count: int = 0
    error: str = ""
    checked_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MCPRuntimeManager:
    """Discovers MCP tools and caches server status for the local process."""

    def __init__(
        self,
        *,
        client_factory=MCPClient,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self.client_factory = client_factory
        self.cache_ttl_seconds = cache_ttl_seconds
        self._tool_cache: dict[str, tuple[float, list[MCPToolSpec]]] = {}
        self._status_cache: dict[str, MCPServerStatus] = {}

    async def list_tools(
        self,
        server: MCPServerConfig,
        *,
        force_refresh: bool = False,
    ) -> list[MCPToolSpec]:
        """List tools for an enabled server, using a short-lived discovery cache."""
        if not server.enabled:
            self._status_cache[server.id] = MCPServerStatus(
                server_id=server.id,
                name=server.name,
                enabled=False,
                status="disabled",
                checked_at=time.time(),
            )
            return []

        cache_key = self._cache_key(server)
        cached = self._tool_cache.get(cache_key)
        if cached and not force_refresh and time.time() - cached[0] <= self.cache_ttl_seconds:
            return cached[1]

        checked_at = time.time()
        try:
            async with self.client_factory(server) as client:
                specs = await client.list_tools()
        except Exception as exc:
            self._status_cache[server.id] = MCPServerStatus(
                server_id=server.id,
                name=server.name,
                enabled=True,
                status="error",
                error=str(exc),
                checked_at=checked_at,
            )
            if isinstance(exc, MCPError):
                raise
            raise MCPError(str(exc)) from exc

        self._tool_cache[cache_key] = (checked_at, specs)
        self._status_cache[server.id] = MCPServerStatus(
            server_id=server.id,
            name=server.name,
            enabled=True,
            status="ready",
            tool_count=len(specs),
            checked_at=checked_at,
        )
        return specs

    async def probe(
        self,
        server: MCPServerConfig,
        *,
        force_refresh: bool = True,
    ) -> MCPServerStatus:
        """Start the server long enough to initialize and list tools."""
        try:
            await self.list_tools(server, force_refresh=force_refresh)
        except MCPError:
            pass
        return self.status(server)

    def status(self, server: MCPServerConfig) -> MCPServerStatus:
        if not server.enabled:
            return MCPServerStatus(
                server_id=server.id,
                name=server.name,
                enabled=False,
                status="disabled",
                checked_at=time.time(),
            )
        return self._status_cache.get(
            server.id,
            MCPServerStatus(
                server_id=server.id,
                name=server.name,
                enabled=True,
                status="unknown",
            ),
        )

    def invalidate(self, server_id: str | None = None) -> None:
        if server_id is None:
            self._tool_cache.clear()
            self._status_cache.clear()
            return
        self._status_cache.pop(server_id, None)
        self._tool_cache = {
            key: value
            for key, value in self._tool_cache.items()
            if not key.startswith(f"{server_id}:")
        }

    @staticmethod
    def _cache_key(server: MCPServerConfig) -> str:
        return f"{server.id}:{server.updated_at}:{server.enabled}"


default_mcp_runtime = MCPRuntimeManager()
