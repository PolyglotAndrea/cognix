"""Connector provider registry."""

from __future__ import annotations

from cognix.connectors.base import ConnectorProvider

_PROVIDERS: dict[str, ConnectorProvider] = {}


def _load() -> dict[str, ConnectorProvider]:
    global _PROVIDERS
    if _PROVIDERS:
        return _PROVIDERS
    from cognix.connectors.providers.instagram_provider import InstagramConnectorProvider
    from cognix.connectors.providers.x_provider import XConnectorProvider

    _PROVIDERS = {
        "x": XConnectorProvider(),
        "instagram": InstagramConnectorProvider(),
    }
    return _PROVIDERS


def get_provider(platform: str) -> ConnectorProvider | None:
    return _load().get(platform)


def all_providers() -> dict[str, ConnectorProvider]:
    return dict(_load())
