"""Workspace REST routes backed by ~/.cognix."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from starlette.responses import StreamingResponse

from cognix.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_agents_write,
    require_skills_read,
    require_skills_write,
)
from cognix.config import get_settings
from cognix.core.agent import Agent, AgentEvent
from cognix.core.context import Context
from cognix.core.streaming import encode_sse_event
from cognix.local.attachments import AttachmentStore, ParsedAttachment
from cognix.local.chat import AttachmentRef, ChatMessage, ChatStore
from cognix.local.files import WorkspaceFileStore
from cognix.local.runs import ConversationRunStore
from cognix.local.workflows import WorkspaceWorkflowStore
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import WorkspaceConfigStore
from cognix.providers.resolver import normalize_openai_base_url
from cognix.storage.database import get_session
from cognix.storage.models import (
    ArtifactModel,
    ArtifactType,
    ScheduledTaskModel,
    TaskRunModel,
    TaskState,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""


class CreateChatRequest(BaseModel):
    title: str = "New Chat"
    system_prompt: str = ""
    model_profiles: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class UpdateChatRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    model_profiles: list[str] | None = None
    metadata: dict | None = None


class UpdateWorkspaceSettingsRequest(BaseModel):
    default_model: str | None = None
    llm: dict | None = None
    enabled_skills: list[str] | None = None
    context: dict | None = None
    ui_mode: str | None = None
    onboarding_completed: bool | None = None


class SetWorkspaceSkillRequest(BaseModel):
    enabled: bool = True


class UpsertMCPServerRequest(BaseModel):
    id: str | None = None
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class InvokeMCPToolRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)
    permission_mode: str = "workspace-write"


class BrowserMCPPresetRequest(BaseModel):
    enabled: bool = True
    profile: str = "default"


class BrowserAutomationRunRequest(BaseModel):
    objective: str
    url: str
    engine: str = "playwright"
    profile: str = "default"
    selectors: dict[str, str] = Field(default_factory=dict)
    extract_text: bool = True
    extract_links: bool = True
    extract_tables: bool = True
    screenshot: bool = False
    wait_for_selector: str = ""
    cdp_endpoint: str = ""
    permission_mode: str = "workspace-write"
    approval_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    plan_id: str = ""


class ToggleMCPToolRequest(BaseModel):
    tool_name: str
    enabled: bool = True


class ClaudeAgentRunRequestBody(BaseModel):
    prompt: str
    agent_id: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    permission_mode: str = "workspace-write"
    max_turns: int | None = None
    resume: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)


class SaveWorkflowRequest(BaseModel):
    name: str
    definition: str
    id: str | None = None


class RunWorkflowRequest(BaseModel):
    input: str = ""


class WriteWorkspaceFileRequest(BaseModel):
    path: str
    content: str


class CodeProjectFileRequest(BaseModel):
    path: str
    content: str = ""


class CreateCodeProjectRequest(BaseModel):
    name: str
    description: str = ""
    files: list[CodeProjectFileRequest] = Field(default_factory=list)
    start_command: str = ""
    metadata: dict = Field(default_factory=dict)


class StartCodeProjectRequest(BaseModel):
    command: str = ""


class AttachmentRequest(BaseModel):
    id: str | None = None
    name: str
    path: str
    mime_type: str = "application/octet-stream"
    size: int = 0
    kind: str = "file"
    content: str | None = None
    metadata: dict = Field(default_factory=dict)


class SendChatMessageRequest(BaseModel):
    content: str
    models: list[str] = Field(default_factory=list)
    attachments: list[AttachmentRequest] = Field(default_factory=list)


class AppendRawMessageRequest(BaseModel):
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)


class CreateConversationRunRequest(BaseModel):
    chat_id: str
    raw_intent: str
    locale: str = ""
    timezone: str = ""
    state: str = "intent_received"
    sources: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class UpdateConversationRunRequest(BaseModel):
    state: str | None = None
    intent: dict | None = None
    sources: list[dict] | None = None
    capabilities: list[dict] | None = None
    requirements: list[dict] | None = None
    plan_id: str | None = None
    execution_id: str | None = None
    artifact_ids: list[str] | None = None
    promotion_candidates: dict | None = None
    metadata: dict | None = None
    event_type: str | None = None
    event_data: dict = Field(default_factory=dict)


@router.get("")
async def list_workspaces(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    manager = WorkspaceManager()
    workspaces = manager.list_all(owner_id=user.id)
    if not workspaces:
        workspaces = [
            manager.create(
                "My Workspace",
                description="Default workspace",
                owner_id=user.id,
            )
        ]
    return [workspace.__dict__ for workspace in workspaces]


@router.post("", status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    workspace = WorkspaceManager().create(
        body.name,
        description=body.description,
        owner_id=user.id,
    )
    return workspace.__dict__


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    workspace = WorkspaceManager().get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if workspace.owner_id != user.id:
        raise HTTPException(404, "Workspace not found")
    return workspace.__dict__


@router.get("/{workspace_id}/events")
async def list_workspace_events(
    workspace_id: str,
    limit: int = 100,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    manager = WorkspaceManager()
    if not manager.get(workspace_id):
        raise HTTPException(404, "Workspace not found")
    return manager.list_events(workspace_id, limit=limit)


@router.get("/{workspace_id}/orchestration/snapshots")
async def list_orchestration_snapshots(
    workspace_id: str,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    manager = WorkspaceManager()
    if not manager.get(workspace_id):
        raise HTTPException(404, "Workspace not found")
    from dataclasses import asdict

    from cognix.orchestrator.protocol import OrchestrationSnapshotStore

    return [
        asdict(snapshot)
        for snapshot in OrchestrationSnapshotStore().list(workspace_id, limit=limit)
    ]


@router.get("/{workspace_id}/orchestration/snapshots/{run_id}")
async def get_orchestration_snapshot(
    workspace_id: str,
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    manager = WorkspaceManager()
    if not manager.get(workspace_id):
        raise HTTPException(404, "Workspace not found")
    from dataclasses import asdict

    from cognix.orchestrator.protocol import OrchestrationSnapshotStore

    snapshot = OrchestrationSnapshotStore().get(workspace_id, run_id)
    if not snapshot:
        raise HTTPException(404, "Orchestration snapshot not found")
    return asdict(snapshot)


@router.get("/{workspace_id}/settings")
async def get_workspace_settings(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    settings = _workspace_config(workspace_id).get_settings()
    # Mask API key in LLM settings for display
    llm = settings.get("llm", {})
    if llm.get("api_key"):
        key = llm["api_key"]
        settings["llm"] = {**llm, "api_key": key[:3] + "***" if len(key) > 3 else "***"}
    return settings


@router.patch("/{workspace_id}/settings")
async def update_workspace_settings(
    workspace_id: str,
    body: UpdateWorkspaceSettingsRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    updates = body.model_dump(exclude_unset=True)
    # Don't overwrite real API key with masked value from GET response
    llm = updates.get("llm")
    if llm and isinstance(llm, dict):
        api_key = llm.get("api_key", "")
        if isinstance(api_key, str) and api_key.endswith("***"):
            llm.pop("api_key", None)
        if "base_url" in llm:
            llm["base_url"] = normalize_openai_base_url(llm.get("base_url"))
    settings = _workspace_config(workspace_id).update_settings(updates)
    llm = settings.get("llm", {})
    if llm.get("api_key"):
        key = llm["api_key"]
        settings["llm"] = {**llm, "api_key": key[:3] + "***" if len(key) > 3 else "***"}
    return settings


@router.get("/{workspace_id}/llm")
async def get_workspace_llm(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return resolved LLM config for a workspace (workspace overrides + global fallback)."""
    llm = resolve_workspace_llm(workspace_id)
    key = llm.get("api_key")
    return {
        "base_url": llm["base_url"],
        "api_key": (key[:3] + "***" if len(key) > 3 else "***") if key else None,
        "default_model": llm["default_model"],
    }


@router.get("/{workspace_id}/skills")
async def list_workspace_skills(
    workspace_id: str,
    user: CurrentUser = Depends(require_skills_read),
) -> list[dict]:
    from cognix.config import get_settings
    from cognix.skills.manager import SkillsManager

    settings = _workspace_config(workspace_id).get_settings()
    enabled = set(settings.get("enabled_skills", []))
    manager = SkillsManager(local_dir=get_settings().skills.local_dir)
    return [{**skill, "enabled": skill["name"] in enabled} for skill in manager.list_installed()]


@router.put("/{workspace_id}/skills/{skill_name}")
async def set_workspace_skill(
    workspace_id: str,
    skill_name: str,
    body: SetWorkspaceSkillRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.config import get_settings
    from cognix.skills.manager import SkillsManager

    manager = SkillsManager(local_dir=get_settings().skills.local_dir)
    if not manager.load(skill_name):
        raise HTTPException(404, "Skill not found")
    settings = _workspace_config(workspace_id).set_skill_enabled(skill_name, body.enabled)
    response = {"workspace_id": workspace_id, "skill": skill_name, "enabled": body.enabled, **settings}

    if skill_name == "browser_automation":
        from cognix.api.state import agent_registry
        from cognix.core.mounts import attach_browser_automation_tool

        affected_agents: list[str] = []
        for row in agent_registry.list_all():
            if row.get("workspace_id") != workspace_id:
                continue
            agent = agent_registry.get(str(row.get("id") or ""))
            if not agent:
                continue
            if body.enabled:
                attach_browser_automation_tool(agent, workspace_id)
            elif "browser_automation" in [tool.name for tool in agent.tools]:
                agent.remove_tool("browser_automation")
            affected_agents.append(agent.id)
        response["runtime"] = {
            "browser_automation": body.enabled,
            "engines": ["playwright", "cdp", "browser_use"],
            "attached_agents": affected_agents,
            "note": (
                "Browser automation is an internal runtime capability. The skill toggle "
                "enables planner routing and refreshes currently loaded workspace agents."
            ),
        }

    return response


@router.get("/{workspace_id}/mcp/servers")
async def list_workspace_mcp_servers(
    workspace_id: str,
    user: CurrentUser = Depends(require_skills_read),
) -> list[dict]:
    return [server.__dict__ for server in _workspace_config(workspace_id).list_mcp_servers()]


@router.post("/{workspace_id}/mcp/servers", status_code=201)
async def upsert_workspace_mcp_server(
    workspace_id: str,
    body: UpsertMCPServerRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    server = _workspace_config(workspace_id).upsert_mcp_server(
        server_id=body.id,
        name=body.name,
        command=body.command,
        args=body.args,
        env=body.env,
        enabled=body.enabled,
        metadata=body.metadata,
    )
    await default_mcp_runtime.invalidate(server.id)
    return server.__dict__


@router.post("/{workspace_id}/browser/mcp-preset", status_code=201)
async def ensure_browser_mcp_preset(
    workspace_id: str,
    body: BrowserMCPPresetRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    """Provision the internal Browser MCP preset for a workspace."""
    from cognix.browser.service import BrowserAutomationService
    from cognix.mcp.manager import default_mcp_runtime

    server = BrowserAutomationService(workspace_id).ensure_mcp_preset(
        enabled=body.enabled,
        profile=body.profile,
    )
    await default_mcp_runtime.invalidate(server.id)
    return server.__dict__


@router.get("/{workspace_id}/browser/profile")
async def get_browser_profile_status(
    workspace_id: str,
    profile: str = "default",
    user: CurrentUser = Depends(require_skills_read),
) -> dict:
    """Return the isolated browser profile status for a workspace."""
    from cognix.browser.service import BrowserAutomationService

    return BrowserAutomationService(workspace_id).profile_status(profile)


@router.post("/{workspace_id}/browser/run")
async def run_browser_automation(
    workspace_id: str,
    body: BrowserAutomationRunRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Run or approval-gate a workspace browser automation task."""
    from cognix.browser.service import BrowserAutomationRun, BrowserAutomationService
    from cognix.core.permissions import clamp_permission_mode

    engine = body.engine if body.engine in {"playwright", "cdp", "browser_use"} else "playwright"
    request = BrowserAutomationRun(
        objective=body.objective,
        url=body.url,
        engine=engine,  # type: ignore[arg-type]
        profile=body.profile,
        selectors=body.selectors,
        extract_text=body.extract_text,
        extract_links=body.extract_links,
        extract_tables=body.extract_tables,
        screenshot=body.screenshot,
        wait_for_selector=body.wait_for_selector,
        cdp_endpoint=body.cdp_endpoint,
        permission_mode=clamp_permission_mode(body.permission_mode, user.role),
        approval_id=body.approval_id,
        task_id=body.task_id,
        agent_id=body.agent_id,
        plan_id=body.plan_id,
    )
    try:
        return await BrowserAutomationService(workspace_id).run(request, user_id=user.id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None


@router.get("/{workspace_id}/mcp/servers/{server_id}/tools")
async def list_workspace_mcp_tools(
    workspace_id: str,
    server_id: str,
    user: CurrentUser = Depends(require_skills_read),
) -> list[dict]:
    from cognix.mcp.adapter import mcp_server_to_core_tools
    from cognix.mcp.manager import default_mcp_runtime

    servers = _workspace_config(workspace_id).list_mcp_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")
    tools = await mcp_server_to_core_tools(server, runtime=default_mcp_runtime)
    return [
        {
            "name": tool.name,
            "original_name": tool.metadata.get("original_name", tool.name),
            "description": tool.description,
            "parameters": tool.parameters,
            "access_level": tool.access_level,
        }
        for tool in tools
    ]


@router.post("/{workspace_id}/mcp/servers/{server_id}/tools/{tool_name}/call")
async def call_workspace_mcp_tool(
    workspace_id: str,
    server_id: str,
    tool_name: str,
    body: InvokeMCPToolRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.core.permissions import PermissionDeniedError, ensure_permission
    from cognix.core.policy import WorkspacePolicyService
    from cognix.mcp.adapter import mcp_server_to_core_tools
    from cognix.mcp.manager import default_mcp_runtime

    servers = _workspace_config(workspace_id).list_mcp_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")

    tools = await mcp_server_to_core_tools(server, runtime=default_mcp_runtime)
    tool = next(
        (
            item
            for item in tools
            if (
                item.name == tool_name
                or item.name.endswith(f"_{tool_name}")
                or tool_name == item.name.split("_")[-1]
            )
        ),
        None,
    )
    if not tool:
        raise HTTPException(404, "MCP tool not found or disabled")

    policy_result = await WorkspacePolicyService(workspace_id).check_mcp_tool(
        tool.name,
        tool.access_level,
        permission_mode=body.permission_mode,
        user_id=user.id,
    )
    if not policy_result.allowed:
        if policy_result.requires_approval:
            raise HTTPException(
                409,
                {
                    "code": "approval_required",
                    "message": policy_result.reason or "MCP tool requires approval by policy.",
                },
            )
        raise HTTPException(403, policy_result.reason or "MCP tool denied by policy")

    try:
        ensure_permission(
            body.permission_mode,
            tool.access_level,
            f"call MCP tool '{tool.name}'",
        )
    except PermissionDeniedError as exc:
        raise HTTPException(403, str(exc)) from None

    result = await tool.execute(**body.arguments)
    return {
        "server_id": server.id,
        "tool": tool.name,
        "access_level": tool.access_level,
        "result": result,
    }


@router.put("/{workspace_id}/mcp/servers/{server_id}/tools/{tool_name}")
async def toggle_workspace_mcp_tool(
    workspace_id: str,
    server_id: str,
    tool_name: str,
    body: ToggleMCPToolRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    config_store = _workspace_config(workspace_id)
    server = next((s for s in config_store.list_mcp_servers() if s.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")

    # Verify the tool actually exists on the server
    try:
        specs = await default_mcp_runtime.list_tools(server, force_refresh=True)
    except Exception as exc:
        raise HTTPException(502, f"Failed to discover tools from MCP server: {exc}") from exc
    known_names = {spec.name for spec in specs}
    if tool_name not in known_names:
        raise HTTPException(
            404,
            f"Tool '{tool_name}' not found on server. Available: {sorted(known_names)}",
        )

    updated = config_store.set_mcp_tool_enabled(server_id, tool_name, body.enabled)
    if not updated:
        raise HTTPException(404, f"Tool '{tool_name}' not found on server")
    await default_mcp_runtime.invalidate(server_id)
    return {
        "server_id": server_id,
        "tool_name": tool_name,
        "enabled": body.enabled,
        "disabled_tools": updated.metadata.get("disabled_tools", []),
    }


@router.get("/{workspace_id}/mcp/servers/{server_id}/status")
async def get_workspace_mcp_server_status(
    workspace_id: str,
    server_id: str,
    refresh: bool = False,
    user: CurrentUser = Depends(require_skills_read),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    servers = _workspace_config(workspace_id).list_mcp_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")
    if refresh:
        return (await default_mcp_runtime.probe(server)).to_dict()
    return default_mcp_runtime.status(server).to_dict()


@router.post("/{workspace_id}/mcp/servers/{server_id}/restart")
async def restart_workspace_mcp_server(
    workspace_id: str,
    server_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    servers = _workspace_config(workspace_id).list_mcp_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")
    return (await default_mcp_runtime.restart(server)).to_dict()


@router.post("/{workspace_id}/mcp/servers/{server_id}/stop")
async def stop_workspace_mcp_server(
    workspace_id: str,
    server_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    servers = _workspace_config(workspace_id).list_mcp_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if not server:
        raise HTTPException(404, "MCP server not found")
    return (await default_mcp_runtime.stop(server)).to_dict()


@router.delete("/{workspace_id}/mcp/servers/{server_id}")
async def delete_workspace_mcp_server(
    workspace_id: str,
    server_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    if not _workspace_config(workspace_id).delete_mcp_server(server_id):
        raise HTTPException(404, "MCP server not found")
    await default_mcp_runtime.invalidate(server_id)
    return {"deleted": server_id}


@router.get("/{workspace_id}/code-projects")
async def list_code_projects(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    from cognix.local.code_sandbox import CodeSandboxStore

    try:
        store = CodeSandboxStore(workspace_id)
        return [store.to_dict(project) for project in store.list_all()]
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/{workspace_id}/code-projects", status_code=201)
async def create_code_project(
    workspace_id: str,
    body: CreateCodeProjectRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.local.code_sandbox import CodeSandboxStore

    try:
        project = CodeSandboxStore(workspace_id).create_project(
            name=body.name,
            description=body.description,
            files=[item.model_dump() for item in body.files],
            start_command=body.start_command,
            metadata=body.metadata,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return CodeSandboxStore.to_dict(project)


@router.post("/{workspace_id}/code-projects/{project_id}/start")
async def start_code_project(
    workspace_id: str,
    project_id: str,
    body: StartCodeProjectRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.core.policy import WorkspacePolicyService
    from cognix.local.code_sandbox import CodeSandboxStore

    command = body.command or "workspace preview"
    policy = await WorkspacePolicyService(workspace_id).check_command(
        command,
        permission_mode="workspace-write",
        user_id=user.id,
    )
    if not policy.allowed and not policy.requires_approval:
        raise HTTPException(403, policy.reason or "Code preview denied by workspace policy")
    try:
        project = await CodeSandboxStore(workspace_id).start_project(
            project_id,
            command=body.command,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return CodeSandboxStore.to_dict(project)


@router.post("/{workspace_id}/code-projects/{project_id}/stop")
async def stop_code_project(
    workspace_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.local.code_sandbox import CodeSandboxStore

    try:
        project = CodeSandboxStore(workspace_id).stop_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return CodeSandboxStore.to_dict(project)


@router.get("/{workspace_id}/code-projects/{project_id}/logs")
async def get_code_project_logs(
    workspace_id: str,
    project_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    from cognix.local.code_sandbox import CodeSandboxStore

    try:
        logs = CodeSandboxStore(workspace_id).logs(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return {"project_id": project_id, "logs": logs}


@router.post("/{workspace_id}/claude/stream")
async def stream_claude_agent(
    workspace_id: str,
    body: ClaudeAgentRunRequestBody,
    user: CurrentUser = Depends(require_agents_write),
) -> StreamingResponse:
    from cognix.billing.entitlement import EntitlementService
    from cognix.claude.runtime import ClaudeAgentRunRequest, ClaudeAgentRuntime
    from cognix.core.permissions import clamp_permission_mode

    entitlement = await EntitlementService.check_model_execution(user.id, workspace_id)
    if not entitlement.allowed:
        raise HTTPException(402, detail=entitlement.to_dict())

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    # Server-side ceiling: prevent client from escalating beyond role-allowed level
    effective_mode = clamp_permission_mode(body.permission_mode, user.role)

    # Resolve workspace LLM for model fallback
    ws_llm = resolve_workspace_llm(workspace_id)
    effective_model = body.model or ws_llm["default_model"]

    request = ClaudeAgentRunRequest(
        workspace_id=workspace_id,
        prompt=body.prompt,
        agent_id=body.agent_id,
        model=effective_model,
        system_prompt=body.system_prompt,
        permission_mode=effective_mode,
        max_turns=body.max_turns,
        resume=body.resume,
        allowed_tools=body.allowed_tools,
        disallowed_tools=body.disallowed_tools,
    )

    async def event_generator():
        async for event in ClaudeAgentRuntime().stream(request):
            yield encode_sse_event(event, extra={"runtime": "claude-agent-sdk"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{workspace_id}/workflows")
async def list_workspace_workflows(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = _workflow_store(workspace_id)
    return [store.to_dict(workflow) for workflow in store.list_all()]


@router.post("/{workspace_id}/workflows", status_code=201)
async def save_workspace_workflow(
    workspace_id: str,
    body: SaveWorkflowRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    store = _workflow_store(workspace_id)
    workflow = store.save(name=body.name, definition=body.definition, workflow_id=body.id)
    return store.to_dict(workflow)


@router.get("/{workspace_id}/workflows/{workflow_id}")
async def get_workspace_workflow(
    workspace_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    store = _workflow_store(workspace_id)
    try:
        workflow = store.describe(workflow_id)
        return {**store.to_dict(workflow), "definition": store.get_definition(workflow_id)}
    except FileNotFoundError:
        raise HTTPException(404, "Workflow not found") from None


@router.delete("/{workspace_id}/workflows/{workflow_id}")
async def delete_workspace_workflow(
    workspace_id: str,
    workflow_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    if not _workflow_store(workspace_id).delete(workflow_id):
        raise HTTPException(404, "Workflow not found")
    return {"deleted": workflow_id}


@router.post("/{workspace_id}/workflows/{workflow_id}/run")
async def run_workspace_workflow(
    workspace_id: str,
    workflow_id: str,
    body: RunWorkflowRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.api.state import agent_registry
    from cognix.billing.entitlement import EntitlementService
    from cognix.orchestrator.workflow import execute_workflow, parse_workflow

    entitlement = await EntitlementService.check_model_execution(user.id, workspace_id)
    if not entitlement.allowed:
        raise HTTPException(402, detail=entitlement.to_dict())

    store = _workflow_store(workspace_id)
    try:
        workflow_info = store.describe(workflow_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workflow not found") from None
    if workflow_info.errors:
        raise HTTPException(400, {"errors": workflow_info.errors})

    workflow = parse_workflow(workflow_info.path)
    result = await execute_workflow(workflow, agent_registry, initial_input=body.input)
    return {
        "content": result.content,
        "steps": result.steps,
        "metadata": result.metadata,
    }


@router.get("/{workspace_id}/files")
async def list_workspace_files(
    workspace_id: str,
    path: str = "",
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = _file_store(workspace_id)
    try:
        return [store.to_dict(item) for item in store.list(path)]
    except FileNotFoundError:
        raise HTTPException(404, "Directory not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/{workspace_id}/files/preview")
async def preview_workspace_file(
    workspace_id: str,
    path: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    from cognix.core.policy import WorkspacePolicyService

    policy_result = await WorkspacePolicyService(workspace_id).check_file_access(
        path,
        "read",
        permission_mode="read-only",
        user_id=user.id,
    )
    if not policy_result.allowed:
        raise HTTPException(403, policy_result.reason or "File read denied by policy")
    store = _file_store(workspace_id)
    try:
        return {"path": path, "content": store.read_text(path)}
    except FileNotFoundError:
        raise HTTPException(404, "File not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.put("/{workspace_id}/files")
async def write_workspace_file(
    workspace_id: str,
    body: WriteWorkspaceFileRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.core.policy import WorkspacePolicyService

    policy_result = await WorkspacePolicyService(workspace_id).check_file_access(
        body.path,
        "write",
        permission_mode="workspace-write",
        user_id=user.id,
    )
    if not policy_result.allowed or policy_result.requires_approval:
        raise HTTPException(
            403 if not policy_result.requires_approval else 409,
            policy_result.reason or "File write denied by workspace policy",
        )
    store = _file_store(workspace_id)
    try:
        return store.to_dict(store.write_text(body.path, body.content))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.delete("/{workspace_id}/files")
async def delete_workspace_file(
    workspace_id: str,
    path: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.core.policy import WorkspacePolicyService

    policy_result = await WorkspacePolicyService(workspace_id).check_file_access(
        path,
        "delete",
        permission_mode="workspace-write",
        user_id=user.id,
    )
    if not policy_result.allowed or policy_result.requires_approval:
        raise HTTPException(
            403 if not policy_result.requires_approval else 409,
            policy_result.reason or "File delete denied by workspace policy",
        )
    store = _file_store(workspace_id)
    try:
        if not store.delete(path):
            raise HTTPException(404, "File not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"deleted": path}


@router.get("/{workspace_id}/chats")
async def list_chats(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = _chat_store(workspace_id)
    return [chat.__dict__ for chat in store.list_all()]


@router.post("/{workspace_id}/chats", status_code=201)
async def create_chat(
    workspace_id: str,
    body: CreateChatRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    store = _chat_store(workspace_id)
    chat = store.create(
        title=body.title,
        system_prompt=body.system_prompt,
        model_profiles=body.model_profiles,
        metadata=body.metadata,
    )
    return chat.__dict__


@router.get("/{workspace_id}/chats/{chat_id}")
async def get_chat(
    workspace_id: str,
    chat_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    store = _chat_store(workspace_id)
    chat = store.get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    return chat.__dict__


@router.patch("/{workspace_id}/chats/{chat_id}")
async def update_chat(
    workspace_id: str,
    chat_id: str,
    body: UpdateChatRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    store = _chat_store(workspace_id)
    try:
        chat = store.update(
            chat_id,
            title=body.title,
            system_prompt=body.system_prompt,
            model_profiles=body.model_profiles,
            metadata=body.metadata,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Chat not found") from None
    return chat.__dict__


@router.delete("/{workspace_id}/chats/{chat_id}", status_code=204)
async def delete_chat(
    workspace_id: str,
    chat_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> None:
    store = _chat_store(workspace_id)
    try:
        store.delete(chat_id)
    except FileNotFoundError:
        raise HTTPException(404, "Chat not found") from None


@router.get("/{workspace_id}/runs")
async def list_conversation_runs(
    workspace_id: str,
    chat_id: str | None = None,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = ConversationRunStore(workspace_id)
    return [run.to_dict() for run in store.list_all(chat_id=chat_id, limit=limit)]


@router.post("/{workspace_id}/runs", status_code=201)
async def create_conversation_run(
    workspace_id: str,
    body: CreateConversationRunRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    chat_store = _chat_store(workspace_id)
    if not chat_store.get(body.chat_id):
        raise HTTPException(404, "Chat not found")
    store = ConversationRunStore(workspace_id)
    try:
        run = store.create(
            chat_id=body.chat_id,
            user_id=user.id,
            raw_intent=body.raw_intent,
            locale=body.locale,
            timezone=body.timezone,
            sources=body.sources,
            metadata=body.metadata,
            state=body.state,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return run.to_dict()


@router.get("/{workspace_id}/runs/latest")
async def get_latest_conversation_run(
    workspace_id: str,
    chat_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    store = ConversationRunStore(workspace_id)
    run = store.latest(chat_id=chat_id)
    if not run:
        raise HTTPException(404, "Conversation run not found")
    return run.to_dict()


@router.get("/{workspace_id}/runs/{run_id}")
async def get_conversation_run(
    workspace_id: str,
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    store = ConversationRunStore(workspace_id)
    run = store.get(run_id)
    if not run:
        raise HTTPException(404, "Conversation run not found")
    return run.to_dict()


@router.patch("/{workspace_id}/runs/{run_id}")
async def update_conversation_run(
    workspace_id: str,
    run_id: str,
    body: UpdateConversationRunRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    store = ConversationRunStore(workspace_id)
    try:
        run = store.update(
            run_id,
            state=body.state,
            intent=body.intent,
            sources=body.sources,
            capabilities=body.capabilities,
            requirements=body.requirements,
            plan_id=body.plan_id,
            execution_id=body.execution_id,
            artifact_ids=body.artifact_ids,
            promotion_candidates=body.promotion_candidates,
            metadata=body.metadata,
            event_type=body.event_type,
            event_data=body.event_data,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Conversation run not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return run.to_dict()


@router.get("/{workspace_id}/chats/{chat_id}/messages")
async def list_chat_messages(
    workspace_id: str,
    chat_id: str,
    limit: int | None = None,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    store = _chat_store(workspace_id)
    try:
        return [_message_to_dict(message) for message in store.list_messages(chat_id, limit=limit)]
    except FileNotFoundError:
        raise HTTPException(404, "Chat not found") from None


@router.post("/{workspace_id}/chats/{chat_id}/messages")
async def send_chat_message(
    workspace_id: str,
    chat_id: str,
    body: SendChatMessageRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    from cognix.billing.entitlement import EntitlementService

    entitlement = await EntitlementService.check_model_execution(user.id, workspace_id)
    if not entitlement.allowed:
        raise HTTPException(402, detail=entitlement.to_dict())

    store = _chat_store(workspace_id)
    chat = store.get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    attachments = _attachments_from_requests(workspace_id, body.attachments)
    attachment_context = _attachment_context(attachments)
    history = store.list_messages(chat_id, limit=20)
    user_message = store.append_message(
        chat_id,
        role="user",
        content=body.content,
        attachments=attachments,
    )
    ws_llm = resolve_workspace_llm(workspace_id)
    if not ws_llm.get("api_key"):
        raise HTTPException(400, "No model provider API key is configured")
    models = body.models or chat.model_profiles or [ws_llm["default_model"]]
    responses = await asyncio.gather(
        *[
            _run_model_response(
                workspace_id=workspace_id,
                chat_id=chat_id,
                user_content=body.content,
                model=model,
                system_prompt=chat.system_prompt,
                parent_id=user_message.id,
                history=history,
                attachment_context=attachment_context,
                attachments=attachments,
            )
            for model in models
        ]
    )
    return {
        "user_message": _message_to_dict(user_message),
        "assistant_messages": responses,
    }


@router.post("/{workspace_id}/chats/{chat_id}/messages/raw")
async def append_raw_chat_message(
    workspace_id: str,
    chat_id: str,
    body: AppendRawMessageRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    store = _chat_store(workspace_id)
    chat = store.get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    message = store.append_message(
        chat_id,
        role=body.role,
        content=body.content,
        metadata=body.metadata,
    )
    return _message_to_dict(message)


@router.post("/{workspace_id}/chats/{chat_id}/messages/stream")
async def stream_chat_message(
    workspace_id: str,
    chat_id: str,
    body: SendChatMessageRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> StreamingResponse:
    from cognix.billing.entitlement import EntitlementService

    entitlement = await EntitlementService.check_model_execution(user.id, workspace_id)
    if not entitlement.allowed:
        raise HTTPException(402, detail=entitlement.to_dict())

    store = _chat_store(workspace_id)
    chat = store.get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    ws_llm = resolve_workspace_llm(workspace_id)
    if not ws_llm.get("api_key"):
        raise HTTPException(400, "No model provider API key is configured")
    model = (body.models or chat.model_profiles or [ws_llm["default_model"]])[0]
    attachments = _attachments_from_requests(workspace_id, body.attachments)
    attachment_context = _attachment_context(attachments)
    history = store.list_messages(chat_id, limit=20)
    context = _history_context(history, attachment_context=attachment_context)
    _set_multimodal_user_content(context, body.content, attachments)
    user_message = store.append_message(
        chat_id,
        role="user",
        content=body.content,
        attachments=attachments,
    )

    async def event_generator():
        agent = _chat_agent(
            workspace_id=workspace_id,
            name=f"chat-{model}",
            model=model,
            system_prompt=chat.system_prompt or "You are a helpful assistant.",
        )
        yield encode_sse_event(
            AgentEvent(
                "status",
                {
                    "stage": "planning",
                    "message": (
                        "Preparing workspace context, attachments, tools, "
                        "and model provider."
                    ),
                },
            ),
            extra={"model": model},
        )
        yield encode_sse_event(
            AgentEvent(
                "todo",
                {
                    "items": [
                        {"id": "context", "label": "Load workspace chat context", "status": "done"},
                        {
                            "id": "attachments",
                            "label": "Parse attached files and images",
                            "status": "done",
                        },
                        {
                            "id": "provider",
                            "label": "Resolve provider and selected model",
                            "status": "done",
                        },
                        {"id": "execute", "label": "Run model stream", "status": "running"},
                        {"id": "persist", "label": "Save assistant response", "status": "pending"},
                    ]
                },
            ),
            extra={"model": model},
        )
        await _prepare_chat_agent(agent, workspace_id)
        yield encode_sse_event(
            AgentEvent(
                "status",
                {"stage": "executing", "message": f"Streaming response from {model}."},
            ),
            extra={"model": model},
        )
        assistant_content = ""
        stream_failed = False
        async for event in agent.stream_events(
            body.content,
            context=context,
        ):
            if event.type == "delta":
                assistant_content += event.data.get("delta", "")
            elif event.type == "error":
                stream_failed = True
            yield encode_sse_event(event, extra={"model": model})
        if stream_failed:
            return
        yield encode_sse_event(
            AgentEvent(
                "todo",
                {
                    "items": [
                        {"id": "context", "label": "Load workspace chat context", "status": "done"},
                        {
                            "id": "attachments",
                            "label": "Parse attached files and images",
                            "status": "done",
                        },
                        {
                            "id": "provider",
                            "label": "Resolve provider and selected model",
                            "status": "done",
                        },
                        {"id": "execute", "label": "Run model stream", "status": "done"},
                        {"id": "persist", "label": "Save assistant response", "status": "running"},
                    ]
                },
            ),
            extra={"model": model},
        )
        assistant = store.append_message(
            chat_id,
            role="assistant",
            content=assistant_content,
            model=model,
            parent_id=user_message.id,
        )
        yield encode_sse_event(
            AgentEvent("status", {"stage": "saved", "message": "Assistant response saved."}),
            extra={"model": model},
        )
        yield (
            "data: "
            + json.dumps(
                {"type": "message_saved", "message": _message_to_dict(assistant)},
                ensure_ascii=False,
            )
            + "\n\n"
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _chat_store(workspace_id: str) -> ChatStore:
    try:
        return ChatStore(workspace_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found") from None


def _workspace_config(workspace_id: str) -> WorkspaceConfigStore:
    try:
        return WorkspaceConfigStore(workspace_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found") from None


def _workflow_store(workspace_id: str) -> WorkspaceWorkflowStore:
    try:
        return WorkspaceWorkflowStore(workspace_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found") from None


def _payload_dict(payload) -> dict:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload or {}


def _file_store(workspace_id: str) -> WorkspaceFileStore:
    try:
        return WorkspaceFileStore(workspace_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found") from None


def resolve_workspace_llm(workspace_id: str) -> dict:
    """Resolve effective LLM config for a workspace. Delegates to unified resolver."""
    from cognix.providers.resolver import resolve_provider

    provider = resolve_provider(workspace_id)
    return {
        "base_url": provider.base_url,
        "api_key": provider.api_key,
        "default_model": provider.default_model,
    }


def _chat_agent(*, workspace_id: str, name: str, model: str, system_prompt: str) -> Agent:
    from cognix.providers.resolver import resolve_provider

    provider = resolve_provider(workspace_id)
    agent = Agent(
        name=name,
        model=model or provider.default_model,
        system_prompt=system_prompt,
        workspace_id=workspace_id,
        api_key=provider.api_key,
        api_base=provider.base_url,
    )
    return agent


async def _prepare_chat_agent(agent: Agent, workspace_id: str) -> Agent:
    from cognix.core.mounts import attach_workspace_runtime_tools

    await attach_workspace_runtime_tools(agent, workspace_id)
    return agent


async def _run_model_response(
    *,
    workspace_id: str,
    chat_id: str,
    user_content: str,
    model: str,
    system_prompt: str,
    parent_id: str,
    history: list[ChatMessage],
    attachment_context: str,
    attachments: list[AttachmentRef],
) -> dict:
    store = ChatStore(workspace_id)
    agent = _chat_agent(
        workspace_id=workspace_id,
        name=f"chat-{model}",
        model=model,
        system_prompt=system_prompt or "You are a helpful assistant.",
    )
    await _prepare_chat_agent(agent, workspace_id)
    context = _history_context(history, attachment_context=attachment_context)
    _set_multimodal_user_content(context, user_content, attachments)
    response = await agent.run(user_content, context=context)
    assistant = store.append_message(
        chat_id,
        role="assistant",
        content=response.content,
        model=model,
        parent_id=parent_id,
        metadata={"usage": response.usage},
    )
    return _message_to_dict(assistant)


def _history_context(messages: list[ChatMessage], *, attachment_context: str = "") -> Context:
    ctx = Context()
    if attachment_context:
        ctx.add_message("system", attachment_context)
    for message in messages:
        if message.role in ("user", "assistant", "system", "tool"):
            ctx.add_message(message.role, message.content)
    return ctx


def _attachments_from_requests(
    workspace_id: str,
    items: list[AttachmentRequest],
) -> list[AttachmentRef]:
    store = AttachmentStore(workspace_id)
    attachments = []
    for item in items:
        parsed = _parse_attachment_request(store, item)
        attachments.append(parsed.to_ref())
    return attachments


def _parse_attachment_request(
    store: AttachmentStore,
    item: AttachmentRequest,
) -> ParsedAttachment:
    metadata = {"client_id": item.id, **item.metadata}
    if item.content is not None:
        if item.mime_type.startswith("image/") or item.kind == "image":
            return store.ingest_inline_bytes(
                name=item.name,
                content=_decode_inline_content(item.content),
                mime_type=item.mime_type,
                kind="image",
                metadata=metadata,
            )
        return store.ingest_inline(
            name=item.name,
            content=item.content,
            mime_type=item.mime_type,
            kind=item.kind,
            metadata=metadata,
        )
    return store.ingest_path(item.path, metadata=metadata)


def _decode_inline_content(content: str) -> bytes:
    if content.startswith("data:"):
        _, encoded = content.split(",", 1)
        return base64.b64decode(encoded)
    return base64.b64decode(content)


def _attachment_context(attachments: list[AttachmentRef]) -> str:
    snippets = []
    for attachment in attachments:
        text = str(attachment.metadata.get("extracted_text", "")).strip()
        if not text:
            continue
        snippets.append(f"## {attachment.name}\n{text[:4000]}")
    if not snippets:
        return ""
    return "Attached file excerpts:\n\n" + "\n\n".join(snippets)


def _set_multimodal_user_content(
    context: Context,
    text: str,
    attachments: list[AttachmentRef],
) -> None:
    image_parts = []
    for attachment in attachments:
        if not attachment.mime_type.startswith("image/"):
            continue
        path = Path(attachment.path)
        if not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        image_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{attachment.mime_type};base64,{encoded}"},
            }
        )

    if image_parts:
        context.metadata["next_user_content"] = [
            {"type": "text", "text": text},
            *image_parts,
        ]


def _message_to_dict(message) -> dict:
    data = message.__dict__.copy()
    data["attachments"] = [attachment.__dict__ for attachment in message.attachments]
    return data


# ── Policy endpoints ───────────────────────────────────────────────


@router.get("/{workspace_id}/policy")
async def get_workspace_policy(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get workspace sandbox policy settings."""
    store = _workspace_config(workspace_id)
    settings = store.get_settings()
    return settings.get("policy", {})


class UpdatePolicyRequest(BaseModel):
    file_write: str | None = None
    network_access: str | None = None
    mcp_tools: str | None = None
    connector_access: str | None = None
    max_file_size_mb: int | None = None
    allowed_domains: list[str] | None = None
    blocked_commands: list[str] | None = None


@router.patch("/{workspace_id}/policy")
async def update_workspace_policy(
    workspace_id: str,
    body: UpdatePolicyRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    """Update workspace sandbox policy settings."""
    store = _workspace_config(workspace_id)
    updates = {"policy": body.model_dump(exclude_unset=True)}
    store.update_settings(updates)
    return store.get_settings().get("policy", {})


@router.post("/{workspace_id}/onboarding/complete")
async def complete_onboarding(
    workspace_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    """Mark onboarding as completed and optionally set UI mode."""
    store = _workspace_config(workspace_id)
    store.update_settings({"onboarding_completed": True})
    return {"workspace_id": workspace_id, "onboarding_completed": True}


@router.delete("/{workspace_id}/dev/history")
async def clear_workspace_dev_history(
    workspace_id: str,
    failed_only: bool = True,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    """Dev-only cleanup for stale local task/artifact output in the current workspace."""
    if not get_settings().debug:
        raise HTTPException(404, "Not found")
    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    artifact_ids: list[str] = []
    task_ids: list[str] = []
    async with get_session() as session:
        artifact_stmt = select(ArtifactModel).where(ArtifactModel.workspace_id == workspace_id)
        if failed_only:
            artifact_stmt = artifact_stmt.where(
                (ArtifactModel.artifact_type == ArtifactType.LOG)
                | (ArtifactModel.title.ilike("%error%"))
                | (ArtifactModel.title.ilike("%failed%"))
            )
        artifact_rows = (await session.execute(artifact_stmt)).scalars().all()
        artifact_ids = [row.id for row in artifact_rows]
        if artifact_ids:
            await session.execute(delete(ArtifactModel).where(ArtifactModel.id.in_(artifact_ids)))

        task_rows = (await session.execute(select(ScheduledTaskModel))).scalars().all()
        for task in task_rows:
            payload = _payload_dict(task.payload)
            if payload.get("workspace_id") != workspace_id:
                continue
            if failed_only and task.state not in (TaskState.FAILED, TaskState.CANCELED):
                continue
            task_ids.append(task.id)
        if task_ids:
            await session.execute(delete(TaskRunModel).where(TaskRunModel.task_id.in_(task_ids)))
            await session.execute(
                delete(ScheduledTaskModel).where(ScheduledTaskModel.id.in_(task_ids))
            )

    return {
        "workspace_id": workspace_id,
        "failed_only": failed_only,
        "deleted_artifacts": len(artifact_ids),
        "deleted_tasks": len(task_ids),
    }


@router.get("/{workspace_id}/audit-log")
async def get_policy_audit_log(
    workspace_id: str,
    agent_id: str | None = None,
    decision: str | None = None,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Get policy audit log for a workspace."""
    from cognix.storage.models import PolicyAuditLogModel

    async with get_session() as session:
        stmt = select(PolicyAuditLogModel).where(
            PolicyAuditLogModel.workspace_id == workspace_id,
        )
        if agent_id:
            stmt = stmt.where(PolicyAuditLogModel.agent_id == agent_id)
        if decision:
            stmt = stmt.where(PolicyAuditLogModel.decision == decision)
        stmt = stmt.order_by(PolicyAuditLogModel.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "agent_id": r.agent_id,
            "operation": r.operation,
            "access_level": r.access_level,
            "permission_mode": r.permission_mode,
            "decision": r.decision,
            "reason": r.reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
