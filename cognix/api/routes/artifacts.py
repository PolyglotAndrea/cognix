"""Artifact REST routes — workspace-scoped task outputs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.storage.database import get_session
from cognix.storage.models import ArtifactModel, ArtifactType

router = APIRouter(prefix="/api/v1/workspaces", tags=["artifacts"])


class CreateArtifactRequest(BaseModel):
    artifact_type: str = "note"
    title: str
    content: str = ""
    task_id: str | None = None
    agent_id: str | None = None
    metadata: dict | None = None


class UpdateArtifactRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    artifact_type: str | None = None
    metadata: dict | None = None


def _artifact_to_dict(row: ArtifactModel) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "task_id": row.task_id,
        "agent_id": row.agent_id,
        "artifact_type": row.artifact_type.value,
        "title": row.title,
        "content": row.content,
        "metadata": row.metadata_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/{workspace_id}/artifacts")
async def list_artifacts(
    workspace_id: str,
    artifact_type: str | None = None,
    task_id: str | None = None,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List artifacts for a workspace, optionally filtered by type or task."""
    async with get_session() as session:
        stmt = select(ArtifactModel).where(ArtifactModel.workspace_id == workspace_id)
        if artifact_type:
            stmt = stmt.where(ArtifactModel.artifact_type == artifact_type)
        if task_id:
            stmt = stmt.where(ArtifactModel.task_id == task_id)
        stmt = stmt.order_by(ArtifactModel.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()
    return [_artifact_to_dict(row) for row in rows]


@router.post("/{workspace_id}/artifacts", status_code=201)
async def create_artifact(
    workspace_id: str,
    body: CreateArtifactRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Create a new artifact in a workspace."""
    try:
        atype = ArtifactType(body.artifact_type)
    except ValueError:
        raise HTTPException(
            400,
            f"Invalid artifact_type: {body.artifact_type}. "
            f"Must be one of: {', '.join(t.value for t in ArtifactType)}",
        )

    artifact_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    artifact = ArtifactModel(
        id=artifact_id,
        workspace_id=workspace_id,
        task_id=body.task_id,
        agent_id=body.agent_id,
        artifact_type=atype,
        title=body.title,
        content=body.content,
        metadata_json=body.metadata or {},
        created_at=now,
        updated_at=now,
    )
    async with get_session() as session:
        session.add(artifact)
    return _artifact_to_dict(artifact)


@router.get("/{workspace_id}/artifacts/{artifact_id}")
async def get_artifact(
    workspace_id: str,
    artifact_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get a single artifact."""
    async with get_session() as session:
        result = await session.execute(
            select(ArtifactModel).where(
                ArtifactModel.id == artifact_id,
                ArtifactModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Artifact not found")
    return _artifact_to_dict(row)


@router.patch("/{workspace_id}/artifacts/{artifact_id}")
async def update_artifact(
    workspace_id: str,
    artifact_id: str,
    body: UpdateArtifactRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Update an existing artifact."""
    from sqlalchemy import update

    async with get_session() as session:
        result = await session.execute(
            select(ArtifactModel).where(
                ArtifactModel.id == artifact_id,
                ArtifactModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Artifact not found")

        changes: dict = {}
        if body.title is not None:
            changes["title"] = body.title
        if body.content is not None:
            changes["content"] = body.content
        if body.artifact_type is not None:
            try:
                changes["artifact_type"] = ArtifactType(body.artifact_type)
            except ValueError:
                raise HTTPException(400, f"Invalid artifact_type: {body.artifact_type}")
        if body.metadata is not None:
            changes["metadata_json"] = body.metadata
        if changes:
            changes["updated_at"] = datetime.now(UTC)
            await session.execute(
                update(ArtifactModel)
                .where(ArtifactModel.id == artifact_id)
                .values(**changes)
            )

    # Re-fetch to return updated state
    async with get_session() as session:
        result = await session.execute(
            select(ArtifactModel).where(ArtifactModel.id == artifact_id)
        )
        row = result.scalar_one()
    return _artifact_to_dict(row)


@router.delete("/{workspace_id}/artifacts/{artifact_id}")
async def delete_artifact(
    workspace_id: str,
    artifact_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Delete an artifact."""
    from sqlalchemy import delete as sqldelete

    async with get_session() as session:
        result = await session.execute(
            sqldelete(ArtifactModel)
            .where(
                ArtifactModel.id == artifact_id,
                ArtifactModel.workspace_id == workspace_id,
            )
            .returning(ArtifactModel.id)
        )
        deleted = result.scalar_one_or_none()
    if not deleted:
        raise HTTPException(404, "Artifact not found")
    return {"deleted": artifact_id}
