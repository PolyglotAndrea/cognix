"""Plan schema definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    """A single step in a workspace plan."""

    id: str
    action: str  # "create_agent", "create_task", "install_skill", "configure_mcp", etc.
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "description": self.description,
            "params": self.params,
            "depends_on": self.depends_on,
        }


@dataclass
class WorkspacePlan:
    """A structured execution plan generated from user intent."""

    id: str
    workspace_id: str
    summary: str
    steps: list[PlanStep] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    required_connectors: list[str] = field(default_factory=list)
    sandbox_permissions: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    estimated_cost: str = "unknown"
    status: str = "proposed"  # proposed, confirmed, rejected, applied
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "summary": self.summary,
            "steps": [s.to_dict() for s in self.steps],
            "required_skills": self.required_skills,
            "required_connectors": self.required_connectors,
            "sandbox_permissions": self.sandbox_permissions,
            "expected_artifacts": self.expected_artifacts,
            "estimated_cost": self.estimated_cost,
            "status": self.status,
            "created_at": self.created_at,
        }
