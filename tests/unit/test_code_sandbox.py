from __future__ import annotations

from cognix.local.code_sandbox import CodeSandboxStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


def test_code_sandbox_creates_project_files(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Sandbox")
    store = CodeSandboxStore(workspace.id, home=home)

    project = store.create_project(
        name="Demo App",
        files=[
            {"path": "index.html", "content": "<h1>Hello</h1>"},
            {"path": "src/main.js", "content": "console.log('ok')"},
        ],
    )

    assert project.status == "created"
    assert (store.projects_dir / project.id / "index.html").read_text() == "<h1>Hello</h1>"
    assert (store.projects_dir / project.id / "src/main.js").exists()
    assert store.get(project.id) == project


def test_code_sandbox_rejects_path_escape(tmp_path) -> None:
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Sandbox")
    store = CodeSandboxStore(workspace.id, home=home)

    try:
        store.create_project(
            name="Bad App",
            files=[{"path": "../bad.txt", "content": "bad"}],
        )
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("Expected ValueError for path escape")
