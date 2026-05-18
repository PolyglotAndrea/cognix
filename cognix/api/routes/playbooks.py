"""Playbook REST routes — workspace-scoped reusable task templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.playbooks.service import PlaybookService

router = APIRouter(prefix="/api/v1/workspaces", tags=["playbooks"])


class ExtractPlaybookRequest(BaseModel):
    artifact_id: str


@router.get("/{workspace_id}/playbooks")
async def list_playbooks(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List all playbooks for a workspace."""
    service = PlaybookService(workspace_id)
    return await service.list_playbooks()


@router.post("/{workspace_id}/playbooks/extract", status_code=201)
async def extract_playbook(
    workspace_id: str,
    body: ExtractPlaybookRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Extract a reusable playbook from an artifact."""
    service = PlaybookService(workspace_id)
    try:
        return await service.extract_from_artifact(
            body.artifact_id,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{workspace_id}/playbooks/{playbook_id}")
async def get_playbook(
    workspace_id: str,
    playbook_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get a single playbook."""
    service = PlaybookService(workspace_id)
    result = await service.get_playbook(playbook_id)
    if not result:
        raise HTTPException(404, "Playbook not found")
    return result


@router.post("/{workspace_id}/playbooks/{playbook_id}/validate")
async def validate_playbook(
    workspace_id: str,
    playbook_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Validate a playbook (mark as validated)."""
    service = PlaybookService(workspace_id)
    try:
        return await service.validate_playbook(playbook_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{workspace_id}/playbooks/{playbook_id}/promote")
async def promote_playbook(
    workspace_id: str,
    playbook_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Promote a playbook to a skill."""
    service = PlaybookService(workspace_id)
    try:
        return await service.promote_to_skill(playbook_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# Also add extract-playbook convenience endpoint to artifacts
@router.post("/{workspace_id}/artifacts/{artifact_id}/extract-playbook", status_code=201)
async def extract_playbook_from_artifact(
    workspace_id: str,
    artifact_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Extract a playbook directly from an artifact."""
    service = PlaybookService(workspace_id)
    try:
        return await service.extract_from_artifact(artifact_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
