"""Workspace-scoped code project sandbox and preview runner."""

from __future__ import annotations

import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


@dataclass(frozen=True)
class CodeProject:
    id: str
    name: str
    description: str = ""
    status: str = "created"
    preview_url: str = ""
    port: int | None = None
    pid: int | None = None
    start_command: str = ""
    path: str = ""
    last_error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class CodeSandboxStore:
    """Manage generated code projects under a workspace sandbox directory."""

    def __init__(self, workspace_id: str, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        if not self.projects_file.exists():
            self._write([])

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def sandbox_dir(self) -> Path:
        return self.workspace_path / "sandbox"

    @property
    def projects_dir(self) -> Path:
        return self.sandbox_dir / "projects"

    @property
    def projects_file(self) -> Path:
        return self.sandbox_dir / "projects.json"

    def create_project(
        self,
        *,
        name: str,
        files: list[dict[str, str]],
        description: str = "",
        start_command: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CodeProject:
        project_id = uuid.uuid4().hex[:12]
        project_dir = self.projects_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        if not files:
            files = [
                {
                    "path": "index.html",
                    "content": (
                        "<!doctype html><html><head><meta charset='utf-8'>"
                        f"<title>{name}</title></head><body><h1>{name}</h1></body></html>"
                    ),
                }
            ]

        for item in files:
            self._write_project_file(project_dir, item.get("path", ""), item.get("content", ""))

        now = datetime.now(UTC).isoformat()
        project = CodeProject(
            id=project_id,
            name=name,
            description=description,
            start_command=start_command,
            path=str(project_dir),
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        projects = self.list_all(include_stale=True)
        projects.append(project)
        self._write(projects)
        return project

    def list_all(self, *, include_stale: bool = False) -> list[CodeProject]:
        rows = json.loads(self.projects_file.read_text(encoding="utf-8") or "[]")
        projects = [CodeProject(**row) for row in rows if isinstance(row, dict)]
        if include_stale:
            return projects
        refreshed = [self._refresh_status(project) for project in projects]
        if refreshed != projects:
            self._write(refreshed)
        return refreshed

    def get(self, project_id: str) -> CodeProject | None:
        return next((project for project in self.list_all() if project.id == project_id), None)

    async def start_project(self, project_id: str, *, command: str = "") -> CodeProject:
        project = self.get(project_id)
        if not project:
            raise FileNotFoundError(f"Code project not found: {project_id}")
        if project.pid and _pid_alive(project.pid):
            return project

        project_dir = Path(project.path)
        port = _find_port(project.port or 4300)
        argv, command_text = self._command(project_dir, command or project.start_command, port)
        log_path = project_dir / ".cognix-run.log"
        log_file = log_path.open("ab")
        try:
            process = subprocess.Popen(
                argv,
                cwd=project_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PORT": str(port), "HOST": "127.0.0.1"},
                start_new_session=True,
            )
        except Exception as exc:
            log_file.close()
            return self._update(
                project_id,
                status="failed",
                last_error=str(exc),
                updated_at=datetime.now(UTC).isoformat(),
            )
        log_file.close()
        return self._update(
            project_id,
            status="running",
            pid=process.pid,
            port=port,
            preview_url=f"http://127.0.0.1:{port}",
            start_command=command_text,
            last_error="",
            updated_at=datetime.now(UTC).isoformat(),
        )

    def stop_project(self, project_id: str) -> CodeProject:
        project = self.get(project_id)
        if not project:
            raise FileNotFoundError(f"Code project not found: {project_id}")
        if project.pid and _pid_alive(project.pid):
            try:
                os.killpg(project.pid, signal.SIGTERM)
            except Exception:
                try:
                    os.kill(project.pid, signal.SIGTERM)
                except Exception:
                    pass
        return self._update(
            project_id,
            status="stopped",
            pid=None,
            preview_url="",
            updated_at=datetime.now(UTC).isoformat(),
        )

    def logs(self, project_id: str, *, max_bytes: int = 20000) -> str:
        project = self.get(project_id)
        if not project:
            raise FileNotFoundError(f"Code project not found: {project_id}")
        path = Path(project.path) / ".cognix-run.log"
        if not path.exists():
            return ""
        return path.read_bytes()[-max_bytes:].decode("utf-8", errors="replace")

    def _write_project_file(self, project_dir: Path, relative_path: str, content: str) -> None:
        if not relative_path or Path(relative_path).is_absolute():
            raise ValueError("Project file path must be relative")
        target = (project_dir / relative_path).resolve()
        root = project_dir.resolve()
        if target != root and root not in target.parents:
            raise ValueError("Project file path escapes project directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _command(self, project_dir: Path, command: str, port: int) -> tuple[list[str], str]:
        package_json = project_dir / "package.json"
        if command:
            argv = shlex.split(command)
            if not argv or argv[0] not in {"npm", "node", "python", "python3", sys.executable}:
                raise ValueError("Only npm, node, or python preview commands are allowed")
            return argv, command
        if package_json.exists():
            return (
                ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port)],
                f"npm run dev -- --host 127.0.0.1 --port {port}",
            )
        return (
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            f"{sys.executable} -m http.server {port} --bind 127.0.0.1",
        )

    def _refresh_status(self, project: CodeProject) -> CodeProject:
        if project.status == "running" and project.pid and not _pid_alive(project.pid):
            return CodeProject(
                **{
                    **asdict(project),
                    "status": "stopped",
                    "pid": None,
                    "preview_url": "",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
        return project

    def _update(self, project_id: str, **changes: Any) -> CodeProject:
        projects = self.list_all(include_stale=True)
        updated: CodeProject | None = None
        next_projects = []
        for project in projects:
            if project.id == project_id:
                updated = CodeProject(**{**asdict(project), **changes})
                next_projects.append(updated)
            else:
                next_projects.append(project)
        if not updated:
            raise FileNotFoundError(f"Code project not found: {project_id}")
        self._write(next_projects)
        return updated

    def _write(self, projects: list[CodeProject]) -> None:
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.projects_file.write_text(
            json.dumps([asdict(project) for project in projects], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def to_dict(project: CodeProject) -> dict[str, Any]:
        return asdict(project)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _find_port(start: int) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available preview port found")
