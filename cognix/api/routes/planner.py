"""Planner REST routes — intent-to-plan lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cognix.auth.dependencies import CurrentUser, require_agents_write

router = APIRouter(prefix="/api/v1/workspaces", tags=["planner"])


class CreatePlanRequest(BaseModel):
    intent: str


class PlanActionRequest(BaseModel):
    pass


@router.post("/{workspace_id}/plans", status_code=201)
async def create_plan(
    workspace_id: str,
    body: CreatePlanRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Generate a structured plan from user intent."""
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    service = PlannerService()
    plan = await service.create_plan(workspace_id, body.intent, user.id)
    return plan.to_dict()


@router.get("/{workspace_id}/plans")
async def list_plans(
    workspace_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> list[dict]:
    """List all plans for a workspace."""
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    return PlannerService().list_plans(workspace_id)


@router.get("/{workspace_id}/plans/{plan_id}")
async def get_plan(
    workspace_id: str,
    plan_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Get plan detail."""
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    plan = PlannerService().get_plan(workspace_id, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan.to_dict()


@router.post("/{workspace_id}/plans/{plan_id}/apply")
async def apply_plan(
    workspace_id: str,
    plan_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Apply a confirmed plan — creates agents, tasks, skills, etc."""
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    service = PlannerService()
    plan = service.get_plan(workspace_id, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Auto-confirm if still proposed
    if plan.status == "proposed":
        service.confirm_plan(workspace_id, plan_id)

    try:
        result = await service.apply_plan(workspace_id, plan_id, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return result


@router.post("/{workspace_id}/plans/{plan_id}/reject")
async def reject_plan(
    workspace_id: str,
    plan_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Reject a proposed plan."""
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    try:
        result = PlannerService().reject_plan(workspace_id, plan_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return result
