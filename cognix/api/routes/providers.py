"""Provider discovery routes used by the workspace UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cognix.api.routes.settings import discover_llm_models
from cognix.auth.dependencies import CurrentUser, require_permission

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])

require_provider_read = require_permission("settings:read")


@router.get("/models")
async def list_provider_models(
    user: CurrentUser = Depends(require_provider_read),
) -> list[str]:
    """Return available model ids for lightweight selectors."""
    return await discover_llm_models()
