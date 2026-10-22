"""Graph update events and ops (§7.2) and fuzzy targets (§7.3)."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from axelrod_wm.model.categories import TagSet
from axelrod_wm.model.distributions import Beta, Distribution
from axelrod_wm.model.entity import EntityKind
from axelrod_wm.model.evidence import Evidence
from axelrod_wm.model.hypothesis import Hypothesis
from axelrod_wm.model.ids import TEMP_PREFIX
from axelrod_wm.model.interaction import Direction, EdgeDynamics, EdgeType, ParameterBinding
from axelrod_wm.model.superentity import SuperentityPattern


class EventKind(StrEnum):
    REAL = "real"
    HYPOTHETICAL = "hypothetical"


class Specificity(IntEnum):
    GENERALIZATION = 0     # only a taxonomy node is known
    ENTITY = 1             # the entity is known, but not the subentity
    SUBENTITY = 2          # concrete


SPECIFICITY_NAMES = {0: "generalization", 1: "entity", 2: "subentity"}


class ConcreteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["concrete"] = "concrete"
    subentity_id: str                     # an existing id or a "new:" temp id


class AbstractTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["abstract"] = "abstract"
    generalization_id: str | None = None  # object taxonomy node; None means the root
    entity_id: str | None = None          # set when the entity is known but the subentity is not
    candidate_entity_ids: list[str] = []  # explicit candidates, e.g. the members of a hull in the Draw tool
    attribute_kind: str | None = None
    constraints: dict[str, str] = {}      # e.g. {"product": "semiconductors", "region": "IN"}
    mention: str | None = None            # text span from the market event


TargetSpec = Annotated[Union[ConcreteTarget, AbstractTarget], Field(discriminator="kind")]


def target_specificity(t: ConcreteTarget | AbstractTarget) -> Specificity:
    if isinstance(t, ConcreteTarget):
        return Specificity.SUBENTITY
    return Specificity.ENTITY if t.entity_id else Specificity.GENERALIZATION


class ChangeMode(StrEnum):
    ABSOLUTE = "absolute"          # native units
    RELATIVE = "relative"          # fraction, e.g. 0.18 for +18%
    STANDARDIZED = "standardized"  # standard units of the subentity


class Persistence(StrEnum):
    STEP = "step"      # the change persists
    PULSE = "pulse"    # the change lasts one day


class AddEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_entity"] = "add_entity"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    temp_id: str                          # "new:<final id>"
    name: str
    kind: EntityKind
    category_tags: TagSet = set()
    features: dict[str, str] = {}
    aliases: list[str] = []


class AddSubentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_subentity"] = "add_subentity"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    entity: str                           # entity id or temp id
    temp_id: str                          # "new:<entity_id>.<slug>"
    name: str
    attribute_kind: str
    unit: str
    features: dict[str, str] = {}
    aliases: list[str] = []
    family: str | None = None             # None: from the attribute vocabulary
    prior: Optional[Distribution] = None  # None: inherited (§8.4.2)
    scale: float | None = None            # None: inherited (§8.4.2)


class ObserveValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["observe_value"] = "observe_value"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    target: TargetSpec
    value: float                          # native units
    noise_sd: float | None = None         # standardized units; None uses the subentity's obs_noise
    observed_at: datetime


class ChangeValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["change_value"] = "change_value"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    target: TargetSpec
    delta: float
    delta_sd: float = 0.0                 # uncertainty about the change, same units as delta
    mode: ChangeMode
    persistence: Persistence = Persistence.STEP
    intervention: bool = False            # hypothetical only: do(); cut the target's in-channels while set
    window_days: int | None = None        # for interventions: how long the value is held
    at: datetime


class PatternRelationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    relation_index: int


class AddInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_interaction"] = "add_interaction"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    source: TargetSpec
    target: TargetSpec
    label: str
    polarity: int
    direction: Direction = Direction.UNIDIRECTIONAL
    edge_type: EdgeType = EdgeType.CAUSAL
    interaction_generalization_id: str | None = None   # the broad connection this op asserts, if known
    pattern_relation: Optional[PatternRelationRef] = None  # the pattern relation it would realize, if known
    dynamics: Optional[EdgeDynamics] = None   # None: inherited from the interaction generalization
    reverse: Optional[EdgeDynamics] = None    # for BIDIRECTIONAL
    existence: Optional[Beta] = None
    parameters: list[ParameterBinding] = []
    hedge: str | None = None              # a soft interaction of a fuzzy end's hedge: the hedge's key (Oct 8)


class ReweightInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["reweight_interaction"] = "reweight_interaction"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    interaction_id: str
    supports: bool                        # True: evidence for the relation; False: against it
    strength: float = 0.5


class AnnotateInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["annotate_interaction"] = "annotate_interaction"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    interaction_id: str
    note: str
    valid_from: datetime
    valid_to: datetime | None = None


class ProposeHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["propose_hypothesis"] = "propose_hypothesis"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    hypothesis: Hypothesis


class ProposeSuperentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["propose_superentity"] = "propose_superentity"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    pattern: SuperentityPattern
    bindings: dict[str, str] = {}


class DissolveSuperentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["dissolve_superentity"] = "dissolve_superentity"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    pattern_id: str
    reason: str


class RetireInteraction(BaseModel):
    """Delete an interaction from the current graph (restructure). Like `git rm`: it leaves the active
    graph and the forecasts, and the ledger keeps its whole history."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["retire_interaction"] = "retire_interaction"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    interaction_id: str
    reason: str


class RetireEntity(BaseModel):
    """Delete an entity (a node) from the current graph, with its subentities; every interaction that
    touches them is retired, and superentity instances that bound it dissolve (restructure). Its own
    long-term memory stays: the model remembers what it learned about the entity."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["retire_entity"] = "retire_entity"
    confidence: float | None = None       # the reviewer's confidence in this change, 0..1; None: the event's
    entity_id: str
    reason: str


GraphOp = Annotated[
    Union[AddEntity, AddSubentity, ObserveValue, ChangeValue, AddInteraction, ReweightInteraction,
          AnnotateInteraction, ProposeHypothesis, ProposeSuperentity, DissolveSuperentity,
          RetireInteraction, RetireEntity],
    Field(discriminator="op"),
]
GRAPH_OP_ADAPTER: TypeAdapter = TypeAdapter(GraphOp)

STRUCTURAL_OPS = frozenset({"add_entity", "add_subentity", "add_interaction", "retire_interaction",
                            "retire_entity"})


def op_ends(op: Any) -> list[tuple[str, ConcreteTarget | AbstractTarget]]:
    """The target ends of an op: ("subject", t) for value ops, ("source"/"target", t) for edges."""
    if isinstance(op, (ObserveValue, ChangeValue)):
        return [("subject", op.target)]
    if isinstance(op, AddInteraction):
        return [("source", op.source), ("target", op.target)]
    return []


def op_specificity(op: Any) -> Specificity:
    ends = op_ends(op)
    return min((target_specificity(t) for _, t in ends), default=Specificity.SUBENTITY)


class GraphUpdateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: EventKind
    event_type: str | None = None          # e.g. "policy_decision", "supply_shock", "regulatory_action"
    occurred_at: datetime
    recorded_at: datetime
    ops: list[GraphOp]
    evidence: list[Evidence] = []
    market_event_id: str | None = None
    produced_by: str                       # translator name, "human", or "engine"
    confidence: float = 1.0                # the translator's own confidence
    user_confidence: float = 1.0           # the reviewer's confidence in the article's changes (Oct 8), 0..1
    ripple: dict[str, float] = {}          # subentity id -> the reviewer's probability its ripple arrives (Oct 9)
    tags: list[str] = []                   # e.g. ["bank-run-like"]; copied into episodes
    mentions: list[str] = []               # text spans the refiner can match, e.g. ["chip capex"]

    def specificity(self) -> Specificity:
        """The lowest specificity over all target ends of all ops."""
        return min((op_specificity(op) for op in self.ops), default=Specificity.SUBENTITY)


def op_confidence(event: GraphUpdateEvent, op: Any) -> float:
    """The reviewer's confidence in one op: its own if set, else the event's (Oct 8). 1.0 changes nothing."""
    c = getattr(op, "confidence", None)
    return float(min(1.0, max(0.0, event.user_confidence if c is None else c)))


TRANSLATOR_NAMES = frozenset({"hand_drawn", "data_feed", "template", "llm", "structured"})


class EventValidationError(ValueError):
    pass


def validate_event(event: GraphUpdateEvent) -> None:
    """§7.2 validation: temp ids are defined before use; structural superentity ops never come
    from translators; hypothetical events may not contain observe_value."""
    defined: set[str] = set()

    def check_ref(ref: str | None, what: str) -> None:
        if ref and ref.startswith(TEMP_PREFIX) and ref not in defined:
            raise EventValidationError(f"{event.id}: {what} uses temp id {ref!r} before it is defined")

    for i, op in enumerate(event.ops):
        if isinstance(op, (ProposeSuperentity, DissolveSuperentity)) and event.produced_by in TRANSLATOR_NAMES:
            raise EventValidationError(f"{event.id}: op {i} ({op.op}) cannot come from a translator")
        if isinstance(op, ObserveValue) and event.kind == EventKind.HYPOTHETICAL:
            raise EventValidationError(f"{event.id}: hypothetical events may not contain observe_value")
        if isinstance(op, (RetireInteraction, RetireEntity)) and event.kind == EventKind.HYPOTHETICAL:
            raise EventValidationError(f"{event.id}: a thesis cannot retire structure; pose the interaction as "
                                       "absent (an interaction-absent hypothesis) instead")
        if isinstance(op, AddEntity):
            if not op.temp_id.startswith(TEMP_PREFIX):
                raise EventValidationError(f"{event.id}: add_entity temp_id must start with 'new:'")
            defined.add(op.temp_id)
        elif isinstance(op, AddSubentity):
            check_ref(op.entity, f"op {i} entity")
            if not op.temp_id.startswith(TEMP_PREFIX):
                raise EventValidationError(f"{event.id}: add_subentity temp_id must start with 'new:'")
            defined.add(op.temp_id)
        for _, t in op_ends(op):
            if isinstance(t, ConcreteTarget):
                check_ref(t.subentity_id, f"op {i}")
            elif t.entity_id:
                check_ref(t.entity_id, f"op {i}")
