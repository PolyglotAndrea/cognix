"""Plan definitions and management."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanLimits:
    """Usage limits for a plan."""

    max_agents: int = 3
    max_tasks: int = 10
    api_calls_monthly: int = 1_000
    tokens_monthly: int = 10_000
    agent_runs_monthly: int = 100


@dataclass
class PlanFeatures:
    """Features available in a plan."""

    orchestration: bool = False
    skills_marketplace: bool = False
    workflow_builder: bool = False
    priority_support: bool = False
    custom_models: bool = False
    sso: bool = False


@dataclass
class Plan:
    """Subscription plan definition."""

    id: str
    name: str
    stripe_price_id: str | None
    price_monthly: float
    price_yearly: float
    limits: PlanLimits = field(default_factory=PlanLimits)
    features: PlanFeatures = field(default_factory=PlanFeatures)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "price_monthly": self.price_monthly,
            "price_yearly": self.price_yearly,
            "limits": {
                "max_agents": self.limits.max_agents,
                "max_tasks": self.limits.max_tasks,
                "api_calls_monthly": self.limits.api_calls_monthly,
                "tokens_monthly": self.limits.tokens_monthly,
                "agent_runs_monthly": self.limits.agent_runs_monthly,
            },
            "features": {
                "orchestration": self.features.orchestration,
                "skills_marketplace": self.features.skills_marketplace,
                "workflow_builder": self.features.workflow_builder,
                "priority_support": self.features.priority_support,
                "custom_models": self.features.custom_models,
                "sso": self.features.sso,
            },
        }


# Default plans
DEFAULT_PLANS: list[Plan] = [
    Plan(
        id="free",
        name="Free",
        stripe_price_id=None,
        price_monthly=0,
        price_yearly=0,
        limits=PlanLimits(
            max_agents=3,
            max_tasks=10,
            api_calls_monthly=1_000,
            tokens_monthly=10_000,
            agent_runs_monthly=100,
        ),
        features=PlanFeatures(
            orchestration=False,
            skills_marketplace=False,
            workflow_builder=False,
        ),
    ),
    Plan(
        id="starter",
        name="Starter",
        stripe_price_id=None,  # Set via env: COGNIX_BILLING__STRIPE_PRICE_STARTER
        price_monthly=29,
        price_yearly=290,
        limits=PlanLimits(
            max_agents=10,
            max_tasks=100,
            api_calls_monthly=10_000,
            tokens_monthly=100_000,
            agent_runs_monthly=1_000,
        ),
        features=PlanFeatures(
            orchestration=True,
            skills_marketplace=True,
            workflow_builder=False,
        ),
    ),
    Plan(
        id="pro",
        name="Pro",
        stripe_price_id=None,  # Set via env: COGNIX_BILLING__STRIPE_PRICE_PRO
        price_monthly=99,
        price_yearly=990,
        limits=PlanLimits(
            max_agents=50,
            max_tasks=500,
            api_calls_monthly=100_000,
            tokens_monthly=1_000_000,
            agent_runs_monthly=10_000,
        ),
        features=PlanFeatures(
            orchestration=True,
            skills_marketplace=True,
            workflow_builder=True,
            priority_support=True,
            custom_models=True,
        ),
    ),
    Plan(
        id="enterprise",
        name="Enterprise",
        stripe_price_id=None,  # Custom pricing
        price_monthly=0,
        price_yearly=0,
        limits=PlanLimits(
            max_agents=999999,
            max_tasks=999999,
            api_calls_monthly=999999,
            tokens_monthly=999999,
            agent_runs_monthly=999999,
        ),
        features=PlanFeatures(
            orchestration=True,
            skills_marketplace=True,
            workflow_builder=True,
            priority_support=True,
            custom_models=True,
            sso=True,
        ),
    ),
]


def get_plan_by_id(plan_id: str) -> Plan | None:
    """Get a plan by its ID."""
    for plan in DEFAULT_PLANS:
        if plan.id == plan_id:
            return plan
    return None


def get_all_plans() -> list[Plan]:
    """Get all available plans."""
    return DEFAULT_PLANS
