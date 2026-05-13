"""Unified LLM provider resolver with workspace > global > default precedence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResolvedProvider:
    """Effective LLM provider configuration."""

    base_url: str | None
    api_key: str | None
    default_model: str


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
                base_url=ws_llm.get("base_url") or global_cfg.base_url,
                api_key=ws_llm.get("api_key") or global_cfg.api_key,
                default_model=ws_llm.get("default_model") or global_cfg.default_model or "gpt-4o",
            )
        except FileNotFoundError:
            pass

    return ResolvedProvider(
        base_url=global_cfg.base_url,
        api_key=global_cfg.api_key,
        default_model=global_cfg.default_model or "gpt-4o",
    )
