"""Adapters between package skills and core Agent tools."""

from __future__ import annotations

import inspect
from typing import Any

from cognix.core.tool import Tool
from cognix.skills.loader import SkillInfo, SkillTool


def skill_tool_to_core_tool(skill: SkillInfo, skill_tool: SkillTool) -> Tool:
    """Convert a loaded skill tool into a core runtime Tool."""
    handler = skill_tool.handler
    if handler is None:
        raise ValueError(f"Skill '{skill.name}' tool '{skill_tool.name}' has no handler")

    async def _handler(**kwargs: Any) -> Any:
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    return Tool(
        name=skill_tool.name,
        description=skill_tool.description,
        handler=_handler,
        parameters=skill_tool.parameters,
    )


def skill_to_core_tools(skill: SkillInfo) -> list[Tool]:
    """Convert all tools from a loaded skill to core runtime tools."""
    return [skill_tool_to_core_tool(skill, tool) for tool in skill.tools]
