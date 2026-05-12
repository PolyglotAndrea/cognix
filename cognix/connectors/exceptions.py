"""Shared exceptions for connector providers."""

from __future__ import annotations

from typing import Any


class ConnectorAPIError(Exception):
    """Structured error from a connector platform API call."""

    def __init__(
        self,
        platform: str,
        tool: str,
        status_code: int,
        error_body: dict[str, Any],
        message: str = "",
    ):
        self.platform = platform
        self.tool = tool
        self.status_code = status_code
        self.error_body = error_body
        self.message = message or f"{platform} API error ({status_code})"
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "platform": self.platform,
            "tool": self.tool,
            "status_code": self.status_code,
            "message": self.message,
            "details": self.error_body,
        }


class ConnectorTokenExpiredError(Exception):
    """Raised when a connector token has expired and cannot be refreshed."""

    def __init__(self, platform: str, credential_id: str, message: str = ""):
        self.platform = platform
        self.credential_id = credential_id
        self.message = message or (
            f"{platform} token expired. Re-authorize to continue."
        )
        super().__init__(self.message)
