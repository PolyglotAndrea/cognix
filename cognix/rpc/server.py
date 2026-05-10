"""JSON-RPC 2.0 server implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

from cognix.core.registry import AgentRegistry

logger = logging.getLogger(__name__)


class RPCError(Exception):
    """JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
FORBIDDEN = -32003


# Method registry
_handlers: dict[str, Any] = {}
_method_permissions: dict[str, str] = {
    "agent.chat": "agents:write",
    "agent.create": "agents:write",
    "agent.delete": "agents:write",
    "agent.list": "agents:read",
    "task.create": "tasks:write",
    "task.delete": "tasks:write",
    "task.list": "tasks:read",
    "task.pause": "tasks:write",
    "task.resume": "tasks:write",
    "task.runs": "tasks:read",
    "task.trigger": "tasks:write",
    "workflow.list": "agents:read",
    "workflow.run": "agents:write",
}


def rpc_method(name: str):
    """Decorator to register an RPC method."""

    def decorator(func):
        _handlers[name] = func
        return func

    return decorator


@rpc_method("agent.chat")
async def _agent_chat(params: dict, registry: AgentRegistry) -> dict:
    from cognix.api.state import get_agent_runtime

    agent = await get_agent_runtime(params["agent_id"])
    if not agent:
        raise RPCError(METHOD_NOT_FOUND, f"Agent '{params['agent_id']}' not found")
    await _attach_runtime_mcp_tools(agent)
    response = await agent.run(params["message"])
    return {"content": response.content, "usage": response.usage}


@rpc_method("agent.list")
async def _agent_list(params: dict, registry: AgentRegistry) -> list[dict]:
    from cognix.api.state import list_agent_runtimes

    return await list_agent_runtimes()


@rpc_method("agent.create")
async def _agent_create(params: dict, registry: AgentRegistry) -> dict:
    from cognix.core.agent import Agent
    from cognix.core.memory import SQLiteBackend
    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    agent = Agent(
        name=params["name"],
        model=params.get("model", "gpt-4o"),
        system_prompt=params.get("system_prompt", "You are a helpful assistant."),
        description=params.get("description", ""),
        temperature=params.get("temperature", 0.7),
        max_iterations=params.get("max_iterations", 10),
        api_base=params.get("api_base"),
        workspace_id=params.get("workspace_id"),
        permission_mode=params.get("permission_mode", "workspace-write"),
    )
    agent.memory = SQLiteBackend(agent_id=agent.id)
    registry.register(agent)

    async with get_session() as session:
        db_agent = AgentModel(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            model=agent.model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            max_iterations=agent.max_iterations,
            api_base=agent.api_base,
            workspace_id=agent.workspace_id,
            permission_mode=agent.permission_mode,
        )
        session.add(db_agent)

    return agent.to_dict()


@rpc_method("agent.delete")
async def _agent_delete(params: dict, registry: AgentRegistry) -> dict:
    from sqlalchemy import delete

    from cognix.api.state import get_agent_runtime
    from cognix.storage.database import get_session
    from cognix.storage.models import AgentModel

    agent = await get_agent_runtime(params["agent_id"])
    if not agent:
        raise RPCError(METHOD_NOT_FOUND, f"Agent '{params['agent_id']}' not found")
    registry.unregister(agent.id)

    async with get_session() as session:
        await session.execute(delete(AgentModel).where(AgentModel.id == agent.id))

    return {"deleted": agent.id}


@rpc_method("system.ping")
async def _ping(params: dict, registry: AgentRegistry) -> str:
    return "pong"


@rpc_method("system.methods")
async def _list_methods(params: dict, registry: AgentRegistry) -> list[str]:
    """List all available RPC methods."""
    return sorted(_handlers.keys())


# ── Task methods ────────────────────────────────────────────────────


@rpc_method("task.create")
async def _task_create(params: dict, registry: AgentRegistry) -> dict:
    import uuid

    from cognix.api.state import get_scheduler_engine, schedule_task_in_engine
    from cognix.scheduler.store import TaskStore
    from cognix.storage.models import TaskType

    task_id = uuid.uuid4().hex[:12]
    store = TaskStore()

    task_type = TaskType(params.get("task_type", "agent_call"))
    payload = {**params.get("payload", {}), "task_type": task_type.value}
    schedule = params["schedule"]
    name = params.get("name", task_id)
    await store.create(
        task_id=task_id,
        name=name,
        task_type=task_type,
        schedule=schedule,
        payload=payload,
        max_retries=params.get("max_retries", 3),
    )

    engine = get_scheduler_engine()
    if engine:
        schedule_task_in_engine(engine, task_id, schedule, payload, name=name)

    return {"id": task_id, "name": name, "state": "active"}


@rpc_method("task.list")
async def _task_list(params: dict, registry: AgentRegistry) -> list[dict]:
    from cognix.scheduler.store import TaskStore

    store = TaskStore()
    tasks = await store.list_all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "task_type": t.task_type.value,
            "schedule": t.schedule,
            "state": t.state.value,
            "run_count": t.run_count,
        }
        for t in tasks
    ]


@rpc_method("task.delete")
async def _task_delete(params: dict, registry: AgentRegistry) -> dict:
    from cognix.api.state import get_scheduler_engine
    from cognix.scheduler.store import TaskStore

    task_id = params["task_id"]
    engine = get_scheduler_engine()
    if engine:
        engine.remove(task_id)

    if not await TaskStore().delete(task_id):
        raise RPCError(METHOD_NOT_FOUND, f"Task '{task_id}' not found")

    return {"deleted": task_id}


@rpc_method("task.pause")
async def _task_pause(params: dict, registry: AgentRegistry) -> dict:
    from cognix.api.state import get_scheduler_engine
    from cognix.scheduler.store import TaskStore
    from cognix.storage.models import TaskState

    task_id = params["task_id"]
    if not await TaskStore().update_state(task_id, TaskState.PAUSED):
        raise RPCError(METHOD_NOT_FOUND, f"Task '{task_id}' not found")

    engine = get_scheduler_engine()
    if engine:
        engine.pause(task_id)

    return {"id": task_id, "state": "paused"}


@rpc_method("task.resume")
async def _task_resume(params: dict, registry: AgentRegistry) -> dict:
    from cognix.api.state import get_scheduler_engine, schedule_task_in_engine
    from cognix.scheduler.store import TaskStore
    from cognix.storage.models import TaskState

    task_id = params["task_id"]
    store = TaskStore()
    if not await store.update_state(task_id, TaskState.ACTIVE):
        raise RPCError(METHOD_NOT_FOUND, f"Task '{task_id}' not found")

    task = await store.get(task_id)
    engine = get_scheduler_engine()
    if engine and task:
        payload = _payload_dict(task.payload)
        schedule_task_in_engine(engine, task.id, task.schedule, payload, name=task.name)
        engine.resume(task_id)

    return {"id": task_id, "state": "active"}


@rpc_method("task.trigger")
async def _task_trigger(params: dict, registry: AgentRegistry) -> dict:
    from cognix.scheduler.executor import TaskExecutor
    from cognix.scheduler.store import TaskStore

    task_id = params["task_id"]
    store = TaskStore()
    task = await store.get(task_id)
    if not task:
        raise RPCError(METHOD_NOT_FOUND, f"Task '{task_id}' not found")

    payload = _payload_dict(task.payload)
    executor = TaskExecutor(agent_registry=registry)
    return await executor.execute(task_id, payload)


@rpc_method("task.runs")
async def _task_runs(params: dict, registry: AgentRegistry) -> list[dict]:
    from cognix.scheduler.store import TaskStore

    task_id = params["task_id"]
    runs = await TaskStore().get_runs(task_id, limit=params.get("limit", 20))
    return [
        {
            "id": r.id,
            "status": r.status,
            "result": r.result[:2000] if r.result else "",
            "error": r.error,
            "duration_ms": r.duration_ms,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in runs
    ]


# ── Workflow methods ────────────────────────────────────────────────


@rpc_method("workflow.list")
async def _workflow_list(params: dict, registry: AgentRegistry) -> list[dict]:
    from pathlib import Path

    from cognix.orchestrator.workflow import parse_workflow

    directory = params.get("directory", "./workflows")
    workflows_dir = Path(directory)
    if not workflows_dir.exists():
        return []

    results = []
    for f in list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml")):
        try:
            wf = parse_workflow(f)
            results.append({"file": f.name, "name": wf.name, "steps": len(wf.steps)})
        except Exception:
            pass
    return results


@rpc_method("workflow.run")
async def _workflow_run(params: dict, registry: AgentRegistry) -> dict:
    from cognix.orchestrator.workflow import execute_workflow, parse_workflow

    workflow_path = params["path"]
    initial_input = params.get("input", "")

    workflow = parse_workflow(workflow_path)
    result = await execute_workflow(workflow, registry, initial_input=initial_input)
    return {"content": result.content, "steps": result.steps}


async def handle_rpc(body: Any, registry: AgentRegistry, user: Any = None) -> Any:
    """Handle a JSON-RPC 2.0 request or batch of requests."""
    # Batch request
    if isinstance(body, list):
        results = []
        for item in body:
            result = await _handle_single(item, registry, user=user)
            if result:  # Skip empty responses (notifications)
                results.append(result)
        return results

    # Single request
    return await _handle_single(body, registry, user=user)


async def _handle_single(body: dict, registry: AgentRegistry, user: Any = None) -> dict:
    """Handle a single JSON-RPC 2.0 request."""
    # Validate basic structure
    jsonrpc = body.get("jsonrpc")
    if jsonrpc != "2.0":
        return _error_response(None, INVALID_REQUEST, "Invalid JSON-RPC version")

    method = body.get("method")
    if not method:
        return _error_response(body.get("id"), INVALID_REQUEST, "Missing method")

    params = body.get("params", {})
    req_id = body.get("id")

    # Is this a notification (no id)?
    is_notification = req_id is None

    handler = _handlers.get(method)
    if not handler:
        if is_notification:
            return {}
        return _error_response(req_id, METHOD_NOT_FOUND, f"Method '{method}' not found")

    try:
        _ensure_rpc_permission(method, user)
        result = await handler(params, registry)
    except RPCError as e:
        if is_notification:
            return {}
        return _error_response(req_id, e.code, e.message, e.data)
    except Exception as e:
        logger.exception("RPC handler error for method %s", method)
        if is_notification:
            return {}
        return _error_response(req_id, INTERNAL_ERROR, str(e))

    if is_notification:
        return {}

    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": req_id,
    }


def rpc_permission(method: str) -> str | None:
    """Return the RBAC permission required by a JSON-RPC method."""
    return _method_permissions.get(method)


def _ensure_rpc_permission(method: str, user: Any = None) -> None:
    if user is None:
        return

    permission = rpc_permission(method)
    if not permission:
        return

    from cognix.auth.dependencies import has_permission

    role = getattr(getattr(user, "role", ""), "value", getattr(user, "role", ""))
    if not has_permission(str(role), permission):
        raise RPCError(FORBIDDEN, f"Permission required: {permission}")


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload or {}


async def _attach_runtime_mcp_tools(agent) -> None:
    if not getattr(agent, "workspace_id", None):
        return
    from cognix.core.mounts import attach_workspace_runtime_tools

    await attach_workspace_runtime_tools(agent, agent.workspace_id)


def _error_response(
    req_id: Any, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "error": error, "id": req_id}
