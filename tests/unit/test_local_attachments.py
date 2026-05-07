"""Tests for local-first attachment parsing."""

from __future__ import annotations

from cognix.local.attachments import AttachmentStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


def test_attachment_store_ingests_inline_text(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Attachments")
    store = AttachmentStore(workspace.id, home=home)

    parsed = store.ingest_inline(
        name="notes.md",
        content="# Notes\nUse local-first storage.",
        mime_type="text/markdown",
    )

    assert parsed.name == "notes.md"
    assert "local-first" in parsed.extracted_text
    assert store.get(parsed.id) == parsed
    assert store.list_all() == [parsed]
    assert parsed.to_ref().metadata["extracted_text"].startswith("# Notes")


def test_attachment_store_ingests_text_path(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Attachments")
    source = tmp_path / "example.py"
    source.write_text("print('hello')", encoding="utf-8")

    parsed = AttachmentStore(workspace.id, home=home).ingest_path(source)

    assert parsed.path != str(source)
    assert parsed.mime_type
    assert "print" in parsed.extracted_text


def test_attachment_store_ingests_inline_bytes(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Attachments")
    store = AttachmentStore(workspace.id, home=home)

    parsed = store.ingest_inline_bytes(
        name="sample.png",
        content=b"\x89PNG\r\n",
        mime_type="image/png",
        kind="image",
    )

    assert parsed.kind == "image"
    assert parsed.mime_type == "image/png"
    assert parsed.size == 6
    assert parsed.extracted_text == ""
    assert store.get(parsed.id) == parsed
