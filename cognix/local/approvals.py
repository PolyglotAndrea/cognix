"""Local-first human approval request store."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cognix.local.home import CognixHome

ApprovalStatus = Literal["pending", "approved", "rejected", "completed"]
ApprovalKind = Literal["tool_permission", "plan_confirmation", "question"]


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any]
    access_level: str
    reason: str
    status: ApprovalStatus = "pending"
    kind: ApprovalKind = "tool_permission"
    workspace_id: str | None = None
    response: str = ""
    result: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalStore:
    """Stores pending and resolved approvals under ``~/.cognix/approvals``."""

    def __init__(self, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        if not self.approvals_file.exists():
            self._write([])

    @property
    def approvals_dir(self) -> Path:
        return self.home.root / "approvals"

    @property
    def approvals_file(self) -> Path:
        return self.approvals_dir / "requests.json"

    def create(
        self,
        *,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        access_level: str,
        reason: str,
        workspace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        kind: ApprovalKind = "tool_permission",
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            id=uuid.uuid4().hex[:12],
            agent_id=agent_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            arguments=arguments,
            access_level=access_level,
            reason=reason,
            kind=kind,
            metadata=metadata or {},
        )
        approvals = self.list_all(include_resolved=True)
        approvals.append(request)
        self._write(approvals)
        return request

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return next(
            (
                approval
                for approval in self.list_all(include_resolved=True)
                if approval.id == approval_id
            ),
            None,
        )

    def list_all(
        self,
        *,
        workspace_id: str | None = None,
        status: ApprovalStatus | None = None,
        include_resolved: bool = False,
    ) -> list[ApprovalRequest]:
        rows = json.loads(self.approvals_file.read_text(encoding="utf-8") or "[]")
        approvals = [ApprovalRequest(**row) for row in rows if isinstance(row, dict)]
        if workspace_id:
            approvals = [
                approval for approval in approvals if approval.workspace_id == workspace_id
            ]
        if status:
            approvals = [approval for approval in approvals if approval.status == status]
        elif not include_resolved:
            approvals = [approval for approval in approvals if approval.status == "pending"]
        return sorted(approvals, key=lambda item: item.created_at, reverse=True)

    def approve(self, approval_id: str) -> ApprovalRequest | None:
        existing = self.get(approval_id)
        if existing and existing.status != "pending":
            return existing  # no-op for already resolved
        return self._set_status(approval_id, "approved")

    def respond(self, approval_id: str, response: str) -> ApprovalRequest | None:
        return self._set_status(approval_id, "approved", response=response)

    def reject(self, approval_id: str) -> ApprovalRequest | None:
        return self._set_status(approval_id, "rejected")

    def complete(self, approval_id: str, result: str) -> ApprovalRequest | None:
        return self._set_status(approval_id, "completed", result=result)

    def _set_status(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        response: str = "",
        result: str = "",
    ) -> ApprovalRequest | None:
        approvals = self.list_all(include_resolved=True)
        updated: ApprovalRequest | None = None
        next_rows: list[ApprovalRequest] = []
        for approval in approvals:
            if approval.id == approval_id:
                updated = ApprovalRequest(
                    **{
                        **asdict(approval),
                        "status": status,
                        "response": response or approval.response,
                        "result": result or approval.result,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                next_rows.append(updated)
            else:
                next_rows.append(approval)
        self._write(next_rows)
        return updated

    def _write(self, approvals: list[ApprovalRequest]) -> None:
        self.approvals_file.write_text(
            json.dumps([asdict(item) for item in approvals], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
