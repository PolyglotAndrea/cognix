"""Local-first remote bot bridge configuration."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cognix.local.home import CognixHome

BotProvider = Literal["lark", "feishu", "dingtalk", "wechat"]


@dataclass(frozen=True)
class BotConfig:
    id: str
    name: str
    provider: BotProvider
    workspace_id: str
    agent_id: str
    secret_hash: str
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("secret_hash", None)
        data["webhook_path"] = f"/api/v1/bots/{self.provider}/{self.id}/webhook"
        return data


class BotConfigStore:
    """Stores remote bot bridge configs under ``~/.cognix/bots``."""

    def __init__(self, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.bots_dir.mkdir(parents=True, exist_ok=True)

    @property
    def bots_dir(self) -> Path:
        return self.home.root / "bots"

    def create(
        self,
        *,
        name: str,
        provider: BotProvider,
        workspace_id: str,
        agent_id: str,
        secret: str,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> BotConfig:
        now = datetime.now(UTC).isoformat()
        bot = BotConfig(
            id=uuid.uuid4().hex[:12],
            name=name,
            provider=provider,
            workspace_id=workspace_id,
            agent_id=agent_id,
            secret_hash=self.hash_secret(secret),
            enabled=enabled,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        self._write(bot)
        return bot

    def get(self, bot_id: str) -> BotConfig | None:
        path = self._path(bot_id)
        if not path.exists():
            return None
        return BotConfig(**json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[BotConfig]:
        bots = []
        for path in sorted(self.bots_dir.glob("*.json")):
            bot = self.get(path.stem)
            if bot:
                bots.append(bot)
        return sorted(bots, key=lambda bot: bot.updated_at, reverse=True)

    def update(self, bot_id: str, updates: dict[str, Any]) -> BotConfig:
        bot = self.get(bot_id)
        if not bot:
            raise FileNotFoundError(f"Bot bridge not found: {bot_id}")
        data = asdict(bot)
        if "secret" in updates:
            data["secret_hash"] = self.hash_secret(str(updates.pop("secret")))
        data.update(updates)
        data["updated_at"] = datetime.now(UTC).isoformat()
        updated = BotConfig(**data)
        self._write(updated)
        return updated

    def delete(self, bot_id: str) -> bool:
        path = self._path(bot_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def verify_secret(self, bot: BotConfig, secret: str) -> bool:
        return hmac.compare_digest(bot.secret_hash, self.hash_secret(secret))

    def verify_signature(
        self,
        bot: BotConfig,
        *,
        body: bytes,
        timestamp: str,
        signature: str,
    ) -> bool:
        if not timestamp or not signature:
            return False
        digest = hmac.new(
            bot.secret_hash.encode("utf-8"),
            timestamp.encode("utf-8") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, signature.removeprefix("sha256="))

    def _path(self, bot_id: str) -> Path:
        return self.bots_dir / f"{bot_id}.json"

    def _write(self, bot: BotConfig) -> None:
        self._path(bot.id).write_text(
            json.dumps(asdict(bot), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
