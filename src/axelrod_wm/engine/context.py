"""Process context and the hypothetical overlay (§8.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.memory.working import WorkingMemory

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import GraphMutator
    from axelrod_wm.core.taxonomy import AttributeVocabulary
    from axelrod_wm.engine.config import EngineConfig
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.trace import Tracer


class GraphOverlay:
    """A copy-on-write view over the CausalGraph. It holds the transient objects of one
    hypothetical run and is thrown away afterwards. Base objects are shared, never mutated;
    replacing one puts a modified copy in the overlay."""

    def __init__(self, wm: WorkingMemory, scope: str) -> None:
        self.base = wm
        self.scope = scope
        g = wm.graph
        self.graph = CausalGraph.model_construct(
            entities=dict(g.entities), subentities=dict(g.subentities), interactions=dict(g.interactions),
            instances=dict(g.instances), super_interactions=dict(g.super_interactions),
            entity_link_labels=g.entity_link_labels)
        fields = {name: getattr(wm, name) for name in WorkingMemory.model_fields}
        fields["graph"] = self.graph
        fields["hypotheses"] = dict(wm.hypotheses)
        self.wm = WorkingMemory.model_construct(**fields)
        self._counters: dict[str, int] = {}
        self.created: dict[str, list[str]] = {}

    def next_id(self, prefix: str) -> str:
        """Ids scoped to the thesis, e.g. ``inst-T-01-1`` (performance never touches IdFactory)."""
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}-{self.scope}-{n}"

    def put(self, collection: str, obj: Any) -> None:
        target = {
            "entities": self.graph.entities,
            "subentities": self.graph.subentities,
            "interactions": self.graph.interactions,
            "instances": self.graph.instances,
            "hypotheses": self.wm.hypotheses,
        }[collection]
        target[obj.id] = obj
        self.created.setdefault(collection, []).append(obj.id)


@dataclass
class ProcessContext:
    config: EngineConfig
    rng: np.random.Generator
    tracer: Tracer
    now: datetime
    state_version: int
    mutator: GraphMutator
    vocab: AttributeVocabulary                 # from the construction spec (§6.13)
    learn: bool                                # True for real events, False for hypothetical ones
    processing_day: int | None = None          # the day an update run is processing (§7.8)
    initializing: bool = False                 # True during the history replay (§8.13)
    overlay: Optional[GraphOverlay] = None     # transient objects for a scaffolded thesis
    engine: Any = None
    scope: str = ""                            # thesis id for performance runs
    notes: dict[str, Any] = field(default_factory=dict)

    def child_rng(self, *keys: int | str) -> np.random.Generator:
        """Deterministic sub-generator seeded from (config.seed, state_version, *keys)
        via numpy.random.SeedSequence. String keys are hashed with SHA-256. Keys must be
        stable names: stage names, thesis ids, pattern ids, and interaction ids. Never use
        generated ids (FC-, NW-, SC-), so that posing the same thesis twice draws the same numbers."""
        return make_rng(self.config.seed, self.state_version, *keys)

    @property
    def wm(self) -> WorkingMemory:
        if self.overlay is not None:
            return self.overlay.wm
        return self.engine.wm

    @property
    def ltm(self) -> LongTermMemory:
        return self.engine.ltm

    @property
    def step_days(self) -> float:
        return float(self.config.time.step_days)

    @property
    def day(self) -> int:
        """The day being processed, or the next day to process outside an update run."""
        if self.processing_day is not None:
            return int(self.processing_day)
        return int(self.wm.last_processed_day) + 1

    @property
    def today(self) -> int:
        """"Now" (day 0 of a propagation): the day being processed inside an update run, else the
        last processed day."""
        if self.processing_day is not None:
            return int(self.processing_day)
        return int(self.wm.last_processed_day)

    @property
    def recall_threshold(self) -> float:
        return float(self.config.thresholds.recall)

    @property
    def recognition(self) -> float:
        return float(self.config.thresholds.recognition)
