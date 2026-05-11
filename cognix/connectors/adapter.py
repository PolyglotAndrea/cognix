"""Convert connector platform tools into core Tool instances."""

from __future__ import annotations

import logging
from typing import Any

from cognix.connectors.base import ConnectorProvider, ConnectorSpec
from cognix.core.tool import Tool

logger = logging.getLogger(__name__)


def _safe_name(name: str) -> str:
    return name.replace("-", "_").replace(" ", "_").lower()


def connector_access_level(spec: ConnectorSpec, config_metadata: dict[str, Any]) -> str:
    """Determine the access level for a connector tool.

    Priority:
    1. Per-tool override from config metadata tool_access
    2. Spec default from the provider
    3. Heuristic fallback
    """
    overrides = config_metadata.get("tool_access", {})
    if spec.name in overrides:
        return overrides[spec.name]

    if spec.access_level in ("read", "write", "dangerous"):
        return spec.access_level

    # Heuristic
    dangerous = {"delete", "remove", "post", "publish", "send", "submit", "upload"}
    write = {"create", "update", "edit", "reply", "comment"}
    name_lower = spec.name.lower()
    if any(w in name_lower for w in dangerous):
        return "dangerous"
    if any(w in name_lower for w in write):
        return "write"
    return "read"


def _make_handler(
    provider: ConnectorProvider,
    tool_name: str,
    credential_id: str,
):
    """Create an async handler closure with proper variable binding.

    On each invocation the handler fetches the credential from the DB,
    decrypts the token (refreshing if expired), then calls the provider.
    """

    async def handler(**kwargs: Any) -> Any:
        from cognix.connectors.manager import ConnectorManager

        manager = ConnectorManager()
        credential = await manager.get_credential(credential_id)
        if not credential:
            return {"error": "Connector credential not found. Re-connect."}
        token = await manager.get_decrypted_token(credential)
        return await provider.call_tool(tool_name, kwargs, token)

    return handler


def connector_to_core_tools(
    platform: str,
    provider: ConnectorProvider,
    credential_id: str,
    config_metadata: dict[str, Any] | None = None,
) -> list[Tool]:
    """Convert a connector provider's tools into core Tool instances.

    Each tool gets a prefixed name (conn_{platform}_{tool_name}) and a handler
    closure that calls the provider's call_tool with the stored access token.
    """
    metadata = config_metadata or {}
    disabled_tools = set(metadata.get("disabled_tools", []))
    tools: list[Tool] = []

    for spec in provider.list_tools():
        if spec.name in disabled_tools:
            continue

        tool_name = f"conn_{_safe_name(platform)}_{_safe_name(spec.name)}"
        level = connector_access_level(spec, metadata)

        handler = _make_handler(provider, spec.name, credential_id)

        tool = Tool(
            name=tool_name,
            description=f"[{provider.display_name}] {spec.description}",
            handler=handler,
            parameters=spec.parameters,
            access_level=level,
            metadata={
                "original_name": spec.name,
                "platform": platform,
                "provider": provider.display_name,
                "credential_id": credential_id,
            },
        )
        tools.append(tool)

    return tools
