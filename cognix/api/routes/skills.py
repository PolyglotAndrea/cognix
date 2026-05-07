"""Skill REST routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cognix.auth.dependencies import CurrentUser, require_skills_read, require_skills_write
from cognix.config import get_settings
from cognix.skills.manager import SkillsManager

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class InstallSkillRequest(BaseModel):
    source_dir: str
    name: str | None = None


def _manager() -> SkillsManager:
    return SkillsManager(local_dir=get_settings().skills.local_dir)


@router.get("")
async def list_skills(user: CurrentUser = Depends(require_skills_read)) -> list[dict]:
    return _manager().list_installed()


@router.get("/{name}")
async def get_skill(name: str, user: CurrentUser = Depends(require_skills_read)) -> dict:
    skill = _manager().load(name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return {
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "author": skill.author,
        "tags": skill.tags,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in skill.tools
        ],
    }


@router.post("/install", status_code=201)
async def install_skill(
    body: InstallSkillRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    source = Path(body.source_dir)
    if not source.exists():
        raise HTTPException(404, "Source directory not found")
    skill = _manager().install(source, name=body.name)
    return {"name": skill.name, "version": skill.version, "tools": [t.name for t in skill.tools]}


@router.delete("/{name}")
async def uninstall_skill(
    name: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    if not _manager().uninstall(name):
        raise HTTPException(404, "Skill not found")
    return {"deleted": name}
