"""Local-first workspace workflow storage."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.orchestrator.workflow import parse_workflow, validate_workflow


@dataclass(frozen=True)
class WorkspaceWorkflow:
    id: str
    name: str
    path: str
    description: str
    step_count: int
    updated_at: str
    errors: list[str]


class WorkspaceWorkflowStore:
    """Stores YAML workflow definitions under a workspace."""

    def __init__(self, workspace_id: str, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def workflows_dir(self) -> Path:
        return self.workspace_path / "tasks" / "workflows"

    def list_all(self) -> list[WorkspaceWorkflow]:
        workflows = []
        for path in sorted(self.workflows_dir.glob("*.y*ml")):
            workflows.append(self.describe(path.stem))
        return sorted(workflows, key=lambda item: item.updated_at, reverse=True)

    def save(
        self,
        *,
        name: str,
        definition: str,
        workflow_id: str | None = None,
    ) -> WorkspaceWorkflow:
        workflow_id = workflow_id or self._slug(name)
        path = self._workflow_path(workflow_id)
        path.write_text(definition.rstrip() + "\n", encoding="utf-8")
        return self.describe(workflow_id)

    def get_definition(self, workflow_id: str) -> str:
        path = self._workflow_path(workflow_id)
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")
        return path.read_text(encoding="utf-8")

    def describe(self, workflow_id: str) -> WorkspaceWorkflow:
        path = self._workflow_path(workflow_id)
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")

        errors = validate_workflow(path)
        name = workflow_id
        description = ""
        step_count = 0
        if not errors:
            workflow = parse_workflow(path)
            name = workflow.name
            description = workflow.description
            step_count = len(workflow.steps)

        return WorkspaceWorkflow(
            id=workflow_id,
            name=name,
            path=str(path),
            description=description,
            step_count=step_count,
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            errors=errors,
        )

    def delete(self, workflow_id: str) -> bool:
        path = self._workflow_path(workflow_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def to_dict(self, workflow: WorkspaceWorkflow) -> dict:
        return asdict(workflow)

    def _workflow_path(self, workflow_id: str) -> Path:
        return self.workflows_dir / f"{workflow_id}.yaml"

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "workflow"
