"""MCP server lifecycle and discovery helpers."""

from __future__ import annotations

import asyncio
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
    stderr: str = ""
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
        self._persistent_clients: dict[str, MCPClient] = {}
        self._persistent_locks: dict[str, asyncio.Lock] = {}

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
        stderr = ""
        try:
            client = self.client_factory(server)
            async with client:
                specs = await client.list_tools()
            stderr = str(getattr(client, "stderr_tail", "") or "")
        except Exception as exc:
            stderr = str(getattr(locals().get("client", None), "stderr_tail", "") or "")
            self._status_cache[server.id] = MCPServerStatus(
                server_id=server.id,
                name=server.name,
                enabled=True,
                status="error",
                error=str(exc),
                stderr=stderr,
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
            stderr=stderr,
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

    async def invalidate(self, server_id: str | None = None) -> None:
        """Clear caches and close persistent connections."""
        await self.close_persistent(server_id)
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

    async def restart(self, server: MCPServerConfig) -> MCPServerStatus:
        """Clear cached discovery data, close persistent connection, and probe again."""
        await self.invalidate(server.id)
        return await self.probe(server, force_refresh=True)

    async def stop(self, server: MCPServerConfig) -> MCPServerStatus:
        """Close persistent connection and drop local runtime cache for a server."""
        await self.invalidate(server.id)
        status = MCPServerStatus(
            server_id=server.id,
            name=server.name,
            enabled=server.enabled,
            status="stopped" if server.enabled else "disabled",
            checked_at=time.time(),
        )
        self._status_cache[server.id] = status
        return status

    async def call_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool on an MCP server, reusing a persistent connection if available."""
        if not server.enabled:
            raise MCPError(f"MCP server '{server.name}' is disabled")
        client = await self._get_persistent_client(server)
        return await client.call_tool(tool_name, arguments)

    async def _get_persistent_client(self, server: MCPServerConfig) -> MCPClient:
        """Get or create a persistent client connection for a server."""
        lock = self._persistent_locks.setdefault(server.id, asyncio.Lock())
        async with lock:
            client = self._persistent_clients.get(server.id)
            if client is not None and client._process is not None and client._process.returncode is None:
                return client
            # Create new persistent connection
            client = self.client_factory(server)
            await client.__aenter__()
            self._persistent_clients[server.id] = client
            return client

    async def close_persistent(self, server_id: str | None = None) -> None:
        """Close persistent client connections."""
        if server_id:
            client = self._persistent_clients.pop(server_id, None)
            if client:
                await client.__aexit__(None, None, None)
        else:
            for client in self._persistent_clients.values():
                await client.__aexit__(None, None, None)
            self._persistent_clients.clear()
        self._persistent_locks.pop(server_id, None) if server_id else self._persistent_locks.clear()

    @staticmethod
    def _cache_key(server: MCPServerConfig) -> str:
        return f"{server.id}:{server.updated_at}:{server.enabled}"


default_mcp_runtime = MCPRuntimeManager()
