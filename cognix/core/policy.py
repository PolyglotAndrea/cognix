"""Workspace-scoped policy service wrapping the permission matrix."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from cognix.core.permissions import decide_permission

logger = logging.getLogger(__name__)


@dataclass
class PolicyResult:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""


class WorkspacePolicyService:
    """Enforces workspace-level policy on tool execution, file access, and network."""

    def __init__(self, workspace_id: str | None = None) -> None:
        self.workspace_id = workspace_id

    def _get_policy(self) -> dict:
        if not self.workspace_id:
            return {}
        try:
            from cognix.local.workspace_config import WorkspaceConfigStore

            settings = WorkspaceConfigStore(self.workspace_id).get_settings()
            return settings.get("policy", {})
        except Exception:
            return {}

    async def check_file_access(
        self,
        path: str,
        operation: str,
        *,
        permission_mode: str = "workspace-write",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyResult:
        policy = self._get_policy()
        effective_mode = policy.get("file_write", permission_mode)
        access_level = "write" if operation in ("write", "delete") else "read"

        decision = decide_permission(effective_mode, access_level, f"file {operation}: {path}")
        result = PolicyResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        await self._log(
            operation=f"file_{operation}:{path}",
            access_level=access_level,
            permission_mode=effective_mode,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result

    async def check_network_access(
        self,
        url: str,
        *,
        permission_mode: str = "workspace-write",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyResult:
        policy = self._get_policy()
        effective_mode = policy.get("network_access", permission_mode)

        # Check domain allowlist
        allowed_domains = policy.get("allowed_domains", [])
        if allowed_domains:
            try:
                parsed = urlparse(url)
                domain = parsed.hostname or ""
                if not any(domain.endswith(d) for d in allowed_domains):
                    result = PolicyResult(
                        allowed=False,
                        reason=f"Domain '{domain}' not in allowlist",
                    )
                    await self._log(
                        operation=f"network:{url}",
                        access_level="write",
                        permission_mode=effective_mode,
                        decision="denied",
                        reason=result.reason,
                        user_id=user_id,
                        agent_id=agent_id,
                    )
                    return result
            except Exception:
                pass

        decision = decide_permission(effective_mode, "write", f"network access: {url}")
        result = PolicyResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        await self._log(
            operation=f"network:{url}",
            access_level="write",
            permission_mode=effective_mode,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result

    async def check_mcp_tool(
        self,
        tool_name: str,
        access_level: str = "write",
        *,
        permission_mode: str = "workspace-write",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyResult:
        policy = self._get_policy()
        effective_mode = policy.get("mcp_tools", permission_mode)

        decision = decide_permission(
            effective_mode, access_level, f"MCP tool: {tool_name}",
        )
        result = PolicyResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        await self._log(
            operation=f"mcp_tool:{tool_name}",
            access_level=access_level,
            permission_mode=effective_mode,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result

    async def check_connector(
        self,
        platform: str,
        *,
        permission_mode: str = "workspace-write",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyResult:
        policy = self._get_policy()
        effective_mode = policy.get("connector_access", permission_mode)

        decision = decide_permission(effective_mode, "write", f"connector: {platform}")
        result = PolicyResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        await self._log(
            operation=f"connector:{platform}",
            access_level="write",
            permission_mode=effective_mode,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result

    async def check_command(
        self,
        command: str,
        *,
        permission_mode: str = "workspace-write",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyResult:
        policy = self._get_policy()
        blocked = policy.get("blocked_commands", [])

        # Check blocklist
        cmd_lower = command.lower().strip()
        for blocked_cmd in blocked:
            if blocked_cmd and blocked_cmd.lower() in cmd_lower:
                result = PolicyResult(
                    allowed=False,
                    reason=f"Command blocked by policy: '{blocked_cmd}'",
                )
                await self._log(
                    operation=f"command:{command}",
                    access_level="dangerous",
                    permission_mode=permission_mode,
                    decision="denied",
                    reason=result.reason,
                    user_id=user_id,
                    agent_id=agent_id,
                )
                return result

        decision = decide_permission(permission_mode, "dangerous", f"command: {command}")
        result = PolicyResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        await self._log(
            operation=f"command:{command}",
            access_level="dangerous",
            permission_mode=permission_mode,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            user_id=user_id,
            agent_id=agent_id,
        )
        return result

    async def _log(
        self,
        *,
        operation: str,
        access_level: str,
        permission_mode: str,
        decision: str,
        reason: str = "",
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        if not self.workspace_id:
            return
        try:
            from cognix.storage.database import get_session
            from cognix.storage.models import PolicyAuditLogModel

            entry = PolicyAuditLogModel(
                workspace_id=self.workspace_id,
                user_id=user_id,
                agent_id=agent_id,
                operation=operation,
                access_level=access_level,
                permission_mode=permission_mode,
                decision=decision,
                reason=reason,
            )
            async with get_session() as session:
                session.add(entry)
        except Exception:
            logger.debug("Failed to write policy audit log", exc_info=True)
