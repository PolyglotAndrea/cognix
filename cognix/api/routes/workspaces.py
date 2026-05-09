"""Workspace REST routes backed by ~/.cognix."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from cognix.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_skills_read,
    require_skills_write,
)
from cognix.core.agent import Agent
from cognix.core.context import Context
from cognix.core.streaming import encode_sse_event
from cognix.local.attachments import AttachmentStore, ParsedAttachment
from cognix.local.chat import AttachmentRef, ChatMessage, ChatStore
from cognix.local.files import WorkspaceFileStore
from cognix.local.workflows import WorkspaceWorkflowStore
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import WorkspaceConfigStore

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
    enabled_skills: list[str] | None = None
    context: dict | None = None


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


@router.get("")
async def list_workspaces(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [workspace.__dict__ for workspace in WorkspaceManager().list_all()]


@router.post("", status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    workspace = WorkspaceManager().create(body.name, description=body.description)
    return workspace.__dict__


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    workspace = WorkspaceManager().get(workspace_id)
    if not workspace:
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


@router.get("/{workspace_id}/settings")
async def get_workspace_settings(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    return _workspace_config(workspace_id).get_settings()


@router.patch("/{workspace_id}/settings")
async def update_workspace_settings(
    workspace_id: str,
    body: UpdateWorkspaceSettingsRequest,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    updates = body.model_dump(exclude_unset=True)
    return _workspace_config(workspace_id).update_settings(updates)


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
    return {"workspace_id": workspace_id, "skill": skill_name, "enabled": body.enabled, **settings}


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
    default_mcp_runtime.invalidate(server.id)
    return server.__dict__


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
            "description": tool.description,
            "parameters": tool.parameters,
            "access_level": tool.access_level,
        }
        for tool in tools
    ]


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


@router.delete("/{workspace_id}/mcp/servers/{server_id}")
async def delete_workspace_mcp_server(
    workspace_id: str,
    server_id: str,
    user: CurrentUser = Depends(require_skills_write),
) -> dict:
    from cognix.mcp.manager import default_mcp_runtime

    if not _workspace_config(workspace_id).delete_mcp_server(server_id):
        raise HTTPException(404, "MCP server not found")
    default_mcp_runtime.invalidate(server_id)
    return {"deleted": server_id}


@router.post("/{workspace_id}/claude/stream")
async def stream_claude_agent(
    workspace_id: str,
    body: ClaudeAgentRunRequestBody,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    from cognix.claude.runtime import ClaudeAgentRunRequest, ClaudeAgentRuntime

    if not WorkspaceManager().get(workspace_id):
        raise HTTPException(404, "Workspace not found")

    request = ClaudeAgentRunRequest(
        workspace_id=workspace_id,
        prompt=body.prompt,
        agent_id=body.agent_id,
        model=body.model,
        system_prompt=body.system_prompt,
        permission_mode=body.permission_mode,
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
    from cognix.orchestrator.workflow import execute_workflow, parse_workflow

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
    user: CurrentUser = Depends(get_current_user),
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
    user: CurrentUser = Depends(get_current_user),
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
    user: CurrentUser = Depends(get_current_user),
) -> dict:
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
    models = body.models or chat.model_profiles or ["echo"]
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


@router.post("/{workspace_id}/chats/{chat_id}/messages/stream")
async def stream_chat_message(
    workspace_id: str,
    chat_id: str,
    body: SendChatMessageRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    store = _chat_store(workspace_id)
    chat = store.get(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    model = (body.models or chat.model_profiles or ["echo"])[0]
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
        await _prepare_chat_agent(agent, workspace_id)
        assistant_content = ""
        async for event in agent.stream_events(
            body.content,
            context=context,
        ):
            if event.type == "delta":
                assistant_content += event.data.get("delta", "")
            yield encode_sse_event(event, extra={"model": model})
        assistant = store.append_message(
            chat_id,
            role="assistant",
            content=assistant_content,
            model=model,
            parent_id=user_message.id,
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


def _file_store(workspace_id: str) -> WorkspaceFileStore:
    try:
        return WorkspaceFileStore(workspace_id)
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found") from None


def _chat_agent(*, workspace_id: str, name: str, model: str, system_prompt: str) -> Agent:
    agent = Agent(
        name=name,
        model=model,
        system_prompt=system_prompt,
        workspace_id=workspace_id,
    )
    _attach_workspace_skills(agent, workspace_id)
    return agent


async def _prepare_chat_agent(agent: Agent, workspace_id: str) -> Agent:
    from cognix.mcp.adapter import attach_workspace_mcp_tools

    await attach_workspace_mcp_tools(agent, workspace_id)
    return agent


def _attach_workspace_skills(agent: Agent, workspace_id: str) -> None:
    from cognix.config import get_settings
    from cognix.skills.adapter import skill_to_core_tools
    from cognix.skills.manager import SkillsManager

    enabled_skills = _workspace_config(workspace_id).get_settings().get("enabled_skills", [])
    if not enabled_skills:
        return

    manager = SkillsManager(local_dir=get_settings().skills.local_dir)
    for skill_name in enabled_skills:
        skill = manager.load(skill_name)
        if not skill:
            continue
        for tool in skill_to_core_tools(skill):
            if tool.name in [existing.name for existing in agent.tools]:
                agent.remove_tool(tool.name)
            agent.add_tool(tool)


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
