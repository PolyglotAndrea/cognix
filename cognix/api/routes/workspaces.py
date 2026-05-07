"""Workspace REST routes backed by ~/.cognix."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.core.agent import Agent
from cognix.core.context import Context
from cognix.local.attachments import AttachmentStore, ParsedAttachment
from cognix.local.chat import AttachmentRef, ChatMessage, ChatStore
from cognix.local.workspace import WorkspaceManager

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
    user_message = store.append_message(
        chat_id,
        role="user",
        content=body.content,
        attachments=attachments,
    )

    async def event_generator():
        agent = Agent(
            name=f"chat-{model}",
            model=model,
            system_prompt=chat.system_prompt or "You are a helpful assistant.",
            workspace_id=workspace_id,
        )
        assistant_content = ""
        async for event in agent.stream_events(
            body.content,
            context=_history_context(history, attachment_context=attachment_context),
        ):
            if event.type == "delta":
                assistant_content += event.data.get("delta", "")
            payload = {"type": event.type, "model": model, **event.data}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
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


async def _run_model_response(
    *,
    workspace_id: str,
    chat_id: str,
    user_content: str,
    model: str,
    system_prompt: str,
    parent_id: str,
    history: list[ChatMessage],
    attachment_context: str = "",
) -> dict:
    store = ChatStore(workspace_id)
    agent = Agent(
        name=f"chat-{model}",
        model=model,
        system_prompt=system_prompt or "You are a helpful assistant.",
        workspace_id=workspace_id,
    )
    response = await agent.run(
        user_content,
        context=_history_context(history, attachment_context=attachment_context),
    )
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
        return store.ingest_inline(
            name=item.name,
            content=item.content,
            mime_type=item.mime_type,
            kind=item.kind,
            metadata=metadata,
        )
    return store.ingest_path(item.path, metadata=metadata)


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


def _message_to_dict(message) -> dict:
    data = message.__dict__.copy()
    data["attachments"] = [attachment.__dict__ for attachment in message.attachments]
    return data
