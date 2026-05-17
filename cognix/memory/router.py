"""Memory router: classify messages and route to appropriate memory stores."""

from __future__ import annotations

import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class MessageCategory(Enum):
    """Classification of incoming messages for memory routing."""

    FACTUAL = "factual"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


# Compiled regex patterns for classification heuristics.
_PROCEDURAL_PATTERNS = re.compile(
    r"\b(?:how\s+to|steps|workflow|process|guide|instructions?|tutorial|procedure|method)\b",
    re.IGNORECASE,
)
_FACTUAL_PATTERNS = re.compile(
    r"\b(?:is\s+a|means|defined\s+as|definition|fact|is\s+the|refers\s+to|"
    r"was\s+founded|was\s+born|capital\s+of|population\s+of|located\s+in)\b",
    re.IGNORECASE,
)

# Default route mapping per category.
_CATEGORY_ROUTES: dict[MessageCategory, list[str]] = {
    MessageCategory.FACTUAL: ["hot", "deep"],
    MessageCategory.EPISODIC: ["hot", "cold"],
    MessageCategory.PROCEDURAL: ["hot", "procedural"],
}

# Messages shorter than this threshold are unlikely to be worth persisting.
_MIN_WRITE_LENGTH = 20


class MemoryRouter:
    """Classify incoming messages into memory categories and route to stores.

    Uses keyword and pattern heuristics so classification is fast and
    dependency-free.  For production use the heuristics can be replaced
    with an LLM-backed classifier without changing the public API.
    """

    def classify(
        self,
        message: str,
        context: dict | None = None,
    ) -> MessageCategory:
        """Classify *message* into a :class:`MessageCategory`.

        Heuristic order:
        1. PROCEDURAL -- contains action-oriented keywords ("how to", "steps", …)
        2. FACTUAL -- contains definitional / knowledge keywords ("is a", "means", …)
        3. EPISODIC -- everything else (conversational, task-related)

        Parameters
        ----------
        message:
            Raw user or agent message text.
        context:
            Optional metadata dict (reserved for future use, e.g. topic tags).

        Returns
        -------
        MessageCategory
        """
        normalized = message.strip()

        if not normalized:
            logger.debug("Empty message classified as EPISODIC")
            return MessageCategory.EPISODIC

        if _PROCEDURAL_PATTERNS.search(normalized):
            logger.debug("Message classified as PROCEDURAL: %s", normalized[:80])
            return MessageCategory.PROCEDURAL

        if _FACTUAL_PATTERNS.search(normalized):
            logger.debug("Message classified as FACTUAL: %s", normalized[:80])
            return MessageCategory.FACTUAL

        logger.debug("Message classified as EPISODIC (default): %s", normalized[:80])
        return MessageCategory.EPISODIC

    def route(
        self,
        message: str,
        context: dict | None = None,
    ) -> list[str]:
        """Return the list of memory store names to query for *message*.

        Parameters
        ----------
        message:
            Raw user or agent message text.
        context:
            Optional metadata dict forwarded to :meth:`classify`.

        Returns
        -------
        list[str]
            Store names, e.g. ``["hot", "cold"]``.
        """
        category = self.classify(message, context)
        stores = _CATEGORY_ROUTES[category]
        logger.debug(
            "Routing message (category=%s) to stores: %s",
            category.value,
            stores,
        )
        return list(stores)

    def should_write(
        self,
        message: str,
        category: MessageCategory,
    ) -> bool:
        """Decide whether *message* is worth persisting to memory.

        The current heuristic is intentionally simple:
        - Skip very short messages (greetings, acknowledgements).
        - Skip messages that look like questions (they are retrieval, not storage).
        - Write everything else.

        Parameters
        ----------
        message:
            Raw user or agent message text.
        category:
            The pre-classified :class:`MessageCategory`.

        Returns
        -------
        bool
        """
        normalized = message.strip()

        if len(normalized) < _MIN_WRITE_LENGTH:
            logger.debug(
                "Skipping write (too short, %d chars): %s",
                len(normalized),
                normalized[:40],
            )
            return False

        # Questions are typically retrieval requests, not facts to store.
        if normalized.endswith("?") and category == MessageCategory.EPISODIC:
            logger.debug("Skipping write (question in EPISODIC): %s", normalized[:60])
            return False

        logger.debug(
            "Write approved (category=%s): %s",
            category.value,
            normalized[:60],
        )
        return True
