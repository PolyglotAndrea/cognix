"""Tests for local runtime node registry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cognix.local.home import CognixHome
from cognix.local.runtime import RuntimeNode, RuntimeNodeStore


def test_runtime_node_store_registers_and_heartbeats(tmp_path) -> None:
    store = RuntimeNodeStore(CognixHome(tmp_path / ".cognix"))

    node = store.register_current(
        role="api",
        capabilities=["rest", "scheduler"],
        node_id="node-1",
    )
    updated = store.heartbeat(node.id, metadata={"dispatcher": {"running": True}})

    assert node.id == "node-1"
    assert updated is not None
    assert updated.status == "online"
    assert updated.metadata == {"dispatcher": {"running": True}}
    assert [item.id for item in store.list_all()] == ["node-1"]


def test_runtime_node_store_marks_stale_nodes(tmp_path) -> None:
    store = RuntimeNodeStore(CognixHome(tmp_path / ".cognix"))
    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    store._write_nodes(
        [
            RuntimeNode(
                id="old-node",
                role="worker",
                host="localhost",
                pid=123,
                status="online",
                started_at=old,
                last_seen=old,
            )
        ]
    )

    nodes = store.list_all(stale_after_seconds=30)

    assert nodes[0].status == "stale"


def test_runtime_node_store_marks_offline(tmp_path) -> None:
    store = RuntimeNodeStore(CognixHome(tmp_path / ".cognix"))
    store.register_current(role="api", node_id="node-1")

    node = store.mark_status("node-1", "offline")

    assert node is not None
    assert node.status == "offline"
    assert store.list_all()[0].status == "offline"
