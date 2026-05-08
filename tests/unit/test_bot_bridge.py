"""Tests for remote bot bridge configuration and message parsing."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from cognix.bots.bridge import BotBridgeService
from cognix.local.bots import BotConfigStore
from cognix.local.home import CognixHome


def test_bot_config_store_hides_and_verifies_secret(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    store = BotConfigStore(home=home)

    bot = store.create(
        name="Lark",
        provider="lark",
        workspace_id="workspace-1",
        agent_id="agent-1",
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
                "message": {"chat_id": "oc_1", "content": "{\"text\":\"hello\"}"},
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
        workspace_id="workspace-1",
        agent_id="agent-1",
        secret="secret-token",
    )
    message = BotBridgeService.extract_message(
        "dingtalk",
        {"senderNick": "Ada", "conversationId": "cid", "text": {"content": "hi"}},
    )

    assert BotBridgeService.session_key(bot, message) == f"dingtalk:{bot.id}:cid"
    remote_content = BotBridgeService.remote_user_content(bot, message)
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
