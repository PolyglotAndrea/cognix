"""Playbook extraction and promotion service."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from cognix.providers.resolver import resolve_provider

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """\
You analyze successful task outputs and extract reusable templates.

Given a task's artifact content, agent configuration, and task parameters, \
produce a JSON template that can be reused for similar tasks.

Output ONLY valid JSON:
{
  "name": "short descriptive name",
  "description": "what this playbook does",
  "agent_config": {
    "model": "recommended model",
    "system_prompt": "template system prompt with {{placeholders}}",
    "temperature": 0.7
  },
  "task_config": {
    "schedule_type": "once|cron|interval",
    "input_template": "template input with {{placeholders}}"
  },
  "required_skills": [],
  "tags": []
}
"""


class PlaybookService:
    """Extract playbooks from artifacts and promote them to skills."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id

    async def extract_from_artifact(
        self,
        artifact_id: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Extract a reusable playbook from a successful artifact."""
        from cognix.storage.database import get_session
        from cognix.storage.models import ArtifactModel, PlaybookModel

        async with get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ArtifactModel).where(ArtifactModel.id == artifact_id)
            )
            artifact = result.scalar_one_or_none()

        if not artifact:
            raise ValueError(f"Artifact not found: {artifact_id}")

        # Use LLM to extract template
        template = await self._extract_template(artifact.content, artifact.metadata_json)

        playbook_id = uuid.uuid4().hex[:12]
        playbook = PlaybookModel(
            id=playbook_id,
            workspace_id=self.workspace_id,
            name=template.get("name", artifact.title),
            description=template.get("description", ""),
            source_artifact_id=artifact_id,
            source_task_id=artifact.task_id,
            template=template,
            status="draft",
        )

        async with get_session() as session:
            session.add(playbook)

        return {
            "id": playbook_id,
            "name": playbook.name,
            "description": playbook.description,
            "template": template,
            "status": "draft",
        }

    async def list_playbooks(self) -> list[dict]:
        """List all playbooks for this workspace."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import PlaybookModel

        async with get_session() as session:
            result = await session.execute(
                select(PlaybookModel)
                .where(PlaybookModel.workspace_id == self.workspace_id)
                .order_by(PlaybookModel.created_at.desc())
            )
            rows = result.scalars().all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "source_artifact_id": r.source_artifact_id,
                "source_task_id": r.source_task_id,
                "status": r.status,
                "usage_count": r.usage_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def get_playbook(self, playbook_id: str) -> dict | None:
        """Get a single playbook."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import PlaybookModel

        async with get_session() as session:
            result = await session.execute(
                select(PlaybookModel).where(
                    PlaybookModel.id == playbook_id,
                    PlaybookModel.workspace_id == self.workspace_id,
                )
            )
            r = result.scalar_one_or_none()

        if not r:
            return None

        return {
            "id": r.id,
            "workspace_id": r.workspace_id,
            "name": r.name,
            "description": r.description,
            "source_artifact_id": r.source_artifact_id,
            "source_task_id": r.source_task_id,
            "template": r.template,
            "status": r.status,
            "usage_count": r.usage_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    async def validate_playbook(self, playbook_id: str) -> dict:
        """Validate a playbook (mark as validated)."""
        from sqlalchemy import select, update

        from cognix.storage.database import get_session
        from cognix.storage.models import PlaybookModel

        async with get_session() as session:
            result = await session.execute(
                select(PlaybookModel).where(
                    PlaybookModel.id == playbook_id,
                    PlaybookModel.workspace_id == self.workspace_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                raise ValueError(f"Playbook not found: {playbook_id}")

            await session.execute(
                update(PlaybookModel)
                .where(PlaybookModel.id == playbook_id)
                .values(status="validated")
            )

        return {"id": playbook_id, "status": "validated"}

    async def promote_to_skill(self, playbook_id: str) -> dict:
        """Convert a validated playbook into a skill scaffold."""
        from sqlalchemy import select, update

        from cognix.storage.database import get_session
        from cognix.storage.models import PlaybookModel

        async with get_session() as session:
            result = await session.execute(
                select(PlaybookModel).where(
                    PlaybookModel.id == playbook_id,
                    PlaybookModel.workspace_id == self.workspace_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                raise ValueError(f"Playbook not found: {playbook_id}")
            if row.status not in ("validated", "draft"):
                raise ValueError(
                    f"Playbook status is '{row.status}', must be 'validated' or 'draft'"
                )

            template = row.template
            name = row.name

        # Create skill scaffold
        skill_dir = await self._create_skill_scaffold(name, template)

        # Mark as promoted
        async with get_session() as session:
            await session.execute(
                update(PlaybookModel)
                .where(PlaybookModel.id == playbook_id)
                .values(status="promoted")
            )

        return {
            "playbook_id": playbook_id,
            "skill_dir": str(skill_dir),
            "status": "promoted",
        }

    async def _extract_template(
        self,
        content: str,
        metadata: dict,
    ) -> dict[str, Any]:
        """Use LLM to extract a reusable template from artifact content."""
        provider = resolve_provider(self.workspace_id)
        if not provider.api_key:
            # Fallback: create a simple template without LLM
            return {
                "name": "extracted-playbook",
                "description": content[:200],
                "agent_config": {
                    "model": provider.default_model,
                    "system_prompt": "You are a helpful assistant.",
                    "temperature": 0.7,
                },
                "task_config": {
                    "schedule_type": "once",
                    "input_template": content[:500],
                },
                "required_skills": [],
                "tags": [],
            }

        try:
            import litellm

            prompt = (
                f"Artifact metadata: {json.dumps(metadata, indent=2)}\n\n"
                f"Artifact content (first 2000 chars):\n{content[:2000]}\n\n"
                "Extract a reusable template."
            )

            kwargs: dict = {}
            if provider.base_url:
                kwargs["api_base"] = provider.base_url

            response = await litellm.acompletion(
                model=provider.default_model,
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.3,
                api_key=provider.api_key,
                **kwargs,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```") and not in_block:
                        in_block = True
                        continue
                    if line.startswith("```") and in_block:
                        break
                    if in_block:
                        json_lines.append(line)
                raw = "\n".join(json_lines)

            return json.loads(raw)
        except Exception as exc:
            logger.warning("LLM template extraction failed: %s", exc)
            return {
                "name": "extracted-playbook",
                "description": content[:200],
                "agent_config": {},
                "task_config": {"schedule_type": "once"},
                "required_skills": [],
                "tags": [],
            }

    async def _create_skill_scaffold(
        self,
        name: str,
        template: dict,
    ) -> Any:
        """Create a skill directory from a playbook template."""
        from cognix.local.home import CognixHome

        home = CognixHome.default().ensure()
        skill_dir = home.skills_dir / name.replace(" ", "_").lower()
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write skill.yaml
        skill_yaml = {
            "name": name,
            "version": "1.0.0",
            "description": template.get("description", ""),
            "tags": template.get("tags", []),
        }
        (skill_dir / "skill.yaml").write_text(
            json.dumps(skill_yaml, indent=2) + "\n", encoding="utf-8",
        )

        # Write handler.py stub
        handler = f'''"""Skill handler for {name}."""

async def run(**kwargs):
    """Execute the skill."""
    return {{"status": "ok", "message": "Skill executed successfully"}}
'''
        (skill_dir / "handler.py").write_text(handler, encoding="utf-8")

        # Write template.json
        (skill_dir / "template.json").write_text(
            json.dumps(template, indent=2) + "\n", encoding="utf-8",
        )

        return skill_dir
