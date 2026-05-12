"""Shared retry backoff logic for scheduled tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def compute_retry_delay(
    attempts: int,
    base_seconds: int = 30,
    max_seconds: int = 3600,
) -> float:
    """Exponential backoff: base * 2^(attempts-1), capped at max."""
    return min(base_seconds * (2 ** max(attempts - 1, 0)), max_seconds)


def compute_retry_at(
    attempts: int,
    base_seconds: int = 30,
    max_seconds: int = 3600,
) -> datetime:
    """Return the UTC datetime when the next retry should fire."""
    delay = compute_retry_delay(attempts, base_seconds, max_seconds)
    return datetime.now(UTC) + timedelta(seconds=delay)
