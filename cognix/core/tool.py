"""Tool system for Agent capabilities."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class Tool:
    """A callable tool that an Agent can use."""

    name: str
    description: str
    handler: ToolHandler
    parameters: dict[str, Any] = field(default_factory=dict)

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with given parameters."""
        logger.debug("Executing tool %s with params %s", self.name, kwargs)
        return await self.handler(**kwargs)

    def to_openai_schema(self) -> dict[str, Any]:
        """Export as OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @classmethod
    def from_function(
        cls,
        func: ToolHandler,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> Tool:
        """Create a Tool from an async function, inferring metadata from signature."""
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip().split("\n")[0]

        if parameters is None:
            parameters = _infer_parameters(func)

        return cls(
            name=tool_name,
            description=tool_desc,
            handler=func,
            parameters=parameters,
        )


def _infer_parameters(func: Callable) -> dict[str, Any]:
    """Infer JSON Schema parameters from function signature."""
    sig = inspect.signature(func)
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            param_type = type_map.get(param.annotation, "string")

        prop: dict[str, Any] = {"type": param_type}
        if param.default != inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def tool(
    name: str | None = None,
    description: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> Callable[[ToolHandler], Tool]:
    """Decorator to create a Tool from an async function.

    Usage:
        @tool(name="search", description="Search the web")
        async def search_web(query: str) -> str:
            ...
    """

    def decorator(func: ToolHandler) -> Tool:
        return Tool.from_function(func, name=name, description=description, parameters=parameters)

    return decorator
