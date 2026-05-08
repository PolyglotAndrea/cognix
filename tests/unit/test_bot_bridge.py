"""Tests for remote bot bridge configuration and message parsing."""

from __future__ import annotations

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
    assert store.verify_secret(bot, "secret-token") is True
    assert store.verify_secret(bot, "wrong") is False
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
