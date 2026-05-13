"""Global LLM configuration stored in ~/.cognix/config.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MISSING = object()


@dataclass
class LLMConfig:
    base_url: str | None = None
    api_key: str | None = None
    default_model: str = "gpt-4o"


class ConfigStore:
    """Read and write global configuration in ~/.cognix/config.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".cognix" / "config.json")

    def get_llm(self) -> LLMConfig:
        data = self._read()
        llm = data.get("llm", {})
        return LLMConfig(
            base_url=llm.get("base_url"),
            api_key=llm.get("api_key"),
            default_model=llm.get("default_model", "gpt-4o"),
        )

    def update_llm(
        self,
        *,
        base_url: str | None | object = _MISSING,
        api_key: str | None | object = _MISSING,
        default_model: str | object = _MISSING,
    ) -> LLMConfig:
        data = self._read()
        llm: dict[str, Any] = data.get("llm", {})
        if base_url is not _MISSING:
            llm["base_url"] = base_url
        if api_key is not _MISSING:
            llm["api_key"] = api_key
        if default_model is not _MISSING:
            llm["default_model"] = default_model
        data["llm"] = llm
        self._write(data)
        return self.get_llm()

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read config from %s: %s", self._path, exc)
            return {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)
