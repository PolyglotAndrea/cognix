"""Schedule parsing helpers shared by API, store, and dispatchers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger


def parse_schedule(schedule: str) -> tuple[str, Any]:
    """Parse a persisted schedule into an engine schedule type and value."""
    schedule = schedule.strip()
    if " " in schedule and len(schedule.split()) == 5:
        return "cron", schedule
    if schedule.startswith("every "):
        parts = schedule.split()
        val = int(parts[1][:-1])
        unit = parts[1][-1]
        seconds = val * {"s": 1, "m": 60, "h": 3600}.get(unit, 1)
        return "interval", seconds
    return "once", datetime.fromisoformat(schedule)


def schedule_trigger(schedule: str) -> Any:
    """Build an APScheduler trigger for a persisted schedule string."""
    schedule_type, value = parse_schedule(schedule)
    if schedule_type == "cron":
        minute, hour, day, month, day_of_week = value.split()
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
    if schedule_type == "interval":
        return IntervalTrigger(seconds=value)
    return DateTrigger(run_date=value)


def next_run_time(schedule: str, *, now: datetime | None = None) -> datetime | None:
    """Return the next fire time for a persisted schedule."""
    trigger = schedule_trigger(schedule)
    timezone = getattr(trigger, "timezone", None)
    current = now or datetime.now(timezone)
    if timezone and current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    elif timezone:
        current = current.astimezone(timezone)
    return trigger.get_next_fire_time(None, current)
