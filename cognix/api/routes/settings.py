"""Global LLM settings REST routes."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cognix.api.routes.auth import CurrentUser
from cognix.auth.dependencies import require_permission
from cognix.local.config import ConfigStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

require_settings_read = require_permission("settings:read")
require_settings_write = require_permission("settings:write")


class UpdateLLMRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None


class TestLLMRequest(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ListModelsRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None


COMMON_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
    "claude-3-opus-20240229",
    "deepseek-chat",
    "deepseek-reasoner",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-pro",
    "ollama/llama3.1",
    "ollama/qwen2.5",
]


def _mask_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return key
    return key[:3] + "***"


def _is_masked_key(value: str) -> bool:
    """Detect masked keys like 'sk-***' returned by GET endpoints."""
    return bool(value) and value.endswith("***") and len(value) < 10


@router.get("/llm")
async def get_llm_config(
    user: CurrentUser = Depends(require_settings_read),
) -> dict:
    store = ConfigStore()
    cfg = store.get_llm()
    return {
        "base_url": cfg.base_url,
        "api_key": _mask_key(cfg.api_key),
        "default_model": cfg.default_model,
    }


@router.patch("/llm")
async def update_llm_config(
    body: UpdateLLMRequest,
    user: CurrentUser = Depends(require_settings_write),
) -> dict:
    store = ConfigStore()
    kwargs: dict = {}
    if body.base_url is not None:
        kwargs["base_url"] = body.base_url if body.base_url.strip() else None
    if body.api_key is not None:
        if _is_masked_key(body.api_key):
            pass  # don't overwrite real key with masked value
        else:
            kwargs["api_key"] = body.api_key if body.api_key.strip() else None
    if body.default_model is not None:
        kwargs["default_model"] = body.default_model.strip()

    cfg = store.update_llm(**kwargs)
    return {
        "base_url": cfg.base_url,
        "api_key": _mask_key(cfg.api_key),
        "default_model": cfg.default_model,
    }


@router.post("/llm/test")
async def test_llm_connection(
    body: TestLLMRequest,
    user: CurrentUser = Depends(require_settings_write),
) -> dict:
    store = ConfigStore()
    cfg = store.get_llm()
    model = body.model or cfg.default_model
    api_key = body.api_key or cfg.api_key
    base_url = body.base_url or cfg.base_url

    if not api_key:
        return {"ok": False, "error": "No API key configured. Set one in Model Providers settings."}

    try:
        import litellm

        kwargs: dict = {
            "model": model,
            "messages": [{"role": "user", "content": "Say hi in one word."}],
            "max_tokens": 10,
            "api_key": api_key,
        }
        if base_url:
            kwargs["api_base"] = base_url

        t0 = time.monotonic()
        await litellm.acompletion(**kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": True, "model": model, "latency_ms": latency_ms}
    except ImportError:
        return {"ok": False, "error": "litellm is not installed. Run: pip install litellm"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/llm/models")
async def list_models(
    body: ListModelsRequest,
    user: CurrentUser = Depends(require_settings_read),
) -> dict:
    store = ConfigStore()
    cfg = store.get_llm()
    api_key = body.api_key or cfg.api_key
    base_url = body.base_url or cfg.base_url

    models: list[str] = []

    # Try fetching from the provider's /models endpoint directly
    if base_url:
        try:
            import httpx

            headers: dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", data) if isinstance(data, dict) else data
                    if isinstance(items, list):
                        models = [
                            m.get("id", m) if isinstance(m, dict) else str(m)
                            for m in items
                        ]
        except Exception:
            pass

    # Fallback to litellm's built-in model list
    if not models:
        try:
            import litellm

            if hasattr(litellm, "model_list") and isinstance(litellm.model_list, list):
                models = list(litellm.model_list)
        except ImportError:
            pass

    if not models:
        models = COMMON_MODELS

    return {"models": sorted(models)}
