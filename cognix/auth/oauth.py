"""OAuth2 providers (Google, GitHub)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from cognix.config import get_settings

logger = logging.getLogger(__name__)


class OAuthProvider:
    """Base OAuth provider."""

    name: str
    authorize_url: str
    token_url: str
    user_info_url: str

    def get_authorize_url(self, redirect_uri: str) -> str:
        raise NotImplementedError

    async def get_user_info(self, code: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError


class GoogleOAuth(OAuthProvider):
    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"

    def get_authorize_url(self, redirect_uri: str) -> str:
        settings = get_settings()
        params = {
            "client_id": settings.auth.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query}"

    async def get_user_info(self, code: str, redirect_uri: str) -> dict[str, Any]:
        settings = get_settings()

        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": settings.auth.google_client_id,
                    "client_secret": settings.auth.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            # Get user info
            user_resp = await client.get(
                self.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_data = user_resp.json()

        return {
            "oauth_id": user_data.get("id"),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "avatar_url": user_data.get("picture"),
        }


class GitHubOAuth(OAuthProvider):
    name = "github"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    user_info_url = "https://api.github.com/user"

    def get_authorize_url(self, redirect_uri: str) -> str:
        settings = get_settings()
        params = {
            "client_id": settings.auth.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query}"

    async def get_user_info(self, code: str, redirect_uri: str) -> dict[str, Any]:
        settings = get_settings()

        async with httpx.AsyncClient() as client:
            # Exchange code for token
            token_resp = await client.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": settings.auth.github_client_id,
                    "client_secret": settings.auth.github_client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")

            # Get user info
            user_resp = await client.get(
                self.user_info_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            user_data = user_resp.json()

            # Get email if not public
            email = user_data.get("email")
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                emails = emails_resp.json()
                primary = next((e for e in emails if e.get("primary")), None)
                if primary:
                    email = primary.get("email")

        return {
            "oauth_id": str(user_data.get("id")),
            "email": email,
            "name": user_data.get("name") or user_data.get("login"),
            "avatar_url": user_data.get("avatar_url"),
        }


# Provider registry
PROVIDERS: dict[str, OAuthProvider] = {
    "google": GoogleOAuth(),
    "github": GitHubOAuth(),
}


def get_provider(name: str) -> OAuthProvider | None:
    """Get an OAuth provider by name."""
    return PROVIDERS.get(name)
