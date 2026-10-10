"""Interfaces for the five stages of the shared process (§8.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.propagation import Channel, PropagationResult
from axelrod_wm.engine.registry import registry
from axelrod_wm.model.distributions import DistSummary, Gaussian, from_link_moments
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.taxonomy import Taxonomy, TaxonomyKind

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn
    from axelrod_wm.shared.process import ParsedEvent
    from axelrod_wm.shared.recognize import InductionResult


class EventParser(ABC):
    @abstractmethod
    def parse(self, event: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn | None) -> ParsedEvent: ...


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    taxonomy: TaxonomyKind
    path: list[str]                  # root -> deepest matching generalization
    prior_source_id: str             # deepest node on the path whose support exceeds the recall threshold
    created_generalization_ids: list[str] = []
    is_new: bool = False


class Classifier(ABC):
    """Sorts an item (an entity, an interaction, a superentity pattern) down its taxonomy.

    # DECISION (restructure): sorting and incorporating are separate. `classify` finds the path and gives
    # the item its kind and inherited priors (working memory); `incorporate` adds the item to the kind and
    # may split a crowded node (long-term memory). Working-memory learning classifies with
    # incorporate=False and leaves incorporation to long-term learning; construction and structural
    # changes do both at once.
    """

    @abstractmethod
    def classify(self, taxonomy: TaxonomyKind, item_id: str, is_new: bool,
                 ctx: ProcessContext, txn: MutationTxn | None, *, incorporate: bool = True) -> Classification: ...

    def incorporate(self, c: Classification, ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        """Add a classified item to its generalization in long-term memory. Returns new node ids."""
        return []


class TaxonomyGrower(ABC):
    @abstractmethod
    def maybe_split(self, taxonomy: Taxonomy, gen_id: str, ctx: ProcessContext,
                    txn: MutationTxn) -> list[str]: ...


class ScoredSuperentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    instance_id: str | None
    score: float
    attention: float
    via_episode: str | None = None


class ScoredEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    score: float
    attention: float
    shared_generalizations: list[str]


class RecallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    superentities: list[ScoredSuperentity]
    analogs: list[ScoredEpisode]

    def attention_of(self, pattern_id: str) -> float:
        return max((s.attention for s in self.superentities if s.pattern_id == pattern_id), default=0.0)


class AttentionPolicy(ABC):
    @abstractmethod
    def select(self, scores: dict[str, float], top_k: int) -> dict[str, float]:
        """Return the kept ids and their attention weights."""


class Recaller(ABC):
    @abstractmethod
    def recall(self, parsed: ParsedEvent, wm: WorkingMemory, ltm: LongTermMemory,
               ctx: ProcessContext) -> RecallResult: ...


class AnalogEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    implied_effect: float          # b_E: the edge's implied effect in that episode
    weight: float                  # w_E: sum of phi^2 for the edge in that episode
    attention: float               # a_E: the episode's attention in this recall


class PrefilledModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    channels: dict[str, Channel]                         # working set, with plain posterior dynamics
    analog_evidence: dict[str, list[AnalogEvidence]]     # channel id -> evidence from recalled episodes' responses
    network_episodes: dict[str, list[str]]               # instance id -> recalled episodes where its pattern was active
    drifts: dict[str, float]                             # subentity -> trend of its local level, per day
    instance_ids: list[str]                              # bound instances relevant to this event
    notes: list[str]                                     # human-readable adjustments, for explanations
    target_noise: dict[str, float] = {}                  # channel key -> obs noise of its target
    focus: list[str] = []
    recalled_episode_ids: list[str] = []

    def dynamics_for(self, interaction_id: str, episode_ids: set[str]) -> EdgeDynamics:
        """The plain posterior combined once with a single pooled pseudo-observation built from
        the analog evidence of the given distinct episodes (§8.4.4). An empty set gives the
        plain posterior."""
        ch = self.channels.get(interaction_id)
        if ch is None:
            raise KeyError(interaction_id)
        base = ch.dynamics
        if not episode_ids:
            return base
        ev = [e for e in self.analog_evidence.get(interaction_id, []) if e.episode_id in episode_ids]
        seen: set[str] = set()
        uniq = []
        for e in sorted(ev, key=lambda x: x.episode_id):
            if e.episode_id not in seen:
                seen.add(e.episode_id)
                uniq.append(e)
        aw = sum(e.attention * e.weight for e in uniq)
        if aw <= 1e-12:
            return base
        pooled_mean = sum(e.attention * e.weight * e.implied_effect for e in uniq) / aw
        noise = self.target_noise.get(interaction_id, 0.15)
        pooled_var = noise * noise / aw + 0.1**2
        m0, v0 = base.effect.mean(), max(base.effect.var(), 1e-9)
        prec = 1.0 / v0 + 1.0 / pooled_var
        mean = (m0 / v0 + pooled_mean / pooled_var) / prec
        var = 1.0 / prec
        if isinstance(base.effect, Gaussian):
            effect = Gaussian(mu=mean, sigma=var ** 0.5)
        else:
            effect = from_link_moments(base.effect.family, mean, var)
        return EdgeDynamics(effect=effect, kernel=base.kernel)

    def channel_with(self, key: str, episode_ids: set[str], forced: bool | None = None) -> Channel:
        ch = self.channels[key]
        return ch.model_copy(update={"dynamics": self.dynamics_for(key, episode_ids),
                                     "forced": forced if forced is not None else ch.forced})


class Prefiller(ABC):
    @abstractmethod
    def prefill(self, parsed: ParsedEvent, recall: RecallResult, induction: InductionResult,
                wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> PrefilledModel: ...


class Analysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    event_id: str
    result: PropagationResult | None                     # the event's effect (shocked minus unshocked)
    expected_moves: dict[str, DistSummary]               # at the horizon, |median| >= 0.1
    levels: PropagationResult | None = None              # the shocked run (levels)
    horizon_days: int = 0
    transmission: list[Any] = []                         # material effects by order, with paths (addition)


class Analyzer(ABC):
    @abstractmethod
    def analyze(self, parsed: ParsedEvent, model: PrefilledModel, wm: WorkingMemory,
                ctx: ProcessContext) -> Analysis: ...


registry("parser", EventParser)
registry("classifier", Classifier)
registry("taxonomy_grower", TaxonomyGrower)
registry("attention", AttentionPolicy)
registry("recaller", Recaller)
registry("prefiller", Prefiller)
registry("analyzer", Analyzer)
