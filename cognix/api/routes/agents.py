"""Agent REST and streaming routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from cognix.api.security import authenticate_websocket
from cognix.api.state import agent_registry, get_agent_runtime
from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    name: str
    model: str = "gpt-4o"
    system_prompt: str = "You are a helpful assistant."
    description: str = ""
    temperature: float = 0.7
    max_iterations: int = 10
    api_base: str | None = None


class ChatRequest(BaseModel):
    message: str


@router.get("")
async def list_agents(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return agent_registry.list_all()


@router.post("", status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.core.agent import Agent
    from cognix.core.memory import SQLiteBackend
    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    agent = Agent(
        name=body.name,
        model=body.model,
        system_prompt=body.system_prompt,
        description=body.description,
        temperature=body.temperature,
        max_iterations=body.max_iterations,
        api_base=body.api_base,
    )
    agent.memory = SQLiteBackend(agent_id=agent.id)
    agent_registry.register(agent)

    async with get_session() as session:
        db_agent = AgentModel(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            model=agent.model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            max_iterations=agent.max_iterations,
            api_base=body.api_base,
        )
        session.add(db_agent)

    return agent.to_dict()


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    agent = await get_agent_runtime(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent.to_dict()


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    agent = await get_agent_runtime(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    agent_registry.unregister(agent.id)

    from sqlalchemy import delete

    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    async with get_session() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent.id))

    return {"deleted": agent.id}


@router.post("/{agent_id}/chat")
async def agent_chat(
    agent_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    agent = await get_agent_runtime(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    response = await agent.run(body.message)
    return {"content": response.content, "usage": response.usage}


@router.post("/{agent_id}/chat/stream")
async def agent_chat_stream(
    agent_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """SSE endpoint using the stable AgentEvent protocol."""
    agent = await get_agent_runtime(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    async def event_generator():
        async for event in agent.stream_events(body.message):
            payload = {"type": event.type, **event.data}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{agent_id}/skills/{skill_name}")
async def attach_skill(
    agent_id: str,
    skill_name: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Attach all tools from an installed skill to a runtime agent."""
    from cognix.config import get_settings
    from cognix.skills.adapter import skill_to_core_tools
    from cognix.skills.manager import SkillsManager

    agent = await get_agent_runtime(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    manager = SkillsManager(local_dir=get_settings().skills.local_dir)
    skill = manager.load(skill_name)
    if not skill:
        raise HTTPException(404, "Skill not found")

    attached = []
    for tool in skill_to_core_tools(skill):
        if tool.name in [existing.name for existing in agent.tools]:
            agent.remove_tool(tool.name)
        agent.add_tool(tool)
        attached.append(tool.name)

    return {"agent_id": agent.id, "skill": skill.name, "tools": attached}


@router.websocket("/{agent_id}/chat/ws")
async def agent_chat_ws(websocket: WebSocket, agent_id: str) -> None:
    """Authenticated WebSocket endpoint for agent chat with event streaming."""
    try:
        await authenticate_websocket(websocket)
    except HTTPException as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": exc.detail})
        await websocket.close(code=1008)
        return

    await websocket.accept()

    agent = await get_agent_runtime(agent_id)
    if not agent:
        await websocket.send_json({"type": "error", "message": "Agent not found"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            async for event in agent.stream_events(message):
                await websocket.send_json({"type": event.type, **event.data})
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()
