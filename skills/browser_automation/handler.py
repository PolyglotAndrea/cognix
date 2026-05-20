"""Browser automation planning skill.

This skill intentionally does not drive a browser directly. It gives the planner a
safe internal capability for routing authorized browser work to MCP, Playwright, or
export/API based execution while keeping approval and artifact contracts explicit.
"""

from __future__ import annotations

import json
from typing import Any


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


async def plan_browser_task(
    objective: str,
    source_url: str | None = None,
    data_needed: list[str] | None = None,
    authorization_confirmed: bool = False,
    preferred_route: str = "unknown",
    constraints: list[str] | None = None,
) -> str:
    """Build a browser automation plan without executing external actions."""
    fields = _as_list(data_needed)
    known_constraints = _as_list(constraints)
    route = preferred_route if preferred_route in {"api", "export_file", "browser"} else "unknown"
    requires_approval = route == "browser" or not authorization_confirmed

    if not authorization_confirmed:
        status = "needs_authorization_confirmation"
        first_step = "Confirm the user has authorization for the target system and data."
    else:
        status = "ready_for_planner"
        first_step = "Resolve the lowest-risk acquisition route for the target data."

    plan = {
        "capability": "browser_automation",
        "status": status,
        "objective": objective,
        "source": {
            "url": source_url or "",
            "preferred_route": route,
            "route_priority": ["api", "export_file", "browser"],
        },
        "compliance": {
            "authorization_confirmed": authorization_confirmed,
            "approval_required": requires_approval,
            "rules": [
                "Prefer official APIs or exported files before browser automation.",
                "Use browser automation only for authorized systems and permitted data.",
                (
                    "Do not bypass access controls, paywalls, CAPTCHAs, rate limits, "
                    "or platform restrictions."
                ),
                "Avoid collecting sensitive personal data unless the workspace policy allows it.",
            ],
        },
        "execution_plan": [
            first_step,
            "Identify required MCP tools, Playwright backend, browser profile, and cookie sandbox.",
            (
                "Request human approval before login, file download, form submission, "
                "or bulk extraction."
            ),
            "Run browser steps with domain, rate, and file-write limits.",
            "Normalize observations into structured records with source attribution.",
            "Create an artifact with title, summary, body, sources, task_id, and agent_id.",
        ],
        "expected_artifact": {
            "type": "dataset" if fields else "report",
            "title": "Browser automation result",
            "fields": fields,
            "sources": [source_url] if source_url else [],
            "sections": ["summary", "records", "sources", "limitations", "next_actions"],
        },
        "constraints": known_constraints,
        "planner_hints": {
            "recommended_agent": "browser-operator",
            "recommended_tools": ["browser_mcp", "playwright", "file_writer"],
            "approval_events": ["approval_request", "tool_call", "tool_result", "artifact_created"],
        },
    }
    return _json(plan)


async def browser_result_template(
    objective: str,
    artifact_type: str = "dataset",
    fields: list[str] | None = None,
    sources: list[str] | None = None,
) -> str:
    """Create an artifact contract for browser automation output."""
    normalized_type = (
        artifact_type if artifact_type in {"dataset", "report", "checklist"} else "dataset"
    )
    output_fields = _as_list(fields)
    source_list = _as_list(sources)
    record_shape = {field: "" for field in output_fields} if output_fields else {"value": ""}

    return _json(
        {
            "artifact_type": normalized_type,
            "title": objective,
            "summary": "Browser automation output prepared for review.",
            "body": {
                "objective": objective,
                "records": [],
                "record_shape": record_shape,
                "limitations": [],
                "next_actions": [],
            },
            "sources": source_list,
            "provenance": {
                "capability": "browser_automation",
                "requires_task_id": True,
                "requires_agent_id": True,
            },
        }
    )


async def normalize_browser_observations(
    observations: Any,
    fields: list[str] | None = None,
    source_url: str | None = None,
) -> str:
    """Normalize extracted browser data into artifact-ready JSON."""
    requested_fields = _as_list(fields)
    records: list[dict[str, Any]]

    if isinstance(observations, list):
        records = [
            item if isinstance(item, dict) else {"value": str(item)}
            for item in observations
        ]
    elif isinstance(observations, dict):
        records = [observations]
    else:
        text = str(observations).strip()
        records = [{"value": line.strip()} for line in text.splitlines() if line.strip()]

    if requested_fields:
        records = [
            {field: record.get(field, "") for field in requested_fields} | {
                key: value
                for key, value in record.items()
                if key not in requested_fields
            }
            for record in records
        ]

    return _json(
        {
            "title": "Browser automation observations",
            "summary": f"Normalized {len(records)} record(s) from browser observations.",
            "records": records,
            "sources": [source_url] if source_url else [],
            "limitations": [],
            "provenance": {
                "capability": "browser_automation",
                "normalizer": "normalize_browser_observations",
            },
        }
    )
