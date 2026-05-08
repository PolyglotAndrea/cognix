"""Four-pipeline memory context assembly for Cognix."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager


@dataclass
class HotMemory:
    """Stable prefix memory sourced from USER.md and MEMORY.md files."""

    user: str = ""
    global_memory: str = ""
    workspace_memory: str = ""

    def render(self) -> str:
        sections = []
        if self.user.strip():
            sections.append(f"## User\n{self.user.strip()}")
        if self.global_memory.strip():
            sections.append(f"## Global Memory\n{self.global_memory.strip()}")
        if self.workspace_memory.strip():
            sections.append(f"## Workspace Memory\n{self.workspace_memory.strip()}")
        return "\n\n".join(sections)


@dataclass
class ColdMemoryRecord:
    """A retrievable episodic memory record."""

    id: str
    content: str
    summary: str = ""
    workspace_id: str | None = None
    scope: str = "global"
    kind: str = "message"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def compact(self, max_chars: int = 700) -> str:
        text = self.summary or self.content
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]


@dataclass
class ProceduralMemory:
    """A skill/SOP snippet selected for the current task."""

    name: str
    path: str
    content: str

    def compact(self, max_chars: int = 1200) -> str:
        return self.content.strip()[:max_chars]


@dataclass
class ContextPack:
    """Assembled context ready to feed a chat model or execution worker."""

    hot_memory: HotMemory
    cold_memories: list[ColdMemoryRecord] = field(default_factory=list)
    procedural_memories: list[ProceduralMemory] = field(default_factory=list)
    deep_memory: str = ""
    token_budget: int = 8000

    def render_system_context(self) -> str:
        sections = []
        hot = self.hot_memory.render()
        if hot:
            sections.append("# Hot Memory\n" + hot)
        if self.cold_memories:
            recalled = "\n".join(f"- {m.compact()}" for m in self.cold_memories)
            sections.append("# Recalled History\n" + recalled)
        if self.procedural_memories:
            skills = "\n\n".join(
                f"## {skill.name}\n{skill.compact()}" for skill in self.procedural_memories
            )
            sections.append("# Relevant Skills\n" + skills)
        if self.deep_memory.strip():
            sections.append("# User Model\n" + self.deep_memory.strip())
        return "\n\n".join(sections)


class ColdMemoryStore:
    """SQLite FTS5-backed episodic memory store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cold_memory (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    scope TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS cold_memory_fts
                USING fts5(id UNINDEXED, content, summary)
            """)
            await db.commit()
        self._initialized = True

    async def add(self, record: ColdMemoryRecord) -> None:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cold_memory (
                    id, workspace_id, scope, kind, content, summary, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.workspace_id,
                    record.scope,
                    record.kind,
                    record.content,
                    record.summary,
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at,
                ),
            )
            await db.execute("DELETE FROM cold_memory_fts WHERE id = ?", (record.id,))
            await db.execute(
                "INSERT INTO cold_memory_fts (id, content, summary) VALUES (?, ?, ?)",
                (record.id, record.content, record.summary),
            )
            await db.commit()

    async def remember(
        self,
        content: str,
        *,
        workspace_id: str | None = None,
        scope: str = "global",
        kind: str = "message",
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ColdMemoryRecord:
        record = ColdMemoryRecord(
            id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            scope=scope,
            kind=kind,
            content=content,
            summary=summary,
            metadata=metadata or {},
        )
        await self.add(record)
        return record

    async def search(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 5,
    ) -> list[ColdMemoryRecord]:
        await self.init()
        normalized = self._fts_query(query)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if normalized:
                rows = await self._search_fts(db, normalized, workspace_id, limit)
                if rows:
                    return [self._row_to_record(row) for row in rows]
            rows = await self._search_like(db, query, workspace_id, limit)
            return [self._row_to_record(row) for row in rows]

    async def _search_fts(
        self,
        db: aiosqlite.Connection,
        query: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[aiosqlite.Row]:
        where = ""
        params: list[Any] = [query]
        if workspace_id:
            where = "AND (m.workspace_id = ? OR m.workspace_id IS NULL)"
            params.append(workspace_id)
        params.append(limit)
        cursor = await db.execute(
            f"""
            SELECT m.*
            FROM cold_memory_fts f
            JOIN cold_memory m ON m.id = f.id
            WHERE cold_memory_fts MATCH ? {where}
            ORDER BY rank
            LIMIT ?
            """,
            params,
        )
        return list(await cursor.fetchall())

    async def _search_like(
        self,
        db: aiosqlite.Connection,
        query: str,
        workspace_id: str | None,
        limit: int,
    ) -> list[aiosqlite.Row]:
        where = "WHERE (content LIKE ? OR summary LIKE ?)"
        params: list[Any] = [f"%{query}%", f"%{query}%"]
        if workspace_id:
            where += " AND (workspace_id = ? OR workspace_id IS NULL)"
            params.append(workspace_id)
        params.append(limit)
        cursor = await db.execute(
            f"SELECT * FROM cold_memory {where} ORDER BY created_at DESC LIMIT ?",
            params,
        )
        return list(await cursor.fetchall())

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[\w\u4e00-\u9fff]+", query)
        return " OR ".join(terms[:8])

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> ColdMemoryRecord:
        return ColdMemoryRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            scope=row["scope"],
            kind=row["kind"],
            content=row["content"],
            summary=row["summary"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
        )


class ContextBuilder:
    """Build model context from hot, cold, procedural, and optional deep memory."""

    def __init__(self, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_manager = WorkspaceManager(self.home)
        self.cold_store = ColdMemoryStore(self.home.state_db)

    async def build(
        self,
        user_message: str,
        *,
        workspace_id: str | None = None,
        include_hot_memory: bool = True,
        include_cold_memory: bool = True,
        include_skills: bool = True,
        token_budget: int = 8000,
        deep_memory: str = "",
    ) -> ContextPack:
        hot = self.load_hot_memory(workspace_id=workspace_id) if include_hot_memory else HotMemory()
        cold = []
        if include_cold_memory:
            cold = await self.cold_store.search(
                user_message,
                workspace_id=workspace_id,
                limit=5,
            )
        skills = self.search_procedural_memory(user_message, workspace_id=workspace_id, limit=3)
        if not include_skills:
            skills = []
        return ContextPack(
            hot_memory=hot,
            cold_memories=cold,
            procedural_memories=skills,
            deep_memory=deep_memory,
            token_budget=token_budget,
        )

    def load_hot_memory(self, *, workspace_id: str | None = None) -> HotMemory:
        workspace_memory = ""
        if workspace_id:
            path = self.workspace_manager.workspace_path(workspace_id) / "MEMORY.md"
            workspace_memory = self._read_text(path)
        return HotMemory(
            user=self._read_text(self.home.user_file),
            global_memory=self._read_text(self.home.memory_file),
            workspace_memory=workspace_memory,
        )

    def search_procedural_memory(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 3,
    ) -> list[ProceduralMemory]:
        terms = {term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)}
        candidates = list(self.home.skills_dir.glob("*.md"))
        if workspace_id:
            candidates.extend(
                (self.workspace_manager.workspace_path(workspace_id) / "skills").glob("*.md")
            )

        scored: list[tuple[int, ProceduralMemory]] = []
        for path in candidates:
            content = self._read_text(path)
            haystack = f"{path.stem}\n{content}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append(
                    (
                        score,
                        ProceduralMemory(name=path.stem, path=str(path), content=content),
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
