"""Tests for workspace workflow storage."""

from __future__ import annotations

from cognix.local.home import CognixHome
from cognix.local.workflows import WorkspaceWorkflowStore
from cognix.local.workspace import WorkspaceManager

WORKFLOW_YAML = """
name: Review Team
description: Run a simple agent review.
steps:
  - id: review
    agent: reviewer
    input: "{{ input }}"
    output: review
"""


def test_workspace_workflow_store_saves_and_describes(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Teams")
    store = WorkspaceWorkflowStore(workspace.id, home=home)

    workflow = store.save(name="Review Team", definition=WORKFLOW_YAML)

    assert workflow.id == "review-team"
    assert workflow.name == "Review Team"
    assert workflow.step_count == 1
    assert workflow.errors == []
    assert "agent: reviewer" in store.get_definition(workflow.id)
    assert store.list_all() == [workflow]


def test_workspace_workflow_store_reports_validation_errors(tmp_path):
    home = CognixHome(tmp_path / ".cognix").ensure()
    workspace = WorkspaceManager(home).create("Teams")
    store = WorkspaceWorkflowStore(workspace.id, home=home)

    workflow = store.save(name="Broken", definition="name: Broken\nsteps:\n  - id: nope\n")

    assert workflow.errors == ["Step 'nope' must specify an agent"]
    assert store.delete(workflow.id) is True
