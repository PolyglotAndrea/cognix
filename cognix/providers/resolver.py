"""Unified LLM provider resolver with workspace > global > default precedence."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


@dataclass
class ResolvedProvider:
    """Effective LLM provider configuration."""

    base_url: str | None
    api_key: str | None
    default_model: str


def normalize_openai_base_url(base_url: str | None) -> str | None:
    """Normalize OpenAI-compatible gateway roots to their API prefix.

    New API / One API style gateways often expose the web console at the
    origin root and the OpenAI-compatible API below /v1.  Accepting the root
    URL in settings is friendlier and avoids LiteLLM receiving HTML instead of
    JSON from a web console.
    """
    if not base_url:
        return None

    value = base_url.strip().rstrip("/")
    if not value:
        return None

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value

    if parsed.path in ("", "/"):
        return urlunparse(parsed._replace(path="/v1"))

    return value


def resolve_provider(workspace_id: str | None = None) -> ResolvedProvider:
    """Resolve effective LLM provider.

    Precedence: workspace settings > global config > defaults.
    """
    from cognix.local.config import ConfigStore

    global_cfg = ConfigStore().get_llm()

    if workspace_id:
        try:
            from cognix.local.workspace_config import WorkspaceConfigStore

            ws_llm = WorkspaceConfigStore(workspace_id).get_settings().get("llm", {})
            return ResolvedProvider(
                base_url=normalize_openai_base_url(ws_llm.get("base_url") or global_cfg.base_url),
                api_key=ws_llm.get("api_key") or global_cfg.api_key,
                default_model=ws_llm.get("default_model") or global_cfg.default_model or "gpt-4o",
            )
        except FileNotFoundError:
            pass

    return ResolvedProvider(
        base_url=normalize_openai_base_url(global_cfg.base_url),
        api_key=global_cfg.api_key,
        default_model=global_cfg.default_model or "gpt-4o",
    )
