"""Base classes for connector providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorSpec:
    """Describes a single tool exposed by a connector platform."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    access_level: str = "read"  # "read" | "write" | "dangerous"


class ConnectorProvider(ABC):
    """Abstract base for a connector platform (X, Instagram, etc.)."""

    platform: str = ""
    display_name: str = ""
    authorize_url: str = ""
    token_url: str = ""
    default_scopes: list[str] = []
    client_id_env: str = ""
    client_secret_env: str = ""

    @abstractmethod
    def get_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
    ) -> str:
        """Build the OAuth authorization URL."""

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        state: str = "",
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens.

        The ``state`` parameter carries platform-specific data (e.g. PKCE
        code_verifier for X).  Providers that embed extra data in the state
        string should override this method and extract it.
        """

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token."""

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch the authenticated user's profile."""

    @abstractmethod
    def list_tools(self) -> list[ConnectorSpec]:
        """Return the static list of tools this platform exposes."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any], access_token: str) -> Any:
        """Execute a tool by name with the given arguments and access token."""

    def _client_id(self) -> str | None:
        from cognix.config import get_settings

        key = self.client_id_env.replace("COGNIX_CONNECTORS__", "").lower()
        return getattr(get_settings().connectors, key, None)

    def _client_secret(self) -> str | None:
        from cognix.config import get_settings

        key = self.client_secret_env.replace("COGNIX_CONNECTORS__", "").lower()
        return getattr(get_settings().connectors, key, None)
