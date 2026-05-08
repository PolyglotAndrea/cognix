"""Tests for local skill scaffold management."""

from __future__ import annotations

import pytest

from cognix.skills.manager import SkillsManager


def test_create_scaffold_creates_loadable_skill(tmp_path) -> None:
    manager = SkillsManager(local_dir=tmp_path)

    skill = manager.create_scaffold(
        "reporter",
        description="Generate reports",
        author="Cognix",
    )

    assert skill.name == "reporter"
    assert skill.description == "Generate reports"
    assert [tool.name for tool in skill.tools] == ["reporter"]
    assert (tmp_path / "reporter" / "skill.yaml").exists()
    assert manager.load("reporter") is not None


def test_create_scaffold_requires_overwrite_for_existing_skill(tmp_path) -> None:
    manager = SkillsManager(local_dir=tmp_path)
    manager.create_scaffold("reporter")

    with pytest.raises(FileExistsError):
        manager.create_scaffold("reporter")

    updated = manager.create_scaffold("reporter", description="Updated", overwrite=True)

    assert updated.description == "Updated"


def test_create_scaffold_rejects_path_separator(tmp_path) -> None:
    manager = SkillsManager(local_dir=tmp_path)

    with pytest.raises(ValueError):
        manager.create_scaffold("../bad")
