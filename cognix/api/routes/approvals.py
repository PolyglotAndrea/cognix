"""Human-in-the-loop approval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from cognix.api.state import get_agent_runtime
from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.core.agent import AgentEvent
from cognix.core.streaming import encode_sse_event
from cognix.local.approvals import ApprovalStatus, ApprovalStore

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class ApprovalResponseBody(BaseModel):
    response: str = ""


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


@router.post("/{approval_id}/respond")
async def respond_request(
    approval_id: str,
    body: ApprovalResponseBody,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    approval = ApprovalStore().respond(approval_id, body.response)
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
    body: ApprovalResponseBody | None = None,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    if body and body.response:
        ApprovalStore().respond(approval_id, body.response)
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


@router.post("/{approval_id}/resume-and-continue")
async def resume_and_continue(
    approval_id: str,
    body: ApprovalResponseBody | None = None,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Resume after approval and continue the full LLM loop to completion."""
    if body and body.response:
        ApprovalStore().respond(approval_id, body.response)
    approval = ApprovalStore().get(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")

    agent = await get_agent_runtime(approval.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    events: list[dict] = []
    final_content = ""
    try:
        async for event in agent.resume_and_continue(approval_id):
            events.append({"type": event.type, "data": event.data})
            if event.type == "delta":
                final_content += event.data.get("delta", "")
            if event.type == "error":
                raise ValueError(event.data.get("message", "Unknown error"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "approval_id": approval_id,
        "content": final_content,
        "events": events,
    }


@router.post("/{approval_id}/resume-and-continue/stream")
async def resume_and_continue_stream(
    approval_id: str,
    body: ApprovalResponseBody | None = None,
    user: CurrentUser = Depends(require_agents_write),
) -> StreamingResponse:
    """Stream events after approval — agent continues its full LLM loop."""
    if body and body.response:
        ApprovalStore().respond(approval_id, body.response)
    approval = ApprovalStore().get(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")

    agent = await get_agent_runtime(approval.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    async def event_generator():
        try:
            async for event in agent.resume_and_continue(approval_id):
                yield encode_sse_event(event)
        except ValueError as exc:
            yield encode_sse_event(
                AgentEvent("error", {"message": str(exc), "error": str(exc)})
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{approval_id}/resume/stream")
async def resume_approval_stream(
    approval_id: str,
    body: ApprovalResponseBody | None = None,
    user: CurrentUser = Depends(require_agents_write),
) -> StreamingResponse:
    approval = ApprovalStore().get(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    if approval.metadata.get("runtime") != "claude-agent-sdk":
        raise HTTPException(
            400,
            "Streaming resume is only available for Claude Agent SDK approvals",
        )

    async def event_generator():
        from cognix.claude.runtime import ClaudeAgentRuntime

        async for event in ClaudeAgentRuntime().resume_stream(
            approval_id,
            response=body.response if body else "",
        ):
            yield encode_sse_event(event, extra={"runtime": "claude-agent-sdk"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
