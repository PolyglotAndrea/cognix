"""Task executor for running scheduled tasks."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from cognix.core.registry import AgentRegistry
from cognix.rpc.client import RPCClient

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes tasks of various types."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        rpc_endpoint: str = "http://localhost:8001/rpc",
    ) -> None:
        self.agent_registry = agent_registry
        self.rpc_client = RPCClient(endpoint=rpc_endpoint)
        self._history: dict[str, list[dict[str, Any]]] = {}  # task_id -> runs

    async def execute(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a task based on its type."""
        task_type = payload.get("task_type", "agent_call")
        workspace_id = payload.get("workspace_id")
        user_id = payload.get("user_id")
        start_time = time.monotonic()
        self._append_workspace_event(
            workspace_id,
            {
                "type": "task.started",
                "task_id": task_id,
                "task_type": task_type,
                "payload": self._safe_payload(payload),
            },
        )

        try:
            if task_type == "agent_call":
                result = await self._execute_agent_call(payload)
            elif task_type == "rpc_call":
                result = await self._execute_rpc_call(payload)
            elif task_type == "http_webhook":
                result = await self._execute_http_webhook(payload)
            elif task_type == "skill_exec":
                result = await self._execute_skill(payload)
            elif task_type == "workflow":
                result = await self._execute_workflow(payload)
            else:
                raise ValueError(f"Unknown task type: {task_type}")

            duration_ms = int((time.monotonic() - start_time) * 1000)
            run = {
                "task_id": task_id,
                "status": "success",
                "result": json.dumps(result) if not isinstance(result, str) else result,
                "duration_ms": duration_ms,
                "started_at": datetime.now(UTC).isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "workspace_id": workspace_id,
                "user_id": user_id,
            }

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            run = {
                "task_id": task_id,
                "status": "failure",
                "error": str(e),
                "duration_ms": duration_ms,
                "started_at": datetime.now(UTC).isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "workspace_id": workspace_id,
                "user_id": user_id,
            }
            logger.exception("Task %s failed", task_id)

        # Store in history
        self._history.setdefault(task_id, []).append(run)

        # Persist to DB
        await self._persist_run(run)

        # Flag substantial outputs as playbook candidates
        if run["status"] == "success" and workspace_id:
            result_text = run.get("result", "")
            if isinstance(result_text, str) and len(result_text) > 500:
                await self._flag_playbook_candidate(workspace_id, task_id, result_text)
        self._append_workspace_event(
            workspace_id,
            {
                "type": f"task.{run['status']}",
                "task_id": task_id,
                "task_type": task_type,
                "duration_ms": run["duration_ms"],
                "result": run.get("result", "")[:1000],
                "error": run.get("error", ""),
            },
        )

        return run

    async def _execute_agent_call(self, payload: dict[str, Any]) -> str:
        """Execute an agent call task."""
        from cognix.api.state import get_agent_runtime

        agent_id = payload.get("agent_id")
        message = payload.get("message", "")

        if not agent_id:
            raise ValueError("agent_id required for agent_call task")

        # Entitlement gate: verify user has BYOK or paid plan
        user_id = payload.get("user_id")
        workspace_id = payload.get("workspace_id")
        if user_id:
            from cognix.billing.entitlement import EntitlementService

            entitlement = await EntitlementService.check_model_execution(
                user_id, workspace_id,
            )
            if not entitlement.allowed:
                raise PermissionError(entitlement.reason)

        agent = self.agent_registry.get(agent_id) or await get_agent_runtime(agent_id)
        if not agent:
            raise ValueError(f"Agent '{agent_id}' not found")

        await self._attach_workspace_runtime_tools(agent)
        response = await agent.run(message)
        await self._post_remote_bot_response(payload, response.content)
        return response.content

    async def _execute_rpc_call(self, payload: dict[str, Any]) -> Any:
        """Execute an RPC call task."""
        method = payload.get("method")
        params = payload.get("params", {})

        if not method:
            raise ValueError("method required for rpc_call task")

        return await self.rpc_client.call(method, params)

    async def _execute_http_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute an HTTP webhook task."""
        url = payload.get("url")
        method = payload.get("method", "GET").upper()
        headers = payload.get("headers", {})
        body = payload.get("body")

        if not url:
            raise ValueError("url required for http_webhook task")

        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=body,
                timeout=30,
            )

        return {
            "status_code": resp.status_code,
            "body": resp.text[:1000],
        }

    async def _execute_skill(self, payload: dict[str, Any]) -> Any:
        """Execute a tool from an installed skill."""
        from cognix.config import get_settings
        from cognix.skills.adapter import skill_to_core_tools
        from cognix.skills.manager import SkillsManager

        skill_name = payload.get("skill")
        tool_name = payload.get("tool")
        args = payload.get("args", {})

        if not skill_name:
            raise ValueError("skill required for skill_exec task")

        manager = SkillsManager(local_dir=get_settings().skills.local_dir)
        skill = manager.load(skill_name)
        if not skill:
            raise ValueError(f"Skill '{skill_name}' not found")

        tools = {tool.name: tool for tool in skill_to_core_tools(skill)}
        if not tool_name:
            if len(tools) != 1:
                raise ValueError("tool required when skill exposes multiple tools")
            tool_name = next(iter(tools))

        tool = tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in skill '{skill_name}'")

        self._ensure_tool_allowed(
            permission_mode=payload.get("permission_mode", "workspace-write"),
            access_level=tool.access_level,
            operation=f"scheduled skill tool '{tool.name}'",
        )
        return await tool.execute(**args)

    async def _execute_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a workflow task."""
        from cognix.orchestrator.workflow import execute_workflow, parse_workflow

        workflow_path = payload.get("workflow_path")
        initial_input = payload.get("input", "")

        if not workflow_path:
            raise ValueError("workflow_path required for workflow task")

        workflow = parse_workflow(workflow_path)
        result = await execute_workflow(workflow, self.agent_registry, initial_input=initial_input)
        return {
            "content": result.content,
            "steps": result.steps,
            "metadata": result.metadata,
        }

    async def _persist_run(self, run: dict[str, Any]) -> None:
        """Persist a task run to the database."""
        try:
            from sqlalchemy import update

            from cognix.storage.database import get_session
            from cognix.storage.models import ScheduledTaskModel, TaskRunModel

            async with get_session() as session:
                # Save run record
                db_run = TaskRunModel(
                    task_id=run["task_id"],
                    user_id=run.get("user_id"),
                    status=run["status"],
                    result=run.get("result", ""),
                    error=run.get("error", ""),
                    duration_ms=run.get("duration_ms", 0),
                    started_at=datetime.fromisoformat(run["started_at"]),
                    finished_at=datetime.fromisoformat(run["finished_at"]),
                )
                session.add(db_run)

                # Update task run count and last_run
                await session.execute(
                    update(ScheduledTaskModel)
                    .where(ScheduledTaskModel.id == run["task_id"])
                    .values(
                        run_count=ScheduledTaskModel.run_count + 1,
                        last_run=datetime.now(UTC),
                    )
                )

        except Exception as e:
            logger.error("Failed to persist task run: %s", e)

    def get_history(self, task_id: str) -> list[dict[str, Any]]:
        """Get execution history for a task."""
        return self._history.get(task_id, [])

    @staticmethod
    def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
        redacted = {}
        for key, value in payload.items():
            if "secret" in key.lower() or "token" in key.lower() or "key" in key.lower():
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted

    @staticmethod
    def _append_workspace_event(workspace_id: str | None, event: dict[str, Any]) -> None:
        if not workspace_id:
            return
        try:
            from cognix.local.workspace import WorkspaceManager

            WorkspaceManager().append_event(workspace_id, event)
        except Exception:
            logger.exception("Failed to append workspace task event")

    @staticmethod
    async def _attach_workspace_runtime_tools(agent) -> None:
        from cognix.core.mounts import attach_workspace_runtime_tools

        await attach_workspace_runtime_tools(agent)

    @staticmethod
    def _ensure_tool_allowed(*, permission_mode: str, access_level: str, operation: str) -> None:
        from cognix.core.permissions import ensure_permission

        ensure_permission(permission_mode, access_level, operation)

    @staticmethod
    async def _flag_playbook_candidate(
        workspace_id: str, task_id: str, result_text: str,
    ) -> None:
        """Flag substantial task outputs as playbook candidates."""
        try:
            from sqlalchemy import select, update

            from cognix.storage.database import get_session
            from cognix.storage.models import ArtifactModel

            async with get_session() as session:
                result = await session.execute(
                    select(ArtifactModel).where(ArtifactModel.task_id == task_id)
                )
                artifact = result.scalar_one_or_none()
                if artifact:
                    meta = dict(artifact.metadata_json or {})
                    meta["suggest_playbook"] = True
                    await session.execute(
                        update(ArtifactModel)
                        .where(ArtifactModel.id == artifact.id)
                        .values(metadata_json=meta)
                    )
        except Exception:
            logger.debug("Failed to flag playbook candidate", exc_info=True)

    @staticmethod
    async def _post_remote_bot_response(payload: dict[str, Any], response_text: str) -> None:
        remote_bot = payload.get("remote_bot")
        if not isinstance(remote_bot, dict):
            return

        from cognix.bots.bridge import BotBridgeService, BotMessage
        from cognix.local.bots import BotConfigStore

        bot = BotConfigStore().get(str(remote_bot.get("bot_id", "")))
        if not bot:
            return
        message = BotMessage(
            text=str(payload.get("message", "")),
            sender=str(remote_bot.get("sender", "")),
            chat_id=str(remote_bot.get("chat_id", "")),
            raw={"remote_bot": remote_bot},
        )
        await BotBridgeService().post_response_callback(bot, message, response_text)
