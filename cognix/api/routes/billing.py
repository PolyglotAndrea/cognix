"""Billing and subscription API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from cognix.auth.dependencies import CurrentUser, get_current_user
from cognix.billing.plans import get_all_plans, get_plan_by_id
from cognix.billing.stripe_client import stripe_client
from cognix.billing.usage import get_current_usage, get_user_plan
from cognix.storage.database import get_session
from cognix.storage.models import SubscriptionModel, SubscriptionStatus

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Schemas ─────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan_id: str  # starter, pro


class PortalRequest(BaseModel):
    return_url: str = "http://localhost:5173/billing"


# ── Plans ───────────────────────────────────────────────────────────


@router.get("/plans")
async def list_plans() -> list[dict]:
    """Get all available subscription plans."""
    return [plan.to_dict() for plan in get_all_plans()]


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str) -> dict:
    """Get a specific plan by ID."""
    plan = get_plan_by_id(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan.to_dict()


# ── Subscription ────────────────────────────────────────────────────


@router.get("/subscription")
async def get_subscription(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get current user's subscription."""
    plan_id = await get_user_plan(user.id)
    plan = get_plan_by_id(plan_id)

    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user.id)
        )
        sub = result.scalar_one_or_none()

    return {
        "plan": plan.to_dict() if plan else None,
        "status": sub.status.value if sub else "free",
        "current_period_start": sub.current_period_start.isoformat() if sub and sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "stripe_customer_id": sub.stripe_customer_id if sub else None,
    }


# ── Checkout ────────────────────────────────────────────────────────


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a Stripe Checkout session for upgrading."""
    plan = get_plan_by_id(body.plan_id)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    if plan.id == "free":
        raise HTTPException(400, "Cannot checkout free plan")
    if not plan.stripe_price_id:
        raise HTTPException(400, "Plan not available for purchase")

    # Get or create Stripe customer
    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user.id)
        )
        sub = result.scalar_one_or_none()

        customer_id = sub.stripe_customer_id if sub else None

        if not customer_id:
            customer_id = stripe_client.create_customer(
                email=user.email,
                name=user.name,
                metadata={"user_id": user.id},
            )
            if not customer_id:
                raise HTTPException(500, "Failed to create Stripe customer")

            # Save customer ID
            if sub:
                sub.stripe_customer_id = customer_id
            else:
                sub = SubscriptionModel(
                    id=uuid.uuid4().hex,
                    user_id=user.id,
                    plan_id="free",
                    stripe_customer_id=customer_id,
                    status=SubscriptionStatus.INCOMPLETE,
                )
                session.add(sub)

    # Create checkout session
    base_url = str(request.base_url).rstrip("/")
    checkout_url = stripe_client.create_checkout_session(
        customer_id=customer_id,
        price_id=plan.stripe_price_id,
        success_url=f"{base_url}/billing/success",
        cancel_url=f"{base_url}/billing/cancel",
        metadata={"user_id": user.id, "plan_id": plan.id},
    )

    if not checkout_url:
        raise HTTPException(500, "Failed to create checkout session")

    return {"checkout_url": checkout_url}


# ── Portal ──────────────────────────────────────────────────────────


@router.post("/portal")
async def create_portal(
    body: PortalRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a Stripe Customer Portal session."""
    async with get_session() as session:
        result = await session.execute(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user.id)
        )
        sub = result.scalar_one_or_none()

    if not sub or not sub.stripe_customer_id:
        raise HTTPException(400, "No active subscription found")

    portal_url = stripe_client.create_portal_session(
        customer_id=sub.stripe_customer_id,
        return_url=body.return_url,
    )

    if not portal_url:
        raise HTTPException(500, "Failed to create portal session")

    return {"portal_url": portal_url}


# ── Usage ───────────────────────────────────────────────────────────


@router.get("/usage")
async def get_usage(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get current usage for the authenticated user."""
    usage = await get_current_usage(user.id)
    plan_id = await get_user_plan(user.id)
    plan = get_plan_by_id(plan_id)

    return {
        "plan_id": plan_id,
        "usage": {
            "api_calls": usage.get("api_calls", 0),
            "tokens": usage.get("tokens", 0),
            "agent_runs": usage.get("agent_runs", 0),
        },
        "limits": {
            "api_calls": plan.limits.api_calls_monthly if plan else 1000,
            "tokens": plan.limits.tokens_monthly if plan else 10000,
            "agent_runs": plan.limits.agent_runs_monthly if plan else 100,
        },
    }


# ── Webhook ─────────────────────────────────────────────────────────


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(400, "Missing stripe-signature header")

    event = stripe_client.construct_webhook_event(payload, sig_header)
    if not event:
        raise HTTPException(400, "Invalid webhook signature")

    from cognix.billing.webhooks import process_webhook_event

    handled = await process_webhook_event(event)

    return {"received": True, "handled": handled}
