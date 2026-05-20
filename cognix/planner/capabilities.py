"""Workspace capability discovery for intent planning.

The resolver keeps technical details internal. The planner receives a capability
snapshot and can recommend routes without exposing raw MCP, skill, connector,
CLI, memory, or provider configuration as the primary product surface.
"""

from __future__ import annotations

from typing import Any

from cognix.local.home import CognixHome
from cognix.local.workspace_config import WorkspaceConfigStore


class CapabilityResolver:
    """Resolve workspace capabilities used by the planner."""

    def __init__(self, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()

    async def resolve(self, workspace_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Return a provider-safe, secret-free capability snapshot."""
        from cognix.config import get_settings
        from cognix.providers.resolver import resolve_provider
        from cognix.skills.manager import SkillsManager

        ws_config = WorkspaceConfigStore(workspace_id, home=self.home)
        settings = ws_config.get_settings()
        provider = resolve_provider(workspace_id)
        policy = settings.get("policy", {})
        context_settings = settings.get("context", {})
        enabled_skills = list(settings.get("enabled_skills", []))

        installed_skills = []
        try:
            installed_skills = [
                {
                    "id": skill.get("name", ""),
                    "name": skill.get("name", ""),
                    "kind": "skill",
                    "description": skill.get("description", ""),
                    "tags": skill.get("tags", ""),
                    "enabled": skill.get("name") in enabled_skills,
                    "risk_level": "low",
                    "requires_approval": False,
                    "workspace_enabled": skill.get("name") in enabled_skills,
                }
                for skill in SkillsManager(
                    local_dir=get_settings().skills.local_dir
                ).list_installed()
            ]
        except Exception:
            installed_skills = []

        mcp_servers = self._mcp_servers(ws_config, policy)
        connectors = self._connectors(ws_config, policy)
        browser_automation = self._browser_automation(ws_config, policy)
        workspace_files = self._workspace_files(workspace_id)
        agents = await self._agents(workspace_id)
        entitlement_status = await self._entitlement_status(user_id, workspace_id)

        cli_tools = self._cli_tools(policy)
        memory = {
            "kind": "memory",
            "enabled": bool(
                context_settings.get("include_hot_memory", True)
                or context_settings.get("include_cold_memory", True)
                or context_settings.get("include_skills", True)
                or context_settings.get("include_deep_memory", False)
            ),
            "hot": bool(context_settings.get("include_hot_memory", True)),
            "cold": bool(context_settings.get("include_cold_memory", True)),
            "procedural": bool(context_settings.get("include_skills", True)),
            "deep": bool(context_settings.get("include_deep_memory", False)),
            "token_budget": context_settings.get("token_budget", 8000),
            "routing_strategy": context_settings.get("routing_strategy", "priority"),
        }

        capabilities = [
            *installed_skills,
            *[tool for server in mcp_servers for tool in server.get("tools", [])],
            *[tool for connector in connectors for tool in connector.get("tools", [])],
            browser_automation,
            *cli_tools,
            memory,
        ]

        return {
            "workspace_id": workspace_id,
            "provider": {
                "configured": bool(provider.api_key),
                "base_url_configured": bool(provider.base_url),
                "default_model": provider.default_model,
            },
            "enabled_skills": enabled_skills,
            "installed_skills": installed_skills[:20],
            "mcp_servers": mcp_servers,
            "connectors": connectors,
            "browser_automation": browser_automation,
            "cli_tools": cli_tools,
            "memory": memory,
            "agents": agents,
            "workspace_files": workspace_files,
            "policy": {
                "file_write": policy.get("file_write", "workspace-write"),
                "network_access": policy.get("network_access", "ask"),
                "mcp_tools": policy.get("mcp_tools", "workspace-write"),
                "connector_access": policy.get("connector_access", "ask"),
                "blocked_commands": policy.get("blocked_commands", []),
            },
            "entitlement": entitlement_status,
            "capabilities": capabilities[:80],
        }

    def _mcp_servers(
        self,
        ws_config: WorkspaceConfigStore,
        policy: dict[str, Any],
    ) -> list[dict[str, Any]]:
        servers = []
        try:
            for server in ws_config.list_mcp_servers():
                disabled = set(server.metadata.get("disabled_tools", []))
                tools = []
                for tool in (server.metadata.get("tools") or [])[:12]:
                    if not isinstance(tool, dict):
                        continue
                    name = tool.get("name", "")
                    if not name or name in disabled:
                        continue
                    tools.append(
                        {
                            "id": f"mcp.{server.name}.{name}",
                            "kind": "mcp_tool",
                            "server": server.name,
                            "tool": name,
                            "name": name,
                            "description": tool.get("description", ""),
                            "risk_level": "medium",
                            "requires_approval": policy.get("mcp_tools") == "ask",
                            "workspace_enabled": bool(server.enabled),
                        }
                    )
                servers.append(
                    {
                        "id": server.id,
                        "name": server.name,
                        "kind": "mcp_server",
                        "enabled": bool(server.enabled),
                        "tool_count": len(tools),
                        "tools": tools,
                    }
                )
        except Exception:
            return []
        return servers

    def _connectors(
        self,
        ws_config: WorkspaceConfigStore,
        policy: dict[str, Any],
    ) -> list[dict[str, Any]]:
        connectors = []
        try:
            for connector in ws_config.list_connectors():
                disabled = set(connector.metadata.get("disabled_tools", []))
                tools = [
                    {
                        "id": f"connector.{connector.platform}.send",
                        "kind": "connector_tool",
                        "platform": connector.platform,
                        "tool": "send",
                        "name": f"{connector.platform}.send",
                        "description": f"Send or write back through {connector.platform}.",
                        "risk_level": "high",
                        "requires_approval": policy.get("connector_access") != "workspace-write",
                        "workspace_enabled": connector.enabled and "send" not in disabled,
                    }
                ]
                connectors.append(
                    {
                        "id": connector.id,
                        "kind": "connector",
                        "platform": connector.platform,
                        "enabled": bool(connector.enabled),
                        "tools": tools,
                    }
                )
        except Exception:
            return []
        return connectors

    def _browser_automation(
        self,
        ws_config: WorkspaceConfigStore,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        """Expose browser automation as an internal capability preset."""
        preset = None
        try:
            preset = next(
                (
                    server
                    for server in ws_config.list_mcp_servers()
                    if server.metadata.get("capability") == "browser_automation"
                    or server.id == "browser_playwright"
                ),
                None,
            )
        except Exception:
            preset = None
        return {
            "id": "browser.automation",
            "kind": "browser_automation",
            "name": "Browser automation",
            "description": (
                "Run authorized browser workflows through an isolated Playwright profile "
                "or Browser MCP preset."
            ),
            "risk_level": "high",
            "requires_approval": policy.get("network_access", "ask") != "workspace-write",
            "workspace_enabled": True,
            "mcp_preset_configured": bool(preset),
            "mcp_server_id": preset.id if preset else "",
            "engines": ["playwright", "mcp"],
        }

    def _cli_tools(self, policy: dict[str, Any]) -> list[dict[str, Any]]:
        blocked = policy.get("blocked_commands", [])
        return [
            {
                "id": "cli.python",
                "kind": "cli_tool",
                "name": "Python data processing",
                "description": "Run approved Python scripts for parsing, cleaning, and reports.",
                "risk_level": "medium",
                "requires_approval": policy.get("file_write") == "ask",
                "workspace_enabled": True,
                "blocked_commands": blocked,
            },
            {
                "id": "cli.shell",
                "kind": "cli_tool",
                "name": "Shell command execution",
                "description": "Run approved workspace-scoped shell commands.",
                "risk_level": "high",
                "requires_approval": True,
                "workspace_enabled": True,
                "blocked_commands": blocked,
            },
        ]

    def _workspace_files(self, workspace_id: str) -> list[str]:
        try:
            from cognix.local.workspace import WorkspaceManager

            ws_path = WorkspaceManager(self.home).workspace_path(workspace_id)
            if not ws_path.exists():
                return []
            return [
                path.name
                for path in ws_path.glob("*")
                if path.is_file() and not path.name.startswith(".")
            ][:20]
        except Exception:
            return []

    @staticmethod
    async def _agents(workspace_id: str) -> list[dict[str, Any]]:
        try:
            from sqlalchemy import select

            from cognix.storage.database import get_session
            from cognix.storage.models import AgentModel

            async with get_session() as session:
                result = await session.execute(
                    select(AgentModel).where(AgentModel.workspace_id == workspace_id)
                )
                return [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "model": agent.model,
                        "permission_mode": agent.permission_mode,
                    }
                    for agent in result.scalars().all()
                ]
        except Exception:
            return []

    @staticmethod
    async def _entitlement_status(user_id: str | None, workspace_id: str) -> str:
        if not user_id:
            return "unknown"
        try:
            from cognix.billing.entitlement import EntitlementService

            entitlement = await EntitlementService.check_model_execution(user_id, workspace_id)
            if not entitlement.allowed:
                return "none"
            if not entitlement.requires_byok:
                return "commercial_plan"
            return "byok"
        except Exception:
            return "unknown"
