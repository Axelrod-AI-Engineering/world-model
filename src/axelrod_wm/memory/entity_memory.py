"""Entity memories: one of the four parts of long-term memory (§6.6, §6.13)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import DistSummary


class DecisionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subentity_id: str                 # the decision variable, e.g. federal_reserve.policy_stance
    at: datetime
    change: float                     # native units; 0 for a hold
    context: dict[str, float]         # standardized deviations of related subentities at the time


ACTIONS = ("raised", "cut", "held")


def action_of(change: float, scale_native: float) -> str:
    """Bucket a native-unit change into raised / cut / held (half a standard unit either way)."""
    thr = 0.5 * abs(scale_native) if scale_native else 1e-9
    if change > thr:
        return "raised"
    if change < -thr:
        return "cut"
    return "held"


class DecisionProfile(BaseModel):
    """Counts of how the entity has acted, by context bucket (e.g. "inflation.headline_cpi>+0.75"):
    bucket -> [raised, cut, held]."""

    model_config = ConfigDict(extra="forbid")

    by_context: dict[str, list[int]] = {}

    def p_action(self, bucket: str, action: str) -> float:
        """Laplace-smoothed probability of `action` in `bucket`."""
        counts = self.by_context.get(bucket, [0, 0, 0])
        idx = ACTIONS.index(action)
        return (counts[idx] + 1.0) / (sum(counts) + 3.0)

    def total(self, bucket: str) -> int:
        return sum(self.by_context.get(bucket, [0, 0, 0]))


class EntityMemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    subentity_summaries: dict[str, DistSummary]
    event_ids: list[str] = []
    z: dict[str, float] = {}          # standardized deviation of each subentity at the entry


class EntityMemory(BaseModel):
    """The entity's own long-term memory. It affects how the entity is used later in two ways.
    Entries are written weekly (entity_memory.entry_every_days). At consolidation, the realized
    volatility of each subentity over the last 52 entries sets that subentity's level_noise, which the
    daily predict step and the propagator use (§8.12). The decision profiles supply probabilities for
    ENTITY_DECISION hypotheses."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    entries: list[EntityMemoryEntry] = []
    decisions: list[DecisionObservation] = []
    profiles: dict[str, DecisionProfile] = {}   # decision subentity id -> profile

    # DECISION: keep a bounded window of weekly entries; 52 are needed for level noise.
    MAX_ENTRIES: ClassVar[int] = 60
    MAX_DECISIONS: ClassVar[int] = 500
