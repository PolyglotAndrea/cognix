"""Connector credential management and OAuth flow orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from cognix.connectors.crypto import decrypt_token, encrypt_token
from cognix.connectors.providers import get_provider
from cognix.storage.database import get_session
from cognix.storage.models import ConnectorCredentialModel

logger = logging.getLogger(__name__)


class ConnectorManager:
    """Manages connector credentials and OAuth flows."""

    # ── OAuth Flow ──────────────────────────────────────────────────

    def get_authorize_url(
        self,
        platform: str,
        redirect_uri: str,
        state: str,
    ) -> tuple[str, list[str]]:
        """Build the OAuth authorization URL. Returns (url, scopes)."""
        provider = get_provider(platform)
        if not provider:
            raise ValueError(f"Unknown connector platform: {platform}")
        url = provider.get_authorize_url(redirect_uri, state)
        return url, provider.default_scopes

    async def handle_callback(
        self,
        platform: str,
        code: str,
        redirect_uri: str,
        user_id: str,
        *,
        state: str = "",
        workspace_id: str | None = None,
    ) -> ConnectorCredentialModel:
        """Exchange an auth code for tokens and store the credential."""
        provider = get_provider(platform)
        if not provider:
            raise ValueError(f"Unknown connector platform: {platform}")

        token_data = await provider.exchange_code(code, redirect_uri, state)
        user_info = await provider.get_user_info(token_data["access_token"])

        return await self.store_credential(
            user_id=user_id,
            platform=platform,
            token_data=token_data,
            user_info=user_info,
            workspace_id=workspace_id,
        )

    # ── Credential CRUD ─────────────────────────────────────────────

    async def store_credential(
        self,
        user_id: str,
        platform: str,
        token_data: dict[str, Any],
        user_info: dict[str, Any],
        *,
        workspace_id: str | None = None,
    ) -> ConnectorCredentialModel:
        """Encrypt and store a connector credential. Updates existing if found."""
        access_token_enc = encrypt_token(token_data["access_token"])
        refresh_token_enc = (
            encrypt_token(token_data["refresh_token"])
            if token_data.get("refresh_token")
            else None
        )
        expires_at = None
        if token_data.get("expires_in"):
            expires_at = datetime.now(UTC) + timedelta(seconds=int(token_data["expires_in"]))

        scopes = token_data.get("scope", "")
        if isinstance(scopes, list):
            scopes = " ".join(scopes)

        # Check for existing credential (same user + platform + workspace)
        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.user_id == user_id,
                ConnectorCredentialModel.platform == platform,
                ConnectorCredentialModel.workspace_id == workspace_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.access_token_enc = access_token_enc
                existing.refresh_token_enc = refresh_token_enc
                existing.token_expires_at = expires_at
                existing.scopes = scopes
                existing.platform_user_id = user_info.get(
                    "platform_user_id", existing.platform_user_id
                )
                existing.platform_username = user_info.get("username", existing.platform_username)
                existing.updated_at = datetime.now(UTC)
                return existing

            cred = ConnectorCredentialModel(
                id=uuid.uuid4().hex[:12],
                user_id=user_id,
                workspace_id=workspace_id,
                platform=platform,
                platform_user_id=user_info.get("platform_user_id", ""),
                platform_username=user_info.get("username", ""),
                access_token_enc=access_token_enc,
                refresh_token_enc=refresh_token_enc,
                token_expires_at=expires_at,
                scopes=scopes,
            )
            session.add(cred)
            return cred

    async def get_credential(
        self, credential_id: str
    ) -> ConnectorCredentialModel | None:
        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.id == credential_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_credentials(
        self,
        user_id: str,
        *,
        workspace_id: str | None = None,
    ) -> list[ConnectorCredentialModel]:
        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.user_id == user_id,
            )
            if workspace_id is not None:
                stmt = stmt.where(
                    (ConnectorCredentialModel.workspace_id == workspace_id)
                    | (ConnectorCredentialModel.workspace_id.is_(None))
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_all_credentials_for_platform(
        self,
        platform: str,
        *,
        workspace_id: str | None = None,
    ) -> list[ConnectorCredentialModel]:
        """List credentials for a platform, prioritizing workspace-level."""
        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.platform == platform,
            )
            if workspace_id:
                stmt = stmt.where(
                    (ConnectorCredentialModel.workspace_id == workspace_id)
                    | (ConnectorCredentialModel.workspace_id.is_(None))
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def resolve_credential(
        self,
        user_id: str,
        platform: str,
        workspace_id: str | None = None,
    ) -> ConnectorCredentialModel | None:
        """Resolve the best credential: workspace-level first, then user-level."""
        if workspace_id:
            async with get_session() as session:
                stmt = select(ConnectorCredentialModel).where(
                    ConnectorCredentialModel.platform == platform,
                    ConnectorCredentialModel.workspace_id == workspace_id,
                )
                result = await session.execute(stmt)
                ws_cred = result.scalar_one_or_none()
                if ws_cred:
                    return ws_cred

        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.platform == platform,
                ConnectorCredentialModel.user_id == user_id,
                ConnectorCredentialModel.workspace_id.is_(None),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete_credential(
        self, credential_id: str
    ) -> bool:
        async with get_session() as session:
            stmt = select(ConnectorCredentialModel).where(
                ConnectorCredentialModel.id == credential_id
            )
            result = await session.execute(stmt)
            cred = result.scalar_one_or_none()
            if not cred:
                return False
            await session.delete(cred)
            return True

    async def get_decrypted_token(self, credential: ConnectorCredentialModel) -> str:
        """Return the decrypted access token, refreshing if needed."""
        if credential.token_expires_at and credential.token_expires_at < datetime.now(UTC):
            await self.refresh_if_expired(credential)
        return decrypt_token(credential.access_token_enc)

    async def refresh_if_expired(
        self, credential: ConnectorCredentialModel
    ) -> ConnectorCredentialModel:
        """Attempt to refresh the token if expired."""
        if not credential.token_expires_at or credential.token_expires_at >= datetime.now(UTC):
            return credential

        provider = get_provider(credential.platform)
        if not provider or not credential.refresh_token_enc:
            return credential

        try:
            refresh_token = decrypt_token(credential.refresh_token_enc)
            token_data = await provider.refresh_access_token(refresh_token)
            credential.access_token_enc = encrypt_token(token_data["access_token"])
            if token_data.get("refresh_token"):
                credential.refresh_token_enc = encrypt_token(token_data["refresh_token"])
            if token_data.get("expires_in"):
                expires_in = int(token_data["expires_in"])
                credential.token_expires_at = (
                    datetime.now(UTC) + timedelta(seconds=expires_in)
                )
            credential.updated_at = datetime.now(UTC)

            async with get_session() as session:
                session.add(credential)
            return credential
        except Exception:
            logger.warning(
                "Failed to refresh token for %s credential %s",
                credential.platform,
                credential.id,
            )
            return credential
