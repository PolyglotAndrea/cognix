"""Context budget manager for allocating token budget across memory sources."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetAllocation:
    """Represents a token budget allocation for a single memory source."""

    source_name: str
    token_budget: int
    priority: int


class ContextBudgetManager:
    """Allocates a fixed token budget across multiple memory sources proportionally.

    Default allocation ratios:
        hot=0.40, procedural=0.25, cold=0.25, deep=0.10

    If a source has no content its share is redistributed to the remaining
    sources in proportion to their original ratios.
    """

    DEFAULT_RATIOS: dict[str, float] = {
        "hot": 0.40,
        "procedural": 0.25,
        "cold": 0.25,
        "deep": 0.10,
    }

    def __init__(self, total_budget: int = 4000) -> None:
        """Initialise the budget manager.

        Args:
            total_budget: Total number of tokens available for context.
        """
        self.total_budget = total_budget

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allocate(self, available_sources: dict[str, int]) -> list[BudgetAllocation]:
        """Allocate token budget across the given memory sources.

        Args:
            available_sources: Mapping of source name to the number of tokens
                of content currently available in that source.

        Returns:
            A list of :class:`BudgetAllocation` objects, one per *active*
            source (sources with zero content are excluded).
        """
        # Separate active (non-empty) and empty sources
        active = {name: count for name, count in available_sources.items() if count > 0}
        if not active:
            return []

        # Build ratio map for known sources, falling back to equal share
        ratios = {name: self.DEFAULT_RATIOS.get(name, 0.0) for name in active}
        total_ratio = sum(ratios.values())

        # If none of the sources have a known default ratio, split equally
        if total_ratio == 0:
            ratios = {name: 1.0 / len(active) for name in active}
            total_ratio = 1.0

        # Normalise ratios so they sum to 1.0
        normalised = {name: r / total_ratio for name, r in ratios.items()}

        allocations: list[BudgetAllocation] = []
        for idx, (name, ratio) in enumerate(normalised.items()):
            budget = int(self.total_budget * ratio)
            allocations.append(
                BudgetAllocation(
                    source_name=name,
                    token_budget=min(budget, available_sources[name]),
                    priority=idx,
                )
            )

        # Distribute any leftover tokens (from rounding) to the first source
        assigned = sum(a.token_budget for a in allocations)
        leftover = self.total_budget - assigned
        if leftover > 0 and allocations:
            allocations[0].token_budget += leftover

        return allocations

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate the number of tokens in *text* using a word-based heuristic.

        The estimate is ``len(words) * 1.3``, rounded up.

        Args:
            text: The text to estimate.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    @staticmethod
    def trim_to_budget(text: str, max_tokens: int) -> str:
        """Trim *text* so that its estimated token count does not exceed *max_tokens*.

        Uses a simple word-based heuristic (words * 1.3).  Words are removed
        from the end of the text until the estimate fits within the budget.

        Args:
            text: The text to trim.
            max_tokens: Maximum allowed tokens.

        Returns:
            The trimmed text (may be the original if it already fits).
        """
        if not text or max_tokens <= 0:
            return ""

        words = text.split()
        if int(len(words) * 1.3) <= max_tokens:
            return text

        # Binary search for the right number of words
        lo, hi = 0, len(words)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if int(mid * 1.3) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1

        return " ".join(words[:lo])
