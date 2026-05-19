"""Four-pipeline memory context assembly for Cognix."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
    sources: list[dict[str, Any]] = field(default_factory=list)
    source_details: list[dict[str, Any]] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)

    def render_system_context(self, *, model: str = "gpt-4o") -> str:
        from cognix.memory.token_counter import count_tokens, truncate_to_budget

        sections: list[str] = []
        usage: dict[str, int] = {}

        # Hot memory always included (highest priority)
        hot = self.hot_memory.render()
        if hot:
            hot_tokens = count_tokens(hot, model)
            usage["hot"] = hot_tokens
            sections.append("# Hot Memory\n" + hot)

        # Procedural memory (second priority)
        if self.procedural_memories:
            skills_text = "\n\n".join(
                f"## {skill.name}\n{skill.compact()}" for skill in self.procedural_memories
            )
            skills_tokens = count_tokens(skills_text, model)
            usage["procedural"] = skills_tokens
            sections.append("# Relevant Skills\n" + skills_text)

        # Cold memory (third priority)
        if self.cold_memories:
            recalled = "\n".join(f"- {m.compact()}" for m in self.cold_memories)
            cold_tokens = count_tokens(recalled, model)
            usage["cold"] = cold_tokens
            sections.append("# Recalled History\n" + recalled)

        # Deep memory (lowest priority)
        if self.deep_memory.strip():
            deep_tokens = count_tokens(self.deep_memory.strip(), model)
            usage["deep"] = deep_tokens
            sections.append("# User Model\n" + self.deep_memory.strip())

        self.token_usage = usage
        result = "\n\n".join(sections)

        # Enforce token budget: truncate from the end if over budget
        total_tokens = sum(usage.values())
        if total_tokens > self.token_budget:
            result = truncate_to_budget(result, self.token_budget, model)
            self.token_usage["truncated"] = True

        if self.source_details:
            sources_text = ", ".join(s.get("source", "unknown") for s in self.source_details)
            result += f"\n\n[Sources: {sources_text}]"

        return result

    def source_summary(self) -> list[dict[str, Any]]:
        """Return a list of memory sources used in this context pack."""
        if self.sources:
            return self.sources
        sources: list[dict[str, Any]] = []
        if self.hot_memory.user.strip():
            sources.append({"type": "hot", "name": "USER.md", "chars": len(self.hot_memory.user)})
        if self.hot_memory.global_memory.strip():
            sources.append(
                {
                    "type": "hot",
                    "name": "MEMORY.md",
                    "chars": len(self.hot_memory.global_memory),
                }
            )
        if self.hot_memory.workspace_memory.strip():
            sources.append(
                {
                    "type": "hot",
                    "name": "workspace/MEMORY.md",
                    "chars": len(self.hot_memory.workspace_memory),
                }
            )
        for m in self.cold_memories:
            sources.append(
                {
                    "type": "cold",
                    "id": m.id,
                    "kind": m.kind,
                    "chars": len(m.content),
                    "created_at": m.created_at,
                }
            )
        for s in self.procedural_memories:
            sources.append({"type": "procedural", "name": s.name, "chars": len(s.content)})
        if self.deep_memory.strip():
            sources.append(
                {
                    "type": "deep",
                    "name": "DEEP_MEMORY.md",
                    "chars": len(self.deep_memory),
                }
            )
        return sources


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
        try:
            from cognix.memory.vault import MemoryVault

            MemoryVault(CognixHome(self.db_path.parent)).append_record(record)
        except Exception:
            # The SQLite index is authoritative; vault projection should never
            # block memory persistence.
            pass
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

    async def compress(
        self,
        *,
        workspace_id: str | None = None,
        older_than_days: int | None = None,
        limit: int = 50,
        model: str | None = None,
    ) -> list[ColdMemoryRecord]:
        """Summarize old memories using the LLM to reduce token usage.

        Returns the compressed records (updated with new summaries).
        """
        from cognix.config import get_settings

        settings = get_settings().memory
        if older_than_days is None:
            older_than_days = settings.compress_older_than_days
        if model is None:
            model = settings.compress_model

        await self.init()
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE created_at < ? AND (summary = '' OR summary IS NULL)"
            params: list[Any] = [cutoff]
            if workspace_id:
                where += " AND (workspace_id = ? OR workspace_id IS NULL)"
                params.append(workspace_id)
            params.append(limit)
            cursor = await db.execute(
                f"SELECT * FROM cold_memory {where} ORDER BY created_at ASC LIMIT ?",
                params,
            )
            rows = list(await cursor.fetchall())

        if not rows:
            return []

        records = [self._row_to_record(row) for row in rows]
        # Try LLM summarization, fall back to truncation
        try:
            summaries = await self._llm_summarize_batch(records, model=model)
        except Exception:
            summaries = [r.content[:200] for r in records]

        for record, summary in zip(records, summaries):
            record.summary = summary
            await self.add(record)

        return records

    async def _llm_summarize_batch(
        self,
        records: list[ColdMemoryRecord],
        *,
        model: str = "gpt-4o-mini",
    ) -> list[str]:
        """Summarize a batch of memories using LiteLLM."""
        import litellm

        from cognix.config import get_settings

        batch_size = get_settings().memory.compress_batch_size

        prompts = [
            f"Summarize this memory in one sentence (max 100 chars):\n{r.content[:500]}"
            for r in records
        ]

        summaries: list[str] = []
        for i in range(0, len(prompts), batch_size):
            batch = prompts[i : i + batch_size]
            responses = await asyncio.gather(
                *[
                    litellm.acompletion(
                        model=model,
                        messages=[{"role": "user", "content": p}],
                        max_tokens=60,
                        temperature=0.3,
                    )
                    for p in batch
                ]
            )
            for resp in responses:
                text = resp.choices[0].message.content.strip() if resp.choices else ""
                summaries.append(text[:200])

        return summaries


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
        include_deep_memory: bool = False,
        token_budget: int = 8000,
        routing_strategy: str = "priority",
        deep_memory: str = "",
        model: str = "gpt-4o",
    ) -> ContextPack:
        from cognix.memory.token_counter import count_tokens

        hot = self.load_hot_memory(workspace_id=workspace_id) if include_hot_memory else HotMemory()
        cold: list[ColdMemoryRecord] = []
        skills: list[ProceduralMemory] = []
        deep = deep_memory

        source_details: list[dict[str, Any]] = []
        if routing_strategy in {"routed", "balanced"}:
            from cognix.memory.router import MemoryRouter

            router = MemoryRouter()
            category = router.classify(user_message)
            routes = set(router.route(user_message))
            source_details.append(
                {
                    "source": "memory_router",
                    "category": category.value,
                    "routes": sorted(routes),
                }
            )
            include_cold_memory = include_cold_memory and "cold" in routes
            include_skills = include_skills and "procedural" in routes
            include_deep_memory = include_deep_memory and "deep" in routes

        if routing_strategy == "balanced":
            return await self._build_balanced(
                user_message,
                workspace_id=workspace_id,
                hot=hot,
                include_cold_memory=include_cold_memory,
                include_skills=include_skills,
                include_deep_memory=include_deep_memory,
                token_budget=token_budget,
                deep_memory=deep,
                model=model,
                source_details=source_details,
            )

        if routing_strategy == "greedy":
            # Greedy: include everything, let render_system_context truncate
            if include_cold_memory:
                cold = await self.cold_store.search(
                    user_message,
                    workspace_id=workspace_id,
                    limit=5,
                )
                for m in cold:
                    source_details.append(
                        {
                            "source": "cold_memory",
                            "memory_id": m.id,
                            "category": m.kind,
                        }
                    )
            if include_skills:
                skills = self.search_procedural_memory(
                    user_message,
                    workspace_id=workspace_id,
                    limit=3,
                )
                for s in skills:
                    source_details.append({"source": "procedural", "memory_id": s.name})
            if include_deep_memory and not deep:
                deep = self.load_deep_memory()
                if deep.strip():
                    source_details.append({"source": "deep_memory"})
        else:
            # Priority-based: add sources until budget is exhausted
            used = 0
            hot_text = hot.render()
            if hot_text:
                used += count_tokens(hot_text, model)
                source_details.append({"source": "hot_memory"})

            # Procedural memory (second priority)
            if include_skills and used < token_budget:
                all_skills = self.search_procedural_memory(
                    user_message,
                    workspace_id=workspace_id,
                    limit=3,
                )
                for s in all_skills:
                    s_tokens = count_tokens(s.compact(), model)
                    if used + s_tokens <= token_budget:
                        skills.append(s)
                        used += s_tokens
                        source_details.append({"source": "procedural", "memory_id": s.name})

            # Cold memory (third priority)
            if include_cold_memory and used < token_budget:
                all_cold = await self.cold_store.search(
                    user_message,
                    workspace_id=workspace_id,
                    limit=5,
                )
                for m in all_cold:
                    m_tokens = count_tokens(m.compact(), model)
                    if used + m_tokens <= token_budget:
                        cold.append(m)
                        used += m_tokens
                        source_details.append(
                            {
                                "source": "cold_memory",
                                "memory_id": m.id,
                                "category": m.kind,
                            }
                        )

            # Deep memory (lowest priority)
            if include_deep_memory and not deep and used < token_budget:
                deep = self.load_deep_memory()
                if deep.strip():
                    deep_tokens = count_tokens(deep.strip(), model)
                    if used + deep_tokens > token_budget:
                        deep = ""  # skip if doesn't fit
                    else:
                        source_details.append({"source": "deep_memory"})

        return ContextPack(
            hot_memory=hot,
            cold_memories=cold,
            procedural_memories=skills,
            deep_memory=deep,
            token_budget=token_budget,
            source_details=source_details,
        )

    async def _build_balanced(
        self,
        user_message: str,
        *,
        workspace_id: str | None,
        hot: HotMemory,
        include_cold_memory: bool,
        include_skills: bool,
        include_deep_memory: bool,
        token_budget: int,
        deep_memory: str,
        model: str,
        source_details: list[dict[str, Any]],
    ) -> ContextPack:
        from cognix.memory.budget import ContextBudgetManager
        from cognix.memory.token_counter import count_tokens

        skill_candidates = (
            self.search_procedural_memory(user_message, workspace_id=workspace_id, limit=5)
            if include_skills
            else []
        )
        cold_candidates = (
            await self.cold_store.search(user_message, workspace_id=workspace_id, limit=8)
            if include_cold_memory
            else []
        )
        deep = deep_memory or (self.load_deep_memory() if include_deep_memory else "")

        available = {
            "hot": count_tokens(hot.render(), model),
            "procedural": sum(count_tokens(s.compact(), model) for s in skill_candidates),
            "cold": sum(count_tokens(m.compact(), model) for m in cold_candidates),
            "deep": count_tokens(deep.strip(), model),
        }
        allocations = {
            allocation.source_name: allocation.token_budget
            for allocation in ContextBudgetManager(token_budget).allocate(available)
        }
        source_details.append({"source": "context_budget", "allocations": allocations})

        skills = self._select_by_budget(
            skill_candidates,
            allocations.get("procedural", 0),
            model=model,
            compact=lambda item: item.compact(),
        )
        cold = self._select_by_budget(
            cold_candidates,
            allocations.get("cold", 0),
            model=model,
            compact=lambda item: item.compact(),
        )
        if skills:
            source_details.extend(
                {"source": "procedural", "memory_id": skill.name} for skill in skills
            )
        if cold:
            source_details.extend(
                {
                    "source": "cold_memory",
                    "memory_id": memory.id,
                    "category": memory.kind,
                }
                for memory in cold
            )
        if deep.strip() and allocations.get("deep", 0) <= 0:
            deep = ""
        elif deep.strip():
            source_details.append({"source": "deep_memory"})
        if hot.render():
            source_details.append({"source": "hot_memory"})

        return ContextPack(
            hot_memory=hot,
            cold_memories=cold,
            procedural_memories=skills,
            deep_memory=deep,
            token_budget=token_budget,
            source_details=source_details,
        )

    @staticmethod
    def _select_by_budget(items: list[Any], budget: int, *, model: str, compact) -> list[Any]:
        if budget <= 0:
            return []
        from cognix.memory.token_counter import count_tokens

        selected = []
        used = 0
        for item in items:
            tokens = count_tokens(compact(item), model)
            if used + tokens <= budget:
                selected.append(item)
                used += tokens
        return selected

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

    def load_deep_memory(self) -> str:
        return self._read_text(self.home.deep_memory_file)

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
