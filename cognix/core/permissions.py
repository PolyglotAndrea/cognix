"""Runtime permission policy for tools and workspace files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PermissionMode = Literal["read-only", "workspace-write", "ask", "unrestricted"]
AccessLevel = Literal["read", "write", "dangerous"]


class PermissionDeniedError(RuntimeError):
    """Raised when the runtime permission mode blocks an operation."""


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""


def normalize_permission_mode(mode: str | None) -> PermissionMode:
    if mode in ("read-only", "workspace-write", "ask", "unrestricted"):
        return mode
    return "workspace-write"


def normalize_access_level(level: str | None) -> AccessLevel:
    if level in ("read", "write", "dangerous"):
        return level
    return "read"


def decide_permission(
    mode: str | None,
    access_level: str | None,
    operation: str,
) -> PermissionDecision:
    """Decide whether a runtime operation is allowed."""
    normalized_mode = normalize_permission_mode(mode)
    normalized_access = normalize_access_level(access_level)

    if normalized_mode == "unrestricted":
        return PermissionDecision(allowed=True)

    if normalized_mode == "read-only":
        if normalized_access == "read":
            return PermissionDecision(allowed=True)
        return PermissionDecision(
            allowed=False,
            reason=f"{operation} requires {normalized_access} access in read-only mode",
        )

    if normalized_mode == "ask":
        if normalized_access == "read":
            return PermissionDecision(allowed=True)
        return PermissionDecision(
            allowed=False,
            requires_approval=True,
            reason=f"{operation} requires approval for {normalized_access} access",
        )

    if normalized_access == "dangerous":
        return PermissionDecision(
            allowed=False,
            requires_approval=True,
            reason=f"{operation} requires approval for dangerous access",
        )

    return PermissionDecision(allowed=True)


def ensure_permission(mode: str | None, access_level: str | None, operation: str) -> None:
    decision = decide_permission(mode, access_level, operation)
    if not decision.allowed:
        raise PermissionDeniedError(decision.reason)
