"""Working memory: the current state of the graph (§6.12)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.evidence import Evidence
from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.core.ids import IdFactory
from axelrod_wm.core.serialization import StrSet
from axelrod_wm.engine.explain_records import Explanation
from axelrod_wm.engine.performance.records import Forecast
from axelrod_wm.events.graph_update import GraphOp, Specificity


class DeviationHistory(BaseModel):
    """Standardized deviations and innovations per subentity on the propagation grid."""

    model_config = ConfigDict(extra="forbid")

    origin_date: datetime
    step_days: float
    z: dict[str, dict[int, float]] = {}             # subentity -> step -> deviation
    innovation: dict[str, dict[int, float]] = {}    # subentity -> step -> standardized innovation

    def step_of(self, t: datetime) -> int:
        return int(math.floor((t - self.origin_date).total_seconds() / (self.step_days * 86400.0)))

    def step_start(self, step: int) -> datetime:
        return self.origin_date + timedelta(days=self.step_days * step)

    def observed_steps(self, subentity_id: str) -> list[int]:
        return sorted(self.z.get(subentity_id, {}))

    def last_step(self, subentity_id: str) -> int | None:
        d = self.z.get(subentity_id)
        return max(d) if d else None

    def z_at(self, subentity_id: str, step: int) -> float | None:
        """Forward-filled deviation at `step`; before the first observation, the first value.
        None if the subentity was never observed."""
        d = self.z.get(subentity_id)
        if not d:
            return None
        best_step, best = None, None
        first_step = None
        for s in d:
            if first_step is None or s < first_step:
                first_step = s
            if s <= step and (best_step is None or s > best_step):
                best_step, best = s, d[s]
        if best is None:
            return d[first_step]  # type: ignore[index]
        return best

    def current_z(self, subentity_id: str) -> float:
        d = self.z.get(subentity_id)
        if not d:
            return 0.0
        return d[max(d)]

    def dense(self, subentity_id: str, start_step: int, end_step: int) -> np.ndarray:
        """Forward-filled deviations for steps start..end inclusive (backfilled before the first
        observation, zeros if never observed)."""
        n = end_step - start_step + 1
        out = np.zeros(max(n, 0))
        d = self.z.get(subentity_id)
        if not d or n <= 0:
            return out
        steps = sorted(d)
        vals = [d[s] for s in steps]
        j = -1
        cur = vals[0]
        for k in range(n):
            s = start_step + k
            while j + 1 < len(steps) and steps[j + 1] <= s:
                j += 1
                cur = vals[j]
            out[k] = cur if j >= 0 else vals[0]
        return out

    def increments(self, subentity_id: str, end_step: int, n: int) -> np.ndarray:
        """dz for steps end-n+1..end (oldest first). Steps with no observation count as zero change,
        and the first observation counts as no change."""
        dense = self.dense(subentity_id, end_step - n, end_step)
        return np.diff(dense) if dense.size > 1 else np.zeros(max(n, 0))

    def window_change(self, subentity_id: str, step: int, width: int) -> float:
        a = self.z_at(subentity_id, step)
        b = self.z_at(subentity_id, step - width)
        if a is None or b is None:
            return 0.0
        return a - b

    def window_innovation(self, subentity_id: str, step: int, width: int) -> float:
        """Sum of the last `width` innovations divided by sqrt(width)."""
        d = self.innovation.get(subentity_id, {})
        total = sum(d.get(step - k, 0.0) for k in range(width))
        return total / math.sqrt(max(width, 1))


class PendingRefinement(BaseModel):
    """A graph update op that could not yet be made concrete (§7.5)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    op: GraphOp                         # as specific as it got
    end: str                            # "source", "target", or "subject"
    reached: Specificity
    node_id: str                        # generalization or entity id reached
    candidates: dict[str, float]        # candidate id -> score
    evidence: list[Evidence]
    source_event_id: str
    created_at: datetime
    expires_at: datetime
    relation_node_id: str | None = None         # the interaction generalization the op asserts
    attribute_filter: list[str] = []            # attribute kinds the fuzzy end may take
    explicit_attribute: bool = False            # True if the op itself named the attribute kind
    label: str | None = None
    polarity: int | None = None
    market_event_id: str | None = None


class ForecastStateView(BaseModel):
    """What the forecast layer holds for one thesis: the state updated into a forecast."""

    model_config = ConfigDict(extra="forbid")

    thesis_id: str
    forecast: Forecast                     # the full record (§8.9); read_out() returns it
    explanation: Explanation               # moves into long-term memory at the next consolidation
    thesis: dict | None = None             # the posed thesis (JSON), for "Compare with..." and VOI references


class ForecastLayer(BaseModel):
    """Forecasts written by the performance task, keyed by thesis id (D5). It never touches
    posteriors, it is not part of the state hash, and writing it never bumps the version.
    Unpinned entries are cleared at consolidation, after their explanations are stored."""

    model_config = ConfigDict(extra="forbid")

    by_thesis: dict[str, ForecastStateView] = {}
    pinned: StrSet = set()
    pose_counts: dict[str, int] = {}         # thesis id -> times posed, for FC-<thesis>-<n> ids
    order: list[str] = []                    # thesis ids, most recently posed last


class ActivityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    interaction_id: str
    contribution: float               # standardized contribution mu * phi
    target_move: float | None         # observed window change of the target, if observed
    channel_key: str | None = None
    target_id: str | None = None


class EpisodeEntry(BaseModel):
    """What consolidation needs from each applied real event (§8.12)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    at: datetime
    event_type: str | None
    tags: list[str]
    signature: StrSet                 # from signature_of(), including tag: and etype: keys
    routine: bool                     # True for event_type "data_release" with no move of 1 standard unit or more
    explanation_id: str | None
    z_before: dict[str, float] = {}   # deviations of observed subentities before the event
    z_after: dict[str, float] = {}
    touched_entity_ids: list[str] = []


class WorkingMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clock: datetime
    graph: CausalGraph
    deviations: DeviationHistory
    hypotheses: dict[str, Hypothesis] = {}
    pending_refinements: dict[str, PendingRefinement] = {}
    forecast_layer: ForecastLayer = ForecastLayer()
    activity_log: list[ActivityRecord] = []    # active edges since the last consolidation (§8.6)
    fold_accumulators: dict[str, tuple[float, float]] = {}   # interaction id -> (sum phi*y, sum phi^2) this episode
    episode_buffer: list[EpisodeEntry] = []    # applied real events since the last consolidation
    ids: IdFactory = IdFactory()
    decision_variables: list[str] = []         # from construction (§14.1)
    pending_episode_tags: list[str] = []       # tags for the next episode, e.g. "decision-outcome"
    last_consolidated: date | None = None
    missing_relation_log: dict[str, datetime] = {}   # "<pattern>#<relation index>" -> last proposed

    def touched_days(self) -> list[date]:
        return sorted({e.at.date() for e in self.episode_buffer})
