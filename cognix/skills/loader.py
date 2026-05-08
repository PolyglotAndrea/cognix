"""Skill loader for loading skills from local directory."""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillTool:
    """A tool defined by a skill."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Any = None
    access_level: str = "read"


@dataclass
class SkillInfo:
    """Metadata about a skill."""

    name: str
    version: str
    description: str
    author: str
    tags: list[str]
    path: Path
    tools: list[SkillTool] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


def load_skill_manifest(skill_dir: Path) -> dict[str, Any]:
    """Load and validate a skill.yaml manifest."""
    manifest_path = skill_dir / "skill.yaml"
    if not manifest_path.exists():
        manifest_path = skill_dir / "skill.yml"

    if not manifest_path.exists():
        raise FileNotFoundError(f"No skill.yaml found in {skill_dir}")

    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid skill manifest: expected dict, got {type(data)}")

    required = ["name", "version"]
    for key in required:
        if key not in data:
            raise ValueError(f"Skill manifest missing required field: {key}")

    return data


def load_skill_handler(skill_dir: Path, entrypoint: str = "handler.py") -> Any:
    """Load the skill's Python handler module."""
    handler_path = skill_dir / entrypoint
    if not handler_path.exists():
        raise FileNotFoundError(f"Handler not found: {handler_path}")

    module_name = f"cognix_skill_{skill_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Failed to load module spec for {handler_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


def load_skill(skill_dir: Path) -> SkillInfo:
    """Load a skill from a directory."""
    manifest = load_skill_manifest(skill_dir)

    # Load handler module
    runtime = manifest.get("runtime", {})
    entrypoint = runtime.get("entrypoint", "handler.py")
    handler_module = load_skill_handler(skill_dir, entrypoint)

    # Parse tools
    tools = []
    for tool_def in manifest.get("tools", []):
        tool_name = tool_def.get("name", "")
        handler_func = getattr(handler_module, tool_name, None) or getattr(
            handler_module, "run", None
        )

        tools.append(
            SkillTool(
                name=tool_name,
                description=tool_def.get("description", ""),
                parameters=tool_def.get("parameters", {}),
                handler=handler_func,
                access_level=tool_def.get("access_level", tool_def.get("permission", "read")),
            )
        )

    # Parse config
    config = manifest.get("config", {})

    return SkillInfo(
        name=manifest["name"],
        version=manifest["version"],
        description=manifest.get("description", ""),
        author=manifest.get("author", ""),
        tags=manifest.get("tags", []),
        path=skill_dir,
        tools=tools,
        config=config,
    )
