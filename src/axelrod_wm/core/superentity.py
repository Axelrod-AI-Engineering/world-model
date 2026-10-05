"""Superentities: reusable configurations of entities and interactions (§6.8)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.serialization import StrSet
from axelrod_wm.core.temporal import TimeState


class SuperentityStatus(StrEnum):
    CANDIDATE = "candidate"
    ADMITTED = "admitted"
    DISSOLVED = "dissolved"


class RoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str                         # e.g. "price_level"
    generalization_id: str            # object generalization the role's filler must fall under
    attribute_kinds: list[str] = []


class PatternRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_role: str
    source_attr: str                  # attribute kind
    target_role: str
    target_attr: str
    interaction_generalization_id: str | None = None
    polarity: int                     # +1 or -1
    label: str
    present: bool = True              # a pattern may assert that a relation is ABSENT

    def key(self) -> tuple[str, str, str, str, str, int, bool]:
        return (self.source_role, self.source_attr, self.target_role, self.target_attr,
                self.interaction_generalization_id or "", self.polarity, self.present)


class SuperentityPattern(BaseModel):
    """The reusable configuration (a TRELLIS chunk). Lives in long-term memory."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    roles: list[RoleSpec]
    relations: list[PatternRelation]
    sub_pattern_ids: list[str] = []   # composition: superentities made of superentities
    support: float = 0.0              # decayed count of supporting episodes
    status: SuperentityStatus = SuperentityStatus.CANDIDATE
    rival_ids: StrSet = set()         # patterns that explain the same moves with different structure
    episode_ids: list[str] = []
    generalization_id: str | None = None   # superentities are objects, so they classify too
    origin: Origin = Origin.INFERENCE
    palette: str | None = None             # hull color key for the UI
    history: list[TimeState] = []          # support over time, one entry per consolidation
    created_at: datetime
    last_seen: datetime | None = None
    proposed_at: datetime | None = None    # when an admission or dissolution was last proposed

    def role(self, name: str) -> RoleSpec | None:
        for r in self.roles:
            if r.name == name:
                return r
        return None

    def present_relations(self) -> list[PatternRelation]:
        return [r for r in self.relations if r.present]


class SuperentityInstance(BaseModel):
    """A pattern bound to concrete entities. Lives in working memory.
    The performance task calls a bound instance a network (D1)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    pattern_id: str
    bindings: dict[str, str]          # role name -> entity id
    interaction_ids: list[str]        # concrete edges that realize the pattern's relations
    absent_interaction_ids: list[str] = []   # edges the pattern says are absent
    child_instance_ids: list[str] = []
    activation: float = 0.0           # share of its interactions in the activity log since the last consolidation
    transient: bool = False           # bound only for one hypothetical; never persisted

    def entity_ids(self) -> list[str]:
        return sorted(set(self.bindings.values()))


class SuperLinkKind(StrEnum):
    CAUSAL = "causal"
    SHARES_MEMBERS = "shares_members"


class SuperInteraction(BaseModel):
    """An interaction between two instances: an abstraction over the edges from
    members of one to members of the other (Figure 4)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_instance_id: str
    target_instance_id: str
    kind: SuperLinkKind
    label: str
    underlying_interaction_ids: list[str] = []
    shared_entity_ids: list[str] = []
    significance: float = 0.0
