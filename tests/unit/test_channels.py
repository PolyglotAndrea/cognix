"""Tests for unified channel routing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cognix.channels import ChannelEvent, ChannelRouteTarget, MessageRouter


def test_channel_event_builds_stable_session_and_user_content() -> None:
    event = ChannelEvent(
        channel="telegram",
        workspace_id="workspace-1",
        text="ship it",
        sender_id="user-1",
        thread_id="chat-1",
        metadata={"source_id": "bot-1"},
    )

    assert event.session_key == "telegram:bot-1:chat-1"
    content = event.user_content()
    assert "[channel=telegram]" in content
    assert "[session_key=telegram:bot-1:chat-1]" in content
    assert "ship it" in content


@pytest.mark.asyncio
async def test_message_router_dispatches_direct_agent_call(monkeypatch) -> None:
    captured = {}

    class FakeAgent:
        workspace_id = ""

        async def run(self, message, context=None):
            captured["message"] = message
            captured["context"] = context
            captured["workspace_id"] = self.workspace_id
            return SimpleNamespace(content="done")

    async def fake_get_agent_runtime(agent_id):
        captured["agent_id"] = agent_id
        return FakeAgent()

    async def fake_attach_workspace_runtime_tools(agent):
        captured["tools_attached"] = True

    monkeypatch.setattr("cognix.api.state.get_agent_runtime", fake_get_agent_runtime)
    monkeypatch.setattr(
        "cognix.core.mounts.attach_workspace_runtime_tools",
        fake_attach_workspace_runtime_tools,
    )

    event = ChannelEvent(
        channel="wechat",
        workspace_id="workspace-1",
        text="hello",
        sender_id="wx-user",
        thread_id="wx-thread",
        metadata={"source_id": "bot-1"},
    )
    result = await MessageRouter().route(
        event,
        ChannelRouteTarget(
            workspace_id="workspace-1",
            agent_id="agent-1",
            target_id="bot-1",
            event_prefix="bot",
        ),
    )

    assert result.status == "success"
    assert result.response == "done"
    assert result.session_key == "wechat:bot-1:wx-thread"
    assert captured["agent_id"] == "agent-1"
    assert captured["workspace_id"] == "workspace-1"
    assert captured["message"] == "hello"
    assert captured["tools_attached"] is True
    assert captured["context"].conversation_id == "wechat:bot-1:wx-thread"
    assert captured["context"].metadata["channel_event"]["channel"] == "wechat"
