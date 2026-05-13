"""Entitlement and BYOK execution gate."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from cognix.billing.usage import get_user_plan
from cognix.local.config import ConfigStore

logger = logging.getLogger(__name__)

# Plans that allow paid model execution without BYOK
PAID_PLANS = {"starter", "pro", "enterprise"}


@dataclass
class EntitlementResult:
    """Result of an entitlement check."""

    allowed: bool
    reason: str = ""
    requires_byok: bool = False
    requires_plan: bool = False

    def to_dict(self) -> dict:
        return {
            "code": "entitlement_required",
            "message": self.reason,
            "requires_byok": self.requires_byok,
            "requires_plan": self.requires_plan,
        }


class EntitlementService:
    """Gate model execution behind BYOK or paid plan."""

    @staticmethod
    async def check_model_execution(
        user_id: str,
        workspace_id: str | None = None,
    ) -> EntitlementResult:
        """Check if user can execute a model call.

        Allowed if:
        1. Workspace has BYOK configured (llm.api_key set in workspace or global config), OR
        2. User has active paid subscription (starter/pro/enterprise)
        """
        # Check BYOK: workspace-level or global-level API key
        if workspace_id:
            try:
                from cognix.local.workspace_config import WorkspaceConfigStore

                ws_settings = WorkspaceConfigStore(workspace_id).get_settings()
                ws_llm = ws_settings.get("llm", {})
                if ws_llm.get("api_key"):
                    return EntitlementResult(allowed=True)
            except FileNotFoundError:
                pass

        # Check global config
        global_cfg = ConfigStore().get_llm()
        if global_cfg.api_key:
            return EntitlementResult(allowed=True)

        # Check paid plan
        plan_id = await get_user_plan(user_id)
        if plan_id in PAID_PLANS:
            return EntitlementResult(allowed=True)

        # Neither BYOK nor paid plan
        return EntitlementResult(
            allowed=False,
            reason="Configure a model provider (BYOK) or upgrade to a paid plan to execute tasks.",
            requires_byok=True,
            requires_plan=True,
        )

    @staticmethod
    async def check_workspace_access(
        user_id: str,
        workspace_id: str,
    ) -> EntitlementResult:
        """Check if user can access a workspace."""
        # All users can access workspaces for now
        return EntitlementResult(allowed=True)
