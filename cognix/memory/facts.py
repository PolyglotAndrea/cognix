"""Atomic memory facts for stable, low-token user/workspace context."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import aiosqlite


FactStatus = Literal["active", "superseded", "rejected"]


@dataclass(frozen=True)
class AtomicFact:
    """A compact, updateable memory fact.

    Facts are the single source of truth for high-value preferences, stable
    profile data, workspace defaults, and frequently reused system entrypoints.
    """

    id: str
    workspace_id: str | None
    entity_type: str
    entity_id: str
    key: str
    value: str
    status: FactStatus = "active"
    confidence: float = 0.8
    source: str = "extractor"
    source_ref: str = ""
    supersedes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def compact(self, max_chars: int = 240) -> str:
        value = re.sub(r"\s+", " ", self.value).strip()
        if len(value) > max_chars:
            value = value[: max_chars - 1] + "..."
        target = self.entity_id if self.entity_id != "default" else self.entity_type
        return f"{target}.{self.key} = {value}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AtomicFactStore:
    """SQLite-backed atomic fact store.

    This deliberately starts with SQLite so local-first installs stay simple.
    Vector or graph indices can be layered on top later without replacing this
    authoritative table.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS atomic_facts (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    source TEXT NOT NULL DEFAULT 'extractor',
                    source_ref TEXT NOT NULL DEFAULT '',
                    supersedes TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_atomic_facts_lookup
                ON atomic_facts(workspace_id, entity_type, entity_id, key, status)
                """
            )
            await db.commit()
        self._initialized = True

    async def upsert(
        self,
        *,
        workspace_id: str | None,
        entity_type: str,
        entity_id: str,
        key: str,
        value: str,
        confidence: float = 0.8,
        source: str = "extractor",
        source_ref: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AtomicFact:
        await self.init()
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("Atomic fact value cannot be empty")
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            existing = await self._active_for_key(
                db,
                workspace_id=workspace_id,
                entity_type=entity_type,
                entity_id=entity_id,
                key=key,
            )
            if existing and existing["value"] == normalized_value:
                await db.execute(
                    """
                    UPDATE atomic_facts
                    SET confidence = MAX(confidence, ?), updated_at = ?, source_ref = ?
                    WHERE id = ?
                    """,
                    (confidence, now, source_ref or existing["source_ref"], existing["id"]),
                )
                await db.commit()
                return (await self.get(existing["id"]))  # type: ignore[return-value]

            supersedes = ""
            if existing:
                supersedes = existing["id"]
                await db.execute(
                    "UPDATE atomic_facts SET status = 'superseded', updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )

            fact = AtomicFact(
                id=uuid.uuid4().hex[:12],
                workspace_id=workspace_id,
                entity_type=entity_type,
                entity_id=entity_id or "default",
                key=key,
                value=normalized_value,
                confidence=confidence,
                source=source,
                source_ref=source_ref,
                supersedes=supersedes,
                metadata=metadata or {},
                created_at=now,
                updated_at=now,
            )
            await db.execute(
                """
                INSERT INTO atomic_facts (
                    id, workspace_id, entity_type, entity_id, key, value, status,
                    confidence, source, source_ref, supersedes, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.id,
                    fact.workspace_id,
                    fact.entity_type,
                    fact.entity_id,
                    fact.key,
                    fact.value,
                    fact.status,
                    fact.confidence,
                    fact.source,
                    fact.source_ref,
                    fact.supersedes,
                    json.dumps(fact.metadata, ensure_ascii=False),
                    fact.created_at,
                    fact.updated_at,
                ),
            )
            await db.commit()
            return fact

    async def get(self, fact_id: str) -> AtomicFact | None:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM atomic_facts WHERE id = ?", (fact_id,))
            row = await cursor.fetchone()
            return self._row_to_fact(row) if row else None

    async def list_active(
        self,
        *,
        workspace_id: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[AtomicFact]:
        await self.init()
        where = ["status = 'active'"]
        params: list[Any] = []
        if workspace_id:
            where.append("(workspace_id = ? OR workspace_id IS NULL)")
            params.append(workspace_id)
        if entity_type:
            where.append("entity_type = ?")
            params.append(entity_type)
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM atomic_facts
                WHERE {' AND '.join(where)}
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = [self._row_to_fact(row) for row in await cursor.fetchall()]
        return rows

    async def search(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 8,
    ) -> list[AtomicFact]:
        await self.init()
        terms = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())[:8]
        if not terms:
            return await self.list_active(workspace_id=workspace_id, limit=limit)
        like_clauses = []
        params: list[Any] = []
        for term in terms:
            like_clauses.append("(LOWER(key) LIKE ? OR LOWER(value) LIKE ? OR LOWER(entity_id) LIKE ?)")
            pattern = f"%{term}%"
            params.extend([pattern, pattern, pattern])
        where = ["status = 'active'", f"({' OR '.join(like_clauses)})"]
        if workspace_id:
            where.append("(workspace_id = ? OR workspace_id IS NULL)")
            params.append(workspace_id)
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM atomic_facts
                WHERE {' AND '.join(where)}
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = [self._row_to_fact(row) for row in await cursor.fetchall()]
        if rows:
            return rows
        return await self.list_active(workspace_id=workspace_id, limit=limit)

    async def _active_for_key(
        self,
        db: aiosqlite.Connection,
        *,
        workspace_id: str | None,
        entity_type: str,
        entity_id: str,
        key: str,
    ) -> aiosqlite.Row | None:
        cursor = await db.execute(
            """
            SELECT * FROM atomic_facts
            WHERE status = 'active'
              AND COALESCE(workspace_id, '') = COALESCE(?, '')
              AND entity_type = ?
              AND entity_id = ?
              AND key = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (workspace_id, entity_type, entity_id or "default", key),
        )
        return await cursor.fetchone()

    @staticmethod
    def _row_to_fact(row: aiosqlite.Row) -> AtomicFact:
        return AtomicFact(
            id=row["id"],
            workspace_id=row["workspace_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            key=row["key"],
            value=row["value"],
            status=row["status"],
            confidence=float(row["confidence"]),
            source=row["source"],
            source_ref=row["source_ref"],
            supersedes=row["supersedes"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
