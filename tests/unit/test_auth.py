"""Tests for the auth module."""

from __future__ import annotations

import pytest

from cognix.auth.api_key import generate_api_key, verify_api_key
from cognix.auth.dependencies import has_permission, ROLE_PERMISSIONS
from cognix.auth.jwt import create_access_token, create_token, verify_token
from cognix.auth.oauth import get_provider, PROVIDERS


class TestJWT:
    def test_create_and_verify_token(self):
        token = create_token({"sub": "user-123", "role": "user"})
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "user"
        assert "exp" in payload

    def test_create_access_token(self):
        token = create_access_token("user-1", "admin", "admin@test.com")
        payload = verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["role"] == "admin"
        assert payload["email"] == "admin@test.com"
        assert payload["type"] == "access"

    def test_invalid_token_returns_none(self):
        result = verify_token("invalid.token.here")
        assert result is None

    def test_expired_token_returns_none(self):
        from datetime import timedelta

        token = create_token({"sub": "test"}, expires_delta=timedelta(seconds=-1))
        result = verify_token(token)
        assert result is None


class TestAPIKey:
    def test_generate_and_verify(self):
        full_key, key_hash, prefix = generate_api_key()
        assert full_key.startswith("cnx_")
        assert prefix.endswith("...")
        assert verify_api_key(full_key, key_hash)

    def test_wrong_key_fails(self):
        _, key_hash, _ = generate_api_key()
        assert not verify_api_key("wrong_key", key_hash)

    def test_prefix_format(self):
        full_key, _, prefix = generate_api_key()
        assert prefix == full_key[:12] + "..."


class TestPermissions:
    def test_admin_has_all(self):
        assert has_permission("admin", "agents:write")
        assert has_permission("admin", "tasks:delete")
        assert has_permission("admin", "any:permission")

    def test_user_permissions(self):
        assert has_permission("user", "agents:read")
        assert has_permission("user", "agents:write")
        assert has_permission("user", "tasks:read")
        assert has_permission("user", "skills:write")
        assert not has_permission("user", "admin")

    def test_viewer_permissions(self):
        assert has_permission("viewer", "agents:read")
        assert has_permission("viewer", "tasks:read")
        assert not has_permission("viewer", "agents:write")
        assert not has_permission("viewer", "admin")

    def test_unknown_role_has_no_permissions(self):
        assert not has_permission("unknown", "agents:read")


class TestOAuth:
    def test_google_provider_exists(self):
        provider = get_provider("google")
        assert provider is not None
        assert provider.name == "google"
        assert "accounts.google.com" in provider.authorize_url

    def test_github_provider_exists(self):
        provider = get_provider("github")
        assert provider is not None
        assert provider.name == "github"
        assert "github.com" in provider.authorize_url

    def test_unknown_provider_returns_none(self):
        assert get_provider("twitter") is None

    def test_all_providers_registered(self):
        assert "google" in PROVIDERS
        assert "github" in PROVIDERS
