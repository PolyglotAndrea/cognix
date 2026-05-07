"""Local-first chat session and message storage."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class AttachmentRef:
    id: str
    name: str
    path: str
    mime_type: str = "application/octet-stream"
    size: int = 0
    kind: str = "file"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatSession:
    id: str
    workspace_id: str
    title: str
    created_at: str
    updated_at: str
    system_prompt: str = ""
    model_profiles: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    id: str
    chat_id: str
    workspace_id: str
    role: MessageRole
    content: str
    created_at: str
    model: str | None = None
    provider: str | None = None
    status: str = "done"
    parent_id: str | None = None
    attachments: list[AttachmentRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ChatStore:
    """Stores chat metadata as JSON and messages as JSONL under a workspace."""

    def __init__(
        self,
        workspace_id: str,
        *,
        home: CognixHome | None = None,
    ) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.chats_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def chats_dir(self) -> Path:
        return self.workspace_path / "chats"

    def create(
        self,
        *,
        title: str = "New Chat",
        system_prompt: str = "",
        model_profiles: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatSession:
        now = datetime.now(UTC).isoformat()
        chat = ChatSession(
            id=uuid.uuid4().hex[:12],
            workspace_id=self.workspace_id,
            title=title,
            system_prompt=system_prompt,
            model_profiles=model_profiles or [],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._write_json(self._chat_meta_path(chat.id), asdict(chat))
        self._messages_path(chat.id).touch(exist_ok=True)
        return chat

    def get(self, chat_id: str) -> ChatSession | None:
        path = self._chat_meta_path(chat_id)
        if not path.exists():
            return None
        return ChatSession(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[ChatSession]:
        sessions = []
        for path in sorted(self.chats_dir.glob("*.json")):
            chat = self.get(path.stem)
            if chat:
                sessions.append(chat)
        return sorted(sessions, key=lambda chat: chat.updated_at, reverse=True)

    def append_message(
        self,
        chat_id: str,
        *,
        role: MessageRole,
        content: str,
        model: str | None = None,
        provider: str | None = None,
        status: str = "done",
        parent_id: str | None = None,
        attachments: list[AttachmentRef] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        chat = self.get(chat_id)
        if not chat:
            raise FileNotFoundError(f"Chat not found: {chat_id}")

        now = datetime.now(UTC).isoformat()
        message = ChatMessage(
            id=uuid.uuid4().hex,
            chat_id=chat_id,
            workspace_id=self.workspace_id,
            role=role,
            content=content,
            model=model,
            provider=provider,
            status=status,
            parent_id=parent_id,
            attachments=attachments or [],
            metadata=metadata or {},
            created_at=now,
        )
        with self._messages_path(chat_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(self._message_to_dict(message), ensure_ascii=False) + "\n")
        self._touch_chat(chat, updated_at=now)
        return message

    def list_messages(self, chat_id: str, *, limit: int | None = None) -> list[ChatMessage]:
        if not self.get(chat_id):
            raise FileNotFoundError(f"Chat not found: {chat_id}")
        path = self._messages_path(chat_id)
        if not path.exists():
            return []
        rows = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rows.append(self._message_from_dict(json.loads(line)))
        return rows[-limit:] if limit else rows

    def _touch_chat(self, chat: ChatSession, *, updated_at: str) -> None:
        updated = ChatSession(
            id=chat.id,
            workspace_id=chat.workspace_id,
            title=chat.title,
            system_prompt=chat.system_prompt,
            model_profiles=chat.model_profiles,
            metadata=chat.metadata,
            created_at=chat.created_at,
            updated_at=updated_at,
        )
        self._write_json(self._chat_meta_path(chat.id), asdict(updated))

    def _chat_meta_path(self, chat_id: str) -> Path:
        return self.chats_dir / f"{chat_id}.json"

    def _messages_path(self, chat_id: str) -> Path:
        return self.chats_dir / f"{chat_id}.messages.jsonl"

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def _message_to_dict(message: ChatMessage) -> dict[str, Any]:
        data = asdict(message)
        data["attachments"] = [asdict(attachment) for attachment in message.attachments]
        return data

    @staticmethod
    def _message_from_dict(data: dict[str, Any]) -> ChatMessage:
        attachments = [AttachmentRef(**item) for item in data.get("attachments", [])]
        data = {**data, "attachments": attachments}
        return ChatMessage(**data)
