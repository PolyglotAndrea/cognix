"""Worker node registration and discovery for distributed scheduling."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Nodes not seen for this long are marked offline
_OFFLINE_THRESHOLD_SECONDS = 90


class WorkerRegistry:
    """Manages worker node registration, heartbeat, and discovery."""

    async def register(
        self,
        node_id: str,
        *,
        hostname: str = "",
        ip_address: str = "",
        capabilities: dict[str, Any] | None = None,
        max_concurrent: int = 3,
    ) -> None:
        """Register or update a worker node."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        now = datetime.now(UTC)
        async with get_session() as session:
            result = await session.execute(
                select(WorkerNodeModel).where(WorkerNodeModel.id == node_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.hostname = hostname
                existing.ip_address = ip_address
                existing.capabilities = capabilities or {}
                existing.max_concurrent = max_concurrent
                existing.status = "active"
                existing.last_heartbeat = now
            else:
                node = WorkerNodeModel(
                    id=node_id,
                    hostname=hostname,
                    ip_address=ip_address,
                    capabilities=capabilities or {},
                    max_concurrent=max_concurrent,
                    current_load=0,
                    status="active",
                    last_heartbeat=now,
                    registered_at=now,
                )
                session.add(node)

        logger.info("Worker node registered: %s", node_id)

    async def heartbeat(self, node_id: str, current_load: int = 0) -> None:
        """Update heartbeat timestamp and load for a node."""
        from sqlalchemy import update

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            await session.execute(
                update(WorkerNodeModel)
                .where(WorkerNodeModel.id == node_id)
                .values(
                    last_heartbeat=datetime.now(UTC),
                    current_load=current_load,
                )
            )

    async def deregister(self, node_id: str) -> None:
        """Mark a node as offline."""
        from sqlalchemy import update

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            await session.execute(
                update(WorkerNodeModel)
                .where(WorkerNodeModel.id == node_id)
                .values(status="offline")
            )
        logger.info("Worker node deregistered: %s", node_id)

    async def list_active(self) -> list[dict]:
        """List all active worker nodes."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            result = await session.execute(
                select(WorkerNodeModel)
                .where(WorkerNodeModel.status == "active")
                .order_by(WorkerNodeModel.current_load)
            )
            rows = result.scalars().all()

        return [
            {
                "id": r.id,
                "hostname": r.hostname,
                "ip_address": r.ip_address,
                "capabilities": r.capabilities,
                "max_concurrent": r.max_concurrent,
                "current_load": r.current_load,
                "status": r.status,
                "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None,
                "registered_at": r.registered_at.isoformat() if r.registered_at else None,
            }
            for r in rows
        ]

    async def list_all(self) -> list[dict]:
        """List all worker nodes (active and offline)."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            result = await session.execute(
                select(WorkerNodeModel).order_by(WorkerNodeModel.current_load)
            )
            rows = result.scalars().all()

        return [
            {
                "id": r.id,
                "hostname": r.hostname,
                "ip_address": r.ip_address,
                "capabilities": r.capabilities,
                "max_concurrent": r.max_concurrent,
                "current_load": r.current_load,
                "status": r.status,
                "last_heartbeat": r.last_heartbeat.isoformat() if r.last_heartbeat else None,
                "registered_at": r.registered_at.isoformat() if r.registered_at else None,
            }
            for r in rows
        ]

    async def get_least_loaded_node(self) -> str | None:
        """Find the active node with the most available capacity."""
        from sqlalchemy import select

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            result = await session.execute(
                select(WorkerNodeModel)
                .where(WorkerNodeModel.status == "active")
                .where(WorkerNodeModel.current_load < WorkerNodeModel.max_concurrent)
                .order_by(WorkerNodeModel.current_load)
                .limit(1)
            )
            node = result.scalar_one_or_none()
            return node.id if node else None

    async def mark_offline_stale(self) -> int:
        """Mark nodes that haven't heartbeated recently as offline."""
        from sqlalchemy import update

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        cutoff = datetime.now(UTC) - timedelta(seconds=_OFFLINE_THRESHOLD_SECONDS)
        async with get_session() as session:
            result = await session.execute(
                update(WorkerNodeModel)
                .where(WorkerNodeModel.status == "active")
                .where(WorkerNodeModel.last_heartbeat < cutoff)
                .values(status="offline")
            )
            return result.rowcount

    async def drain_node(self, node_id: str) -> None:
        """Mark a node as draining (will not receive new tasks)."""
        from sqlalchemy import update

        from cognix.storage.database import get_session
        from cognix.storage.models import WorkerNodeModel

        async with get_session() as session:
            await session.execute(
                update(WorkerNodeModel)
                .where(WorkerNodeModel.id == node_id)
                .values(status="draining")
            )
        logger.info("Worker node draining: %s", node_id)
