"""Entities and subentities (§6.6). Entity memory lives in memory/entity_memory.py (§6.13)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from axelrod_wm.model.categories import TagSet
from axelrod_wm.model.distributions import Distribution
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.temporal import TimeState


class EntityKind(StrEnum):
    COMPANY = "company"
    PERSON = "person"
    AGENCY = "agency"
    MARKET = "market"
    MACRO_FACTOR = "macro_factor"
    EXTERNAL_FACTOR = "external_factor"
    OTHER = "other"


class EconomicConstraint(BaseModel):
    """A soft bound in native units (addition): an economic limit, not a law. Buyers keep second sources, so
    one supplier's share rarely passes a cap; a yield cannot pass 100%. Simulations bend toward the bound
    instead of crossing it, and forecasts report when it binds."""
    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    reason: str = ""


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
    level_mean: float = 0.0          # local level of the daily state-space model (§8.6), standardized
    level_var: float = 1.0
    level_noise: float | None = None # per-day level noise learned from entity memory; None uses the config
    observed: bool = True            # False if no source ever reports it; it then moves only by propagation
    origin: Origin
    history: list[TimeState] = []    # one per week and one per non-routine event; the newest 260 are kept
    prior_source_id: str | None = None    # generalization (or "graph"/"vocabulary") the prior came from
    state_cov: dict[str, float] = {}      # fold state covariances off the diagonal: "level|<channel>", "<c1>|<c2>"
    # the default its kind supplies (addition): every firm has a "revenue", every airline a "fuel_cost"; kept
    # out of `features` so the shared slot never becomes a feature the taxonomy grower splits on
    slot: str | None = None
    slot_of: str | None = None            # the object generalization whose default this is
    constraint: EconomicConstraint | None = None   # a soft economic bound in native units (addition)
    user_confidence: float | None = None  # the reviewer's confidence when it was added (Oct 8); None: not set

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
    description: str = ""                       # one plain sentence for the demo's tooltips and inspector
    subentity_ids: list[str] = []
    internal_interaction_ids: list[str] = []    # relations among its own subentities
    generalization_id: str | None = None        # set by classification
    origin: Origin
    created_at: datetime
    user_confidence: float | None = None        # the reviewer's confidence when it was added (Oct 8); None: not set
