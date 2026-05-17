"""Memory backends for Agent state persistence."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    key: str
    value: Any
    created_at: datetime
    updated_at: datetime
    ttl: int | None = None  # seconds, None = no expiry
    metadata: dict[str, Any] | None = None


class MemoryBackend(ABC):
    """Abstract base for memory storage."""

    @abstractmethod
    async def get(self, key: str) -> MemoryEntry | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> bool: ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]: ...

    @abstractmethod
    async def clear(self) -> None: ...


class InMemoryBackend(MemoryBackend):
    """In-memory storage for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, MemoryEntry] = {}

    async def get(self, key: str) -> MemoryEntry | None:
        entry = self._store.get(key)
        if entry and entry.ttl is not None:
            elapsed = (datetime.now(UTC) - entry.updated_at).total_seconds()
            if elapsed > entry.ttl:
                del self._store[key]
                return None
        return entry

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        now = datetime.now(UTC)
        existing = self._store.get(key)
        self._store[key] = MemoryEntry(
            key=key,
            value=value,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            ttl=ttl,
        )

    async def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    async def list_keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        query_lower = query.lower()
        results = []
        for entry in self._store.values():
            value_str = json.dumps(entry.value) if not isinstance(entry.value, str) else entry.value
            if query_lower in value_str.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    async def clear(self) -> None:
        self._store.clear()


class SQLiteBackend(MemoryBackend):
    """SQLite-backed persistent memory storage."""

    def __init__(self, agent_id: str, db_path: str = "cognix.db") -> None:
        self.agent_id = agent_id
        self.db_path = db_path
        self._initialized = False

    async def _ensure_table(self) -> None:
        if self._initialized:
            return
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    agent_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ttl INTEGER,
                    PRIMARY KEY (agent_id, key)
                )
            """)
            await db.commit()
        self._initialized = True

    async def get(self, key: str) -> MemoryEntry | None:
        import aiosqlite

        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agent_memory WHERE agent_id = ? AND key = ?",
                (self.agent_id, key),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                entry = MemoryEntry(
                    key=row["key"],
                    value=json.loads(row["value"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    ttl=row["ttl"],
                )

                # Check TTL
                if entry.ttl is not None:
                    elapsed = (datetime.now(UTC) - entry.updated_at).total_seconds()
                    if elapsed > entry.ttl:
                        await self.delete(key)
                        return None

                return entry

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        import aiosqlite

        await self._ensure_table()
        now = datetime.now(UTC).isoformat()
        value_json = json.dumps(value)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO agent_memory (agent_id, key, value, created_at, updated_at, ttl)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, key) DO UPDATE SET
                   value = excluded.value, updated_at = excluded.updated_at, ttl = excluded.ttl""",
                (self.agent_id, key, value_json, now, now, ttl),
            )
            await db.commit()

    async def delete(self, key: str) -> bool:
        import aiosqlite

        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM agent_memory WHERE agent_id = ? AND key = ?",
                (self.agent_id, key),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_keys(self, prefix: str = "") -> list[str]:
        import aiosqlite

        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            if prefix:
                async with db.execute(
                    "SELECT key FROM agent_memory WHERE agent_id = ? AND key LIKE ?",
                    (self.agent_id, f"{prefix}%"),
                ) as cursor:
                    return [row[0] for row in await cursor.fetchall()]
            else:
                async with db.execute(
                    "SELECT key FROM agent_memory WHERE agent_id = ?",
                    (self.agent_id,),
                ) as cursor:
                    return [row[0] for row in await cursor.fetchall()]

    async def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        import aiosqlite

        await self._ensure_table()
        results = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM agent_memory WHERE agent_id = ?",
                (self.agent_id,),
            ) as cursor:
                async for row in cursor:
                    value_str = row["value"]
                    if query.lower() in value_str.lower():
                        results.append(
                            MemoryEntry(
                                key=row["key"],
                                value=json.loads(value_str),
                                created_at=datetime.fromisoformat(row["created_at"]),
                                updated_at=datetime.fromisoformat(row["updated_at"]),
                                ttl=row["ttl"],
                            )
                        )
                        if len(results) >= limit:
                            break
        return results

    async def clear(self) -> None:
        import aiosqlite

        await self._ensure_table()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM agent_memory WHERE agent_id = ?",
                (self.agent_id,),
            )
            await db.commit()
