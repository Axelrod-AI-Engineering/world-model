"""The reliability book: each pattern's track record (§8.14)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReliabilityBook(BaseModel):
    """Track record per pattern, as beta pseudo-counts (hits, misses). Part of long-term memory."""

    model_config = ConfigDict(extra="forbid")

    counts: dict[str, tuple[float, float]] = {}

    def mean(self, pattern_id: str) -> float:
        """(hits + 1) / (hits + misses + 2); 0.5 for an unseen pattern."""
        hits, misses = self.counts.get(pattern_id, (0.0, 0.0))
        return (hits + 1.0) / (hits + misses + 2.0)

    def update(self, pattern_id: str, hit: bool) -> None:
        hits, misses = self.counts.get(pattern_id, (0.0, 0.0))
        self.counts[pattern_id] = (hits + 1.0, misses) if hit else (hits, misses + 1.0)

    def updated(self, results: dict[str, bool]) -> ReliabilityBook:
        """A copy with several updates applied (for writing through the mutator)."""
        out = self.model_copy(deep=True)
        for pid, hit in sorted(results.items()):
            out.update(pid, hit)
        return out
