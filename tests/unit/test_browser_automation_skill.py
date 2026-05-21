from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognix.planner.service import PlannerService
from cognix.skills.loader import load_skill

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "browser_automation"
DOMAIN_SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "life_partner_coupon_codes"


@pytest.mark.asyncio
async def test_browser_automation_skill_loads_and_requires_authorization() -> None:
    skill = load_skill(SKILL_DIR)

    assert skill.name == "browser_automation"
    assert {tool.name for tool in skill.tools} == {
        "plan_browser_task",
        "browser_task_contract",
        "browser_result_template",
        "normalize_browser_observations",
        "browser_error_recovery",
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
    assert payload["runtime_boundary"]["executor"] == "internal_browser_mcp_runtime"
    assert "browser.goto" in payload["runtime_boundary"]["canonical_actions"]
    assert payload["expected_artifact"]["fields"] == ["code", "created_at"]


@pytest.mark.asyncio
async def test_browser_task_contract_defines_runtime_boundary() -> None:
    skill = load_skill(SKILL_DIR)
    contract_tool = next(tool for tool in skill.tools if tool.name == "browser_task_contract")

    payload = json.loads(
        await contract_tool.handler(
            task_type="download_export",
            requires_login=True,
            handles_sensitive_data=True,
            output_format="exported_file",
        )
    )

    assert payload["runtime"]["kind"] == "internal_browser_mcp_runtime"
    assert payload["runtime"]["hidden_from_general_users"] is True
    assert payload["approval_policy"]["required"] is True
    assert "login_session_reuse" in payload["approval_policy"]["reasons"]
    assert "browser.download" in payload["runtime"]["actions"]


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


@pytest.mark.asyncio
async def test_life_partner_coupon_codes_skill_builds_domain_sop() -> None:
    skill = load_skill(DOMAIN_SKILL_DIR)

    assert skill.name == "life_partner_coupon_codes"
    plan_tool = next(tool for tool in skill.tools if tool.name == "plan_coupon_code_export")
    payload = json.loads(
        await plan_tool.handler(
            target_url="https://www.life-partner.cn/subapp/dp-life-service-provider/tickets-data",
            date_range="昨天",
            authorization_confirmed=True,
            login_mode="当前浏览器已有登录态",
        )
    )

    assert payload["task"] == "coupon_code_export"
    assert payload["entry"]["menu_path"] == ["生财有数", "券码数据"]
    assert payload["filter_strategy"]["date_field"] == "支付时间"
    assert payload["browser_runtime_plan"]["preferred_engine"] == "cdp"
    assert "browser.extract_table" in payload["browser_runtime_plan"]["actions"]
    assert "paid_at" in payload["artifact"]["fields"]


def test_life_partner_intent_recommends_domain_skill() -> None:
    context = {
        "installed_skills": [
            {
                "name": "life_partner_coupon_codes",
                "description": "Site-level SOP for authorized Life Partner/LinKe coupon export.",
                "tags": "life-partner,linke,林客,券码,coupon,browser,export",
                "enabled": True,
            },
            {
                "name": "browser_automation",
                "description": "Plan compliant browser automation jobs.",
                "tags": "browser,automation,playwright,crawler,scrape,extraction",
                "enabled": True,
            },
        ]
    }

    recommendations = PlannerService._recommend_skills(
        "我想拉取林客昨天支付券码全部字段",
        context,
    )

    assert [item["name"] for item in recommendations[:2]] == [
        "life_partner_coupon_codes",
        "browser_automation",
    ]
