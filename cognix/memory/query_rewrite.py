"""Query rewrite for memory retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cognix.memory.facts import AtomicFactStore


_COREFERENCE_RE = re.compile(r"\b(it|that|this|there|入口|那个|这个|它|他|她|上次|之前)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RewrittenQuery:
    original: str
    rewritten: str
    additions: list[str]


class QueryRewriter:
    """Expand underspecified user queries with stable facts."""

    def __init__(self, fact_store: AtomicFactStore) -> None:
        self.fact_store = fact_store

    async def rewrite(
        self,
        query: str,
        *,
        workspace_id: str | None = None,
        limit: int = 5,
    ) -> RewrittenQuery:
        normalized = query.strip()
        if not normalized:
            return RewrittenQuery(original=query, rewritten=query, additions=[])

        should_expand = bool(_COREFERENCE_RE.search(normalized)) or len(normalized) < 18
        if not should_expand:
            return RewrittenQuery(original=query, rewritten=query, additions=[])

        facts = await self.fact_store.list_active(workspace_id=workspace_id, limit=limit)
        additions: list[str] = []
        for fact in facts:
            if fact.key in {"entry_url", "url", "login_context", "output_format", "default_instruction"}:
                additions.append(fact.compact())
            if len(additions) >= limit:
                break
        if not additions:
            return RewrittenQuery(original=query, rewritten=query, additions=[])
        return RewrittenQuery(
            original=query,
            rewritten=f"{normalized}\nRelevant stable facts:\n" + "\n".join(f"- {item}" for item in additions),
            additions=additions,
        )
