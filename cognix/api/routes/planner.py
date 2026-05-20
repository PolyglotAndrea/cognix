"""Planner REST routes — intent-to-plan lifecycle."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cognix.api.state import event_bus
from cognix.auth.dependencies import CurrentUser, require_agents_write
from cognix.core.events import Events
from cognix.orchestrator.protocol import (
    register_orchestration_listener,
    unregister_orchestration_listener,
)

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
    from cognix.billing.entitlement import EntitlementService
    from cognix.local.workspace import WorkspaceManager
    from cognix.planner.service import PlannerService

    entitlement = await EntitlementService.check_model_execution(user.id, workspace_id)
    if not entitlement.allowed:
        raise HTTPException(402, detail=entitlement.to_dict())

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


@router.post("/{workspace_id}/plans/{plan_id}/apply/stream")
async def apply_plan_stream(
    workspace_id: str,
    plan_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> StreamingResponse:
    """Apply a plan and stream execution progress using Server-Sent Events (SSE)."""
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

    queue = asyncio.Queue()
    active_agent_ids = set()

    def handle_orchestration_event(event):
        if event.plan_id == plan_id or event.run_id == plan_id:
            if event.type == "agent.created" and event.agent_id:
                active_agent_ids.add(event.agent_id)

            queue.put_nowait({
                "type": event.type,
                "stage": event.stage,
                "status": event.status,
                "agent_id": event.agent_id,
                "task_id": event.task_id,
                "artifact_id": event.artifact_id,
                "data": event.data,
                "timestamp": event.timestamp,
            })

    async def handle_event_bus(event: str, **kwargs):
        agent_id = kwargs.get("agent_id")
        if agent_id and agent_id in active_agent_ids:
            if event == Events.TOOL_CALLED:
                queue.put_nowait({
                    "type": "tool_call",
                    "status": "running",
                    "agent_id": agent_id,
                    "tool": kwargs.get("tool"),
                    "arguments": kwargs.get("arguments"),
                })
            elif event == Events.TOOL_RESULT:
                queue.put_nowait({
                    "type": "tool_result",
                    "status": "completed",
                    "agent_id": agent_id,
                    "tool": kwargs.get("tool"),
                    "result": kwargs.get("result"),
                })
            elif event == Events.TOOL_ERROR:
                queue.put_nowait({
                    "type": "tool_error",
                    "status": "failed",
                    "agent_id": agent_id,
                    "tool": kwargs.get("tool"),
                    "error": kwargs.get("error"),
                })

    register_orchestration_listener(handle_orchestration_event)
    event_bus.on(Events.TOOL_CALLED, handle_event_bus)
    event_bus.on(Events.TOOL_RESULT, handle_event_bus)
    event_bus.on(Events.TOOL_ERROR, handle_event_bus)

    async def run_apply():
        try:
            result = await service.apply_plan(workspace_id, plan_id, user.id)
            queue.put_nowait({
                "type": "execution.completed",
                "status": "completed",
                "result": result,
            })
        except Exception as exc:
            queue.put_nowait({
                "type": "execution.failed",
                "status": "failed",
                "error": str(exc),
            })

    apply_task = asyncio.create_task(run_apply())

    async def sse_generator():
        try:
            while not apply_task.done() or not queue.empty():
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                    queue.task_done()
                except TimeoutError:
                    continue
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        finally:
            unregister_orchestration_listener(handle_orchestration_event)
            event_bus.off(Events.TOOL_CALLED, handle_event_bus)
            event_bus.off(Events.TOOL_RESULT, handle_event_bus)
            event_bus.off(Events.TOOL_ERROR, handle_event_bus)
            if not apply_task.done():
                apply_task.cancel()

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
