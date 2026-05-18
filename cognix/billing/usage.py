"""Usage tracking and quota management."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from cognix.storage.database import get_session
from cognix.storage.models import SubscriptionModel, SubscriptionStatus, UsageRecordModel

logger = logging.getLogger(__name__)


async def record_usage(
    user_id: str,
    metric: str,
    quantity: int = 1,
    subscription_id: str | None = None,
) -> None:
    """Record usage for a user."""
    async with get_session() as session:
        record = UsageRecordModel(
            user_id=user_id,
            subscription_id=subscription_id,
            metric=metric,
            quantity=quantity,
            recorded_at=datetime.now(UTC),
        )
        session.add(record)


async def get_current_usage(user_id: str, period_start: datetime | None = None) -> dict[str, int]:
    """Get current usage for a user in the current billing period."""
    if period_start is None:
        # Default to start of current month
        now = datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        result = await session.execute(
            select(
                UsageRecordModel.metric,
                func.sum(UsageRecordModel.quantity).label("total"),
            )
            .where(UsageRecordModel.user_id == user_id)
            .where(UsageRecordModel.recorded_at >= period_start)
            .group_by(UsageRecordModel.metric)
        )

        usage = {}
        for row in result:
            usage[row.metric] = row.total or 0

    return usage


async def get_user_plan(user_id: str) -> str:
    """Get the user's current plan ID. Defaults to 'free'."""
    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel)
            .where(SubscriptionModel.user_id == user_id)
            .where(
                SubscriptionModel.status.in_(
                    [
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]
                )
            )
        )
        sub = result.scalar_one_or_none()
        return sub.plan_id if sub else "free"


async def check_quota(user_id: str, metric: str, quantity: int = 1) -> tuple[bool, int, int]:
    """Check if user has quota for a metric.

    Returns:
        (allowed, current_usage, limit)
    """
    from cognix.billing.plans import get_plan_by_id

    plan_id = await get_user_plan(user_id)
    plan = get_plan_by_id(plan_id)
    if not plan:
        plan = get_plan_by_id("free")

    # Get current usage
    usage = await get_current_usage(user_id)
    current = usage.get(metric, 0)

    # Get limit from plan
    limit_map = {
        "api_calls": plan.limits.api_calls_monthly,
        "tokens": plan.limits.tokens_monthly,
        "agent_runs": plan.limits.agent_runs_monthly,
    }
    limit = limit_map.get(metric, 999999)

    allowed = (current + quantity) <= limit
    return allowed, current, limit


async def enforce_quota(user_id: str, metric: str, quantity: int = 1) -> bool:
    """Check and record usage. Returns True if allowed, raises if quota exceeded."""
    allowed, current, limit = await check_quota(user_id, metric, quantity)
    if not allowed:
        logger.warning(
            "Quota exceeded for user %s: %s usage %d/%d",
            user_id,
            metric,
            current,
            limit,
        )
        return False

    await record_usage(user_id, metric, quantity)
    return True


async def get_usage_breakdown(
    user_id: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[dict]:
    """Get daily usage breakdown for charts.

    Returns list of {date, metric, quantity} dicts.
    """
    if period_start is None:
        now = datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        stmt = (
            select(
                func.date(UsageRecordModel.recorded_at).label("date"),
                UsageRecordModel.metric,
                func.sum(UsageRecordModel.quantity).label("total"),
            )
            .where(UsageRecordModel.user_id == user_id)
            .where(UsageRecordModel.recorded_at >= period_start)
        )
        if period_end:
            stmt = stmt.where(UsageRecordModel.recorded_at <= period_end)
        stmt = stmt.group_by(
            func.date(UsageRecordModel.recorded_at),
            UsageRecordModel.metric,
        ).order_by(func.date(UsageRecordModel.recorded_at))

        result = await session.execute(stmt)
        rows = result.all()

    return [
        {"date": str(row.date), "metric": row.metric, "quantity": row.total or 0} for row in rows
    ]
