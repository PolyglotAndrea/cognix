"""Stripe webhook event handlers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from cognix.storage.database import get_session
from cognix.storage.models import SubscriptionModel, SubscriptionStatus

logger = logging.getLogger(__name__)


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

    # Map Stripe status to our status
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELED,
        "trialing": SubscriptionStatus.TRIALING,
        "incomplete": SubscriptionStatus.INCOMPLETE,
    }
    our_status = status_map.get(status, SubscriptionStatus.ACTIVE)

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
                sub.current_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
        else:
            logger.warning("No subscription found for stripe_sub_id=%s", stripe_sub_id)


async def handle_subscription_updated(event: dict) -> None:
    """Handle customer.subscription.updated event."""
    sub_data = event["data"]["object"]
    stripe_sub_id = sub_data["id"]
    status = sub_data["status"]

    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELED,
        "trialing": SubscriptionStatus.TRIALING,
        "incomplete": SubscriptionStatus.INCOMPLETE,
    }
    our_status = status_map.get(status, SubscriptionStatus.ACTIVE)

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
            period_start = sub_data.get("current_period_start")
            period_end = sub_data.get("current_period_end")
            if period_start:
                sub.current_period_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)


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
WEBHOOK_HANDLERS: dict[str, callable] = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
}


async def process_webhook_event(event: dict) -> bool:
    """Process a Stripe webhook event. Returns True if handled."""
    event_type = event.get("type")
    handler = WEBHOOK_HANDLERS.get(event_type)

    if handler:
        await handler(event)
        return True

    logger.debug("Unhandled webhook event type: %s", event_type)
    return False
