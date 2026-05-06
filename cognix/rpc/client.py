"""JSON-RPC 2.0 client."""

from __future__ import annotations

import uuid
from typing import Any

import httpx


class RPCClient:
    """Async JSON-RPC client over HTTP."""

    def __init__(self, endpoint: str = "http://localhost:8001/rpc", timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Make a JSON-RPC call and return the result."""
        req_id = uuid.uuid4().hex[:8]
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            err = data["error"]
            raise RPCClientError(err["code"], err["message"], err.get("data"))

        return data.get("result")

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        async with httpx.AsyncClient() as client:
            await client.post(self.endpoint, json=payload, timeout=self.timeout)

    async def batch(
        self, requests: list[tuple[str, dict[str, Any] | None]]
    ) -> list[Any]:
        """Make a batch JSON-RPC call."""
        batch_payload = []
        for method, params in requests:
            batch_payload.append(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or {},
                    "id": uuid.uuid4().hex[:8],
                }
            )

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.endpoint, json=batch_payload, timeout=self.timeout)
            resp.raise_for_status()
            results = resp.json()

        return [r.get("result") if "result" in r else r.get("error") for r in results]


class RPCClientError(Exception):
    """Error returned by RPC server."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")
