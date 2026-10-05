"""Entities, subentities, and entity memory (§6.6)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.categories import TagSet
from axelrod_wm.core.distributions import Distribution, DistSummary
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.temporal import TimeState


class EntityKind(StrEnum):
    COMPANY = "company"
    PERSON = "person"
    AGENCY = "agency"
    MARKET = "market"
    MACRO_FACTOR = "macro_factor"
    EXTERNAL_FACTOR = "external_factor"
    OTHER = "other"


class Subentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                          # "<entity_id>.<slug>"
    entity_id: str
    name: str
    attribute_kind: str              # key into AttributeVocabulary (§6.9)
    unit: str
    aliases: list[str] = []          # words events use for it, e.g. "chip capex"
    features: dict[str, str] = {}    # e.g. {"product": "semiconductors"}
    scale: float                     # one standardized unit, in link space
    obs_noise: float | None = None   # standardized units; None uses the default by attribute kind (§6.3)
    prior: Distribution
    posterior: Distribution
    anchor: float                    # link-space reference that deviations are measured from
    level_mean: float = 0.0          # local level of the fold's state-space model (§8.6), standardized
    level_var: float = 1.0
    level_noise: float | None = None # per-step level noise learned from entity memory; None uses the config
    last_update_step: int | None = None   # for scaling process noise by elapsed steps
    origin: Origin
    history: list[TimeState] = []
    prior_source_id: str | None = None    # generalization (or "graph"/"vocabulary") the prior came from
    state_cov: dict[str, float] = {}      # fold state covariances off the diagonal: "level|<channel>", "<c1>|<c2>"

    @property
    def family(self) -> str:
        return self.posterior.family

    @property
    def link(self):
        return self.posterior.link


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: EntityKind
    aliases: list[str] = []
    category_tags: TagSet
    features: dict[str, str] = {}               # e.g. {"region": "US", "function": "monetary_policy"}
    subentity_ids: list[str] = []
    internal_interaction_ids: list[str] = []    # relations among its own subentities
    generalization_id: str | None = None        # set by classification
    origin: Origin
    created_at: datetime


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
    At consolidation, the realized volatility of each subentity over the last 52 entries sets that
    subentity's level_noise, which the fold and the propagator use (§8.12). The decision profiles
    supply probabilities for ENTITY_DECISION hypotheses."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    entries: list[EntityMemoryEntry] = []
    decisions: list[DecisionObservation] = []
    profiles: dict[str, DecisionProfile] = {}   # decision subentity id -> profile

    # DECISION: keep a bounded window of entries; 52 are needed for level noise.
    MAX_ENTRIES: ClassVar[int] = 60
