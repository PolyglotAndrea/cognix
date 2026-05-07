"""Local-first attachment indexing and lightweight parsing."""

from __future__ import annotations

import json
import mimetypes
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cognix.local.chat import AttachmentRef
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager

TEXT_EXTENSIONS = {
    ".cfg",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".mjs",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class ParsedAttachment:
    id: str
    workspace_id: str
    name: str
    path: str
    mime_type: str
    size: int
    kind: str = "file"
    extracted_text: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_ref(self) -> AttachmentRef:
        metadata = {
            **self.metadata,
            "extracted_text": self.extracted_text,
            "created_at": self.created_at,
        }
        return AttachmentRef(
            id=self.id,
            name=self.name,
            path=self.path,
            mime_type=self.mime_type,
            size=self.size,
            kind=self.kind,
            metadata=metadata,
        )


class AttachmentStore:
    """Stores attachment metadata and extracted text under a workspace."""

    def __init__(self, workspace_id: str, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_path(self) -> Path:
        return self.workspace_manager.workspace_path(self.workspace_id)

    @property
    def attachments_dir(self) -> Path:
        return self.workspace_path / "attachments"

    def ingest_path(
        self,
        path: str | Path,
        *,
        copy_into_workspace: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> ParsedAttachment:
        source = Path(path).expanduser()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Attachment file not found: {source}")

        attachment_id = uuid.uuid4().hex
        filename = source.name
        stored_path = self.attachments_dir / f"{attachment_id}-{filename}"
        if copy_into_workspace:
            shutil.copy2(source, stored_path)
        else:
            stored_path = source

        raw = stored_path.read_bytes()
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parsed = ParsedAttachment(
            id=attachment_id,
            workspace_id=self.workspace_id,
            name=filename,
            path=str(stored_path),
            mime_type=mime_type,
            size=len(raw),
            extracted_text=self._extract_text(filename, mime_type, raw),
            metadata=metadata or {},
        )
        self._write(parsed)
        return parsed

    def ingest_inline(
        self,
        *,
        name: str,
        content: str,
        mime_type: str = "text/plain",
        kind: str = "file",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedAttachment:
        attachment_id = uuid.uuid4().hex
        stored_path = self.attachments_dir / f"{attachment_id}-{Path(name).name}"
        stored_path.write_text(content, encoding="utf-8")
        parsed = ParsedAttachment(
            id=attachment_id,
            workspace_id=self.workspace_id,
            name=Path(name).name,
            path=str(stored_path),
            mime_type=mime_type,
            size=len(content.encode("utf-8")),
            kind=kind,
            extracted_text=self._truncate(content),
            metadata=metadata or {},
        )
        self._write(parsed)
        return parsed

    def ingest_inline_bytes(
        self,
        *,
        name: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        kind: str = "file",
        metadata: dict[str, Any] | None = None,
    ) -> ParsedAttachment:
        attachment_id = uuid.uuid4().hex
        stored_path = self.attachments_dir / f"{attachment_id}-{Path(name).name}"
        stored_path.write_bytes(content)
        parsed = ParsedAttachment(
            id=attachment_id,
            workspace_id=self.workspace_id,
            name=Path(name).name,
            path=str(stored_path),
            mime_type=mime_type,
            size=len(content),
            kind=kind,
            extracted_text=self._extract_text(name, mime_type, content),
            metadata=metadata or {},
        )
        self._write(parsed)
        return parsed

    def get(self, attachment_id: str) -> ParsedAttachment | None:
        path = self.attachments_dir / f"{attachment_id}.json"
        if not path.exists():
            return None
        return ParsedAttachment(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[ParsedAttachment]:
        results = []
        for path in sorted(self.attachments_dir.glob("*.json")):
            attachment = self.get(path.stem)
            if attachment:
                results.append(attachment)
        return results

    def _write(self, attachment: ParsedAttachment) -> None:
        path = self.attachments_dir / f"{attachment.id}.json"
        path.write_text(
            json.dumps(asdict(attachment), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _extract_text(self, filename: str, mime_type: str, raw: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if mime_type.startswith("text/") or suffix in TEXT_EXTENSIONS:
            for encoding in ("utf-8", "utf-16", "latin-1"):
                try:
                    return self._truncate(raw.decode(encoding))
                except UnicodeDecodeError:
                    continue
        return ""

    @staticmethod
    def _truncate(content: str, max_chars: int = 12000) -> str:
        return content.replace("\x00", "")[:max_chars]
