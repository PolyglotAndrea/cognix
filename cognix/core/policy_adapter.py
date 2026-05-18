"""Policy adapter for external execution backends.

Provides an abstract PolicyAdapter interface and a concrete CodexPolicyAdapter
that delegates policy checks to a WorkspacePolicyService instance.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

try:
    from cognix.core.policy_hooks import PolicyResult
except ImportError:
    # Allow module to load even if hooks module is not yet available
    PolicyResult = Any  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class PolicyAdapter(ABC):
    """Abstract interface for policy adapters that gate and record execution."""

    @abstractmethod
    async def check_before_execute(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        """Check whether an operation is allowed before execution.

        Args:
            operation: The operation type (e.g. "file", "network", "command",
                "mcp", "connector").
            context: Arbitrary context relevant to the operation (paths,
                URLs, command strings, etc.).

        Returns:
            A PolicyResult indicating whether the operation is permitted.
        """
        ...

    @abstractmethod
    async def record_execution(
        self, operation: str, result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """Record an executed operation for audit purposes.

        Args:
            operation: The operation type that was executed.
            result: The outcome of the execution (status, output, errors, etc.).
            context: The context that was passed to check_before_execute.
        """
        ...


# ---------------------------------------------------------------------------
# Codex implementation
# ---------------------------------------------------------------------------


class CodexPolicyAdapter(PolicyAdapter):
    """PolicyAdapter backed by a WorkspacePolicyService.

    Delegates pre-execution checks to the appropriate policy service method
    based on the operation type and logs every execution to the standard
    audit trail via the ``logging`` module.
    """

    def __init__(self, policy_service: Any) -> None:
        """Initialise the adapter.

        Args:
            policy_service: A ``WorkspacePolicyService`` (or compatible)
                instance that exposes ``check_file_access``,
                ``check_network_access``, ``check_command_execution``,
                ``check_mcp_access``, and ``check_connector_access`` methods.
        """
        self._policy_service = policy_service

    async def check_before_execute(self, operation: str, context: dict[str, Any]) -> PolicyResult:
        """Delegate to the policy service method matching *operation*.

        Supported operation types and their mapping:
        - ``"file"``       -> ``check_file_access``
        - ``"network"``    -> ``check_network_access``
        - ``"command"``    -> ``check_command_execution``
        - ``"mcp"``        -> ``check_mcp_access``
        - ``"connector"``  -> ``check_connector_access``

        Raises:
            ValueError: If *operation* is not one of the supported types.
        """
        dispatch: dict[str, str] = {
            "file": "check_file_access",
            "network": "check_network_access",
            "command": "check_command_execution",
            "mcp": "check_mcp_access",
            "connector": "check_connector_access",
        }

        method_name = dispatch.get(operation)
        if method_name is None:
            raise ValueError(
                f"Unknown operation type {operation!r}. "
                f"Supported types: {', '.join(sorted(dispatch))}"
            )

        method = getattr(self._policy_service, method_name)
        return await method(context)

    async def record_execution(
        self, operation: str, result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """Log the executed operation to the audit trail."""
        logger.info(
            "Policy audit | operation=%s | result=%s | context=%s",
            operation,
            result,
            context,
        )
