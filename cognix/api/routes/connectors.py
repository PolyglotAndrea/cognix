"""Connector REST routes — OAuth flow, credential CRUD, tool management."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cognix.auth.dependencies import (
    CurrentUser,
    require_connectors_read,
    require_connectors_write,
)
from cognix.connectors.adapter import connector_access_level
from cognix.connectors.exceptions import ConnectorAPIError, ConnectorTokenExpiredError
from cognix.connectors.manager import ConnectorManager
from cognix.connectors.providers import all_providers, get_provider
from cognix.core.permissions import clamp_permission_mode, decide_permission
from cognix.core.policy import WorkspacePolicyService
from cognix.local.approvals import ApprovalStore
from cognix.local.workspace_config import WorkspaceConfigStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _credential_status(cred) -> dict:
    """Compute expiry/reauth fields for a credential."""
    now = datetime.now(UTC)
    expires_at = cred.token_expires_at
    is_expired = bool(expires_at and expires_at < now)
    can_refresh = bool(cred.refresh_token_enc)
    needs_reauth = is_expired and not can_refresh
    return {
        "is_expired": is_expired,
        "needs_reauth": needs_reauth,
        "token_expires_at": expires_at.isoformat() if expires_at else None,
    }


# ── OAuth flow ──────────────────────────────────────────────────────


class AuthorizeResponse(BaseModel):
    url: str
    state: str


@router.get("/platforms")
async def list_platforms(
    user: CurrentUser = Depends(require_connectors_read),
) -> list[dict]:
    """List available connector platforms with connection status."""
    manager = ConnectorManager()
    providers = all_providers()
    all_creds = await manager.list_credentials(user.id)
    result = []
    for platform, provider in providers.items():
        platform_creds = [c for c in all_creds if c.platform == platform]
        result.append(
            {
                "platform": platform,
                "display_name": provider.display_name,
                "connected": len(platform_creds) > 0,
                "credentials": [
                    {
                        "id": c.id,
                        "platform_username": c.platform_username,
                        "platform_user_id": c.platform_user_id,
                        "scopes": c.scopes,
                        "workspace_id": c.workspace_id,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        **_credential_status(c),
                    }
                    for c in platform_creds
                ],
            }
        )
    return result


@router.post("/oauth/{platform}/authorize")
async def authorize(
    platform: str,
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_connectors_write),
) -> AuthorizeResponse:
    """Start OAuth flow for a platform. Returns the authorization URL."""
    from cognix.config import get_settings

    settings = get_settings()
    redirect_uri = f"{settings.auth.frontend_url}/connectors/callback"
    state = secrets.token_urlsafe(16)
    if workspace_id:
        state = f"{state}:{workspace_id}"

    manager = ConnectorManager()
    try:
        url, scopes = manager.get_authorize_url(platform, redirect_uri, state)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return AuthorizeResponse(url=url, state=state)


class CallbackRequest(BaseModel):
    code: str
    state: str


@router.post("/oauth/{platform}/callback")
async def callback(
    platform: str,
    body: CallbackRequest,
    user: CurrentUser = Depends(require_connectors_write),
) -> dict:
    """Handle OAuth callback — exchange code for tokens and store credential."""
    from cognix.config import get_settings

    settings = get_settings()
    redirect_uri = f"{settings.auth.frontend_url}/connectors/callback"

    # Parse state — X embeds {s, cv} JSON; others use "random:workspace_id"
    workspace_id: str | None = None
    raw_state = body.state
    try:
        import json as _json

        state_data = _json.loads(raw_state)
        # X PKCE state: {s: "random", cv: "code_verifier"}
        inner = state_data.get("s", raw_state)
        ws_parts = inner.split(":", 1)
        workspace_id = ws_parts[1] if len(ws_parts) > 1 else None
    except (_json.JSONDecodeError, TypeError, AttributeError):
        parts = raw_state.split(":", 1)
        workspace_id = parts[1] if len(parts) > 1 else None

    manager = ConnectorManager()
    try:
        cred, missing_scopes = await manager.handle_callback(
            platform=platform,
            code=body.code,
            redirect_uri=redirect_uri,
            user_id=user.id,
            state=raw_state,
            workspace_id=workspace_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("OAuth callback failed for %s", platform)
        raise HTTPException(502, f"OAuth exchange failed: {e}")

    # Auto-create a workspace connector config if workspace_id provided
    if workspace_id:
        try:
            store = WorkspaceConfigStore(workspace_id)
            store.upsert_connector(
                platform=platform,
                credential_id=cred.id,
            )
        except Exception:
            logger.warning(
                "Failed to auto-create connector config for workspace %s",
                workspace_id,
            )

    result = {
        "id": cred.id,
        "platform": cred.platform,
        "platform_username": cred.platform_username,
        "workspace_id": cred.workspace_id,
    }
    if missing_scopes:
        result["missing_scopes"] = missing_scopes
        result["warning"] = (
            f"Some features may be limited. Missing scopes: {', '.join(missing_scopes)}"
        )
    return result


# ── Credential CRUD ─────────────────────────────────────────────────


@router.get("/credentials")
async def list_credentials(
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_connectors_read),
) -> list[dict]:
    """List the current user's connector credentials."""
    manager = ConnectorManager()
    creds = await manager.list_credentials(user.id, workspace_id=workspace_id)
    return [
        {
            "id": c.id,
            "platform": c.platform,
            "platform_username": c.platform_username,
            "platform_user_id": c.platform_user_id,
            "scopes": c.scopes,
            "workspace_id": c.workspace_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            **_credential_status(c),
        }
        for c in creds
    ]


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: str,
    user: CurrentUser = Depends(require_connectors_write),
) -> dict:
    """Delete a connector credential."""
    manager = ConnectorManager()
    cred = await manager.get_credential(credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    if cred.user_id != user.id:
        raise HTTPException(403, "Not your credential")

    # Also remove workspace connector configs referencing this credential
    if cred.workspace_id:
        try:
            store = WorkspaceConfigStore(cred.workspace_id)
            for conn in store.list_connectors():
                if conn.credential_id == credential_id:
                    store.delete_connector(conn.id)
        except Exception:
            pass

    await manager.delete_credential(credential_id)
    return {"deleted": credential_id}


# ── Connector tools ─────────────────────────────────────────────────


@router.get("/tools")
async def list_connector_tools(
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_connectors_read),
) -> list[dict]:
    """List all available connector tools for connected platforms."""
    manager = ConnectorManager()
    creds = await manager.list_credentials(user.id, workspace_id=workspace_id)
    result = []

    # Get workspace connector configs for enabled/disabled state
    ws_configs: dict[str, dict] = {}
    if workspace_id:
        try:
            store = WorkspaceConfigStore(workspace_id)
            for conn in store.list_connectors():
                ws_configs[conn.platform] = {
                    "connector_id": conn.id,
                    "disabled_tools": set(conn.metadata.get("disabled_tools", [])),
                    "metadata": conn.metadata,
                }
        except FileNotFoundError:
            pass

    seen_platforms: set[str] = set()
    for cred in creds:
        if cred.platform in seen_platforms:
            continue
        seen_platforms.add(cred.platform)

        provider = get_provider(cred.platform)
        if not provider:
            continue

        config = ws_configs.get(cred.platform, {})
        disabled = config.get("disabled_tools", set())
        metadata = config.get("metadata", {})

        for spec in provider.list_tools():
            tool_name = f"conn_{cred.platform}_{spec.name}"
            result.append(
                {
                    "name": tool_name,
                    "original_name": spec.name,
                    "platform": cred.platform,
                    "display_name": provider.display_name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                    "access_level": connector_access_level(spec, metadata),
                    "enabled": spec.name not in disabled,
                    "connector_id": config.get("connector_id"),
                }
            )

    return result


class ToggleToolRequest(BaseModel):
    tool_name: str
    enabled: bool


@router.put("/tools/{tool_name}")
async def toggle_connector_tool(
    tool_name: str,
    body: ToggleToolRequest,
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_connectors_write),
) -> dict:
    """Enable or disable a specific connector tool."""
    if not workspace_id:
        raise HTTPException(400, "workspace_id is required")

    # Parse platform from tool name: conn_{platform}_{tool_name}
    parts = tool_name.split("_", 2)
    if len(parts) < 3 or parts[0] != "conn":
        raise HTTPException(400, f"Invalid connector tool name: {tool_name}")
    platform = parts[1]
    original_name = parts[2]

    try:
        store = WorkspaceConfigStore(workspace_id)
        for conn in store.list_connectors():
            if conn.platform == platform:
                store.set_connector_tool_enabled(conn.id, original_name, body.enabled)
                break
    except FileNotFoundError:
        raise HTTPException(404, "Workspace not found")

    return {"tool_name": tool_name, "enabled": body.enabled}


class CallToolRequest(BaseModel):
    arguments: dict = {}
    permission_mode: str = "workspace-write"
    approval_id: str | None = None


@router.post("/tools/{tool_name}/call")
async def call_connector_tool(
    tool_name: str,
    body: CallToolRequest,
    workspace_id: str | None = None,
    user: CurrentUser = Depends(require_connectors_write),
) -> dict:
    """Call a connector tool (for debugging/testing)."""
    # Parse platform from tool name
    parts = tool_name.split("_", 2)
    if len(parts) < 3 or parts[0] != "conn":
        raise HTTPException(400, f"Invalid connector tool name: {tool_name}")
    platform = parts[1]
    original_name = parts[2]

    provider = get_provider(platform)
    if not provider:
        raise HTTPException(400, f"Unknown platform: {platform}")
    spec = next(
        (item for item in provider.list_tools() if item.name == original_name),
        None,
    )
    if not spec:
        raise HTTPException(404, f"Connector tool not found: {original_name}")

    metadata: dict = {}
    if workspace_id:
        try:
            store = WorkspaceConfigStore(workspace_id)
            for conn in store.list_connectors():
                if conn.platform == platform:
                    metadata = conn.metadata
                    if original_name in set(metadata.get("disabled_tools", [])):
                        raise HTTPException(403, f"Connector tool disabled: {tool_name}")
                    break
        except FileNotFoundError:
            pass

    access_level = connector_access_level(spec, metadata)
    effective_mode = clamp_permission_mode(body.permission_mode, user.role)
    if workspace_id:
        policy_result = await WorkspacePolicyService(workspace_id).check_connector(
            platform,
            permission_mode=effective_mode,
            user_id=user.id,
            agent_id=f"connector-debug:{user.id}",
        )
        if not policy_result.allowed:
            if not policy_result.requires_approval:
                raise HTTPException(403, policy_result.reason or "Connector denied by policy")
            effective_mode = "ask"
    decision = decide_permission(
        effective_mode,
        access_level,
        f"debug connector tool '{tool_name}'",
    )
    approved_id: str | None = None
    if not decision.allowed:
        if not decision.requires_approval:
            raise HTTPException(403, decision.reason)
        approval_store = ApprovalStore()
        if body.approval_id:
            approval = approval_store.get(body.approval_id)
            if not approval:
                raise HTTPException(404, "Approval not found")
            if approval.status != "approved":
                raise HTTPException(409, "Approval has not been approved")
            if (
                approval.tool_name != tool_name
                or approval.arguments != body.arguments
                or approval.workspace_id != workspace_id
            ):
                raise HTTPException(400, "Approval does not match this connector call")
            approved_id = approval.id
        else:
            approval = approval_store.create(
                agent_id=f"connector-debug:{user.id}",
                workspace_id=workspace_id,
                tool_name=tool_name,
                arguments=body.arguments,
                access_level=access_level,
                reason=decision.reason,
                kind="tool_permission",
                metadata={
                    "runtime": "connector-debug",
                    "platform": platform,
                    "original_name": original_name,
                    "permission_mode": effective_mode,
                },
            )
            return {
                "approval_required": True,
                "approval_id": approval.id,
                "tool_name": tool_name,
                "access_level": access_level,
                "permission_mode": effective_mode,
                "reason": decision.reason,
            }

    manager = ConnectorManager()
    cred = await manager.resolve_credential(user.id, platform, workspace_id)
    if not cred:
        raise HTTPException(404, f"No {provider.display_name} credential found. Connect first.")

    try:
        access_token = await manager.get_decrypted_token(cred)
    except ConnectorTokenExpiredError as e:
        raise HTTPException(
            401,
            detail={
                "code": "token_expired",
                "message": str(e),
                "platform": platform,
                "needs_reauth": True,
            },
        )

    try:
        result = await provider.call_tool(original_name, body.arguments, access_token)
    except ConnectorAPIError as e:
        raise HTTPException(e.status_code, detail=e.to_dict())
    except Exception as e:
        logger.exception("Connector tool call failed: %s", tool_name)
        raise HTTPException(502, f"Tool call failed: {e}")

    if approved_id:
        ApprovalStore().complete(approved_id, str(result)[:4000])
    return {"tool_name": tool_name, "result": result}
