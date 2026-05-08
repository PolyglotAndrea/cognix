"""Skills manager for loading, installing, and managing skills."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from cognix.skills.loader import SkillInfo, load_skill

logger = logging.getLogger(__name__)


class SkillsManager:
    """Manages local and remote skills."""

    def __init__(self, local_dir: Path | str | None = None) -> None:
        if local_dir is None:
            local_dir = Path.home() / ".cognix" / "skills"
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[str, SkillInfo] = {}

    def discover(self) -> list[SkillInfo]:
        """Discover all skills in the local directory."""
        skills = []
        for skill_dir in self.local_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "skill.yaml").exists():
                try:
                    skill = load_skill(skill_dir)
                    skills.append(skill)
                except Exception as e:
                    logger.warning("Failed to load skill from %s: %s", skill_dir, e)
        return skills

    def load(self, name: str) -> SkillInfo | None:
        """Load a skill by name."""
        if name in self._loaded:
            return self._loaded[name]

        skill_dir = self.local_dir / name
        if not skill_dir.exists():
            return None

        try:
            skill = load_skill(skill_dir)
            self._loaded[name] = skill
            return skill
        except Exception as e:
            logger.error("Failed to load skill '%s': %s", name, e)
            return None

    def unload(self, name: str) -> bool:
        """Unload a skill from memory."""
        if name in self._loaded:
            del self._loaded[name]
            return True
        return False

    def reload(self, name: str) -> SkillInfo | None:
        """Reload a skill (hot-reload)."""
        self.unload(name)
        return self.load(name)

    def list_installed(self) -> list[dict[str, Any]]:
        """List all installed skills."""
        skills = self.discover()
        return [
            {
                "name": s.name,
                "version": s.version,
                "description": s.description,
                "author": s.author,
                "tags": ",".join(s.tags) if isinstance(s.tags, list) else s.tags,
                "tools": [t.name for t in s.tools],
            }
            for s in skills
        ]

    def install(self, source_dir: Path, name: str | None = None) -> SkillInfo:
        """Install a skill from a source directory."""
        manifest_path = source_dir / "skill.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No skill.yaml in {source_dir}")

        import yaml

        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        skill_name = name or manifest.get("name", source_dir.name)
        dest = self.local_dir / skill_name

        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(source_dir, dest)
        logger.info("Installed skill '%s' to %s", skill_name, dest)

        return load_skill(dest)

    def create_scaffold(
        self,
        name: str,
        *,
        description: str = "",
        author: str = "you",
        overwrite: bool = False,
    ) -> SkillInfo:
        """Create a new local skill scaffold."""
        if Path(name).name != name:
            raise ValueError("Skill name must not contain path separators")

        skill_dir = self.local_dir / name
        if skill_dir.exists():
            if not overwrite:
                raise FileExistsError(f"Skill '{name}' already exists")
            shutil.rmtree(skill_dir)

        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_description = description or f"TODO: describe {name}"

        import yaml

        manifest = {
            "name": name,
            "version": "0.1.0",
            "description": skill_description,
            "author": author,
            "tags": [],
            "runtime": {
                "python": ">=3.11",
                "entrypoint": "handler.py",
            },
            "tools": [
                {
                    "name": name,
                    "description": "TODO",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                }
            ],
        }
        (skill_dir / "skill.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False)
        )
        (skill_dir / "handler.py").write_text(
            '"""Skill handler."""\n'
            "\n"
            "async def run(**params) -> str:\n"
            '    """Entry point for the skill."""\n'
            f'    return "Hello from {name}"\n'
        )

        return load_skill(skill_dir)

    def uninstall(self, name: str) -> bool:
        """Uninstall a skill."""
        skill_dir = self.local_dir / name
        if not skill_dir.exists():
            return False

        self.unload(name)
        shutil.rmtree(skill_dir)
        logger.info("Uninstalled skill '%s'", name)
        return True

    def get_skill_tools(self, name: str) -> list[dict[str, Any]]:
        """Get tools defined by a skill as dict format."""
        skill = self.load(name)
        if not skill:
            return []

        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "access_level": t.access_level,
            }
            for t in skill.tools
        ]
