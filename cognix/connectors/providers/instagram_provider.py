"""Instagram connector provider using Facebook Login + Instagram Graph API."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from cognix.connectors.base import ConnectorProvider, ConnectorSpec

logger = logging.getLogger(__name__)

_FB_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
_FB_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
_IG_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramConnectorProvider(ConnectorProvider):
    platform = "instagram"
    display_name = "Instagram"
    authorize_url = _FB_AUTH_URL
    token_url = _FB_TOKEN_URL
    default_scopes = ["instagram_basic", "instagram_content_publish", "instagram_manage_comments"]
    client_id_env = "instagram_client_id"
    client_secret_env = "instagram_client_secret"

    # ── OAuth ───────────────────────────────────────────────────────

    def get_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
    ) -> str:
        params = {
            "client_id": self._client_id() or "",
            "redirect_uri": redirect_uri,
            "scope": ",".join(scopes or self.default_scopes),
            "state": state,
            "response_type": "code",
        }
        return f"{_FB_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, redirect_uri: str, state: str = "",
    ) -> dict[str, Any]:
        client_id = self._client_id() or ""
        client_secret = self._client_secret() or ""
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(_FB_TOKEN_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            # Exchange short-lived token for long-lived token
            if data.get("access_token"):
                ll_resp = await client.get(
                    f"{_IG_API_BASE}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "fb_exchange_token": data["access_token"],
                    },
                )
                if ll_resp.status_code == 200:
                    return ll_resp.json()
            return data

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        # Instagram/Facebook long-lived tokens (~60 days) can be refreshed
        # by re-exchanging before expiry. There's no standard refresh_token.
        # This is a no-op; the token should be re-authorized.
        raise NotImplementedError(
            "Instagram tokens are long-lived (~60 days). Re-authorize when expired."
        )

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        # First get the Facebook user, then the linked Instagram account
        async with httpx.AsyncClient() as client:
            # Get Instagram Business Account ID
            resp = await client.get(
                f"{_IG_API_BASE}/me/accounts",
                params={"fields": "instagram_business_account,name", "access_token": access_token},
            )
            resp.raise_for_status()
            pages = resp.json().get("data", [])

            ig_account_id = None
            for page in pages:
                ig = page.get("instagram_business_account")
                if ig:
                    ig_account_id = ig["id"]
                    break

            if not ig_account_id:
                raise ValueError("No Instagram Business account linked to this Facebook user")

            # Get Instagram user info
            ig_resp = await client.get(
                f"{_IG_API_BASE}/{ig_account_id}",
                params={
                    "fields": "id,username,name,profile_picture_url",
                    "access_token": access_token,
                },
            )
            ig_resp.raise_for_status()
            ig_data = ig_resp.json()

            return {
                "platform_user_id": ig_data.get("id", ""),
                "username": ig_data.get("username", ""),
                "name": ig_data.get("name", ""),
                "avatar_url": ig_data.get("profile_picture_url"),
            }

    # ── Tools ───────────────────────────────────────────────────────

    def list_tools(self) -> list[ConnectorSpec]:
        return [
            ConnectorSpec(
                name="get_profile",
                description="Read the authenticated Instagram account profile",
                parameters={"type": "object", "properties": {}, "required": []},
                access_level="read",
            ),
            ConnectorSpec(
                name="post_media",
                description="Publish a photo or video to Instagram",
                parameters={
                    "type": "object",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "description": (
                                "Publicly accessible URL"
                                " of the image/video"
                            ),
                        },
                        "caption": {"type": "string", "description": "Caption for the post"},
                        "media_type": {
                            "type": "string",
                            "enum": ["IMAGE", "VIDEO", "REELS"],
                            "description": "Type of media",
                            "default": "IMAGE",
                        },
                    },
                    "required": ["image_url"],
                },
                access_level="write",
            ),
            ConnectorSpec(
                name="get_media",
                description="List recent media posts from the Instagram account",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Number of posts to return"
                                " (max 100)"
                            ),
                            "default": 20,
                        },
                    },
                    "required": [],
                },
                access_level="read",
            ),
            ConnectorSpec(
                name="get_comments",
                description="Get comments on an Instagram media post",
                parameters={
                    "type": "object",
                    "properties": {
                        "media_id": {"type": "string", "description": "ID of the media post"},
                    },
                    "required": ["media_id"],
                },
                access_level="read",
            ),
            ConnectorSpec(
                name="reply_comment",
                description="Reply to a comment on an Instagram post",
                parameters={
                    "type": "object",
                    "properties": {
                        "comment_id": {
                            "type": "string",
                            "description": (
                                "ID of the comment to reply to"
                            ),
                        },
                        "message": {"type": "string", "description": "Reply text"},
                    },
                    "required": ["comment_id", "message"],
                },
                access_level="write",
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any], access_token: str) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Resolve the Instagram account ID
            ig_account_id = await self._get_ig_account_id(client, access_token)

            if name == "get_profile":
                resp = await client.get(
                    f"{_IG_API_BASE}/{ig_account_id}",
                    params={
                        "fields": (
                            "id,username,name,biography,"
                            "followers_count,follows_count,"
                            "media_count,profile_picture_url"
                        ),
                        "access_token": access_token,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            elif name == "post_media":
                media_type = arguments.get("media_type", "IMAGE")
                # Step 1: Create media container
                container_data: dict[str, str] = {
                    "access_token": access_token,
                }
                if media_type == "IMAGE":
                    container_data["image_url"] = arguments["image_url"]
                else:
                    container_data["video_url"] = arguments["image_url"]
                    container_data["media_type"] = media_type

                if arguments.get("caption"):
                    container_data["caption"] = arguments["caption"]

                create_resp = await client.post(
                    f"{_IG_API_BASE}/{ig_account_id}/media",
                    data=container_data,
                )
                create_resp.raise_for_status()
                container_id = create_resp.json()["id"]

                # Step 2: Publish the container
                publish_resp = await client.post(
                    f"{_IG_API_BASE}/{ig_account_id}/media_publish",
                    data={
                        "creation_id": container_id,
                        "access_token": access_token,
                    },
                )
                publish_resp.raise_for_status()
                return publish_resp.json()

            elif name == "get_media":
                limit = arguments.get("limit", 20)
                resp = await client.get(
                    f"{_IG_API_BASE}/{ig_account_id}/media",
                    params={
                        "fields": (
                            "id,caption,media_type,media_url,"
                            "permalink,timestamp,"
                            "like_count,comments_count"
                        ),
                        "limit": limit,
                        "access_token": access_token,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            elif name == "get_comments":
                resp = await client.get(
                    f"{_IG_API_BASE}/{arguments['media_id']}/comments",
                    params={
                        "fields": "id,text,timestamp,username",
                        "access_token": access_token,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            elif name == "reply_comment":
                resp = await client.post(
                    f"{_IG_API_BASE}/{arguments['comment_id']}/replies",
                    data={
                        "message": arguments["message"],
                        "access_token": access_token,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            else:
                raise ValueError(f"Unknown Instagram tool: {name}")

    async def _get_ig_account_id(self, client: httpx.AsyncClient, access_token: str) -> str:
        """Resolve the Instagram Business Account ID from the token."""
        resp = await client.get(
            f"{_IG_API_BASE}/me/accounts",
            params={"fields": "instagram_business_account", "access_token": access_token},
        )
        resp.raise_for_status()
        for page in resp.json().get("data", []):
            ig = page.get("instagram_business_account")
            if ig:
                return ig["id"]
        raise ValueError("No Instagram Business account linked")
