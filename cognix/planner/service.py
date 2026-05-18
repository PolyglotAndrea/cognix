"""Planner service — generates and applies workspace plans from user intent."""

from __future__ import annotations

import json
import logging
import time
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

    def _cleanup_old_plans(self) -> None:
        """Remove plan JSON files older than 30 days."""
        try:
            cutoff = time.time() - 30 * 86400
            for p in self.plans_dir.rglob("*.json"):
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

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
            step_statuses=data.get("step_statuses", {}),
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
        self._cleanup_old_plans()

        # Load workspace context
        context = self._build_workspace_context(workspace_id)

        # Call LLM to generate plan
        plan_json = await self._generate_plan_json(user_intent, context, workspace_id)

        # Parse and validate
        plan_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        steps = [
            PlanStep(
                id=s.get("id", f"step_{i + 1}"),
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
        task_steps: list[tuple[str, dict, str]] = []
        agent_name_to_id: dict[str, str] = {}
        failed_steps: list[str] = []

        # Topological sort: ensures create_agent runs before create_task that depends on it
        sorted_steps = self._sort_steps(plan.steps)

        # Initialize all step statuses to pending
        plan.step_statuses = {s.id: "pending" for s in sorted_steps}
        plan.status = "executing"
        self._save_plan(plan)

        for step in sorted_steps:
            plan.step_statuses[step.id] = "executing"
            self._save_plan(plan)
            try:
                if step.action == "create_agent":
                    agent_id = await self._apply_create_agent(workspace_id, step.params)
                    created["agents"].append(agent_id)
                    agent_name = step.params.get("name", "")
                    if agent_name:
                        agent_name_to_id[agent_name] = agent_id
                elif step.action == "create_task":
                    task_id = await self._apply_create_task(
                        workspace_id,
                        step.params,
                        agent_name_to_id,
                        user_id,
                    )
                    created["tasks"].append(task_id)
                    task_steps.append((task_id, step.params, step.id))
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
                else:
                    raise ValueError(f"Unknown plan step action: {step.action}")
                plan.step_statuses[step.id] = "completed"
            except Exception as exc:
                logger.warning("Plan step %s failed: %s", step.id, exc)
                plan.step_statuses[step.id] = "failed"
                failed_steps.append(step.id)
            self._save_plan(plan)

        # Trigger immediate execution for "once" tasks
        execution_results = []
        artifacts: list[str] = []
        for task_id, params, step_id in task_steps:
            if step_id in failed_steps:
                continue
            schedule = params.get("schedule_type") or params.get("cron") or "once"
            if schedule == "once":
                plan.step_statuses[step_id] = "executing"
                self._save_plan(plan)
                exec_result = await self._trigger_task(task_id, workspace_id)
                execution_results.append({"task_id": task_id, **exec_result})
                if exec_result.get("status") == "failure" or exec_result.get("error"):
                    plan.step_statuses[step_id] = "failed"
                    failed_steps.append(step_id)
                else:
                    plan.step_statuses[step_id] = "completed"
                # TaskExecutor creates success artifacts; fall back to plan-level artifact creation.
                artifact_id = exec_result.get("artifact_id") or await self._store_task_artifact(
                    workspace_id,
                    task_id,
                    params,
                    exec_result,
                )
                if artifact_id:
                    artifacts.append(artifact_id)
                self._save_plan(plan)

        plan.status = "failed" if failed_steps else "applied"
        self._save_plan(plan)

        return {
            "plan_id": plan_id,
            "status": plan.status,
            "created": created,
            "execution_results": execution_results,
            "artifacts": artifacts,
            "plan": plan.to_dict(),
        }

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

    async def _trigger_task(self, task_id: str, workspace_id: str) -> dict:
        """Trigger immediate execution of a once-off task.

        Returns a normalized execution result with status, result, and error.
        """
        from sqlalchemy import select

        from cognix.api.state import agent_registry
        from cognix.scheduler.executor import TaskExecutor
        from cognix.storage.database import get_session
        from cognix.storage.models import ScheduledTaskModel

        async with get_session() as session:
            result = await session.execute(
                select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
            )
            task = result.scalar_one_or_none()

        if not task:
            return {"status": "failure", "result": "", "error": "Task not found in database"}

        payload = json.loads(task.payload) if task.payload else {}
        executor = TaskExecutor(agent_registry=agent_registry)
        try:
            run = await executor.execute(task_id, payload)
        except Exception as exc:
            logger.warning("Plan task execution failed: %s", exc)
            return {"status": "failure", "result": "", "error": str(exc)}

        status = run.get("status", "success")
        return {
            "status": status,
            "result": run.get("result", "") if status == "success" else "",
            "error": run.get("error", "") if status != "success" else "",
            "artifact_id": run.get("artifact_id"),
            "duration_ms": run.get("duration_ms", 0),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
        }

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
            connectors = [{"id": c.id, "platform": c.platform} for c in ws_config.list_connectors()]
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
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Call LLM to generate a structured plan."""
        from cognix.providers.resolver import resolve_provider

        provider = resolve_provider(workspace_id)
        if not provider.api_key:
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

            kwargs: dict = {}
            if provider.base_url:
                kwargs["api_base"] = provider.base_url

            response = await litellm.acompletion(
                model=provider.default_model,
                messages=[
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
                api_key=provider.api_key,
                **kwargs,
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
    def _sort_steps(steps: list[PlanStep]) -> list[PlanStep]:
        """Topological sort of plan steps by depends_on.

        Ensures e.g. create_agent runs before create_task that references it.
        Falls back to original order on cycles or missing refs.
        """
        by_id = {s.id: s for s in steps}
        visited: set[str] = set()
        result: list[PlanStep] = []

        def _visit(step_id: str) -> None:
            if step_id in visited:
                return
            visited.add(step_id)
            step = by_id.get(step_id)
            if not step:
                return
            for dep in step.depends_on:
                _visit(dep)
            result.append(step)

        for step in steps:
            _visit(step.id)

        # Append any steps not reachable via depends_on (shouldn't happen)
        for step in steps:
            if step.id not in visited:
                result.append(step)

        return result

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
    async def _store_task_artifact(
        workspace_id: str,
        task_id: str,
        params: dict,
        exec_result: dict,
    ) -> str | None:
        """Persist task execution output as a workspace artifact. Returns artifact id."""
        from cognix.storage.database import get_session
        from cognix.storage.models import ArtifactModel, ArtifactType

        has_output = exec_result.get("result") or exec_result.get("error")
        if not has_output:
            return None

        artifact_id = uuid.uuid4().hex[:12]
        is_error = bool(exec_result.get("error")) or exec_result.get("status") == "failure"
        title = params.get("name", f"Task {task_id}")
        raw_content = exec_result.get("error") if is_error else exec_result.get("result", "")
        atype = ArtifactType.LOG if is_error else ArtifactType.REPORT
        summary = (
            f"Task failed: {raw_content[:240]}"
            if is_error
            else f"Task completed successfully. Output preview: {raw_content[:240]}"
        )
        content = (
            f"# {title}{' - Error' if is_error else ''}\n\n"
            f"## Summary\n{summary}\n\n"
            f"## Output\n{raw_content}\n\n"
            f"## Provenance\n"
            f"- Source: plan_apply\n"
            f"- Task ID: {task_id}\n"
            f"- Agent ID: {params.get('_resolved_agent_id') or params.get('agent_id', '')}\n"
            f"- Agent Name: {params.get('agent_name', '')}\n"
        )

        artifact = ArtifactModel(
            id=artifact_id,
            workspace_id=workspace_id,
            task_id=task_id,
            agent_id=params.get("_resolved_agent_id") or params.get("agent_id") or None,
            artifact_type=atype,
            title=f"{title}{' — error' if is_error else ''}",
            content=content[:50000],
            source="plan_apply",
            metadata_json={
                "source": "plan_apply",
                "summary": summary,
                "agent_name": params.get("agent_name", ""),
                "agent_id": params.get("_resolved_agent_id") or params.get("agent_id", ""),
                "schedule": params.get("schedule_type", "once"),
                "is_error": is_error,
                "status": exec_result.get("status", "failure" if is_error else "success"),
                "duration_ms": exec_result.get("duration_ms", 0),
            },
        )
        async with get_session() as session:
            session.add(artifact)
        return artifact_id

    @staticmethod
    async def _apply_create_agent(workspace_id: str, params: dict) -> str:
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
        async with get_session() as session:
            session.add(agent)
        return agent_id

    @staticmethod
    async def _apply_create_task(
        workspace_id: str,
        params: dict,
        agent_name_to_id: dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> str:
        """Create a scheduled task from plan step params."""
        from cognix.storage.database import get_session
        from cognix.storage.models import ScheduledTaskModel, TaskState, TaskType

        task_id = uuid.uuid4().hex[:12]
        schedule = params.get("cron") or params.get("schedule") or "once"

        # Resolve agent_name -> agent_id from the name mapping built during apply
        agent_id = params.get("agent_id", "")
        agent_name = params.get("agent_name", "")
        if not agent_id and agent_name and agent_name_to_id:
            agent_id = agent_name_to_id.get(agent_name, "")
        if agent_id:
            params["_resolved_agent_id"] = agent_id

        payload = json.dumps(
            {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "name": params.get("name", "plan-task"),
                "artifact_title": params.get("artifact_title") or params.get("name", "plan-task"),
                "message": params.get("input", ""),
                "workspace_id": workspace_id,
                "user_id": user_id or "",
            }
        )
        task = ScheduledTaskModel(
            id=task_id,
            name=params.get("name", "plan-task"),
            user_id=user_id,
            task_type=TaskType.AGENT_CALL,
            schedule=schedule,
            payload=payload,
            state=TaskState.ACTIVE,
        )
        async with get_session() as session:
            session.add(task)
        return task_id
