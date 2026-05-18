"""Tests for the billing module."""

from __future__ import annotations

from cognix.billing.plans import get_all_plans, get_plan_by_id
from cognix.billing.webhooks import WEBHOOK_HANDLERS


class TestPlans:
    def test_get_all_plans(self):
        plans = get_all_plans()
        assert len(plans) == 4
        plan_ids = [p.id for p in plans]
        assert "free" in plan_ids
        assert "starter" in plan_ids
        assert "pro" in plan_ids
        assert "enterprise" in plan_ids

    def test_free_plan(self):
        plan = get_plan_by_id("free")
        assert plan is not None
        assert plan.price_monthly == 0
        assert plan.limits.max_agents == 3
        assert plan.limits.api_calls_monthly == 1_000
        assert plan.features.orchestration is False

    def test_starter_plan(self):
        plan = get_plan_by_id("starter")
        assert plan is not None
        assert plan.price_monthly == 29
        assert plan.limits.max_agents == 10
        assert plan.limits.api_calls_monthly == 10_000
        assert plan.features.orchestration is True
        assert plan.features.skills_marketplace is True

    def test_pro_plan(self):
        plan = get_plan_by_id("pro")
        assert plan is not None
        assert plan.price_monthly == 99
        assert plan.limits.max_agents == 50
        assert plan.features.workflow_builder is True
        assert plan.features.custom_models is True

    def test_enterprise_plan(self):
        plan = get_plan_by_id("enterprise")
        assert plan is not None
        assert plan.price_monthly == 0  # Custom pricing
        assert plan.limits.max_agents == 999999
        assert plan.features.sso is True

    def test_unknown_plan(self):
        assert get_plan_by_id("unknown") is None

    def test_plan_to_dict(self):
        plan = get_plan_by_id("starter")
        d = plan.to_dict()
        assert d["id"] == "starter"
        assert d["name"] == "Starter"
        assert d["price_monthly"] == 29
        assert "limits" in d
        assert "features" in d
        assert d["limits"]["max_agents"] == 10

    def test_plan_yearly_discount(self):
        starter = get_plan_by_id("starter")
        assert starter.price_yearly < starter.price_monthly * 12


class TestWebhookHandlers:
    def test_all_handlers_registered(self):
        expected_events = [
            "checkout.session.completed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.paid",
            "invoice.payment_failed",
        ]
        for event_type in expected_events:
            assert event_type in WEBHOOK_HANDLERS

    def test_handlers_are_callable(self):
        for handler in WEBHOOK_HANDLERS.values():
            assert callable(handler)
