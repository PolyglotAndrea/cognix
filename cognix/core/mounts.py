"""Runtime helpers for mounting workspace capabilities onto Agents."""

from __future__ import annotations

from cognix.core.agent import Agent


def attach_workspace_skills(agent: Agent, workspace_id: str) -> list[str]:
    """Attach enabled workspace skills to an Agent runtime."""
    from cognix.config import get_settings
    from cognix.local.workspace_config import WorkspaceConfigStore
    from cognix.skills.adapter import skill_to_core_tools
    from cognix.skills.manager import SkillsManager

    attached: list[str] = []
    try:
        enabled_skills = (
            WorkspaceConfigStore(workspace_id)
            .get_settings()
            .get(
                "enabled_skills",
                [],
            )
        )
    except FileNotFoundError:
        return attached
    if not enabled_skills:
        return attached

    manager = SkillsManager(local_dir=get_settings().skills.local_dir)
    for skill_name in enabled_skills:
        skill = manager.load(skill_name)
        if not skill:
            continue
        for tool in skill_to_core_tools(skill):
            if tool.name in [existing.name for existing in agent.tools]:
                agent.remove_tool(tool.name)
            agent.add_tool(tool)
            attached.append(tool.name)
    return attached


async def attach_workspace_connector_tools(agent: Agent, workspace_id: str) -> list[str]:
    """Attach enabled connector tools to an Agent runtime."""
    from cognix.connectors.adapter import connector_to_core_tools
    from cognix.connectors.manager import ConnectorManager
    from cognix.connectors.providers import get_provider
    from cognix.local.workspace_config import WorkspaceConfigStore

    attached: list[str] = []
    try:
        store = WorkspaceConfigStore(workspace_id)
        connectors = store.list_connectors()
    except FileNotFoundError:
        return attached

    if not connectors:
        return attached

    for conn_config in connectors:
        if not conn_config.enabled:
            continue

        provider = get_provider(conn_config.platform)
        if not provider:
            continue

        # Validate credential exists
        manager = ConnectorManager()
        credential = await manager.get_credential(conn_config.credential_id)
        if not credential:
            continue

        tools = connector_to_core_tools(
            platform=conn_config.platform,
            provider=provider,
            credential_id=conn_config.credential_id,
            config_metadata=conn_config.metadata,
        )
        for tool in tools:
            if tool.name in [existing.name for existing in agent.tools]:
                agent.remove_tool(tool.name)
            agent.add_tool(tool)
            attached.append(tool.name)

    return attached


async def attach_workspace_runtime_tools(
    agent: Agent, workspace_id: str | None = None
) -> dict[str, list[str]]:
    """Attach workspace skills, MCP tools, and connector tools to an Agent runtime."""
    target_workspace = workspace_id or getattr(agent, "workspace_id", None)
    if not target_workspace:
        return {"skills": [], "mcp": [], "connectors": []}

    from cognix.mcp.adapter import attach_workspace_mcp_tools

    skill_tools = attach_workspace_skills(agent, target_workspace)
    try:
        mcp_tools = await attach_workspace_mcp_tools(agent, target_workspace)
    except FileNotFoundError:
        mcp_tools = []
    try:
        connector_tools = await attach_workspace_connector_tools(agent, target_workspace)
    except Exception:
        connector_tools = []
    return {"skills": skill_tools, "mcp": mcp_tools, "connectors": connector_tools}
