"""Life Partner/LinKe coupon-code export domain skill.

This is a site-level SOP skill. It does not execute browser actions; it gives the
planner business-specific navigation, filtering, field, export, and artifact
rules that can be routed to browser_automation and the internal browser runtime.
"""

from __future__ import annotations

import json
from typing import Any


DEFAULT_TARGET_URL = (
    "https://www.life-partner.cn/subapp/dp-life-service-provider/tickets-data"
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


async def plan_coupon_code_export(
    target_url: str | None = None,
    date_range: str = "昨天",
    date_field: str = "支付时间",
    field_policy: str = "全部可见字段/全部自定义字段",
    login_mode: str = "当前浏览器已有登录态",
    authorization_confirmed: bool = False,
) -> str:
    """Build a reusable SOP for Life Partner/LinKe coupon-code data export."""
    url = (target_url or DEFAULT_TARGET_URL).strip()
    date = (date_range or "昨天").strip()
    field = (date_field or "支付时间").strip()
    fields = (field_policy or "全部可见字段/全部自定义字段").strip()
    login = (login_mode or "当前浏览器已有登录态").strip()

    return _json(
        {
            "skill": "life_partner_coupon_codes",
            "domain": "Life Partner / 林客",
            "task": "coupon_code_export",
            "authorization": {
                "confirmed": authorization_confirmed,
                "required_before_browser_access": True,
                "pause_on": [
                    "login_required",
                    "captcha",
                    "sms_or_scan_verification",
                    "permission_denied",
                    "field_ambiguity",
                    "unexpected_export_confirmation",
                ],
            },
            "entry": {
                "target_url": url,
                "menu_path": ["生财有数", "券码数据"],
                "login_mode": login,
                "prefer_cdp_when_existing_browser_session": "已有登录态" in login,
            },
            "filter_strategy": {
                "date_field": field,
                "date_range": date,
                "date_semantics": {
                    "昨天": "Use local business day 00:00:00-23:59:59 in Asia/Shanghai unless user specifies otherwise.",
                    "custom": "Ask user for exact start/end timestamps when natural language is ambiguous.",
                },
                "coupon_scope": "支付券码",
            },
            "field_strategy": {
                "policy": fields,
                "open_column_settings": True,
                "select_all_available_fields": True,
                "fallback_fields": [
                    "券码",
                    "券码状态",
                    "券名称",
                    "支付时间",
                    "核销时间",
                    "订单号",
                    "批次/活动名称",
                    "渠道",
                    "面额",
                    "实付金额",
                    "创建时间",
                    "更新时间",
                ],
            },
            "acquisition_priority": [
                "official_export",
                "browser.download",
                "browser.extract_table",
                "browser.observe",
            ],
            "browser_runtime_plan": {
                "capability": "browser_automation",
                "preferred_engine": "cdp" if "已有登录态" in login else "playwright",
                "actions": [
                    "browser.goto",
                    "browser.observe",
                    "browser.click",
                    "browser.select",
                    "browser.wait",
                    "browser.download",
                    "browser.extract_table",
                    "browser.screenshot",
                ],
            },
            "artifact": await _coupon_schema(include_optional_fields=True),
        }
    )


async def coupon_code_artifact_schema(include_optional_fields: bool = True) -> str:
    """Return the coupon-code output schema and field descriptions."""
    return _json(await _coupon_schema(include_optional_fields=include_optional_fields))


async def _coupon_schema(include_optional_fields: bool = True) -> dict[str, Any]:
    required_fields = {
        "coupon_code": "券码或券码唯一标识，以页面实际字段为准。",
        "coupon_status": "券码状态，例如未使用、已使用、已过期、已退款等。",
        "paid_at": "支付时间，任务默认按该字段筛选日期。",
        "source_url": "数据来源页面。",
    }
    optional_fields = {
        "coupon_name": "券名称或商品/权益名称。",
        "redeemed_at": "核销时间。",
        "order_id": "订单号或交易流水号。",
        "batch_or_campaign": "批次、活动或页面可见分组。",
        "channel": "渠道、店铺、商户或来源入口。",
        "face_value": "券面额。",
        "paid_amount": "实付金额。",
        "created_at": "创建或领取时间。",
        "updated_at": "页面可见更新时间。",
        "raw_row": "保留页面原始行数据，便于审计和字段追溯。",
    }
    fields = required_fields | optional_fields if include_optional_fields else required_fields
    return {
        "artifact_type": "dataset",
        "title": "林客券码数据拉取结果",
        "summary": "授权范围内的林客支付券码数据导出/采集结果。",
        "fields": fields,
        "sections": [
            "task_summary",
            "filter_conditions",
            "records",
            "field_definitions",
            "source_attribution",
            "limitations",
            "recovery_notes",
        ],
        "source_attribution_required": True,
    }
