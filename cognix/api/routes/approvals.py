"""Human-in-the-loop approval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from cognix.api.state import get_agent_runtime
from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.local.approvals import ApprovalStatus, ApprovalStore

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("")
async def list_approvals(
    workspace_id: str | None = None,
    status: ApprovalStatus | None = None,
    include_resolved: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return [
        approval.__dict__
        for approval in ApprovalStore().list_all(
            workspace_id=workspace_id,
            status=status,
            include_resolved=include_resolved,
        )
    ]


@router.post("/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    approval = ApprovalStore().approve(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    return approval.__dict__


@router.post("/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    approval = ApprovalStore().reject(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    return approval.__dict__


@router.post("/{approval_id}/resume")
async def resume_approval(
    approval_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    approval = ApprovalStore().get(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")

    if approval.metadata.get("runtime") == "claude-agent-sdk":
        from cognix.claude.runtime import ClaudeAgentRuntime

        try:
            return await ClaudeAgentRuntime().resume_approval(approval_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    agent = await get_agent_runtime(approval.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    try:
        result = await agent.resume_approval(approval_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {"approval_id": approval_id, "result": result}
