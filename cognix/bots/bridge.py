"""Remote bot message normalization and dispatch."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from cognix.api.state import get_agent_runtime
from cognix.core.context import Context
from cognix.local.bots import BotConfig, BotConfigStore
from cognix.local.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

# Retry defaults for direct dispatch and callback delivery
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0  # seconds


@dataclass(frozen=True)
class BotMessage:
    text: str
    sender: str = ""
    chat_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class BotBridgeService:
    """Routes remote robot messages into local Agent workflows."""

    def __init__(self, *, store: BotConfigStore | None = None) -> None:
        self.store = store or BotConfigStore()

    async def handle_webhook(
        self,
        *,
        provider: str,
        bot_id: str,
        secret: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        bot = self.store.get(bot_id)
        if not bot or bot.provider != provider:
            raise FileNotFoundError(f"Bot bridge not found: {bot_id}")
        if not bot.enabled:
            return {"ok": False, "message": "Bot bridge disabled"}
        if not self.store.verify_secret(bot, secret):
            raise PermissionError("Invalid bot bridge secret")

        challenge = self.challenge_response(provider, payload)
        if challenge:
            return challenge

        message = self.extract_message(provider, payload)
        if not message.text.strip():
            return self.format_response(provider, "No message text found.")

        if str(bot.metadata.get("dispatch_mode", "")).lower() in {"task", "async_task"}:
            task_id = await self.enqueue_task(bot, message)
            return self.format_response(provider, f"Task queued: {task_id}")

        response = await self.dispatch(bot, message)
        return self.format_response(provider, response)

    async def enqueue_task(self, bot: BotConfig, message: BotMessage) -> str:
        """Queue a remote bot message as a one-shot scheduled Agent task."""
        from cognix.api.state import get_scheduler_engine, schedule_task_in_engine
        from cognix.scheduler.store import TaskStore
        from cognix.storage.models import TaskType

        run_at = datetime.now(UTC) + timedelta(seconds=1)
        task_id = f"bot-{uuid.uuid4().hex[:12]}"
        payload = {
            "task_type": "agent_call",
            "agent_id": bot.agent_id,
            "workspace_id": bot.workspace_id,
            "message": message.text,
            "remote_bot": {
                "provider": bot.provider,
                "bot_id": bot.id,
                "sender": message.sender,
                "chat_id": message.chat_id,
                "session_key": self.session_key(bot, message),
            },
        }
        schedule = run_at.isoformat()
        await TaskStore().create(
            task_id=task_id,
            name=f"{bot.provider}:{bot.name}",
            task_type=TaskType.AGENT_CALL,
            schedule=schedule,
            payload=payload,
            max_retries=int(bot.metadata.get("task_max_retries", 1)),
        )
        engine = get_scheduler_engine()
        if engine:
            schedule_task_in_engine(engine, task_id, schedule, payload, name=f"{bot.provider}:{bot.name}")

        try:
            WorkspaceManager().append_event(
                bot.workspace_id,
                {
                    "type": "bot.task_queued",
                    "provider": bot.provider,
                    "bot_id": bot.id,
                    "agent_id": bot.agent_id,
                    "task_id": task_id,
                    "sender": message.sender,
                    "chat_id": message.chat_id,
                    "session_key": self.session_key(bot, message),
                    "message": message.text,
                },
            )
        except Exception:
            logger.exception("Failed to append bot task queue event")
        return task_id

    async def dispatch(self, bot: BotConfig, message: BotMessage) -> str:
        max_attempts = int(bot.metadata.get("dispatch_max_retries", _RETRY_MAX_ATTEMPTS))
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self._dispatch_once(bot, message)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Bot dispatch attempt %s/%s failed for %s: %s; retrying in %.1fs",
                        attempt, max_attempts, bot.id, exc, delay,
                    )
                    await asyncio.sleep(delay)
        logger.error("Bot dispatch failed after %s attempts for %s", max_attempts, bot.id)
        raise last_exc  # type: ignore[misc]

    async def _dispatch_once(self, bot: BotConfig, message: BotMessage) -> str:
        agent = await get_agent_runtime(bot.agent_id)
        if not agent:
            raise ValueError(f"Agent '{bot.agent_id}' not found")
        agent.workspace_id = bot.workspace_id
        await self.attach_workspace_runtime_tools(agent)
        session_key = self.session_key(bot, message)
        context = Context(
            conversation_id=session_key,
            metadata={
                "remote_bot": {
                    "provider": bot.provider,
                    "bot_id": bot.id,
                    "sender": message.sender,
                    "chat_id": message.chat_id,
                    "session_key": session_key,
                },
                "next_user_content": self.remote_user_content(bot, message),
            },
        )
        response = await agent.run(message.text, context=context)
        await self.post_response_callback(bot, message, response.content)

        try:
            WorkspaceManager().append_event(
                bot.workspace_id,
                {
                    "type": "bot.message",
                    "provider": bot.provider,
                    "bot_id": bot.id,
                    "agent_id": bot.agent_id,
                    "sender": message.sender,
                    "chat_id": message.chat_id,
                    "session_key": session_key,
                    "message": message.text,
                    "response": response.content,
                },
            )
        except Exception:
            pass

        return response.content

    async def post_response_callback(
        self,
        bot: BotConfig,
        message: BotMessage,
        response_text: str,
    ) -> None:
        """Write the Agent response back to an external bot callback URL when configured."""
        response_url = str(bot.metadata.get("response_url", "")).strip()
        if not response_url:
            return

        method = str(bot.metadata.get("response_method", "POST")).upper()
        headers = bot.metadata.get("response_headers", {})
        if not isinstance(headers, dict):
            headers = {}
        timeout = float(bot.metadata.get("response_timeout", 10))
        max_attempts = int(bot.metadata.get("callback_max_retries", _RETRY_MAX_ATTEMPTS))
        payload = self.callback_payload(bot, message, response_text)
        clean_headers = {str(key): str(value) for key, value in headers.items()}

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(
                        method, response_url, headers=clean_headers, json=payload,
                    )
                    resp.raise_for_status()
                self._append_callback_event(bot, message, ok=True)
                return
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Bot callback attempt %s/%s failed for %s: %s; retrying in %.1fs",
                        attempt, max_attempts, bot.id, exc, delay,
                    )
                    await asyncio.sleep(delay)

        logger.warning("Bot response callback failed after %s attempts for %s: %s", max_attempts, bot.id, last_exc)
        self._append_callback_event(bot, message, ok=False, error=str(last_exc))

    @staticmethod
    def extract_message(provider: str, payload: dict[str, Any]) -> BotMessage:
        if provider in ("lark", "feishu"):
            event = payload.get("event", payload)
            message = event.get("message", {})
            content = message.get("content", "")
            if isinstance(content, str) and content.startswith("{"):
                import json

                content = json.loads(content).get("text", content)
            return BotMessage(
                text=str(content or message.get("text", "")),
                sender=str(event.get("sender", {}).get("sender_id", {}).get("open_id", "")),
                chat_id=str(message.get("chat_id", "") or event.get("chat_id", "")),
                raw=payload,
            )

        if provider == "dingtalk":
            text = payload.get("text", {})
            sender = payload.get("senderStaffId") or payload.get("senderNick", "")
            return BotMessage(
                text=str(text.get("content", payload.get("content", ""))).strip(),
                sender=str(sender),
                chat_id=str(payload.get("conversationId", "")),
                raw=payload,
            )

        if provider == "wechat":
            text = payload.get("Content") or payload.get("content") or payload.get("text", "")
            return BotMessage(
                text=str(text),
                sender=str(payload.get("FromUserName", payload.get("sender", ""))),
                chat_id=str(payload.get("FromUserName", payload.get("chat_id", ""))),
                raw=payload,
            )

        return BotMessage(text=str(payload.get("text", "")), raw=payload)

    @staticmethod
    def session_key(bot: BotConfig, message: BotMessage) -> str:
        remote_id = message.chat_id or message.sender or "direct"
        return f"{bot.provider}:{bot.id}:{remote_id}"

    @staticmethod
    def format_response(provider: str, text: str) -> dict[str, Any]:
        if provider in ("lark", "feishu"):
            return {"msg_type": "text", "content": {"text": text}}
        if provider == "dingtalk":
            return {"msgtype": "text", "text": {"content": text}}
        if provider == "wechat":
            return {"msg_type": "text", "content": text}
        return {"text": text}

    @staticmethod
    def callback_payload(
        bot: BotConfig,
        message: BotMessage,
        response_text: str,
    ) -> dict[str, Any]:
        return {
            "provider": bot.provider,
            "bot_id": bot.id,
            "agent_id": bot.agent_id,
            "workspace_id": bot.workspace_id,
            "sender": message.sender,
            "chat_id": message.chat_id,
            "session_key": BotBridgeService.session_key(bot, message),
            "message": message.text,
            "response": response_text,
            "formatted_response": BotBridgeService.format_response(bot.provider, response_text),
        }

    @staticmethod
    def remote_user_content(bot: BotConfig, message: BotMessage) -> str:
        """Build the user message seen by the Agent with remote chat context."""
        return "\n".join(
            [
                f"[remote_bot provider={bot.provider} bot_id={bot.id}]",
                f"[session_key={BotBridgeService.session_key(bot, message)}]",
                f"[sender={message.sender or 'unknown'} chat_id={message.chat_id or 'direct'}]",
                message.text,
            ]
        )

    @staticmethod
    def challenge_response(provider: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if provider in ("lark", "feishu") and "challenge" in payload:
            return {"challenge": payload["challenge"]}
        return None

    @staticmethod
    async def attach_workspace_runtime_tools(agent) -> None:
        from cognix.core.mounts import attach_workspace_runtime_tools

        await attach_workspace_runtime_tools(agent)

    _challenge_response = challenge_response

    @staticmethod
    def _append_callback_event(
        bot: BotConfig,
        message: BotMessage,
        *,
        ok: bool,
        error: str = "",
    ) -> None:
        try:
            WorkspaceManager().append_event(
                bot.workspace_id,
                {
                    "type": "bot.callback",
                    "provider": bot.provider,
                    "bot_id": bot.id,
                    "agent_id": bot.agent_id,
                    "chat_id": message.chat_id,
                    "session_key": BotBridgeService.session_key(bot, message),
                    "ok": ok,
                    "error": error,
                },
            )
        except Exception:
            logger.exception("Failed to append bot callback event")
