"""Bot health monitoring — tracks per-bot message counts, errors, and latency."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BotHealth:
    bot_id: str
    message_count: int = 0
    error_count: int = 0
    last_success_at: float | None = None
    last_error_at: float | None = None
    latencies: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        if self.message_count == 0:
            return 0.0
        return self.error_count / self.message_count

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
        }


class BotHealthMonitor:
    """In-memory health metrics per bot."""

    def __init__(self) -> None:
        self._health: dict[str, BotHealth] = defaultdict(lambda: BotHealth(bot_id=""))
        self._max_latencies = 100  # Keep last N latencies per bot

    def record_success(self, bot_id: str, latency_ms: float) -> None:
        h = self._health[bot_id]
        h.bot_id = bot_id
        h.message_count += 1
        h.last_success_at = time.monotonic()
        h.latencies.append(latency_ms)
        if len(h.latencies) > self._max_latencies:
            h.latencies = h.latencies[-self._max_latencies:]

    def record_error(self, bot_id: str, error: str) -> None:
        h = self._health[bot_id]
        h.bot_id = bot_id
        h.message_count += 1
        h.error_count += 1
        h.last_error_at = time.monotonic()

    def get_health(self, bot_id: str) -> dict:
        h = self._health.get(bot_id)
        if not h:
            return {"bot_id": bot_id, "message_count": 0, "error_count": 0}
        return h.to_dict()

    def get_all_health(self) -> list[dict]:
        return [h.to_dict() for h in self._health.values()]


# Global singleton
_monitor = BotHealthMonitor()


def get_health_monitor() -> BotHealthMonitor:
    return _monitor
