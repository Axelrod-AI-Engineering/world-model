"""Review and the control plane (§7.6, D12)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.graph_update import GraphUpdateEvent, ReweightInteraction
from axelrod_wm.intake.overlap import overlap_guard
from axelrod_wm.intake.refiner import RefinementStep
from axelrod_wm.memory.working import PendingRefinement

if TYPE_CHECKING:
    from axelrod_ingest.contract.bundle import ImportItem
    from axelrod_wm.memory.working import WorkingMemory


class ProposalKind(StrEnum):
    GRAPH_UPDATE = "graph_update"                     # from a market event or a person
    REFINEMENT = "refinement"                         # a pending refinement became concrete
    FRONTIER_PROMOTION = "frontier_promotion"
    SUPERENTITY_ADMISSION = "superentity_admission"
    SUPERENTITY_DISSOLUTION = "superentity_dissolution"
    MISSING_RELATION = "missing_relation"             # suggested by a bound pattern (§8.8)


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    AUTO_APPLIED = "auto_applied"


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ProposalKind
    event: GraphUpdateEvent
    market_event_id: str | None = None
    refinement_steps: list[RefinementStep] = []
    review_reasons: list[str] = []
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    note: str | None = None
    edited_from: GraphUpdateEvent | None = None
    pending: list[PendingRefinement] = []     # fuzzy ops from refinement, stored on approval
    soft_support: dict[str, float] = {}       # interaction generalization support, added on approval
    retires_pending_id: str | None = None     # for REFINEMENT: the pending item this proposal resolves
    subject_id: str | None = None             # co-movement or pattern the proposal is about
    reason: str | None = None                 # why the engine proposed it
    changeset_id: str | None = None           # the ChangeSet its approval produced
    version_after: int | None = None
    world_event: bool = False                 # folded on its day by the update run (§7.6); else a model edit
    needs_review: bool = True                 # from the review policy's assessment
    update_id: str | None = None              # the update run that raised it
    due_day: int | None = None                # world events: the day it belongs to
    late_from: int | None = None              # set when it is folded on a later day (deferred, then approved)
    folded_day: int | None = None             # world events: the day it was folded in


class ReviewRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    needs_review: bool
    reasons: list[str]


class ReviewPolicy(ABC):
    @abstractmethod
    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement: ...


registry("review_policy", ReviewPolicy)

STRUCTURAL_KINDS = {ProposalKind.FRONTIER_PROMOTION, ProposalKind.SUPERENTITY_ADMISSION,
                    ProposalKind.SUPERENTITY_DISSOLUTION, ProposalKind.MISSING_RELATION, ProposalKind.REFINEMENT}


def text_translators(config: Any = None) -> set[str]:
    """The translators that read free text (a person must check what they made)."""
    text = {"llm"}
    if config is not None:
        for kind in ("news", "filing", "analyst"):
            for name, _ in config.translator_chain(kind):
                text.add(name)
    else:
        text.update({"hand_drawn", "template"})
    return text


@register("review_policy", "default")
class DefaultReviewPolicy(ReviewPolicy):
    """Structural change, model structure, text translations, large reweightings, and low
    confidence need a human; everything else applies automatically (D12)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        rev = getattr(config, "review", None)
        self.min_conf = float(getattr(rev, "min_auto_confidence", 0.8))
        self.auto_human = bool(getattr(rev, "auto_approve_human", True))
        self.text_translators = text_translators(config)

    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement:
        ev = proposal.event
        deletes = any(op.op in ("retire_interaction", "retire_entity") for op in ev.ops)
        # DECISION (restructure): a person's own edit applies at once (they are its reviewer), except a
        # deletion, which always waits for a second look
        if ev.produced_by == "human" and self.auto_human and proposal.kind == ProposalKind.GRAPH_UPDATE and not deletes:
            return ReviewRequirement(needs_review=False, reasons=[])
        reasons: list[str] = []
        if any(op.op in ("add_entity", "add_subentity", "add_interaction") for op in ev.ops):
            reasons.append("structural change")
        if deletes:
            reasons.append("deletes structure")
        if proposal.kind in STRUCTURAL_KINDS:
            reasons.append("model structure")
        if ev.produced_by in self.text_translators:
            reasons.append("translated from text")
        for op in ev.ops:
            if isinstance(op, ReweightInteraction):
                inter = wm.graph.interactions.get(op.interaction_id)
                if op.strength > 0.7 or (inter is not None and inter.origin == "construction"):
                    reasons.append("large reweighting")
                    break
        if ev.confidence < self.min_conf:
            reasons.append("low confidence")
        return ReviewRequirement(needs_review=bool(reasons), reasons=reasons)


@register("review_policy", "auto_approve_all")
class AutoApproveAllPolicy(ReviewPolicy):
    """Approves everything; initialization and headless runs use it."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement:
        return ReviewRequirement(needs_review=False, reasons=[])


@register("review_policy", "review_all")
class ReviewAllPolicy(ReviewPolicy):
    """Every change waits for a person, data releases included (the demos use it, so each example ends at the
    human review)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement:
        return ReviewRequirement(needs_review=True, reasons=["every change is reviewed"])


# -- the standards gate (Oct 25) -------------------------------------------------------------------------------
# An imported item applies without a person only when every check below passes. Each check is a small function that
# returns the reason it failed, or None. A check whose data the item does not carry fails closed: the item waits.

GATE_MIN_CONFIDENCE = 0.6
GATE_ALLOWED_OPS = {"observe_value", "change_value", "reweight_interaction", "annotate_interaction"}
GATE_DELETE_OPS = {"retire_interaction", "retire_entity", "dissolve_superentity"}
THIRD_PARTY_SOURCES = {"broker_research", "expert_call", "news", "other"}    # R21: not the company's own, not a regulator's


@dataclass
class ImportContext:
    """What the gate needs to know about the imported item behind a proposal: the item, the items already folded in
    (for the overlapping-views check), the signals the guard held back from them, and the construction origin of each
    id (file stem), which says which company added it."""

    item: ImportItem
    folded: list[ImportItem] = field(default_factory=list)
    held: dict[str, dict[int, str]] = field(default_factory=dict)
    origin: dict[str, str] = field(default_factory=dict)


@dataclass
class GateInput:
    proposal: Proposal
    wm: WorkingMemory
    context: ImportContext | None
    text_translators: set[str]

    @property
    def item(self) -> ImportItem | None:
        return self.context.item if self.context is not None else None


def company_of(graph: Any, origin: dict[str, str], node: str) -> str | None:
    """The company a value or entity belongs to: its owning entity when that is a company, else the company whose
    construction file added it (origin). A shared player (a central bank, a market) belongs to none."""
    sub = graph.subentities.get(node)
    eid = sub.entity_id if sub is not None else node
    for cand in (eid, origin.get(node), origin.get(eid)):
        ent = graph.entities.get(cand) if cand else None
        if ent is not None and ent.kind == "company":
            return cand
    return None


def check_not_structural(g: GateInput) -> str | None:
    ev = g.proposal.event
    ops = {op.op for op in ev.ops}
    if ops & GATE_DELETE_OPS:
        return "deletes structure (D-12)"
    if g.proposal.kind in STRUCTURAL_KINDS or ops - GATE_ALLOWED_OPS:
        return "adds or changes structure: an entity, value, link or group (D-12)"
    return None


def check_not_text(g: GateInput) -> str | None:
    if g.proposal.event.produced_by in g.text_translators:
        return "translated from text"
    return None


def _link_ends(g: GateInput, op: Any) -> tuple[str, str] | None:
    if op.op == "add_interaction":
        a, b = getattr(op.source, "subentity_id", None), getattr(op.target, "subentity_id", None)
        return (a, b) if a and b else None
    if op.op == "reweight_interaction":
        inter = g.wm.graph.interactions.get(op.interaction_id)
        return (inter.source_id, inter.target_id) if inter is not None else None
    return None


def check_cross_company_cited(g: GateInput) -> str | None:
    origin = g.context.origin if g.context is not None else {}
    for op in g.proposal.event.ops:
        ends = _link_ends(g, op)
        if ends is None:
            continue
        a, b = (company_of(g.wm.graph, origin, x) for x in ends)
        if a and b and a != b and not (g.item is not None and g.item.citation.strip()):
            return f"a link between {a} and {b} needs a citation naming the document that establishes it (R20)"
    return None


def check_attributed(g: GateInput) -> str | None:
    item = g.item
    if item is None:
        return "not an imported item: no source document"
    if not item.source.strip() or not (item.document.strip() or (item.url or "").strip()):
        return "does not name its source document (R21)"
    if item.source_type in THIRD_PARTY_SOURCES:
        if not item.publisher.strip():
            return "third-party material without its publisher (R21)"
        if item.basis is None:
            return "third-party material is not marked direct, proxy or context only (R21)"
        if item.basis == "context_only" and item.signals:
            return "context-only material cannot move a value or a link (R21)"
    return None


def check_one_basis(g: GateInput) -> str | None:
    item = g.item
    if item is None:
        return "not an imported item: no signals to check for overlapping views"
    _, warnings = overlap_guard(g.wm.graph, [item], g.context.folded, g.context.held)
    if warnings:
        w = warnings[0]
        return (f"counts {w['total']} through overlapping views ({', '.join(w['compositions'])}) "
                f"({w['scope']} rule, R19)")
    return None


def check_plausible_confident(g: GateInput) -> str | None:
    item = g.item
    if item is None:
        return "not an imported item: no plausibility band"
    if item.plausible is None:
        return "plausibility was not checked"
    if not item.plausible:
        return "outside the extractor's plausibility band"
    ev = g.proposal.event
    low = min([ev.confidence, item.confidence, *[op.confidence for op in ev.ops if op.confidence is not None]])
    if low < GATE_MIN_CONFIDENCE:
        return f"confidence {low:.2f} is below {GATE_MIN_CONFIDENCE}"
    return None


def check_coverage_labelled(g: GateInput) -> str | None:
    if g.item is None or g.item.coverage is None:
        return "coverage is not labelled full or partial (R18)"
    return None


GATE_CHECKS: list[Callable[[GateInput], str | None]] = [
    check_not_structural, check_not_text, check_cross_company_cited, check_attributed, check_one_basis,
    check_plausible_confident, check_coverage_labelled]


@register("review_policy", "standards")
class StandardsPolicy(ReviewPolicy):
    """Applies an imported item without a person only when it meets the construction standards: no structure added or
    deleted, no uncertain link between companies, attributed, one basis, plausible and confident, coverage labelled.
    Anything else waits, with each failed check as a reason. A person's own edit applies at once, except a deletion."""

    actor = "policy:standards"

    def __init__(self, config: Any = None) -> None:
        self.config = config
        self.text = text_translators(config)
        self._lookup: Callable[[str], ImportContext | None] = lambda _id: None

    def bind(self, lookup: Callable[[str], ImportContext | None]) -> None:
        """Say where an imported item's context comes from (market event id -> ImportContext)."""
        self._lookup = lookup

    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement:
        ev = proposal.event
        if (ev.produced_by == "human" and proposal.kind == ProposalKind.GRAPH_UPDATE
                and not {op.op for op in ev.ops} & GATE_DELETE_OPS):
            return ReviewRequirement(needs_review=False, reasons=[])
        ctx = self._lookup(proposal.market_event_id) if proposal.market_event_id else None
        g = GateInput(proposal=proposal, wm=wm, context=ctx, text_translators=self.text)
        reasons = [r for check in GATE_CHECKS if (r := check(g))]
        return ReviewRequirement(needs_review=bool(reasons), reasons=reasons)
