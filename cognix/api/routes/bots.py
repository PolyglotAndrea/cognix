"""Remote bot bridge REST and webhook routes."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from cognix.auth.dependencies import CurrentUser, get_current_user, require_agents_write
from cognix.bots.bridge import BotBridgeService
from cognix.local.bots import BotConfigStore

router = APIRouter(prefix="/api/v1/bots", tags=["bots"])

BotProvider = Literal["lark", "feishu", "dingtalk", "wechat"]


class CreateBotRequest(BaseModel):
    name: str
    provider: BotProvider
    workspace_id: str
    agent_id: str
    secret: str = Field(min_length=6)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateBotRequest(BaseModel):
    name: str | None = None
    workspace_id: str | None = None
    agent_id: str | None = None
    secret: str | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


@router.get("")
async def list_bots(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [bot.public_dict() for bot in BotConfigStore().list_all()]


@router.post("", status_code=201)
async def create_bot(
    body: CreateBotRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    bot = BotConfigStore().create(
        name=body.name,
        provider=body.provider,
        workspace_id=body.workspace_id,
        agent_id=body.agent_id,
        secret=body.secret,
        enabled=body.enabled,
        metadata=body.metadata,
    )
    return bot.public_dict()


@router.patch("/{bot_id}")
async def update_bot(
    bot_id: str,
    body: UpdateBotRequest,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    try:
        bot = BotConfigStore().update(bot_id, body.model_dump(exclude_unset=True))
    except FileNotFoundError:
        raise HTTPException(404, "Bot bridge not found") from None
    return bot.public_dict()


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: str,
    user: CurrentUser = Depends(require_agents_write),
) -> dict:
    if not BotConfigStore().delete(bot_id):
        raise HTTPException(404, "Bot bridge not found")
    return {"deleted": bot_id}


@router.post("/{provider}/{bot_id}/webhook")
async def bot_webhook(
    provider: BotProvider,
    bot_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    async_dispatch: bool = Query(False, alias="async"),
) -> dict:
    store = BotConfigStore()
    bot = store.get(bot_id)
    if not bot or bot.provider != provider:
        raise HTTPException(404, "Bot bridge not found")

    body = await request.body()
    secret = request.query_params.get("secret") or request.headers.get("X-Cognix-Bot-Secret", "")
    timestamp, signature = _signature_parts(provider, request)
    require_signature = bool(bot.metadata.get("require_signature", False))
    if require_signature and not signature:
        raise HTTPException(401, "Missing bot bridge signature")
    if signature and not store.verify_signature(
        bot,
        body=body,
        timestamp=timestamp,
        signature=signature,
        tolerance_seconds=300,
    ):
        raise HTTPException(401, "Invalid bot bridge signature")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid JSON payload") from exc

    service = BotBridgeService(store=store)
    challenge = service.challenge_response(provider, payload)
    if challenge:
        return challenge
    if not bot.enabled:
        return {"ok": False, "message": "Bot bridge disabled"}
    if not store.verify_secret(bot, secret):
        raise HTTPException(401, "Invalid bot bridge secret")
    if async_dispatch:
        background_tasks.add_task(
            service.handle_webhook,
            provider=provider,
            bot_id=bot_id,
            secret=secret,
            payload=payload,
        )
        return {"ok": True, "queued": True}

    try:
        return await service.handle_webhook(
            provider=provider,
            bot_id=bot_id,
            secret=secret,
            payload=payload,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Bot bridge not found") from None
    except PermissionError:
        raise HTTPException(401, "Invalid bot bridge secret") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def _signature_parts(provider: str, request: Request) -> tuple[str, str]:
    headers = request.headers
    query = request.query_params
    timestamp = (
        headers.get("X-Cognix-Timestamp")
        or headers.get("X-Lark-Request-Timestamp")
        or headers.get("X-Lark-Timestamp")
        or headers.get("X-Dingtalk-Timestamp")
        or headers.get("X-WeChat-Timestamp")
        or query.get("timestamp")
        or ""
    )
    signature = (
        headers.get("X-Cognix-Signature")
        or headers.get("X-Lark-Signature")
        or headers.get("X-Dingtalk-Signature")
        or headers.get("X-WeChat-Signature")
        or query.get("sign")
        or query.get("signature")
        or ""
    )
    if provider in ("lark", "feishu"):
        signature = signature or headers.get("X-Lark-Request-Signature", "")
    return timestamp, signature
