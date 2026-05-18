"""Shared pytest setup."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_settings_for_tests(monkeypatch: pytest.MonkeyPatch):
    """Keep settings deterministic and safe across tests."""
    import cognix.config as config

    monkeypatch.setenv("COGNIX_DEBUG", "true")
    monkeypatch.setenv("COGNIX_AUTH__SECRET_KEY", "test-secret-key-for-local-tests")
    config._settings = None
    yield
    config._settings = None
