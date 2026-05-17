"""Stripe webhook event handlers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from cognix.storage.database import get_session
from cognix.storage.models import SubscriptionModel, SubscriptionStatus

logger = logging.getLogger(__name__)

# In-memory idempotency cache (event_id → True). Survives within a process.
_processed_event_ids: set[str] = set()
_MAX_CACHE_SIZE = 10000


def _is_duplicate(event: dict) -> bool:
    """Check if a webhook event was already processed (idempotency guard)."""
    event_id = event.get("id", "")
    if not event_id:
        return False
    if event_id in _processed_event_ids:
        return True
    # Evict oldest entries if cache grows too large
    if len(_processed_event_ids) >= _MAX_CACHE_SIZE:
        _processed_event_ids.clear()
    _processed_event_ids.add(event_id)
    return False


_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "trialing": SubscriptionStatus.TRIALING,
    "incomplete": SubscriptionStatus.INCOMPLETE,
}


def _map_status(stripe_status: str) -> SubscriptionStatus:
    """Map Stripe status to our status, defaulting to INCOMPLETE for unknowns."""
    mapped = _STATUS_MAP.get(stripe_status)
    if mapped is None:
        logger.warning("Unknown Stripe status '%s', defaulting to INCOMPLETE", stripe_status)
        return SubscriptionStatus.INCOMPLETE
    return mapped


async def handle_checkout_completed(event: dict) -> None:
    """Handle checkout.session.completed event."""
    session_data = event["data"]["object"]
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")
    user_id = session_data.get("metadata", {}).get("user_id")

    if not user_id:
        logger.warning("checkout.session.completed: missing user_id in metadata")
        return

    logger.info("Checkout completed for user %s, subscription %s", user_id, subscription_id)

    # Create or update subscription record
    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.stripe_subscription_id = subscription_id
            sub.stripe_customer_id = customer_id
            sub.status = SubscriptionStatus.ACTIVE
        else:
            sub = SubscriptionModel(
                id=user_id,  # Use user_id as subscription id for simplicity
                user_id=user_id,
                plan_id="starter",  # Will be updated by subscription.created
                stripe_subscription_id=subscription_id,
                stripe_customer_id=customer_id,
                status=SubscriptionStatus.ACTIVE,
            )
            session.add(sub)


async def handle_subscription_created(event: dict) -> None:
    """Handle customer.subscription.created event."""
    sub_data = event["data"]["object"]
    stripe_sub_id = sub_data["id"]
    customer_id = sub_data["customer"]
    status = sub_data["status"]

    our_status = _map_status(status)

    logger.info("Subscription created: %s (status: %s)", stripe_sub_id, status)

    async with get_session() as session:
        # Find subscription by stripe_subscription_id or customer_id
        result = await session.execute(
            select(SubscriptionModel).where(
                (SubscriptionModel.stripe_subscription_id == stripe_sub_id)
                | (SubscriptionModel.stripe_customer_id == customer_id)
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.stripe_subscription_id = stripe_sub_id
            sub.status = our_status
            # Extract period dates
            period_start = sub_data.get("current_period_start")
            period_end = sub_data.get("current_period_end")
            if period_start:
                sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)
        else:
            logger.warning("No subscription found for stripe_sub_id=%s", stripe_sub_id)


async def handle_subscription_updated(event: dict) -> None:
    """Handle customer.subscription.updated event."""
    sub_data = event["data"]["object"]
    stripe_sub_id = sub_data["id"]
    status = sub_data["status"]

    our_status = _map_status(status)

    logger.info("Subscription updated: %s (status: %s)", stripe_sub_id, status)

    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(
                SubscriptionModel.stripe_subscription_id == stripe_sub_id
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.status = our_status
            # Update plan_id from Stripe metadata if available
            plan_id = sub_data.get("metadata", {}).get("plan_id")
            if plan_id:
                sub.plan_id = plan_id
            period_start = sub_data.get("current_period_start")
            period_end = sub_data.get("current_period_end")
            if period_start:
                sub.current_period_start = datetime.fromtimestamp(period_start, tz=UTC)
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)


async def handle_subscription_deleted(event: dict) -> None:
    """Handle customer.subscription.deleted event."""
    sub_data = event["data"]["object"]
    stripe_sub_id = sub_data["id"]

    logger.info("Subscription deleted: %s", stripe_sub_id)

    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(
                SubscriptionModel.stripe_subscription_id == stripe_sub_id
            )
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.status = SubscriptionStatus.CANCELED


async def handle_invoice_paid(event: dict) -> None:
    """Handle invoice.paid event."""
    invoice_data = event["data"]["object"]
    customer_id = invoice_data.get("customer")
    subscription_id = invoice_data.get("subscription")

    logger.info("Invoice paid: customer=%s subscription=%s", customer_id, subscription_id)

    # Ensure subscription is active
    if subscription_id:
        async with get_session() as session:
            result = await session.execute(
                select(SubscriptionModel).where(
                    SubscriptionModel.stripe_subscription_id == subscription_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.ACTIVE


async def handle_invoice_payment_failed(event: dict) -> None:
    """Handle invoice.payment_failed event."""
    invoice_data = event["data"]["object"]
    subscription_id = invoice_data.get("subscription")

    logger.warning("Invoice payment failed: subscription=%s", subscription_id)

    if subscription_id:
        async with get_session() as session:
            result = await session.execute(
                select(SubscriptionModel).where(
                    SubscriptionModel.stripe_subscription_id == subscription_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.PAST_DUE


# Event handler registry
WEBHOOK_HANDLERS: dict[str, Any] = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
}


async def process_webhook_event(event: dict) -> bool:
    """Process a Stripe webhook event. Returns True if handled."""
    if _is_duplicate(event):
        logger.info("Skipping duplicate webhook event: %s", event.get("id"))
        return True

    event_type = event.get("type")
    handler = WEBHOOK_HANDLERS.get(event_type)

    if handler:
        await handler(event)
        return True

    logger.debug("Unhandled webhook event type: %s", event_type)
    return False
