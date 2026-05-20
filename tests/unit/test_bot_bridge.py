"""Tests for remote bot bridge configuration and message parsing."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest

from cognix.bots.bridge import BotBridgeService, BotRoute
from cognix.local.bots import BotConfig, BotConfigStore
from cognix.local.home import CognixHome


def test_bot_config_store_hides_and_verifies_secret(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    store = BotConfigStore(home=home)

    bot = store.create(
        name="Lark",
        provider="lark",
        secret="secret-token",
    )

    public = bot.public_dict()
    assert public["webhook_path"] == f"/api/v1/bots/lark/{bot.id}/webhook"
    assert "secret_hash" not in public
    assert "signing_secret" not in public
    assert store.verify_secret(bot, "secret-token") is True
    assert store.verify_secret(bot, "wrong") is False
    body = json.dumps({"text": "hello"}).encode("utf-8")
    signature = hmac.new(bot.secret_hash.encode("utf-8"), b"1." + body, hashlib.sha256).hexdigest()
    assert store.verify_signature(bot, body=body, timestamp="1", signature=signature) is True
    raw_signature = hmac.new(
        b"secret-token",
        b"1." + body,
        hashlib.sha256,
    ).hexdigest()
    assert store.verify_signature(bot, body=body, timestamp="1", signature=raw_signature) is True
    now = datetime.now(UTC)
    assert (
        store.verify_signature(
            bot,
            body=body,
            timestamp="1",
            signature=raw_signature,
            tolerance_seconds=300,
            now=now,
        )
        is False
    )
    assert store.verify_signature(bot, body=body, timestamp="2", signature=signature) is False
    assert store.list_all() == [bot]


def test_bot_bridge_extracts_provider_messages():
    lark = BotBridgeService.extract_message(
        "lark",
        {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {"chat_id": "oc_1", "content": '{"text":"hello"}'},
            }
        },
    )
    dingtalk = BotBridgeService.extract_message(
        "dingtalk",
        {"senderNick": "Ada", "conversationId": "cid", "text": {"content": " hi "}},
    )
    wechat = BotBridgeService.extract_message(
        "wechat",
        {"FromUserName": "wxid", "Content": "ping"},
    )

    assert lark.text == "hello"
    assert lark.sender == "ou_1"
    assert dingtalk.text == "hi"
    assert dingtalk.chat_id == "cid"
    assert wechat.text == "ping"
    assert wechat.sender == "wxid"


def test_bot_bridge_session_key_uses_chat_or_sender(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    store = BotConfigStore(home=home)
    bot = store.create(
        name="Ding",
        provider="dingtalk",
        secret="secret-token",
    )
    route = BotRoute(workspace_id="workspace-1", agent_id="agent-1")
    message = BotBridgeService.extract_message(
        "dingtalk",
        {"senderNick": "Ada", "conversationId": "cid", "text": {"content": "hi"}},
    )

    assert BotBridgeService.session_key(bot, message, route) == f"dingtalk:{bot.id}:workspace-1:cid"
    remote_content = BotBridgeService.remote_user_content(bot, message, route)
    assert "session_key=dingtalk:" in remote_content
    assert "sender=Ada chat_id=cid" in remote_content
    assert remote_content.endswith("hi")


def test_bot_bridge_formats_provider_responses():
    assert BotBridgeService.format_response("lark", "ok") == {
        "msg_type": "text",
        "content": {"text": "ok"},
    }
    assert BotBridgeService.format_response("dingtalk", "ok") == {
        "msgtype": "text",
        "text": {"content": "ok"},
    }
    assert BotBridgeService.format_response("wechat", "ok") == {
        "msg_type": "text",
        "content": "ok",
    }


def test_bot_bridge_builds_callback_payload():
    bot = BotConfig(
        id="bot-1",
        name="Lark",
        provider="lark",
        secret_hash="hash",
    )
    route = BotRoute(workspace_id="workspace-1", agent_id="agent-1")
    message = BotBridgeService.extract_message(
        "lark",
        {
            "event": {
                "sender": {"sender_id": {"open_id": "ou_1"}},
                "message": {"chat_id": "oc_1", "content": '{"text":"hello"}'},
            }
        },
    )

    payload = BotBridgeService.callback_payload(bot, message, route, "ok")

    assert payload["session_key"] == "lark:bot-1:workspace-1:oc_1"
    assert payload["response"] == "ok"
    assert payload["formatted_response"] == {
        "msg_type": "text",
        "content": {"text": "ok"},
    }


@pytest.mark.asyncio
async def test_bot_bridge_posts_response_callback(tmp_path, monkeypatch):
    requests = []
    events = []

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, *, headers, json):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "timeout": self.timeout,
                }
            )
            return self

        def raise_for_status(self):
            return None

    class FakeWorkspaceManager:
        def append_event(self, workspace_id, event):
            events.append((workspace_id, event))

    monkeypatch.setattr("cognix.bots.bridge.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("cognix.bots.bridge.WorkspaceManager", FakeWorkspaceManager)

    bot = BotConfig(
        id="bot-1",
        name="Ding",
        provider="dingtalk",
        secret_hash="hash",
        metadata={
            "response_url": "https://example.test/callback",
            "response_headers": {"Authorization": "Bearer token"},
            "response_timeout": 3,
        },
    )
    route = BotRoute(workspace_id="workspace-1", agent_id="agent-1")
    message = BotBridgeService.extract_message(
        "dingtalk",
        {"senderNick": "Ada", "conversationId": "cid", "text": {"content": "hi"}},
    )

    store = BotConfigStore(home=CognixHome(tmp_path / ".cognix").ensure())
    await BotBridgeService(store=store).post_response_callback(bot, message, route, "ok")

    assert requests == [
        {
            "method": "POST",
            "url": "https://example.test/callback",
            "headers": {"Authorization": "Bearer token"},
            "json": BotBridgeService.callback_payload(bot, message, route, "ok"),
            "timeout": 3.0,
        }
    ]
    assert events == [
        (
            "workspace-1",
            {
                "type": "bot.callback",
                "provider": "dingtalk",
                "bot_id": "bot-1",
                "agent_id": "agent-1",
                "chat_id": "cid",
                "session_key": "dingtalk:bot-1:workspace-1:cid",
                "ok": True,
                "error": "",
            },
        )
    ]
