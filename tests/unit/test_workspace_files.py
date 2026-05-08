"""Tests for workspace file storage."""

from __future__ import annotations

from cognix.local.files import WorkspaceFileStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


def test_workspace_file_store_writes_lists_and_reads(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Files")
    store = WorkspaceFileStore(workspace.id, home=home)

    item = store.write_text("notes/today.md", "# Today\nShip it.")

    assert item.path == "notes/today.md"
    assert store.list() == [store.describe(store.resolve("notes"))]
    assert store.list("notes")[0].name == "today.md"
    assert "Ship it" in store.read_text("notes/today.md")
    assert store.delete("notes/today.md") is True


def test_workspace_file_store_blocks_path_escape(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Files")
    store = WorkspaceFileStore(workspace.id, home=home)

    try:
        store.write_text("../oops.txt", "no")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("expected path escape to fail")
