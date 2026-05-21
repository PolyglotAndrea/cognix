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


class ApprovalSuggestion(BaseModel):
    approval_id: str
    response: str
    reason: str
    score: float
    created_at: str
    source: str = "approval_history"


@router.get("")
async def list_approvals(
    workspace_id: str | None = None,
    chat_id: str | None = None,
    status: ApprovalStatus | None = None,
    include_resolved: bool = False,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = ApprovalStore()
    store.complete_capability_blocked_questions(workspace_id=workspace_id)
    approvals = store.list_all(
        workspace_id=workspace_id,
        status=status,
        include_resolved=include_resolved,
    )
    if chat_id:
        approvals = [
            approval
            for approval in approvals
            if str(approval.metadata.get("chat_id") or "") == chat_id
        ]
    return [approval.__dict__ for approval in approvals]


@router.get("/{approval_id}/suggestions")
async def approval_suggestions(
    approval_id: str,
    limit: int = 5,
    history_limit: int = 100,
    user: CurrentUser = Depends(get_current_user),
) -> list[ApprovalSuggestion]:
    """Return reusable answer suggestions from recent similar approval history."""
    store = ApprovalStore()
    current = store.get(approval_id)
    if not current:
        raise HTTPException(404, "Approval not found")

    current_text = _approval_text(current)
    current_tokens = _tokens(current_text)
    rows = store.list_all(
        workspace_id=current.workspace_id,
        include_resolved=True,
    )
    recent_rows = rows[: max(1, min(history_limit, 100))]
    suggestions: list[ApprovalSuggestion] = []
    seen: set[str] = set()
    for item in recent_rows:
        if item.id == current.id:
            continue
        if item.kind != "question":
            continue
        if item.status == "pending":
            continue
        response = item.response.strip()
        if not response or response in seen:
            continue
        seen.add(response)
        score = _approval_similarity(
            current_tokens=current_tokens,
            current=current,
            candidate=item,
        )
        if score <= 0:
            continue
        suggestions.append(
            ApprovalSuggestion(
                approval_id=item.id,
                response=response,
                reason=_approval_text(item)[:500],
                score=round(score, 4),
                created_at=item.created_at,
            )
        )
    suggestions.sort(key=lambda row: row.score, reverse=True)
    return suggestions[: max(1, min(limit, 10))]


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

    if approval.metadata.get("source") == "plan_apply":
        from cognix.planner.service import PlannerService

        try:
            result = await PlannerService().resume_plan_approval(
                approval_id,
                user.id,
                response=body.response if body else "",
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "approval_id": approval_id,
            "runtime": "planner",
            "content": result.get("execution_results", [{}])[0].get("result", ""),
            "events": [{"type": "execution.completed", "data": result}],
            **result,
        }

    # Claude Agent SDK path — delegate to runtime's resume_stream
    if approval.metadata.get("runtime") == "claude-agent-sdk":
        from cognix.claude.runtime import ClaudeAgentRuntime

        events: list[dict] = []
        final_content = ""
        try:
            async for event in ClaudeAgentRuntime().resume_stream(
                approval_id,
                response=body.response if body else "",
            ):
                events.append({"type": event.type, "data": event.data})
                if event.type == "delta":
                    final_content += event.data.get("delta", "")
                if event.type == "error":
                    raise ValueError(event.data.get("message", "Unknown error"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "approval_id": approval_id,
            "runtime": "claude-agent-sdk",
            "content": final_content,
            "events": events,
        }

    # Hermes Agent path
    agent = await get_agent_runtime(approval.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    events = []
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
        "runtime": "hermes-agent",
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

    if approval.metadata.get("source") == "plan_apply":

        async def planner_event_generator():
            try:
                from cognix.planner.service import PlannerService

                yield encode_sse_event(
                    AgentEvent(
                        "approval_resumed",
                        {"approval_id": approval_id, "runtime": "planner"},
                    )
                )
                result = await PlannerService().resume_plan_approval(
                    approval_id,
                    user.id,
                    response=body.response if body else "",
                )
                yield encode_sse_event(
                    AgentEvent(
                        "execution.completed",
                        {
                            "result": result,
                            "approval_id": approval_id,
                            "runtime": "planner",
                        },
                    )
                )
            except FileNotFoundError as exc:
                yield encode_sse_event(
                    AgentEvent("error", {"message": str(exc), "error": str(exc)})
                )
            except ValueError as exc:
                yield encode_sse_event(
                    AgentEvent("error", {"message": str(exc), "error": str(exc)})
                )

        return StreamingResponse(planner_event_generator(), media_type="text/event-stream")

    is_sdk = approval.metadata.get("runtime") == "claude-agent-sdk"

    async def event_generator():
        try:
            if is_sdk:
                from cognix.claude.runtime import ClaudeAgentRuntime

                async for event in ClaudeAgentRuntime().resume_stream(
                    approval_id,
                    response=body.response if body else "",
                ):
                    yield encode_sse_event(event, extra={"runtime": "claude-agent-sdk"})
            else:
                agent = await get_agent_runtime(approval.agent_id)
                if not agent:
                    yield encode_sse_event(
                        AgentEvent(
                            "error",
                            {"message": "Agent not found", "error": "Agent not found"},
                        )
                    )
                    return
                async for event in agent.resume_and_continue(approval_id):
                    yield encode_sse_event(event)
        except ValueError as exc:
            yield encode_sse_event(AgentEvent("error", {"message": str(exc), "error": str(exc)}))

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _approval_text(approval) -> str:
    return (
        approval.reason
        or str(approval.arguments.get("question") or approval.metadata.get("question") or "")
        or approval.tool_name
        or ""
    )


def _tokens(text: str) -> set[str]:
    import re

    return {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", text)
        if len(token.strip()) > 1
    }


def _approval_similarity(*, current_tokens: set[str], current, candidate) -> float:
    candidate_tokens = _tokens(_approval_text(candidate))
    score = 0.0
    if current.tool_name and candidate.tool_name == current.tool_name:
        score += 3.0
    if current.metadata.get("source") and candidate.metadata.get("source") == current.metadata.get(
        "source"
    ):
        score += 2.0
    if current.kind == candidate.kind:
        score += 1.0
    if current_tokens and candidate_tokens:
        overlap = len(current_tokens & candidate_tokens)
        union = len(current_tokens | candidate_tokens)
        score += (overlap / union) * 10
    if "目标入口" in candidate.response or "登录方式" in candidate.response:
        score += 1.0
    return score


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
