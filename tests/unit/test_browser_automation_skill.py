from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognix.planner.service import PlannerService
from cognix.skills.loader import load_skill

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "browser_automation"


@pytest.mark.asyncio
async def test_browser_automation_skill_loads_and_requires_authorization() -> None:
    skill = load_skill(SKILL_DIR)

    assert skill.name == "browser_automation"
    assert {tool.name for tool in skill.tools} == {
        "plan_browser_task",
        "browser_result_template",
        "normalize_browser_observations",
    }

    plan_tool = next(tool for tool in skill.tools if tool.name == "plan_browser_task")
    payload = json.loads(
        await plan_tool.handler(
            objective="Collect coupon records from an authorized internal page",
            source_url="https://example.test/coupons",
            data_needed=["code", "created_at"],
            authorization_confirmed=False,
            preferred_route="browser",
        )
    )

    assert payload["status"] == "needs_authorization_confirmation"
    assert payload["compliance"]["approval_required"] is True
    assert payload["expected_artifact"]["fields"] == ["code", "created_at"]


@pytest.mark.asyncio
async def test_browser_automation_normalizes_observations() -> None:
    skill = load_skill(SKILL_DIR)
    normalize_tool = next(
        tool for tool in skill.tools if tool.name == "normalize_browser_observations"
    )

    payload = json.loads(
        await normalize_tool.handler(
            observations=[{"code": "A1", "created_at": "2026-05-20", "extra": "kept"}],
            fields=["code", "created_at"],
            source_url="https://example.test/coupons",
        )
    )

    assert payload["summary"] == "Normalized 1 record(s) from browser observations."
    assert payload["records"][0] == {
        "code": "A1",
        "created_at": "2026-05-20",
        "extra": "kept",
    }
    assert payload["sources"] == ["https://example.test/coupons"]


def test_browser_intent_recommends_browser_automation_skill() -> None:
    context = {
        "installed_skills": [
            {
                "name": "browser_automation",
                "description": "Plan compliant browser automation jobs.",
                "tags": "browser,automation,playwright,crawler,scrape,extraction",
                "enabled": True,
            }
        ]
    }

    recommendations = PlannerService._recommend_skills(
        "我想做一份授权后台的券码数据爬取",
        context,
    )

    assert recommendations
    assert recommendations[0]["name"] == "browser_automation"
