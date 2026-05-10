"""Local-first Cognix home directory management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cognix.config import get_settings

DEFAULT_USER_MD = """# User

Add stable user facts here.
"""

DEFAULT_MEMORY_MD = """# Cognix Memory

Add stable global context and current state here.
"""

DEFAULT_DEEP_MEMORY_MD = """# Deep User Model

Add durable user preferences, working style, and long-term behavioral notes here.
"""


@dataclass(frozen=True)
class CognixHome:
    """Represents the local-first Cognix home rooted at ``~/.cognix`` by default."""

    root: Path

    @classmethod
    def default(cls) -> CognixHome:
        """Resolve the home directory from COGNIX_HOME or settings.data_dir."""
        override = os.environ.get("COGNIX_HOME")
        root = Path(override).expanduser() if override else get_settings().data_dir
        return cls(root=root.expanduser())

    @property
    def user_file(self) -> Path:
        return self.root / "USER.md"

    @property
    def memory_file(self) -> Path:
        return self.root / "MEMORY.md"

    @property
    def deep_memory_file(self) -> Path:
        return self.root / "memory" / "DEEP_MEMORY.md"

    @property
    def state_db(self) -> Path:
        return self.root / "state.db"

    @property
    def events_file(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def workspaces_dir(self) -> Path:
        return self.root / "workspaces"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    def ensure(self) -> CognixHome:
        """Create the standard local-first directory layout if needed."""
        self.root.mkdir(parents=True, exist_ok=True)
        for dirname in (
            "workspaces",
            "skills",
            "mcp",
            "bots",
            "memory",
            "runtime",
            "approvals",
            "logs",
            "cache",
        ):
            (self.root / dirname).mkdir(parents=True, exist_ok=True)

        self._write_default(self.user_file, DEFAULT_USER_MD)
        self._write_default(self.memory_file, DEFAULT_MEMORY_MD)
        self._write_default(self.deep_memory_file, DEFAULT_DEEP_MEMORY_MD)
        self.events_file.touch(exist_ok=True)
        return self

    @staticmethod
    def _write_default(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content, encoding="utf-8")
