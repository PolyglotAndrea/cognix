"""Planner service — generates and applies workspace plans from user intent."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.home import CognixHome
from cognix.local.workspace_config import WorkspaceConfigStore
from cognix.planner.schema import PlanStep, WorkspacePlan

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are a workspace planning agent. Given a user's intent and the current workspace state, \
produce a structured execution plan as JSON.

Output ONLY valid JSON matching this schema:
{
  "summary": "One-sentence description of what will happen",
  "steps": [
    {
      "id": "step_1",
      "action": "create_agent|create_task|install_skill|configure_mcp",
      "description": "Human-readable description",
      "params": { ... },
      "depends_on": []
    }
  ],
  "required_skills": ["skill_name"],
  "required_connectors": ["connector_name"],
  "sandbox_permissions": ["file_write", "network_access"],
  "expected_artifacts": ["report", "dataset"],
  "estimated_cost": "low|medium|high"
}

Actions:
- create_agent: params = { name, model, system_prompt }
- create_task: params = { name, agent_name, schedule_type, cron_or_interval, input }
- install_skill: params = { skill_name }
- configure_mcp: params = { name, command, args }
"""


class PlannerService:
    """Generates and applies workspace plans."""

    def __init__(self, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()

    @property
    def plans_dir(self) -> Path:
        return self.home.root / "plans"

    def _workspace_plans_dir(self, workspace_id: str) -> Path:
        d = self.plans_dir / workspace_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _plan_path(self, workspace_id: str, plan_id: str) -> Path:
        return self._workspace_plans_dir(workspace_id) / f"{plan_id}.json"

    def _save_plan(self, plan: WorkspacePlan) -> None:
        path = self._plan_path(plan.workspace_id, plan.id)
        path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _load_plan(self, workspace_id: str, plan_id: str) -> WorkspacePlan | None:
        path = self._plan_path(workspace_id, plan_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return WorkspacePlan(
            id=data["id"],
            workspace_id=data["workspace_id"],
            summary=data["summary"],
            steps=steps,
            required_skills=data.get("required_skills", []),
            required_connectors=data.get("required_connectors", []),
            sandbox_permissions=data.get("sandbox_permissions", []),
            expected_artifacts=data.get("expected_artifacts", []),
            estimated_cost=data.get("estimated_cost", "unknown"),
            status=data.get("status", "proposed"),
            created_at=data.get("created_at", ""),
        )

    def list_plans(self, workspace_id: str) -> list[dict]:
        """List all plans for a workspace."""
        d = self._workspace_plans_dir(workspace_id)
        plans = []
        for p in sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            plan = self._load_plan(workspace_id, p.stem)
            if plan:
                plans.append(plan.to_dict())
        return plans

    def get_plan(self, workspace_id: str, plan_id: str) -> WorkspacePlan | None:
        return self._load_plan(workspace_id, plan_id)

    async def create_plan(
        self,
        workspace_id: str,
        user_intent: str,
        user_id: str,
    ) -> WorkspacePlan:
        """Analyze user intent and produce a structured plan."""
        # Load workspace context
        context = self._build_workspace_context(workspace_id)

        # Call LLM to generate plan
        plan_json = await self._generate_plan_json(user_intent, context)

        # Parse and validate
        plan_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        steps = [
            PlanStep(
                id=s.get("id", f"step_{i+1}"),
                action=s.get("action", "unknown"),
                description=s.get("description", ""),
                params=s.get("params", {}),
                depends_on=s.get("depends_on", []),
            )
            for i, s in enumerate(plan_json.get("steps", []))
        ]

        plan = WorkspacePlan(
            id=plan_id,
            workspace_id=workspace_id,
            summary=plan_json.get("summary", user_intent[:100]),
            steps=steps,
            required_skills=plan_json.get("required_skills", []),
            required_connectors=plan_json.get("required_connectors", []),
            sandbox_permissions=plan_json.get("sandbox_permissions", []),
            expected_artifacts=plan_json.get("expected_artifacts", []),
            estimated_cost=plan_json.get("estimated_cost", "unknown"),
            status="proposed",
            created_at=now,
        )

        self._save_plan(plan)
        return plan

    async def apply_plan(
        self,
        workspace_id: str,
        plan_id: str,
        user_id: str,
    ) -> dict:
        """Execute a confirmed plan by creating/updating runtime entities."""
        plan = self._load_plan(workspace_id, plan_id)
        if not plan:
            raise FileNotFoundError(f"Plan not found: {plan_id}")
        if plan.status != "confirmed":
            raise ValueError(f"Plan is not confirmed (status: {plan.status})")

        created: dict[str, list[str]] = {
            "agents": [],
            "tasks": [],
            "skills": [],
            "mcp_servers": [],
        }

        ws_config = WorkspaceConfigStore(workspace_id)

        for step in plan.steps:
            if step.action == "create_agent":
                agent_id = self._apply_create_agent(workspace_id, step.params)
                created["agents"].append(agent_id)
            elif step.action == "create_task":
                task_id = self._apply_create_task(workspace_id, step.params)
                created["tasks"].append(task_id)
            elif step.action == "install_skill":
                skill_name = step.params.get("name", step.params.get("skill_name", ""))
                if skill_name:
                    ws_config.set_skill_enabled(skill_name, True)
                    created["skills"].append(skill_name)
            elif step.action == "configure_mcp":
                server = ws_config.upsert_mcp_server(
                    name=step.params.get("name", "unnamed"),
                    command=step.params.get("command", ""),
                    args=step.params.get("args", []),
                    env=step.params.get("env", {}),
                )
                created["mcp_servers"].append(server.id)

        plan.status = "applied"
        self._save_plan(plan)

        return {"plan_id": plan_id, "status": "applied", "created": created}

    def reject_plan(self, workspace_id: str, plan_id: str) -> dict:
        plan = self._load_plan(workspace_id, plan_id)
        if not plan:
            raise FileNotFoundError(f"Plan not found: {plan_id}")
        plan.status = "rejected"
        self._save_plan(plan)
        return {"plan_id": plan_id, "status": "rejected"}

    def confirm_plan(self, workspace_id: str, plan_id: str) -> dict:
        plan = self._load_plan(workspace_id, plan_id)
        if not plan:
            raise FileNotFoundError(f"Plan not found: {plan_id}")
        plan.status = "confirmed"
        self._save_plan(plan)
        return {"plan_id": plan_id, "status": "confirmed"}

    def _build_workspace_context(self, workspace_id: str) -> dict:
        """Load current workspace state for the planner."""
        ws_config = WorkspaceConfigStore(workspace_id)

        skills = []
        try:
            settings = ws_config.get_settings()
            skills = settings.get("enabled_skills", [])
        except Exception:
            pass

        mcp_servers = []
        try:
            mcp_servers = [
                {"id": s.id, "name": s.name, "command": s.command}
                for s in ws_config.list_mcp_servers()
            ]
        except Exception:
            pass

        connectors = []
        try:
            connectors = [
                {"id": c.id, "platform": c.platform}
                for c in ws_config.list_connectors()
            ]
        except Exception:
            pass

        return {
            "workspace_id": workspace_id,
            "enabled_skills": skills,
            "mcp_servers": mcp_servers,
            "connectors": connectors,
        }

    async def _generate_plan_json(
        self,
        user_intent: str,
        context: dict,
    ) -> dict[str, Any]:
        """Call LLM to generate a structured plan."""
        from cognix.local.config import ConfigStore

        llm_cfg = ConfigStore().get_llm()
        if not llm_cfg.api_key:
            # Fallback: generate a simple default plan
            return self._default_plan(user_intent)

        try:
            import litellm

            context_str = json.dumps(context, indent=2, ensure_ascii=False)
            prompt = (
                f"Workspace context:\n{context_str}\n\n"
                f"User intent:\n{user_intent}\n\n"
                "Generate a plan as JSON."
            )

            response = await litellm.acompletion(
                model=llm_cfg.default_model,
                messages=[
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
                api_key=llm_cfg.api_key,
                **({"api_base": llm_cfg.base_url} if llm_cfg.base_url else {}),
            )

            content = response.choices[0].message.content.strip()
            # Extract JSON from markdown code blocks if present
            if content.startswith("```"):
                lines = content.split("\n")
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
                content = "\n".join(json_lines)

            return json.loads(content)
        except Exception as exc:
            logger.warning("LLM plan generation failed: %s — using default plan", exc)
            return self._default_plan(user_intent)

    @staticmethod
    def _default_plan(user_intent: str) -> dict[str, Any]:
        """Generate a simple default plan when LLM is unavailable."""
        return {
            "summary": f"Execute: {user_intent[:100]}",
            "steps": [
                {
                    "id": "step_1",
                    "action": "create_agent",
                    "description": "Create an agent to handle the task",
                    "params": {
                        "name": "task-agent",
                        "model": "gpt-4o",
                        "system_prompt": f"You are a helpful assistant. Task: {user_intent}",
                    },
                    "depends_on": [],
                },
                {
                    "id": "step_2",
                    "action": "create_task",
                    "description": "Run the agent with the user's request",
                    "params": {
                        "name": "user-task",
                        "agent_name": "task-agent",
                        "schedule_type": "once",
                        "input": user_intent,
                    },
                    "depends_on": ["step_1"],
                },
            ],
            "required_skills": [],
            "required_connectors": [],
            "sandbox_permissions": ["workspace_write"],
            "expected_artifacts": [],
            "estimated_cost": "low",
        }

    @staticmethod
    def _apply_create_agent(workspace_id: str, params: dict) -> str:
        """Create an agent from plan step params."""
        from cognix.storage.database import get_session
        from cognix.storage.models import AgentModel

        agent_id = uuid.uuid4().hex[:12]
        agent = AgentModel(
            id=agent_id,
            workspace_id=workspace_id,
            name=params.get("name", "plan-agent"),
            model=params.get("model", "gpt-4o"),
            system_prompt=params.get("system_prompt", ""),
        )

        import asyncio

        async def _insert():
            async with get_session() as session:
                session.add(agent)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_insert())
        except RuntimeError:
            asyncio.run(_insert())

        return agent_id

    @staticmethod
    def _apply_create_task(workspace_id: str, params: dict) -> str:
        """Create a scheduled task from plan step params."""
        from cognix.storage.database import get_session
        from cognix.storage.models import ScheduledTaskModel

        task_id = uuid.uuid4().hex[:12]
        task = ScheduledTaskModel(
            id=task_id,
            workspace_id=workspace_id,
            name=params.get("name", "plan-task"),
            task_type="agent_call",
            agent_name=params.get("agent_name", ""),
            schedule_type=params.get("schedule_type", "once"),
            cron_expression=params.get("cron", None),
            interval_seconds=params.get("interval_seconds", None),
            input_data=params.get("input", ""),
        )

        import asyncio

        async def _insert():
            async with get_session() as session:
                session.add(task)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_insert())
        except RuntimeError:
            asyncio.run(_insert())

        return task_id
