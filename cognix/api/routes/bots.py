"""Remote bot bridge REST and webhook routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
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
async def bot_webhook(provider: BotProvider, bot_id: str, request: Request) -> dict:
    secret = request.query_params.get("secret") or request.headers.get("X-Cognix-Bot-Secret", "")
    payload = await request.json()
    try:
        return await BotBridgeService().handle_webhook(
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
