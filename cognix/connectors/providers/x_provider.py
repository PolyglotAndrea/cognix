"""X (Twitter) connector provider using OAuth 2.0 with PKCE."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from cognix.connectors.base import ConnectorProvider, ConnectorSpec
from cognix.connectors.exceptions import ConnectorAPIError

logger = logging.getLogger(__name__)


def _handle_x_error(resp, tool_name: str) -> None:
    """Raise ConnectorAPIError with X-specific error details."""
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    errors = body.get("errors", [])
    detail = body.get("detail", "")
    title = body.get("title", "")
    msg = detail or title or (errors[0].get("message", "") if errors else "")
    raise ConnectorAPIError(
        platform="x",
        tool=tool_name,
        status_code=resp.status_code,
        error_body=body,
        message=msg or f"X API error ({resp.status_code})",
    )


_X_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
_X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
_X_API_BASE = "https://api.twitter.com/2"
_X_UPLOAD_BASE = "https://upload.twitter.com/1.1"


class XConnectorProvider(ConnectorProvider):
    platform = "x"
    display_name = "X (Twitter)"
    authorize_url = _X_AUTH_URL
    token_url = _X_TOKEN_URL
    default_scopes = ["tweet.read", "tweet.write", "users.read", "media.write", "offline.access"]
    client_id_env = "x_client_id"
    client_secret_env = "x_client_secret"

    # ── OAuth ───────────────────────────────────────────────────────

    def get_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
    ) -> str:
        code_verifier = secrets.token_urlsafe(43)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        # Store code_verifier in state so callback can retrieve it
        state_payload = json.dumps({"s": state, "cv": code_verifier})
        params = {
            "response_type": "code",
            "client_id": self._client_id() or "",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes or self.default_scopes),
            "state": state_payload,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{_X_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        state: str = "",
    ) -> dict[str, Any]:
        client_id = self._client_id() or ""
        client_secret = self._client_secret() or ""

        # Extract code_verifier from state (PKCE flow)
        code_verifier = None
        try:
            state_data = json.loads(state)
            code_verifier = state_data.get("cv")
        except (json.JSONDecodeError, TypeError):
            pass

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth = None
        if client_secret:
            auth = (client_id, client_secret)

        async with httpx.AsyncClient() as client:
            resp = await client.post(_X_TOKEN_URL, data=data, headers=headers, auth=auth)
            if resp.status_code >= 400:
                _handle_x_error(resp, "exchange_code")
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        client_id = self._client_id() or ""
        client_secret = self._client_secret() or ""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        auth = (client_id, client_secret) if client_secret else None
        async with httpx.AsyncClient() as client:
            resp = await client.post(_X_TOKEN_URL, data=data, auth=auth)
            if resp.status_code >= 400:
                _handle_x_error(resp, "refresh_access_token")
            return resp.json()

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_X_API_BASE}/users/me?user.fields=profile_image_url",
                headers=headers,
            )
            if resp.status_code >= 400:
                _handle_x_error(resp, "get_user_info")
            data = resp.json().get("data", {})
            return {
                "platform_user_id": data.get("id", ""),
                "username": data.get("username", ""),
                "name": data.get("name", ""),
                "avatar_url": data.get("profile_image_url"),
            }

    # ── Tools ───────────────────────────────────────────────────────

    def list_tools(self) -> list[ConnectorSpec]:
        return [
            ConnectorSpec(
                name="read_profile",
                description="Read the authenticated user's X profile",
                parameters={"type": "object", "properties": {}, "required": []},
                access_level="read",
            ),
            ConnectorSpec(
                name="post_tweet",
                description="Post a new tweet",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Tweet text (max 280 chars)"},
                        "reply_to": {
                            "type": "string",
                            "description": "Tweet ID to reply to (optional)",
                        },
                        "media_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Media IDs from upload_media (optional)",
                        },
                    },
                    "required": ["text"],
                },
                access_level="dangerous",
            ),
            ConnectorSpec(
                name="delete_tweet",
                description="Delete a tweet by ID",
                parameters={
                    "type": "object",
                    "properties": {
                        "tweet_id": {"type": "string", "description": "ID of the tweet to delete"},
                    },
                    "required": ["tweet_id"],
                },
                access_level="dangerous",
            ),
            ConnectorSpec(
                name="search_tweets",
                description="Search recent tweets",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max results (10-100)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
                access_level="read",
            ),
            ConnectorSpec(
                name="upload_media",
                description="Upload an image or video for use in tweets",
                parameters={
                    "type": "object",
                    "properties": {
                        "media_data": {
                            "type": "string",
                            "description": "Base64-encoded media data",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type (e.g. image/png, video/mp4)",
                        },
                    },
                    "required": ["media_data", "mime_type"],
                },
                access_level="dangerous",
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any], access_token: str) -> Any:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            if name == "read_profile":
                fields = "description,public_metrics,profile_image_url"
                resp = await client.get(
                    f"{_X_API_BASE}/users/me?user.fields={fields}",
                    headers=headers,
                )
                if resp.status_code >= 400:
                    _handle_x_error(resp, name)
                return resp.json()

            elif name == "post_tweet":
                payload: dict[str, Any] = {"text": arguments["text"]}
                if arguments.get("reply_to"):
                    payload["reply"] = {"in_reply_to_tweet_id": arguments["reply_to"]}
                if arguments.get("media_ids"):
                    payload["media"] = {"media_ids": arguments["media_ids"]}
                resp = await client.post(f"{_X_API_BASE}/tweets", json=payload, headers=headers)
                if resp.status_code >= 400:
                    _handle_x_error(resp, name)
                return resp.json()

            elif name == "delete_tweet":
                tid = arguments["tweet_id"]
                resp = await client.delete(
                    f"{_X_API_BASE}/tweets/{tid}",
                    headers=headers,
                )
                if resp.status_code >= 400:
                    _handle_x_error(resp, name)
                return resp.json()

            elif name == "search_tweets":
                params = {
                    "query": arguments["query"],
                    "max_results": arguments.get("max_results", 10),
                    "tweet.fields": "created_at,public_metrics,author_id",
                }
                resp = await client.get(
                    f"{_X_API_BASE}/tweets/search/recent",
                    params=params,
                    headers=headers,
                )
                if resp.status_code >= 400:
                    _handle_x_error(resp, name)
                return resp.json()

            elif name == "upload_media":
                import base64 as b64

                media_bytes = b64.b64decode(arguments["media_data"])
                # Simple INIT + APPEND + FINALIZE for small media
                # INIT
                init_resp = await client.post(
                    f"{_X_UPLOAD_BASE}/media/upload.json",
                    data={
                        "command": "INIT",
                        "total_bytes": len(media_bytes),
                        "media_type": arguments["mime_type"],
                    },
                    headers=headers,
                )
                if init_resp.status_code >= 400:
                    _handle_x_error(init_resp, name)
                media_id = init_resp.json()["media_id_string"]

                # APPEND
                chunk_size = 5 * 1024 * 1024
                for i in range(0, len(media_bytes), chunk_size):
                    chunk = media_bytes[i : i + chunk_size]
                    segment = i // chunk_size
                    await client.post(
                        f"{_X_UPLOAD_BASE}/media/upload.json",
                        data={
                            "command": "APPEND",
                            "media_id": media_id,
                            "segment_index": str(segment),
                        },
                        files={"media": ("chunk", chunk, arguments["mime_type"])},
                        headers=headers,
                    )

                # FINALIZE
                final_resp = await client.post(
                    f"{_X_UPLOAD_BASE}/media/upload.json",
                    data={"command": "FINALIZE", "media_id": media_id},
                    headers=headers,
                )
                if final_resp.status_code >= 400:
                    _handle_x_error(final_resp, name)
                return {"media_id": media_id, **final_resp.json()}

            else:
                raise ValueError(f"Unknown X tool: {name}")
