"""Stripe API client wrapper."""

from __future__ import annotations

import logging
from typing import Any

from cognix.config import get_settings

logger = logging.getLogger(__name__)


def _get_stripe():
    """Lazy import stripe to avoid import errors when not installed."""
    try:
        import stripe

        settings = get_settings()
        if settings.billing.stripe_secret_key:
            stripe.api_key = settings.billing.stripe_secret_key
        return stripe
    except ImportError:
        logger.warning("stripe package not installed. Run: pip install stripe")
        return None


class StripeClient:
    """Wrapper around Stripe API."""

    def create_customer(self, email: str, name: str, metadata: dict | None = None) -> str | None:
        """Create a Stripe customer. Returns customer ID."""
        stripe = _get_stripe()
        if not stripe:
            return None

        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata=metadata or {},
            )
            return customer.id
        except Exception as e:
            logger.error("Failed to create Stripe customer: %s", e)
            return None

    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
    ) -> str | None:
        """Create a Stripe Checkout session. Returns session URL."""
        stripe = _get_stripe()
        if not stripe:
            return None

        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {},
            )
            return session.url
        except Exception as e:
            logger.error("Failed to create checkout session: %s", e)
            return None

    def create_portal_session(self, customer_id: str, return_url: str) -> str | None:
        """Create a Stripe Customer Portal session. Returns portal URL."""
        stripe = _get_stripe()
        if not stripe:
            return None

        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except Exception as e:
            logger.error("Failed to create portal session: %s", e)
            return None

    def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a Stripe subscription."""
        stripe = _get_stripe()
        if not stripe:
            return False

        try:
            stripe.Subscription.delete(subscription_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel subscription: %s", e)
            return False

    def get_subscription(self, subscription_id: str) -> dict | None:
        """Get subscription details from Stripe."""
        stripe = _get_stripe()
        if not stripe:
            return None

        try:
            sub = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": sub.id,
                "status": sub.status,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
            }
        except Exception as e:
            logger.error("Failed to get subscription: %s", e)
            return None

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Any | None:
        """Verify and construct a webhook event."""
        stripe = _get_stripe()
        if not stripe:
            return None

        settings = get_settings()
        webhook_secret = settings.billing.stripe_webhook_secret
        if not webhook_secret:
            logger.error("Stripe webhook secret not configured")
            return None

        try:
            return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:
            logger.error("Webhook verification failed: %s", e)
            return None


# Singleton instance
stripe_client = StripeClient()
