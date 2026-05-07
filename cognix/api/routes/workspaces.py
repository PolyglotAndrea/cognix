"""Workspace REST routes backed by ~/.cognix."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.local.workspace import WorkspaceManager

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_workspaces(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [workspace.__dict__ for workspace in WorkspaceManager().list_all()]


@router.post("", status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    workspace = WorkspaceManager().create(body.name, description=body.description)
    return workspace.__dict__


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    workspace = WorkspaceManager().get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    return workspace.__dict__
