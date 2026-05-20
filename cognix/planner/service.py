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
from cognix.orchestrator.protocol import OrchestrationEvent, emit_orchestration_event
from cognix.planner.schema import PlanStep, WorkspacePlan

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are a workspace planning agent. Given a user's intent and the current workspace state, \
produce a structured execution plan as JSON. You must decide whether the request is a simple \
chat, one-shot task, long-running task, recurring scheduled task, research workflow, file \
operation, integration workflow, or multi-agent team workflow. Use only capabilities that are \
available in the workspace context unless you explicitly recommend installing or enabling them.

Output ONLY valid JSON matching this schema:
{
  "summary": "One-sentence description of what will happen",
  "intent_type": "chat|task|research|automation|file_operation|integration|multi_agent|scheduled",
  "execution_mode": "chat|once|long_running|scheduled|multi_agent",
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
  "recommended_agents": [
    {"name": "research-agent", "role": "researcher", "reason": "why this agent is needed"}
  ],
  "recommended_skills": [
    {"name": "web_search", "available": true, "reason": "why it helps"}
  ],
  "recommended_mcp_tools": [
    {"server": "filesystem", "tool": "read_file", "reason": "why it is needed"}
  ],
  "scheduling": {
    "needed": false,
    "kind": "once|interval|cron",
    "expression": "",
    "reason": ""
  },
  "estimated_cost": "low|medium|high"
}

Actions:
- create_agent: params = { name, model, system_prompt }
- create_task: params = { name, agent_name, schedule_type, cron_or_interval, input }
- install_skill: params = { skill_name }
- configure_mcp: params = { name, command, args }

Rules:
- Prefer one primary agent for simple work.
- Use multiple agents only when distinct roles can run independently or sequentially.
- Use create_task with schedule_type="once" for immediate execution.
- Use create_task with schedule_type="cron" or "interval" only for explicitly recurring work.
- Set expected_artifacts to useful user-facing outputs, never raw logs.
- If a model is not listed as available, use the effective default model from context.
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
            intent_type=data.get("intent_type", "task"),
            execution_mode=data.get("execution_mode", "once"),
            steps=steps,
            required_skills=data.get("required_skills", []),
            required_connectors=data.get("required_connectors", []),
            sandbox_permissions=data.get("sandbox_permissions", []),
            expected_artifacts=data.get("expected_artifacts", []),
            recommended_agents=data.get("recommended_agents", []),
            recommended_skills=data.get("recommended_skills", []),
            recommended_mcp_tools=data.get("recommended_mcp_tools", []),
            scheduling=data.get("scheduling", {}),
            capability_snapshot=data.get("capability_snapshot", {}),
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
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="intent.received",
                stage="intent",
                status="received",
                run_id=plan_id,
                plan_id=plan_id,
                data={"intent": user_intent, "user_id": user_id},
            )
        )

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
            intent_type=plan_json.get("intent_type", "task"),
            execution_mode=plan_json.get("execution_mode", "once"),
            steps=steps,
            required_skills=plan_json.get("required_skills", []),
            required_connectors=plan_json.get("required_connectors", []),
            sandbox_permissions=plan_json.get("sandbox_permissions", []),
            expected_artifacts=plan_json.get("expected_artifacts", []),
            recommended_agents=plan_json.get("recommended_agents", []),
            recommended_skills=plan_json.get("recommended_skills", []),
            recommended_mcp_tools=plan_json.get("recommended_mcp_tools", []),
            scheduling=plan_json.get("scheduling", {}),
            capability_snapshot=self._compact_capability_snapshot(context),
            estimated_cost=plan_json.get("estimated_cost", "unknown"),
            status="proposed",
            created_at=now,
        )

        self._save_plan(plan)
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="plan.proposed",
                stage="plan",
                status="proposed",
                run_id=plan_id,
                plan_id=plan_id,
                data={"summary": plan.summary, "steps": [step.to_dict() for step in steps]},
            )
        )
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
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="execution.started",
                stage="execution",
                status="running",
                run_id=plan_id,
                plan_id=plan_id,
                data={"user_id": user_id, "step_count": len(sorted_steps)},
            )
        )

        for step in sorted_steps:
            plan.step_statuses[step.id] = "executing"
            self._save_plan(plan)
            emit_orchestration_event(
                OrchestrationEvent(
                    workspace_id=workspace_id,
                    type="plan.step.started",
                    stage="plan",
                    status="running",
                    run_id=plan_id,
                    plan_id=plan_id,
                    step_id=step.id,
                    data={"action": step.action, "description": step.description},
                )
            )
            try:
                if step.action == "create_agent":
                    agent_id = await self._apply_create_agent(workspace_id, step.params)
                    created["agents"].append(agent_id)
                    emit_orchestration_event(
                        OrchestrationEvent(
                            workspace_id=workspace_id,
                            type="agent.created",
                            stage="execution",
                            status="created",
                            run_id=plan_id,
                            plan_id=plan_id,
                            step_id=step.id,
                            agent_id=agent_id,
                            data={"name": step.params.get("name", "")},
                        )
                    )
                    agent_name = step.params.get("name", "")
                    if agent_name:
                        agent_name_to_id[agent_name] = agent_id
                elif step.action == "create_task":
                    step.params["_plan_id"] = plan_id
                    step.params["_step_id"] = step.id
                    task_id = await self._apply_create_task(
                        workspace_id,
                        step.params,
                        agent_name_to_id,
                        user_id,
                    )
                    created["tasks"].append(task_id)
                    task_steps.append((task_id, step.params, step.id))
                    emit_orchestration_event(
                        OrchestrationEvent(
                            workspace_id=workspace_id,
                            type="task.created",
                            stage="execution",
                            status="created",
                            run_id=plan_id,
                            plan_id=plan_id,
                            step_id=step.id,
                            task_id=task_id,
                            agent_id=step.params.get("_resolved_agent_id", ""),
                            data={"name": step.params.get("name", "")},
                        )
                    )
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
                emit_orchestration_event(
                    OrchestrationEvent(
                        workspace_id=workspace_id,
                        type="plan.step.completed",
                        stage="plan",
                        status="completed",
                        run_id=plan_id,
                        plan_id=plan_id,
                        step_id=step.id,
                        data={"action": step.action},
                    )
                )
            except Exception as exc:
                logger.warning("Plan step %s failed: %s", step.id, exc)
                plan.step_statuses[step.id] = "failed"
                failed_steps.append(step.id)
                emit_orchestration_event(
                    OrchestrationEvent(
                        workspace_id=workspace_id,
                        type="plan.step.failed",
                        stage="plan",
                        status="failed",
                        run_id=plan_id,
                        plan_id=plan_id,
                        step_id=step.id,
                        data={"action": step.action, "error": str(exc)},
                    )
                )
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
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="execution.failed" if failed_steps else "execution.completed",
                stage="execution",
                status="failed" if failed_steps else "completed",
                run_id=plan_id,
                plan_id=plan_id,
                data={"created": created, "failed_steps": failed_steps, "artifacts": artifacts},
            )
        )

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
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="plan.rejected",
                stage="plan",
                status="rejected",
                run_id=plan_id,
                plan_id=plan_id,
            )
        )
        return {"plan_id": plan_id, "status": "rejected"}

    def confirm_plan(self, workspace_id: str, plan_id: str) -> dict:
        plan = self._load_plan(workspace_id, plan_id)
        if not plan:
            raise FileNotFoundError(f"Plan not found: {plan_id}")
        plan.status = "confirmed"
        self._save_plan(plan)
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="plan.confirmed",
                stage="plan",
                status="confirmed",
                run_id=plan_id,
                plan_id=plan_id,
            )
        )
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
            return {
                "status": "failure",
                "result": "",
                "error": self._humanize_runtime_error(str(exc)),
            }

        status = run.get("status", "success")
        return {
            "status": status,
            "result": run.get("result", "") if status == "success" else "",
            "error": self._humanize_runtime_error(run.get("error", ""))
            if status != "success"
            else "",
            "artifact_id": run.get("artifact_id"),
            "duration_ms": run.get("duration_ms", 0),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
        }

    @staticmethod
    def _humanize_runtime_error(error: str) -> str:
        """Convert provider/runtime internals into actionable product errors."""
        if not error:
            return ""
        lowered = error.lower()
        if "<!doctype html>" in lowered or "<html" in lowered:
            return (
                "The configured provider returned a web page instead of an API response. "
                "Check the provider Base URL in Account Settings or Workspace Settings; "
                "OpenAI-compatible gateways usually need a /v1 API endpoint."
            )
        if "model" in lowered and (
            "not found" in lowered or "no channel" in lowered or "under group" in lowered
        ):
            return (
                "The selected model is not available from the current provider. "
                "Choose an available model or update the provider configuration."
            )
        if "api key" in lowered or "unauthorized" in lowered or "401" in lowered:
            return (
                "The provider rejected the API key. Update the API key in Account Settings "
                "or configure a workspace-level provider override."
            )
        return error

    def _build_workspace_context(self, workspace_id: str) -> dict:
        """Load current workspace state for the planner."""
        from cognix.config import get_settings
        from cognix.providers.resolver import resolve_provider
        from cognix.skills.manager import SkillsManager

        ws_config = WorkspaceConfigStore(workspace_id)
        provider = resolve_provider(workspace_id)

        skills = []
        installed_skills = []
        try:
            settings = ws_config.get_settings()
            skills = settings.get("enabled_skills", [])
        except Exception:
            pass
        try:
            installed_skills = [
                {
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "tags": skill.get("tags", ""),
                    "enabled": skill.get("name") in skills,
                }
                for skill in SkillsManager(
                    local_dir=get_settings().skills.local_dir
                ).list_installed()
            ]
        except Exception:
            pass

        mcp_servers = []
        try:
            mcp_servers = [
                {
                    "id": s.id,
                    "name": s.name,
                    "command": s.command,
                    "enabled": getattr(s, "enabled", True),
                    "tool_count": len(getattr(s, "tools", []) or []),
                    "tools": [
                        {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                        }
                        for tool in (getattr(s, "tools", []) or [])[:8]
                        if isinstance(tool, dict)
                    ],
                }
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
            "provider": {
                "configured": bool(provider.api_key),
                "base_url_configured": bool(provider.base_url),
                "default_model": provider.default_model,
            },
            "enabled_skills": skills,
            "installed_skills": installed_skills[:20],
            "mcp_servers": mcp_servers,
            "connectors": connectors,
            "agents": [],
        }

    @staticmethod
    def _compact_capability_snapshot(context: dict) -> dict:
        """Persist a small explanation snapshot without storing secrets or large tool schemas."""
        return {
            "provider": context.get("provider", {}),
            "enabled_skills": context.get("enabled_skills", []),
            "installed_skill_count": len(context.get("installed_skills", [])),
            "mcp_server_count": len(context.get("mcp_servers", [])),
            "connector_count": len(context.get("connectors", [])),
            "mcp_servers": [
                {
                    "name": server.get("name", ""),
                    "tool_count": server.get("tool_count", 0),
                    "enabled": server.get("enabled", True),
                }
                for server in context.get("mcp_servers", [])[:10]
            ],
            "connectors": context.get("connectors", [])[:10],
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
            return self._default_plan(user_intent, context)

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

            return self._normalize_plan_json(json.loads(content), user_intent, context)
        except Exception as exc:
            logger.warning("LLM plan generation failed: %s — using default plan", exc)
            return self._default_plan(user_intent, context)

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

    def _default_plan(self, user_intent: str, context: dict | None = None) -> dict[str, Any]:
        """Generate a capability-aware default plan when LLM planning is unavailable."""
        context = context or {}
        text = user_intent.lower()
        provider = context.get("provider", {})
        model = provider.get("default_model") or "gpt-4o"
        scheduled = any(
            token in text
            for token in (
                "daily",
                "weekly",
                "monthly",
                "每天",
                "每周",
                "每月",
                "定时",
                "周期",
                "cron",
            )
        )
        research = any(
            token in text for token in ("research", "deep research", "调研", "研究", "分析")
        )
        long_running = any(
            token in text for token in ("long", "长期", "持续", "监控", "watch", "monitor")
        )
        multi_agent = any(
            token in text
            for token in ("team", "团队", "多 agent", "多agent", "拆分", "子 agent", "子agent")
        )
        needs_web = any(
            token in text for token in ("web", "search", "news", "联网", "搜索", "新闻", "最新")
        )

        intent_type = (
            "scheduled"
            if scheduled
            else "multi_agent"
            if multi_agent
            else "research"
            if research
            else "automation"
            if long_running
            else "task"
        )
        execution_mode = (
            "scheduled"
            if scheduled
            else "multi_agent"
            if multi_agent
            else "long_running"
            if long_running
            else "once"
        )

        recommended_skills = self._recommend_skills(user_intent, context)
        recommended_mcp_tools = self._recommend_mcp_tools(user_intent, context)
        if needs_web and not any(item.get("name") == "web_search" for item in recommended_skills):
            recommended_skills.append(
                {
                    "name": "web_search",
                    "available": False,
                    "reason": "The request appears to need current external information.",
                }
            )

        agent_name = (
            "research-agent"
            if research
            else "automation-agent"
            if scheduled or long_running
            else "task-agent"
        )
        artifact = "research report" if research else "task result"
        schedule_expression = "every 24h" if scheduled else ""
        schedule_type = "interval" if scheduled else "once"
        return {
            "summary": f"Execute: {user_intent[:100]}",
            "intent_type": intent_type,
            "execution_mode": execution_mode,
            "steps": [
                {
                    "id": "step_1",
                    "action": "create_agent",
                    "description": "Create an agent to handle the task",
                    "params": {
                        "name": agent_name,
                        "model": model,
                        "system_prompt": (
                            f"You are a workspace agent. Execute the user's task with clear "
                            f"progress, source attribution, and durable artifact output.\n\n"
                            f"Task: {user_intent}"
                        ),
                    },
                    "depends_on": [],
                },
                {
                    "id": "step_2",
                    "action": "create_task",
                    "description": "Run the agent with the user's request",
                    "params": {
                        "name": "user-task",
                        "agent_name": agent_name,
                        "schedule_type": schedule_type,
                        "cron_or_interval": schedule_expression,
                        "input": user_intent,
                        "artifact_title": artifact.title(),
                    },
                    "depends_on": ["step_1"],
                },
            ],
            "required_skills": [
                item["name"] for item in recommended_skills if item.get("available")
            ],
            "required_connectors": [],
            "sandbox_permissions": ["network_access"] if needs_web else ["workspace_write"],
            "expected_artifacts": [artifact],
            "recommended_agents": [
                {
                    "name": agent_name,
                    "role": "researcher" if research else "operator",
                    "reason": "Primary owner for planning, execution, and artifact generation.",
                }
            ],
            "recommended_skills": recommended_skills,
            "recommended_mcp_tools": recommended_mcp_tools,
            "scheduling": {
                "needed": scheduled,
                "kind": schedule_type,
                "expression": schedule_expression,
                "reason": "The request asks for recurring execution." if scheduled else "",
            },
            "estimated_cost": "medium" if research or multi_agent else "low",
        }

    def _normalize_plan_json(
        self, plan: dict[str, Any], user_intent: str, context: dict
    ) -> dict[str, Any]:
        """Fill missing planner fields and keep model/tool choices aligned with context."""
        defaults = self._default_plan(user_intent, context)
        normalized = {**defaults, **plan}
        normalized["steps"] = plan.get("steps") or defaults["steps"]
        normalized["recommended_agents"] = (
            plan.get("recommended_agents") or defaults["recommended_agents"]
        )
        normalized["recommended_skills"] = plan.get("recommended_skills") or self._recommend_skills(
            user_intent, context
        )
        normalized["recommended_mcp_tools"] = plan.get(
            "recommended_mcp_tools"
        ) or self._recommend_mcp_tools(user_intent, context)
        normalized["scheduling"] = plan.get("scheduling") or defaults["scheduling"]

        model = context.get("provider", {}).get("default_model") or "gpt-4o"
        for step in normalized.get("steps", []):
            if step.get("action") == "create_agent":
                params = step.setdefault("params", {})
                params["model"] = params.get("model") or model
            if step.get("action") == "create_task":
                params = step.setdefault("params", {})
                if params.get("schedule_type") in {"interval", "cron"} and not params.get(
                    "cron_or_interval"
                ):
                    params["cron_or_interval"] = (
                        normalized.get("scheduling", {}).get("expression") or "every 24h"
                    )
        return normalized

    @staticmethod
    def _recommend_skills(user_intent: str, context: dict) -> list[dict[str, Any]]:
        terms = {
            part
            for part in user_intent.lower().replace("/", " ").replace("-", " ").split()
            if len(part) > 2
        }
        recommendations: list[dict[str, Any]] = []
        for skill in context.get("installed_skills", []):
            haystack = " ".join(
                str(skill.get(key, "")).lower() for key in ("name", "description", "tags")
            )
            if terms and not any(term in haystack for term in terms):
                continue
            recommendations.append(
                {
                    "name": skill.get("name", ""),
                    "available": True,
                    "enabled": skill.get("enabled", False),
                    "reason": skill.get("description") or "Installed skill matching the request.",
                }
            )
            if len(recommendations) >= 5:
                break
        return recommendations

    @staticmethod
    def _recommend_mcp_tools(user_intent: str, context: dict) -> list[dict[str, Any]]:
        text = user_intent.lower()
        recommendations: list[dict[str, Any]] = []
        for server in context.get("mcp_servers", []):
            for tool in server.get("tools", []) or []:
                tool_text = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
                if any(token in tool_text for token in text.split() if len(token) > 2):
                    recommendations.append(
                        {
                            "server": server.get("name", ""),
                            "tool": tool.get("name", ""),
                            "reason": tool.get("description")
                            or "MCP tool appears relevant to this task.",
                        }
                    )
                if len(recommendations) >= 6:
                    return recommendations
        return recommendations

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
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="artifact.created",
                stage="artifact",
                status="created",
                run_id=str(params.get("_plan_id") or task_id),
                plan_id=str(params.get("_plan_id") or ""),
                step_id=str(params.get("_step_id") or ""),
                task_id=task_id,
                agent_id=params.get("_resolved_agent_id") or params.get("agent_id") or "",
                artifact_id=artifact_id,
                data={"title": artifact.title, "source": artifact.source},
            )
        )
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
        from cognix.scheduler.schedules import next_run_time
        from cognix.storage.database import get_session
        from cognix.storage.models import ScheduledTaskModel, TaskState, TaskType

        task_id = uuid.uuid4().hex[:12]
        schedule = (
            params.get("cron") or params.get("cron_or_interval") or params.get("schedule") or "once"
        )

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
                "plan_id": params.get("_plan_id", ""),
                "step_id": params.get("_step_id", ""),
            }
        )
        next_run = None
        if schedule != "once":
            try:
                next_run = next_run_time(schedule)
            except Exception:
                next_run = None
        task = ScheduledTaskModel(
            id=task_id,
            name=params.get("name", "plan-task"),
            user_id=user_id,
            task_type=TaskType.AGENT_CALL,
            schedule=schedule,
            payload=payload,
            state=TaskState.ACTIVE,
            next_run=next_run,
        )
        async with get_session() as session:
            session.add(task)
        if schedule != "once":
            try:
                from cognix.api.state import get_scheduler_engine, schedule_task_in_engine

                engine = get_scheduler_engine()
                if engine:
                    schedule_task_in_engine(
                        engine, task_id, schedule, json.loads(payload), name=task.name
                    )
            except Exception:
                logger.warning("Failed to register planned task in scheduler", exc_info=True)
        return task_id
