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


class CreateSkillRequest(BaseModel):
    name: str
    description: str = ""
    author: str = "you"
    overwrite: bool = False


def _manager() -> SkillsManager:
    return SkillsManager(local_dir=get_settings().skills.local_dir)


@router.get("")
async def list_skills(user: CurrentUser = Depends(require_skills_read)) -> list[dict]:
    return _manager().list_installed()


@router.get("/search")
async def search_skills(
    q: str,
    user: CurrentUser = Depends(require_skills_read),
) -> list[dict]:
    query = q.lower().strip()
    return [
        skill
        for skill in _manager().list_installed()
        if query in skill["name"].lower()
        or query in skill["description"].lower()
        or query in str(skill.get("tags", "")).lower()
    ]


@router.post("", status_code=201)
async def create_skill(
    body: CreateSkillRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    try:
        skill = _manager().create_scaffold(
            body.name,
            description=body.description,
            author=body.author,
            overwrite=body.overwrite,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc

    return {
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "path": str(skill.path),
        "tools": [tool.name for tool in skill.tools],
    }


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
                "access_level": tool.access_level,
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
