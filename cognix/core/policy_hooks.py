"""Extensible policy hook system for workspace-scoped operation gating.

Provides a protocol-based hook interface so that file, network, and command
policies can be registered and evaluated in a uniform way.  Each hook
independently inspects an operation and returns a `PolicyResult`.  The
`PolicyHookRegistry` aggregates registered hooks and short-circuits on the
first denial.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyResult:
    """Outcome of a single policy check.

    Attributes:
        allowed: Whether the operation is permitted.
        reason:  Human-readable explanation for the decision.
        details: Arbitrary key-value metadata (e.g. matched rule, severity).
    """

    allowed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Hook protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PolicyHook(Protocol):
    """Interface that every policy hook must satisfy."""

    async def check(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        """Evaluate *operation* against the hook's rules.

        Args:
            operation: A dotted identifier such as ``file.write``,
                ``network.request``, or ``command.exec``.
            context: Hook-specific payload (paths, URLs, command strings, etc.).

        Returns:
            A `PolicyResult` indicating whether the operation is allowed.
        """
        ...


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


class FilePolicyHook:
    """Checks file paths against workspace policy rules.

    Accepted *context* keys:

    * ``path`` (str, required) -- the absolute or relative file path.

    Policy rules are supplied at construction time:

    * ``allowed_roots``: list of directory prefixes the agent may access.
      An empty list means *all* paths are allowed (subject to other rules).
    * ``blocked_paths``: list of path substrings that are always denied.
    * ``blocked_extensions``: list of file extensions (e.g. ``[".env", ".pem"]``)
      that are denied.
    """

    def __init__(
        self,
        *,
        allowed_roots: list[str] | None = None,
        blocked_paths: list[str] | None = None,
        blocked_extensions: list[str] | None = None,
    ) -> None:
        self.allowed_roots = [os.path.realpath(r) for r in (allowed_roots or [])]
        self.blocked_paths = blocked_paths or []
        self.blocked_extensions = [
            ext if ext.startswith(".") else f".{ext}" for ext in (blocked_extensions or [])
        ]

    async def check(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        path: str | None = context.get("path")
        if not path:
            return PolicyResult(
                allowed=False,
                reason="Missing required context key: 'path'",
                details={"operation": operation},
            )

        real_path = os.path.realpath(path)

        # Blocked-path substring check.
        for blocked in self.blocked_paths:
            if blocked and blocked in real_path:
                return PolicyResult(
                    allowed=False,
                    reason=f"Path matches blocked rule: '{blocked}'",
                    details={"path": real_path, "matched_rule": blocked},
                )

        # Blocked-extension check.
        _, ext = os.path.splitext(real_path)
        if ext and ext.lower() in {e.lower() for e in self.blocked_extensions}:
            return PolicyResult(
                allowed=False,
                reason=f"File extension '{ext}' is blocked by policy",
                details={"path": real_path, "extension": ext},
            )

        # Allowed-roots check.
        if self.allowed_roots:
            within_root = any(
                real_path.startswith(root + os.sep) or real_path == root
                for root in self.allowed_roots
            )
            if not within_root:
                return PolicyResult(
                    allowed=False,
                    reason="Path is outside allowed workspace roots",
                    details={"path": real_path, "allowed_roots": self.allowed_roots},
                )

        return PolicyResult(
            allowed=True,
            reason="File access permitted",
            details={"path": real_path},
        )


class NetworkPolicyHook:
    """Checks network access against workspace policy rules.

    Accepted *context* keys:

    * ``url`` (str, required) -- the target URL.

    Policy rules:

    * ``allowed_domains``: allowlist of domain suffixes (e.g. ``["api.openai.com"]``).
      An empty list means all domains pass this check.
    * ``blocked_domains``: denylist of domain suffixes.
    * ``blocked_ports``: set of port numbers that are never allowed.
    """

    def __init__(
        self,
        *,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        blocked_ports: set[int] | None = None,
    ) -> None:
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []
        self.blocked_ports = blocked_ports or set()

    async def check(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        url: str | None = context.get("url")
        if not url:
            return PolicyResult(
                allowed=False,
                reason="Missing required context key: 'url'",
                details={"operation": operation},
            )

        try:
            parsed = urlparse(url)
        except Exception as exc:
            return PolicyResult(
                allowed=False,
                reason=f"Failed to parse URL: {exc}",
                details={"url": url},
            )

        hostname = parsed.hostname or ""
        port = parsed.port

        # Blocked-port check.
        if port and port in self.blocked_ports:
            return PolicyResult(
                allowed=False,
                reason=f"Port {port} is blocked by policy",
                details={"url": url, "port": port},
            )

        # Blocked-domain check.
        for domain in self.blocked_domains:
            if domain and hostname.endswith(domain):
                return PolicyResult(
                    allowed=False,
                    reason=f"Domain '{hostname}' matches blocked rule: '{domain}'",
                    details={"url": url, "hostname": hostname, "matched_rule": domain},
                )

        # Allowed-domain check.
        if self.allowed_domains:
            if not any(hostname.endswith(d) for d in self.allowed_domains):
                return PolicyResult(
                    allowed=False,
                    reason=f"Domain '{hostname}' is not in the allowlist",
                    details={"url": url, "hostname": hostname},
                )

        return PolicyResult(
            allowed=True,
            reason="Network access permitted",
            details={"url": url, "hostname": hostname},
        )


class CommandPolicyHook:
    """Checks command execution against workspace policy rules.

    Accepted *context* keys:

    * ``command`` (str, required) -- the shell command string.

    Policy rules:

    * ``blocked_commands``: list of command prefixes or tokens that are denied
      (e.g. ``["rm -rf", "shutdown"]``).
    * ``allowed_commands``: if non-empty, only commands starting with one of
      these prefixes are permitted.
    * ``blocked_patterns``: list of regex patterns; if any match the full
      command string the command is denied.
    """

    def __init__(
        self,
        *,
        blocked_commands: list[str] | None = None,
        allowed_commands: list[str] | None = None,
        blocked_patterns: list[str] | None = None,
    ) -> None:
        self.blocked_commands = [c.lower() for c in (blocked_commands or [])]
        self.allowed_commands = [c.lower() for c in (allowed_commands or [])]
        self.blocked_patterns = [re.compile(p) for p in (blocked_patterns or [])]

    async def check(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        command: str | None = context.get("command")
        if not command:
            return PolicyResult(
                allowed=False,
                reason="Missing required context key: 'command'",
                details={"operation": operation},
            )

        cmd_lower = command.lower().strip()

        # Blocked-command token/prefix check.
        for blocked in self.blocked_commands:
            if blocked and blocked in cmd_lower:
                return PolicyResult(
                    allowed=False,
                    reason=f"Command matches blocked rule: '{blocked}'",
                    details={"command": command, "matched_rule": blocked},
                )

        # Regex pattern check.
        for pattern in self.blocked_patterns:
            if pattern.search(command):
                return PolicyResult(
                    allowed=False,
                    reason=f"Command matches blocked pattern: '{pattern.pattern}'",
                    details={"command": command, "matched_pattern": pattern.pattern},
                )

        # Allowlist check.
        if self.allowed_commands:
            cmd_start = cmd_lower.split()[0] if cmd_lower.split() else ""
            if not any(cmd_start == allowed for allowed in self.allowed_commands):
                return PolicyResult(
                    allowed=False,
                    reason=f"Command '{cmd_start}' is not in the allowlist",
                    details={"command": command, "command_prefix": cmd_start},
                )

        return PolicyResult(
            allowed=True,
            reason="Command execution permitted",
            details={"command": command},
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PolicyHookRegistry:
    """Manages a named collection of `PolicyHook` instances.

    Callers register hooks by name, then invoke `check_all` to evaluate every
    registered hook against an operation.  The first hook that denies the
    operation short-circuits the evaluation and its result is returned.  If all
    hooks allow, a permissive result is returned.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, PolicyHook] = {}

    # -- mutation -----------------------------------------------------------

    def register(self, hook_name: str, hook: PolicyHook) -> None:
        """Add or replace a hook identified by *hook_name*.

        Args:
            hook_name: Unique name for this hook (e.g. ``"file_policy"``).
            hook: An object satisfying the `PolicyHook` protocol.

        Raises:
            TypeError: If *hook* does not satisfy the `PolicyHook` protocol.
        """
        if not isinstance(hook, PolicyHook):
            raise TypeError(
                f"Expected an object implementing PolicyHook, got {type(hook).__name__}"
            )
        if hook_name in self._hooks:
            logger.info("Replacing existing policy hook '%s'", hook_name)
        else:
            logger.info("Registering policy hook '%s'", hook_name)
        self._hooks[hook_name] = hook

    def unregister(self, hook_name: str) -> None:
        """Remove the hook identified by *hook_name*.

        Raises:
            KeyError: If no hook with that name is registered.
        """
        if hook_name not in self._hooks:
            raise KeyError(f"No policy hook registered with name '{hook_name}'")
        logger.info("Unregistering policy hook '%s'", hook_name)
        del self._hooks[hook_name]

    # -- evaluation ---------------------------------------------------------

    async def check_all(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        """Run every registered hook and return the composite decision.

        Hooks are evaluated in insertion order.  The first hook that returns
        ``allowed=False`` terminates the chain and its result is returned.
        If all hooks pass, an allowing result is returned.

        Args:
            operation: Dotted operation identifier (e.g. ``"file.write"``).
            context: Payload forwarded to each hook.

        Returns:
            A `PolicyResult` reflecting the overall decision.
        """
        if not self._hooks:
            logger.debug("No policy hooks registered; allowing by default")
            return PolicyResult(
                allowed=True,
                reason="No policy hooks registered",
                details={"operation": operation},
            )

        for name, hook in self._hooks.items():
            result = await hook.check(operation, context)
            logger.debug(
                "Hook '%s' returned allowed=%s reason=%s",
                name,
                result.allowed,
                result.reason,
            )
            if not result.allowed:
                logger.info(
                    "Operation '%s' denied by hook '%s': %s",
                    operation,
                    name,
                    result.reason,
                )
                # Augment details with the denying hook name.
                denied_details = dict(result.details)
                denied_details["denied_by_hook"] = name
                return PolicyResult(
                    allowed=False,
                    reason=result.reason,
                    details=denied_details,
                )

        logger.debug("All %d hooks passed for operation '%s'", len(self._hooks), operation)
        return PolicyResult(
            allowed=True,
            reason="All policy hooks passed",
            details={"operation": operation, "hooks_evaluated": len(self._hooks)},
        )

    # -- introspection ------------------------------------------------------

    def list_hooks(self) -> list[str]:
        """Return the names of all currently registered hooks."""
        return list(self._hooks.keys())

    def __len__(self) -> int:
        return len(self._hooks)

    def __contains__(self, hook_name: str) -> bool:
        return hook_name in self._hooks
