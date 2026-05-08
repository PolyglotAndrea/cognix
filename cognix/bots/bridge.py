"""Remote bot message normalization and dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cognix.api.state import get_agent_runtime
from cognix.core.context import Context
from cognix.local.bots import BotConfig, BotConfigStore
from cognix.local.workspace import WorkspaceManager


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

        response = await self.dispatch(bot, message)
        return self.format_response(provider, response)

    async def dispatch(self, bot: BotConfig, message: BotMessage) -> str:
        agent = await get_agent_runtime(bot.agent_id)
        if not agent:
            raise ValueError(f"Agent '{bot.agent_id}' not found")
        agent.workspace_id = bot.workspace_id
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

    _challenge_response = challenge_response
