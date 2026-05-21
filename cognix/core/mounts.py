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


def attach_browser_automation_tool(agent: Agent, workspace_id: str) -> list[str]:
    """Attach the internal browser automation tool to an Agent runtime."""
    from typing import Any

    from cognix.browser.service import BrowserAutomationRun, BrowserAutomationService
    from cognix.core.tool import Tool

    async def _handler(**kwargs: Any) -> Any:
        url = str(kwargs.get("url") or kwargs.get("target_url") or "")
        objective = str(kwargs.get("objective") or kwargs.get("task") or f"Browser task for {url}")
        if not url:
            raise ValueError("url is required")
        service = BrowserAutomationService(workspace_id)
        return await service.run(
            BrowserAutomationRun(
                objective=objective,
                url=url,
                engine=str(kwargs.get("engine") or "playwright"),  # type: ignore[arg-type]
                profile=str(kwargs.get("profile") or "default"),
                selectors=dict(kwargs.get("selectors") or {}),
                extract_text=bool(kwargs.get("extract_text", True)),
                extract_links=bool(kwargs.get("extract_links", True)),
                extract_tables=bool(kwargs.get("extract_tables", True)),
                screenshot=bool(kwargs.get("screenshot", True)),
                wait_for_selector=str(kwargs.get("wait_for_selector") or ""),
                cdp_endpoint=str(kwargs.get("cdp_endpoint") or ""),
                permission_mode=str(getattr(agent, "permission_mode", "workspace-write")),
                agent_id=str(getattr(agent, "id", "")),
            )
        )

    tool = Tool(
        name="browser_automation",
        description=(
            "Run an authorized browser automation workflow in the workspace browser profile. "
            "Use for page navigation, text/table extraction, screenshots, and browser artifacts."
        ),
        handler=_handler,
        parameters={
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "url": {"type": "string"},
                "engine": {
                    "type": "string",
                    "enum": ["playwright", "cdp", "browser_use"],
                },
                "profile": {"type": "string"},
                "cdp_endpoint": {"type": "string"},
                "selectors": {"type": "object"},
                "extract_text": {"type": "boolean"},
                "extract_links": {"type": "boolean"},
                "extract_tables": {"type": "boolean"},
                "screenshot": {"type": "boolean"},
                "wait_for_selector": {"type": "string"},
            },
            "required": ["url"],
        },
        access_level="write",
        metadata={"type": "browser_automation"},
    )
    if tool.name in [existing.name for existing in agent.tools]:
        agent.remove_tool(tool.name)
    agent.add_tool(tool)
    return [tool.name]


async def attach_workspace_runtime_tools(
    agent: Agent, workspace_id: str | None = None
) -> dict[str, list[str]]:
    """Attach workspace skills, MCP tools, and connector tools to an Agent runtime."""
    target_workspace = workspace_id or getattr(agent, "workspace_id", None)
    if not target_workspace:
        return {"skills": [], "mcp": [], "connectors": [], "browser": []}

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
    try:
        browser_tools = attach_browser_automation_tool(agent, target_workspace)
    except Exception:
        browser_tools = []
    return {
        "skills": skill_tools,
        "mcp": mcp_tools,
        "connectors": connector_tools,
        "browser": browser_tools,
    }
