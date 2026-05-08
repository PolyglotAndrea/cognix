"""Memory pipeline management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.memory.pipeline import ColdMemoryStore, ContextBuilder

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class UpdateHotMemoryRequest(BaseModel):
    user: str | None = None
    global_memory: str | None = None
    workspace_memory: str | None = None


class RememberRequest(BaseModel):
    content: str
    workspace_id: str | None = None
    scope: str = "global"
    kind: str = "message"
    summary: str = ""
    metadata: dict = Field(default_factory=dict)


class SearchMemoryRequest(BaseModel):
    query: str
    workspace_id: str | None = None
    limit: int = 10


class ContextPreviewRequest(BaseModel):
    message: str
    workspace_id: str | None = None
    include_skills: bool = True
    token_budget: int = 8000


@router.get("/hot")
async def get_hot_memory(
    workspace_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    home = CognixHome.default().ensure()
    hot = ContextBuilder(home).load_hot_memory(workspace_id=workspace_id)
    return {
        "user": hot.user,
        "global_memory": hot.global_memory,
        "workspace_memory": hot.workspace_memory,
    }


@router.patch("/hot")
async def update_hot_memory(
    body: UpdateHotMemoryRequest,
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    home = CognixHome.default().ensure()
    if body.user is not None:
        home.user_file.write_text(body.user, encoding="utf-8")
    if body.global_memory is not None:
        home.memory_file.write_text(body.global_memory, encoding="utf-8")
    if body.workspace_memory is not None:
        if not workspace_id:
            raise HTTPException(400, "workspace_id required for workspace memory")
        manager = WorkspaceManager(home)
        if not manager.get(workspace_id):
            raise HTTPException(404, "Workspace not found")
        (manager.workspace_path(workspace_id) / "MEMORY.md").write_text(
            body.workspace_memory,
            encoding="utf-8",
        )
    hot = ContextBuilder(home).load_hot_memory(workspace_id=workspace_id)
    return {
        "user": hot.user,
        "global_memory": hot.global_memory,
        "workspace_memory": hot.workspace_memory,
    }


@router.post("/remember", status_code=201)
async def remember(
    body: RememberRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    home = CognixHome.default().ensure()
    record = await ColdMemoryStore(home.state_db).remember(
        body.content,
        workspace_id=body.workspace_id,
        scope=body.scope,
        kind=body.kind,
        summary=body.summary,
        metadata=body.metadata,
    )
    return record.__dict__


@router.post("/search")
async def search_memory(
    body: SearchMemoryRequest,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    home = CognixHome.default().ensure()
    records = await ColdMemoryStore(home.state_db).search(
        body.query,
        workspace_id=body.workspace_id,
        limit=body.limit,
    )
    return [record.__dict__ for record in records]


@router.post("/context-preview")
async def context_preview(
    body: ContextPreviewRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    pack = await ContextBuilder().build(
        body.message,
        workspace_id=body.workspace_id,
        include_skills=body.include_skills,
        token_budget=body.token_budget,
    )
    return {
        "rendered": pack.render_system_context(),
        "cold_memories": [record.__dict__ for record in pack.cold_memories],
        "procedural_memories": [memory.__dict__ for memory in pack.procedural_memories],
        "token_budget": pack.token_budget,
    }
