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
        enabled_skills = WorkspaceConfigStore(workspace_id).get_settings().get(
            "enabled_skills",
            [],
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


async def attach_workspace_runtime_tools(agent: Agent, workspace_id: str | None = None) -> dict[str, list[str]]:
    """Attach workspace skills and MCP tools to an Agent runtime."""
    target_workspace = workspace_id or getattr(agent, "workspace_id", None)
    if not target_workspace:
        return {"skills": [], "mcp": []}

    from cognix.mcp.adapter import attach_workspace_mcp_tools

    skill_tools = attach_workspace_skills(agent, target_workspace)
    try:
        mcp_tools = await attach_workspace_mcp_tools(agent, target_workspace)
    except FileNotFoundError:
        mcp_tools = []
    return {"skills": skill_tools, "mcp": mcp_tools}
