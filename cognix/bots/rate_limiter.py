"""In-memory sliding window rate limiter for bot message dispatch."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Sliding window rate limiter per bot_id.

    Uses in-memory counters — works for single-node and small multi-node.
    Falls back to no-op if limits are not configured.
    """

    def __init__(self) -> None:
        # bot_id -> list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._limits: dict[str, dict] = {}

    def configure(self, bot_id: str, rate_per_minute: int = 30, rate_per_hour: int = 500) -> None:
        """Set rate limits for a specific bot."""
        self._limits[bot_id] = {
            "per_minute": rate_per_minute,
            "per_hour": rate_per_hour,
        }

    def check(self, bot_id: str) -> bool:
        """Check if a message is allowed for this bot. Returns True if allowed."""
        limits = self._limits.get(bot_id)
        if not limits:
            return True  # No limits configured, allow all

        now = time.monotonic()
        window = self._windows[bot_id]

        # Clean old entries
        cutoff = now - 3600  # 1 hour
        self._windows[bot_id] = [t for t in window if t > cutoff]
        window = self._windows[bot_id]

        # Check hourly limit
        if len(window) >= limits["per_hour"]:
            logger.warning("Bot %s hourly rate limit exceeded (%d)", bot_id, limits["per_hour"])
            return False

        # Check per-minute limit
        minute_cutoff = now - 60
        recent = sum(1 for t in window if t > minute_cutoff)
        if recent >= limits["per_minute"]:
            logger.warning(
                "Bot %s per-minute rate limit exceeded (%d)",
                bot_id,
                limits["per_minute"],
            )
            return False

        return True

    def record(self, bot_id: str) -> None:
        """Record a message dispatch for this bot."""
        self._windows[bot_id].append(time.monotonic())

    def get_usage(self, bot_id: str) -> dict:
        """Get current usage stats for a bot."""
        now = time.monotonic()
        window = self._windows.get(bot_id, [])
        minute_cutoff = now - 60
        hour_cutoff = now - 3600

        return {
            "per_minute_count": sum(1 for t in window if t > minute_cutoff),
            "per_hour_count": sum(1 for t in window if t > hour_cutoff),
            "limits": self._limits.get(bot_id, {}),
        }


# Global singleton
_rate_limiter = TokenBucketRateLimiter()


def get_rate_limiter() -> TokenBucketRateLimiter:
    return _rate_limiter
