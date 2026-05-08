"""Workspace file storage and preview helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from cognix.core.permissions import ensure_permission
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


@dataclass(frozen=True)
class WorkspaceFile:
    path: str
    name: str
    kind: str
    size: int
    updated_at: str


class WorkspaceFileStore:
    """Safely read and write files under a workspace's files directory."""

    def __init__(
        self,
        workspace_id: str,
        *,
        home: CognixHome | None = None,
        permission_mode: str = "workspace-write",
    ) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.permission_mode = permission_mode
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.files_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def files_dir(self) -> Path:
        return self.workspace_path / "files"

    def list(self, relative_dir: str = "") -> list[WorkspaceFile]:
        directory = self.resolve(relative_dir)
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"Directory not found: {relative_dir}")
        items = []
        for path in sorted(
            directory.iterdir(),
            key=lambda item: (item.is_file(), item.name.lower()),
        ):
            stat = path.stat()
            items.append(
                WorkspaceFile(
                    path=self.relative(path),
                    name=path.name,
                    kind="directory" if path.is_dir() else "file",
                    size=0 if path.is_dir() else stat.st_size,
                    updated_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                )
            )
        return items

    def read_text(self, relative_path: str, *, max_bytes: int = 200_000) -> str:
        ensure_permission(self.permission_mode, "read", f"read workspace file {relative_path}")
        path = self.resolve(relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        raw = path.read_bytes()[:max_bytes]
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def write_text(self, relative_path: str, content: str) -> WorkspaceFile:
        ensure_permission(self.permission_mode, "write", f"write workspace file {relative_path}")
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self.describe(path)

    def delete(self, relative_path: str) -> bool:
        ensure_permission(self.permission_mode, "write", f"delete workspace file {relative_path}")
        path = self.resolve(relative_path)
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True

    def describe(self, path: Path) -> WorkspaceFile:
        stat = path.stat()
        return WorkspaceFile(
            path=self.relative(path),
            name=path.name,
            kind="directory" if path.is_dir() else "file",
            size=0 if path.is_dir() else stat.st_size,
            updated_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        )

    def resolve(self, relative_path: str) -> Path:
        target = (self.files_dir / relative_path).resolve()
        root = self.files_dir.resolve()
        if target != root and root not in target.parents:
            raise ValueError("Path escapes workspace files directory")
        return target

    def relative(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.files_dir.resolve()))

    @staticmethod
    def to_dict(item: WorkspaceFile) -> dict:
        return asdict(item)
