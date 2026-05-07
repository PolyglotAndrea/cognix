"""Tests for local-first chat storage."""

from __future__ import annotations

from cognix.local.chat import AttachmentRef, ChatStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


def test_chat_store_creates_sessions_and_jsonl_messages(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Chat")
    store = ChatStore(workspace.id, home=home)

    chat = store.create(title="Design Review", model_profiles=["echo", "gpt-4o"])
    user_message = store.append_message(
        chat.id,
        role="user",
        content="Review this file",
        attachments=[
            AttachmentRef(
                id="att-1",
                name="spec.md",
                path="/tmp/spec.md",
                mime_type="text/markdown",
                size=42,
            )
        ],
    )
    assistant_message = store.append_message(
        chat.id,
        role="assistant",
        content="Looks good.",
        model="echo",
        parent_id=user_message.id,
    )

    assert store.get(chat.id) == store.list_all()[0]
    messages = store.list_messages(chat.id)
    assert messages == [user_message, assistant_message]
    assert messages[0].attachments[0].name == "spec.md"


def test_chat_store_requires_existing_workspace(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()

    try:
        ChatStore("missing", home=home)
    except FileNotFoundError as exc:
        assert "Workspace not found" in str(exc)
    else:
        raise AssertionError("expected missing workspace to fail")
