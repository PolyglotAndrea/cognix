"""Planner service — generates and applies workspace plans from user intent."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.code_sandbox import CodeSandboxStore
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
      "action": "create_agent",
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
  "capability_recommendations": {
    "skills": [],
    "mcp_tools": [],
    "cli_tools": [],
    "connectors": [],
    "memory": []
  },
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
- create_code_project: params = { name, description, files, start_command, auto_start }
- start_code_project: params = { project_id, project_name, command }

Rules:
- Agent Naming: Generate a descriptive semantic name for the agent(s) you create.
  Summarize the user's intent into a brief prefix and combine it with a role suffix
  such as `-task-agent`, `-research-agent`, or `-automation-agent`.
  Examples: `write-blog-task-agent`, `每天发送邮件-automation-agent`.
  Do not use generic names like `task-agent`.
- Prefer one primary agent for simple work.
- Use multiple agents only when distinct roles can run independently or sequentially.
- Use create_task with schedule_type="once" for immediate execution.
- Use create_task with schedule_type="cron" or "interval" only for explicitly recurring work.
- For code app/page/prototype/build requests, prefer create_code_project with runnable files
  and auto_start=true instead of returning code snippets in chat.
- Set expected_artifacts to useful user-facing outputs, never raw logs.
- If a model is not listed as available, use the effective default model from context.
- Treat MCP, skills, CLI, connectors, scheduler, and memory as internal capabilities.
  Describe the user outcome and approval needs, not raw configuration steps.
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
        context = await self._build_workspace_context(workspace_id, user_id)

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
            "code_projects": [],
        }

        ws_config = WorkspaceConfigStore(workspace_id, home=self.home)
        task_steps: list[tuple[str, dict, str]] = []
        agent_name_to_id: dict[str, str] = {}
        code_project_name_to_id: dict[str, str] = {}
        failed_steps: list[str] = []
        failed_step_errors: dict[str, str] = {}

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
            # Check if any dependencies failed
            failed_deps = [dep for dep in step.depends_on if dep in failed_steps]
            if failed_deps:
                logger.warning(
                    "Plan step %s skipped because dependencies failed: %s",
                    step.id,
                    failed_deps,
                )
                plan.step_statuses[step.id] = "failed"
                failed_steps.append(step.id)
                failed_step_errors[step.id] = (
                    f"Dependency step(s) failed: {', '.join(failed_deps)}"
                )
                self._save_plan(plan)
                emit_orchestration_event(
                    OrchestrationEvent(
                        workspace_id=workspace_id,
                        type="plan.step.failed",
                        stage="plan",
                        status="failed",
                        run_id=plan_id,
                        plan_id=plan_id,
                        step_id=step.id,
                        data={
                            "action": step.action,
                            "error": f"Dependency step(s) failed: {', '.join(failed_deps)}",
                        },
                    )
                )
                continue

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
                            data={
                                "name": step.params.get(
                                    "_resolved_agent_name",
                                    step.params.get("name", ""),
                                ),
                                "requested_name": step.params.get("name", ""),
                            },
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
                elif step.action == "create_code_project":
                    project = await self._apply_create_code_project(workspace_id, step.params)
                    created["code_projects"].append(project["id"])
                    project_name = str(step.params.get("name") or "")
                    if project_name:
                        code_project_name_to_id[project_name] = project["id"]
                    emit_orchestration_event(
                        OrchestrationEvent(
                            workspace_id=workspace_id,
                            type="code_project.created",
                            stage="execution",
                            status=project.get("status", "created"),
                            run_id=plan_id,
                            plan_id=plan_id,
                            step_id=step.id,
                            data=project,
                        )
                    )
                elif step.action == "start_code_project":
                    project = await self._apply_start_code_project(
                        workspace_id,
                        step.params,
                        code_project_name_to_id,
                    )
                    if project["id"] not in created["code_projects"]:
                        created["code_projects"].append(project["id"])
                    emit_orchestration_event(
                        OrchestrationEvent(
                            workspace_id=workspace_id,
                            type="code_project.started",
                            stage="execution",
                            status=project.get("status", "running"),
                            run_id=plan_id,
                            plan_id=plan_id,
                            step_id=step.id,
                            data=project,
                        )
                    )
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
                error = str(exc)
                logger.warning("Plan step %s failed: %s", step.id, error)
                plan.step_statuses[step.id] = "failed"
                failed_steps.append(step.id)
                failed_step_errors[step.id] = error
                emit_orchestration_event(
                    OrchestrationEvent(
                        workspace_id=workspace_id,
                        type="plan.step.failed",
                        stage="plan",
                        status="failed",
                        run_id=plan_id,
                        plan_id=plan_id,
                        step_id=step.id,
                        data={"action": step.action, "error": error},
                    )
                )
            self._save_plan(plan)

        # Trigger immediate execution for "once" tasks
        execution_results = []
        artifacts: list[str] = []
        approval_ids: list[str] = []
        needs_input_steps: list[str] = []
        for task_id, params, step_id in task_steps:
            if step_id in failed_steps:
                continue
            schedule = params.get("schedule_type") or params.get("cron") or "once"
            if schedule == "once":
                plan.step_statuses[step_id] = "executing"
                self._save_plan(plan)
                exec_result = await self._trigger_task(task_id, workspace_id)
                execution_results.append({"task_id": task_id, **exec_result})
                task_failed = bool(
                    exec_result.get("status") == "failure" or exec_result.get("error")
                )
                await self._finalize_once_task(task_id, failed=task_failed)
                if exec_result.get("status") == "failure" or exec_result.get("error"):
                    plan.step_statuses[step_id] = "failed"
                    if step_id not in failed_steps:
                        failed_steps.append(step_id)
                    failed_step_errors[step_id] = str(
                        exec_result.get("error")
                        or exec_result.get("result")
                        or "Task execution failed."
                    )
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
                if self._result_blocked_by_capability(exec_result):
                    plan.step_statuses[step_id] = "failed"
                    if step_id not in failed_steps:
                        failed_steps.append(step_id)
                    failed_step_errors[step_id] = (
                        "The selected capability cannot perform this browser action yet. "
                        "Enable a browser runtime/MCP tool or choose a supported execution path."
                    )
                elif self._result_needs_input(exec_result):
                    approval_id = self._create_question_approval(
                        workspace_id=workspace_id,
                        plan_id=plan_id,
                        task_id=task_id,
                        params=params,
                        exec_result=exec_result,
                        artifact_id=artifact_id,
                    )
                    if approval_id:
                        approval_ids.append(approval_id)
                        needs_input_steps.append(step_id)
                self._save_plan(plan)

        plan.status = "failed" if failed_steps else "needs_input" if approval_ids else "applied"
        self._save_plan(plan)
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="execution.failed" if failed_steps else "execution.completed",
                stage="approval" if approval_ids else "execution",
                status="failed" if failed_steps else "needs_input" if approval_ids else "completed",
                run_id=plan_id,
                plan_id=plan_id,
                data={
                    "created": created,
                    "failed_steps": failed_steps,
                    "failed_step_errors": failed_step_errors,
                    "artifacts": artifacts,
                    "approval_ids": approval_ids,
                    "needs_input_steps": needs_input_steps,
                },
            )
        )

        return {
            "plan_id": plan_id,
            "status": plan.status,
            "created": created,
            "execution_results": execution_results,
            "artifacts": artifacts,
            "approval_ids": approval_ids,
            "failed_steps": failed_steps,
            "failed_step_errors": failed_step_errors,
            "plan": plan.to_dict(),
        }

    async def resume_plan_approval(
        self,
        approval_id: str,
        user_id: str,
        response: str | None = None,
    ) -> dict:
        """Continue a plan_apply task after a human answered a question approval."""
        from sqlalchemy import select

        from cognix.local.approvals import ApprovalStore
        from cognix.storage.database import get_session
        from cognix.storage.models import ScheduledTaskModel, TaskState

        store = ApprovalStore()
        if response:
            store.respond(approval_id, response)
        approval = store.get(approval_id)
        if not approval:
            raise FileNotFoundError(f"Approval not found: {approval_id}")
        if approval.metadata.get("source") != "plan_apply":
            raise ValueError("Approval is not a planner task approval")
        if approval.status not in {"approved", "completed"}:
            raise ValueError(f"Approval is not approved (status: {approval.status})")

        workspace_id = approval.workspace_id
        plan_id = str(approval.metadata.get("plan_id") or "")
        task_id = str(approval.metadata.get("task_id") or approval.arguments.get("task_id") or "")
        answer = (response or approval.response or "").strip()
        if not workspace_id or not plan_id or not task_id:
            raise ValueError("Planner approval is missing workspace, plan, or task metadata")
        if not answer:
            raise ValueError("A response is required to continue the planner task")

        plan = self._load_plan(workspace_id, plan_id)
        if not plan:
            raise FileNotFoundError(f"Plan not found: {plan_id}")

        async with get_session() as session:
            result = await session.execute(
                select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                raise FileNotFoundError(f"Task not found: {task_id}")

            payload = json.loads(task.payload or "{}")
            original_message = str(payload.get("message") or "")
            payload["message"] = (
                f"{original_message}\n\n"
                "The user has answered the required follow-up questions. "
                "Use these details to continue the task without asking for the same information again.\n\n"
                f"{answer}"
            ).strip()
            payload["approval_id"] = approval_id
            payload["approval_response"] = answer
            payload["user_id"] = user_id or payload.get("user_id", "")
            task.payload = json.dumps(payload, ensure_ascii=False)
            task.state = TaskState.ACTIVE

        step_id = str(payload.get("step_id") or "")
        params = {
            "name": payload.get("name") or task_id,
            "agent_name": payload.get("agent_name", ""),
            "agent_id": payload.get("agent_id", ""),
            "_resolved_agent_id": payload.get("agent_id", ""),
            "_plan_id": plan_id,
            "_step_id": step_id,
            "schedule_type": "once",
        }

        if step_id:
            plan.step_statuses[step_id] = "executing"
        plan.status = "executing"
        self._save_plan(plan)
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="approval.resumed",
                stage="approval",
                status="running",
                run_id=plan_id,
                plan_id=plan_id,
                step_id=step_id,
                task_id=task_id,
                agent_id=str(payload.get("agent_id") or ""),
                data={"approval_id": approval_id},
            )
        )

        exec_result = await self._trigger_task(task_id, workspace_id)
        task_failed = bool(exec_result.get("status") == "failure" or exec_result.get("error"))
        await self._finalize_once_task(task_id, failed=task_failed)

        artifact_id = exec_result.get("artifact_id") or await self._store_task_artifact(
            workspace_id,
            task_id,
            params,
            exec_result,
        )
        artifacts = [artifact_id] if artifact_id else []
        approval_ids: list[str] = []

        if task_failed:
            if step_id:
                plan.step_statuses[step_id] = "failed"
            plan.status = "failed"
        elif self._result_blocked_by_capability(exec_result):
            if step_id:
                plan.step_statuses[step_id] = "failed"
            plan.status = "failed"
        elif self._result_needs_input(exec_result):
            if step_id:
                plan.step_statuses[step_id] = "completed"
            new_approval_id = self._create_question_approval(
                workspace_id=workspace_id,
                plan_id=plan_id,
                task_id=task_id,
                params=params,
                exec_result=exec_result,
                artifact_id=artifact_id,
            )
            if new_approval_id:
                approval_ids.append(new_approval_id)
            plan.status = "needs_input"
        else:
            if step_id:
                plan.step_statuses[step_id] = "completed"
            plan.status = "applied"

        self._save_plan(plan)
        store.complete(approval_id, "Planner task continued after human input.")
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=workspace_id,
                type="execution.completed" if not task_failed else "execution.failed",
                stage="execution",
                status=plan.status,
                run_id=plan_id,
                plan_id=plan_id,
                step_id=step_id,
                task_id=task_id,
                agent_id=str(payload.get("agent_id") or ""),
                artifact_id=artifact_id,
                data={
                    "approval_id": approval_id,
                    "artifacts": artifacts,
                    "approval_ids": approval_ids,
                    "execution_result": exec_result,
                },
            )
        )

        return {
            "plan_id": plan_id,
            "status": plan.status,
            "created": {},
            "execution_results": [{"task_id": task_id, **exec_result}],
            "artifacts": artifacts,
            "approval_ids": approval_ids,
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

    async def _build_workspace_context(self, workspace_id: str, user_id: str | None = None) -> dict:
        """Load current workspace state for the planner."""
        from cognix.planner.capabilities import CapabilityResolver

        return await CapabilityResolver(home=self.home).resolve(workspace_id, user_id)

    @staticmethod
    def _compact_capability_snapshot(context: dict) -> dict:
        """Persist a small explanation snapshot without storing secrets or large tool schemas."""
        return {
            "provider": context.get("provider", {}),
            "enabled_skills": context.get("enabled_skills", []),
            "installed_skill_count": len(context.get("installed_skills", [])),
            "mcp_server_count": len(context.get("mcp_servers", [])),
            "connector_count": len(context.get("connectors", [])),
            "cli_tool_count": len(context.get("cli_tools", [])),
            "agent_count": len(context.get("agents", [])),
            "memory": context.get("memory", {}),
            "policy": context.get("policy", {}),
            "mcp_servers": [
                {
                    "name": server.get("name", ""),
                    "tool_count": server.get("tool_count", 0),
                    "enabled": server.get("enabled", True),
                }
                for server in context.get("mcp_servers", [])[:10]
            ],
            "connectors": context.get("connectors", [])[:10],
            "cli_tools": context.get("cli_tools", [])[:10],
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
        code_project = any(
            token in text
            for token in (
                "app",
                "website",
                "web app",
                "page",
                "prototype",
                "component",
                "代码工程",
                "项目",
                "页面",
                "网站",
                "小程序",
                "应用",
                "原型",
                "落项目",
                "运行",
                "预览",
            )
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

        # Generate a descriptive semantic name from the user intent
        import re
        tokens = re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', user_intent)
        semantic_prefix = ""
        if tokens:
            semantic_prefix = "-".join(tokens[:3]).lower()
            # Clean and sanitize the prefix
            semantic_prefix = re.sub(r'[^a-z0-9\u4e00-\u9fff-]', '', semantic_prefix)
            semantic_prefix = semantic_prefix[:20].strip("-")

        base_role = (
            "research"
            if research
            else "automation"
            if scheduled or long_running
            else "task"
        )
        agent_name = (
            f"{semantic_prefix}-{base_role}-agent"
            if semantic_prefix
            else f"{base_role}-agent"
        )
        project_name = f"{semantic_prefix}-app" if semantic_prefix else "generated-app"

        if code_project and not scheduled:
            safe_title = user_intent[:80].replace("<", "").replace(">", "")
            fallback_html = "".join(
                [
                    "<!doctype html><html><head><meta charset='utf-8'>",
                    "<meta name='viewport' content='width=device-width,initial-scale=1'>",
                    f"<title>{safe_title}</title>",
                    "<style>",
                    "body{font-family:Inter,system-ui,sans-serif;margin:0;",
                    "background:#f7f7f8;color:#161616}",
                    ".wrap{max-width:900px;margin:0 auto;padding:56px 24px}",
                    ".card{background:white;border:1px solid #e7e7ec;",
                    "border-radius:18px;padding:28px;box-shadow:0 12px 40px #0001}",
                    "h1{font-size:32px;margin:0 0 16px}",
                    "p{line-height:1.7;color:#555}",
                    "</style></head><body><main class='wrap'><section class='card'>",
                    f"<h1>{safe_title}</h1>",
                    "<p>This sandbox project was generated from your request. ",
                    "Use the Apps panel to open the live preview and iterate.</p>",
                    "</section></main></body></html>",
                ]
            )
            return {
                "summary": f"Create and run a sandbox app for: {user_intent[:100]}",
                "intent_type": "file_operation",
                "execution_mode": "once",
                "steps": [
                    {
                        "id": "step_1",
                        "action": "create_code_project",
                        "description": "Create a runnable sandbox project",
                        "params": {
                            "name": project_name,
                            "description": user_intent[:240],
                            "auto_start": True,
                            "files": [
                                {
                                    "path": "index.html",
                                    "content": fallback_html,
                                }
                            ],
                            "metadata": {
                                "intent": user_intent,
                                "planner_fallback": True,
                            },
                        },
                        "depends_on": [],
                    }
                ],
                "required_skills": [],
                "required_connectors": [],
                "sandbox_permissions": ["workspace_write", "command_execution"],
                "expected_artifacts": ["running app preview"],
                "recommended_agents": [],
                "recommended_skills": recommended_skills,
                "recommended_mcp_tools": recommended_mcp_tools,
                "scheduling": {
                    "needed": False,
                    "kind": "once",
                    "expression": "",
                    "reason": "",
                },
                "estimated_cost": "low",
            }

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
        text = user_intent.lower()
        terms = {
            part
            for part in text.replace("/", " ").replace("-", " ").split()
            if len(part) > 2
        }
        if any(
            signal in text
            for signal in (
                "browser",
                "playwright",
                "browser-use",
                "crawl",
                "crawler",
                "scrape",
                "extract",
                "网页",
                "浏览器",
                "采集",
                "爬取",
                "抓取",
                "券码",
            )
        ):
            terms.update(
                {
                    "browser",
                    "automation",
                    "playwright",
                    "browser-use",
                    "crawler",
                    "scrape",
                    "extraction",
                }
            )
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
    async def _finalize_once_task(task_id: str, *, failed: bool) -> None:
        """Immediate planner tasks should not be restored as recurring scheduler work."""
        try:
            from cognix.scheduler.store import TaskStore
            from cognix.storage.models import TaskState

            state = TaskState.FAILED if failed else TaskState.COMPLETED
            await TaskStore().update_state(task_id, state)
            await TaskStore().set_next_run(task_id, None)
        except Exception:
            logger.warning("Failed to finalize immediate task %s", task_id, exc_info=True)

    @staticmethod
    def _result_needs_input(exec_result: dict) -> bool:
        """Detect model output that is asking the user for missing information."""
        if exec_result.get("status") == "failure" or exec_result.get("error"):
            return False
        text = str(exec_result.get("result") or "")
        if not text:
            return False
        if PlannerService._result_blocked_by_capability(exec_result):
            return False
        signals = (
            "请提供",
            "请一次性回复",
            "请明确回复",
            "请说明",
            "请补充",
            "还缺少关键信息",
            "缺少关键信息",
            "等待批准",
            "等待确认",
            "等待你",
            "等待您",
            "人工登录",
            "二次验证",
            "provide",
            "need you to",
            "missing information",
            "waiting for approval",
        )
        lowered = text.lower()
        return any(signal.lower() in lowered for signal in signals)

    @staticmethod
    def _result_blocked_by_capability(exec_result: dict) -> bool:
        """Detect outputs that are blocked by missing execution capability, not user input."""
        if exec_result.get("status") == "failure" or exec_result.get("error"):
            return False
        text = str(exec_result.get("result") or "").lower()
        if not text:
            return False
        blockers = (
            "未暴露可直接实际点击网页",
            "未接入可实际操作页面",
            "未接入实际浏览器执行通道",
            "未提供可直接执行网页操作",
            "无法在本条消息内真正发起浏览器",
            "无法在本轮消息内完成真实页面",
            "只有“规划与结果模板”能力",
            "只能完成合规规划",
            "browser runtime",
            "playwright 执行接口",
            "browser_automation / browser_mcp / playwright",
        )
        return any(signal.lower() in text for signal in blockers)

    @staticmethod
    def _create_question_approval(
        *,
        workspace_id: str,
        plan_id: str,
        task_id: str,
        params: dict,
        exec_result: dict,
        artifact_id: str | None,
    ) -> str | None:
        """Create a human-input request when an executed task asks follow-up questions."""
        try:
            from cognix.local.approvals import ApprovalStore

            output = str(exec_result.get("result") or "")[:4000]
            request = ApprovalStore().create(
                agent_id=params.get("_resolved_agent_id") or params.get("agent_id") or "",
                workspace_id=workspace_id,
                tool_name="user_input",
                arguments={
                    "task_id": task_id,
                    "artifact_id": artifact_id or "",
                    "question": output,
                },
                access_level="user_input",
                reason=output,
                kind="question",
                metadata={
                    "source": "plan_apply",
                    "plan_id": plan_id,
                    "task_id": task_id,
                    "artifact_id": artifact_id or "",
                    "agent_name": params.get("agent_name", ""),
                    "resume_hint": "Provide the missing details, then rerun or continue the plan.",
                },
            )
            return request.id
        except Exception:
            logger.exception("Failed to create follow-up approval for task %s", task_id)
            return None

    async def _apply_create_code_project(self, workspace_id: str, params: dict) -> dict[str, Any]:
        """Create a runnable code project in the workspace sandbox."""
        store = CodeSandboxStore(workspace_id, home=self.home)
        project = store.create_project(
            name=str(params.get("name") or "Generated App"),
            description=str(params.get("description") or ""),
            files=list(params.get("files") or []),
            start_command=str(params.get("start_command") or ""),
            metadata={
                **dict(params.get("metadata") or {}),
                "source": "planner",
            },
        )
        if params.get("auto_start", True):
            project = await store.start_project(project.id)
        return store.to_dict(project)

    async def _apply_start_code_project(
        self,
        workspace_id: str,
        params: dict,
        project_name_to_id: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Start a previously created code project and return its preview metadata."""
        store = CodeSandboxStore(workspace_id, home=self.home)
        project_id = str(params.get("project_id") or "")
        project_name = str(params.get("project_name") or params.get("name") or "")
        if not project_id and project_name and project_name_to_id:
            project_id = project_name_to_id.get(project_name, "")
        if not project_id and project_name:
            existing = next(
                (project for project in store.list_all() if project.name == project_name),
                None,
            )
            project_id = existing.id if existing else ""
        if not project_id:
            raise ValueError("Cannot start code project because no project_id was resolved.")
        project = await store.start_project(project_id, command=str(params.get("command") or ""))
        return store.to_dict(project)

    @staticmethod
    async def _apply_create_agent(workspace_id: str, params: dict) -> str:
        """Create an agent from plan step params."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import AgentModel

        requested_name = params.get("name", "plan-agent")
        async with get_session() as session:
            stmt = select(AgentModel).where(
                AgentModel.name == requested_name,
                AgentModel.workspace_id == workspace_id,
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                logger.info(
                    "Workspace agent '%s' already exists (ID: %s). Reusing.",
                    requested_name,
                    existing.id,
                )
                params["_resolved_agent_name"] = existing.name
                return existing.id

            name = await PlannerService._unique_agent_name(
                session,
                requested_name,
                workspace_id,
            )
            agent_id = uuid.uuid4().hex[:12]
            agent = AgentModel(
                id=agent_id,
                workspace_id=workspace_id,
                name=name,
                model=params.get("model", "gpt-4o"),
                system_prompt=params.get("system_prompt", ""),
            )
            session.add(agent)
            params["_resolved_agent_name"] = name
        return agent_id

    @staticmethod
    async def _unique_agent_name(session: Any, requested_name: str, workspace_id: str) -> str:
        """Return a DB-unique internal agent name without leaking collisions to users."""
        from sqlalchemy import select

        from cognix.storage.models import AgentModel

        res = await session.execute(select(AgentModel).where(AgentModel.name == requested_name))
        if res.scalar_one_or_none() is None:
            return requested_name

        suffix = workspace_id.rsplit("-", 1)[-1][:8] or uuid.uuid4().hex[:6]
        base = f"{requested_name}-{suffix}"
        candidate = base
        counter = 2
        while True:
            res = await session.execute(select(AgentModel).where(AgentModel.name == candidate))
            if res.scalar_one_or_none() is None:
                return candidate
            candidate = f"{base}-{counter}"
            counter += 1

    @staticmethod
    async def _resolve_existing_agent_id(workspace_id: str, agent_name: str) -> str:
        """Resolve a persisted workspace agent by name for plans that reuse agents."""
        if not agent_name:
            return ""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import AgentModel

        async with get_session() as session:
            result = await session.execute(
                select(AgentModel).where(
                    AgentModel.name == agent_name,
                    AgentModel.workspace_id == workspace_id,
                )
            )
            agent = result.scalar_one_or_none()
            return str(agent.id) if agent else ""

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
        if not agent_id and agent_name:
            agent_id = await PlannerService._resolve_existing_agent_id(workspace_id, agent_name)
        if not agent_id:
            raise ValueError(
                "Cannot create agent task because no agent_id was resolved. "
                "Create or reuse an agent before creating an agent_call task."
            )
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
