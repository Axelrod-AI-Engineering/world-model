"""Review and the control plane (§7.6, D12)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.graph_update import GraphUpdateEvent, ReweightInteraction
from axelrod_wm.ingest.refiner import RefinementStep
from axelrod_wm.memory.working import PendingRefinement

if TYPE_CHECKING:
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


@register("review_policy", "default")
class DefaultReviewPolicy(ReviewPolicy):
    """Structural change, model structure, text translations, large reweightings, and low
    confidence need a human; everything else applies automatically (D12)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        rev = getattr(config, "review", None)
        self.min_conf = float(getattr(rev, "min_auto_confidence", 0.8))
        self.auto_human = bool(getattr(rev, "auto_approve_human", True))
        text = {"llm"}
        if config is not None:
            for kind in ("news", "filing", "analyst"):
                for name, _ in config.translator_chain(kind):
                    text.add(name)
        else:
            text.update({"hand_drawn", "template"})
        self.text_translators = text

    def assess(self, proposal: Proposal, wm: WorkingMemory) -> ReviewRequirement:
        ev = proposal.event
        if ev.produced_by == "human" and self.auto_human and proposal.kind == ProposalKind.GRAPH_UPDATE:
            return ReviewRequirement(needs_review=False, reasons=[])
        reasons: list[str] = []
        if any(op.op in ("add_entity", "add_subentity", "add_interaction") for op in ev.ops):
            reasons.append("structural change")
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
