"""Minimal stdio MCP JSON-RPC client."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from cognix.local.workspace_config import MCPServerConfig


class MCPError(RuntimeError):
    """Raised when an MCP server returns an error or invalid response."""


@dataclass(frozen=True)
class MCPToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """A small MCP client for stdio servers.

    It starts the configured process for the duration of the context manager.
    A later runtime worker pool can cache these clients, but per-call startup is
    predictable and safe for local-first execution.
    """

    def __init__(self, server: MCPServerConfig, *, timeout: float = 20.0) -> None:
        self.server = server
        self.timeout = timeout
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def __aenter__(self) -> MCPClient:
        env = {**os.environ, **self.server.env}
        self._process = await asyncio.create_subprocess_exec(
            self.server.command,
            *self.server.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if not self._process:
            return
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None

    async def initialize(self) -> dict[str, Any]:
        return await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cognix", "version": "0.1.0"},
            },
        )

    async def list_tools(self) -> list[MCPToolSpec]:
        result = await self.request("tools/list", {})
        tools = result.get("tools", [])
        return [
            MCPToolSpec(
                name=item["name"],
                description=item.get("description", ""),
                input_schema=item.get("inputSchema", {"type": "object", "properties": {}}),
                annotations=item.get("annotations", {}),
            )
            for item in tools
            if isinstance(item, dict) and item.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        if "content" in result:
            return _content_to_text(result["content"])
        return result

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._require_process()
        self._request_id += 1
        request_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        await self._write_message(payload)

        while True:
            response = await asyncio.wait_for(self._read_message(), timeout=self.timeout)
            if response.get("id") != request_id:
                continue
            if response.get("error"):
                raise MCPError(str(response["error"]))
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise MCPError(f"Invalid MCP result for {method}: {result!r}")
            return result

    def _require_process(self) -> asyncio.subprocess.Process:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise MCPError("MCP process is not running")
        return self._process

    async def _write_message(self, payload: dict[str, Any]) -> None:
        process = self._require_process()
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        frame = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        process.stdin.write(frame)
        await process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        process = self._require_process()
        headers: dict[str, str] = {}
        while True:
            line = await process.stdout.readline()
            if not line:
                raise MCPError("MCP process closed stdout")
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("ascii").partition(":")
            headers[key.lower()] = value.strip()

        length = int(headers.get("content-length", "0"))
        if length <= 0:
            raise MCPError("MCP response missing Content-Length")
        body = await process.stdout.readexactly(length)
        return json.loads(body.decode("utf-8"))


def _content_to_text(content: Any) -> str:
    if not isinstance(content, list):
        return str(content)
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif isinstance(item, dict):
            parts.append(json.dumps(item, ensure_ascii=False))
        else:
            parts.append(str(item))
    return "\n".join(part for part in parts if part)
