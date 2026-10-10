"""The shared process: how the model reads any event, real or hypothetical (§8.4).

parse -> classify -> recall -> bind -> prefill -> analyze. Working-memory learning runs it on a vetted
real event (inside its commit); inference runs it on a thesis (writing only to a scratch overlay, the
thesis's branch). Inputs: a graph update event. Output: a SharedResult (the parsed event, its
classifications, what it recalls, the patterns it binds, the prefilled model, and the ripple analysis).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.propagation import ShockInput
from axelrod_wm.engine.interfaces import Analysis, Classification, PrefilledModel, RecallResult
from axelrod_wm.events.graph_update import EventKind
from axelrod_wm.model.serialization import StrSet
from axelrod_wm.model.taxonomy import TaxonomyKind
from axelrod_wm.shared.recognize import InductionResult
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.repo.mutator import MutationTxn


class ParsedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: EventKind
    event_type: str | None
    day: int                                   # day index of occurred_at
    processing_day: int                        # the day being processed; observations and shocks apply on it
    shocks: list[ShockInput]                   # from change_value ops
    observations: list[tuple[str, float, float, datetime]]   # (subentity id, value, noise_sd, at)
    touched_subentity_ids: list[str]
    touched_entity_ids: list[str]
    new_entity_ids: list[str]
    new_interaction_ids: list[str]
    touched_interaction_ids: list[str]         # named by an op, or an in-channel of an observed
                                               # subentity with |phi| >= min_regressor
    tags: list[str] = []
    mentions: list[str] = []
    signature: StrSet = set()                  # filled after classification
    new_subentity_ids: list[str] = []
    change_observations: list[tuple[str, float, float, datetime]] = []  # real change_value: (sid, size, R sd, at)
    occurred_at: datetime | None = None
    market_event_id: str | None = None
    produced_by: str = ""
    temp_map: dict[str, str] = {}              # temp id -> final id
    z_before: dict[str, float] = {}
    max_abs_move: float = 0.0                  # largest standardized move observed or shocked
    annotated_interaction_ids: list[str] = []
    origin_hint: str | None = None             # proposal kind that produced the event, if structural
    retired_interaction_ids: list[str] = []    # deleted from the current graph (restructure)
    retired_entity_ids: list[str] = []
    retired_subentity_ids: list[str] = []

    def to_classify(self) -> list[tuple[TaxonomyKind, str, bool]]:
        """(taxonomy, item id, is_new) for new and touched entities and interactions."""
        out: list[tuple[TaxonomyKind, str, bool]] = []
        new_e = list(self.new_entity_ids)
        for eid in new_e:
            out.append((TaxonomyKind.OBJECT, eid, True))
        for eid in sorted(set(self.touched_entity_ids) - set(new_e)):
            out.append((TaxonomyKind.OBJECT, eid, False))
        new_i = list(self.new_interaction_ids)
        for iid in new_i:
            out.append((TaxonomyKind.INTERACTION, iid, True))
        for iid in sorted(set(self.touched_interaction_ids) - set(new_i)):
            out.append((TaxonomyKind.INTERACTION, iid, False))
        return out

    def is_routine(self) -> bool:
        return self.event_type == "data_release" and self.max_abs_move < 1.0


class SharedResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parsed: ParsedEvent
    classifications: list[Classification]
    recall: RecallResult
    induction: InductionResult
    model: PrefilledModel
    analysis: Analysis


def signature_of(classifications: list[Classification], ltm: LongTermMemory, ctx: ProcessContext,
                 parsed: ParsedEvent | None = None) -> set[str]:
    """Generalization ids on the classification paths whose support exceeds the recall threshold,
    plus etype:<event_type> and one tag:<tag> key per event tag."""
    thr = ctx.recall_threshold
    out: set[str] = set()
    for c in classifications:
        tax = ltm.taxonomy(c.taxonomy)
        for gid in c.path:
            node = tax.nodes.get(gid)
            if node is not None and node.stats.support > thr:
                out.add(gid)
    if parsed is not None:
        if parsed.event_type:
            out.add(f"etype:{parsed.event_type}")
        for t in parsed.tags:
            out.add(f"tag:{t}")
    return out


def build_new_channels(interaction_ids: list[str], ctx: ProcessContext, txn: MutationTxn) -> None:
    """Every interaction has a ChannelState per direction from the moment it is created, warm-started
    at the current day (§6.12). Built after classification, which fills the kernel the op left out."""
    from axelrod_wm.dynamics.daily import ensure_channel_states

    wm = ctx.wm
    for iid in interaction_ids:
        inter = wm.graph.interactions.get(iid)
        if inter is not None:
            ensure_channel_states(inter, wm, ctx, txn)


class SharedProcess:
    def __init__(self, engine: Any, parser: Any, classifier: Any, recaller: Any, inducer: Any,
                 prefiller: Any, analyzer: Any) -> None:
        self.engine = engine
        self.parser = parser
        self.classifier = classifier
        self.recaller = recaller
        self.inducer = inducer
        self.prefiller = prefiller
        self.analyzer = analyzer

    @property
    def ltm(self) -> LongTermMemory:
        return self.engine.ltm

    def run(self, event: GraphUpdateEvent, ctx: ProcessContext, txn: MutationTxn | None, *,
            incorporate: bool = True) -> SharedResult:
        """txn is None for hypothetical events; their new objects go to ctx.overlay. Working-memory
        learning passes incorporate=False: new items get their kind now, and long-term learning adds
        them to the taxonomies when it registers the event."""
        wm = ctx.wm
        parsed = self.parser.parse(event, wm, self.ltm, ctx, txn)
        classifications = [self.classifier.classify(kind, item_id, is_new, ctx, txn, incorporate=incorporate)
                           for kind, item_id, is_new in parsed.to_classify()]
        if txn is not None:
            build_new_channels(parsed.new_interaction_ids, ctx, txn)
        parsed.signature = signature_of(classifications, self.ltm, ctx, parsed)
        recall = self.recaller.recall(parsed, ctx.wm, self.ltm, ctx)
        induction = self.inducer.bind(parsed, recall, ctx.wm, self.ltm, ctx, txn)
        model = self.prefiller.prefill(parsed, recall, induction, ctx.wm, self.ltm, ctx)
        analysis = self.analyzer.analyze(parsed, model, ctx.wm, ctx)
        if analysis.expected_moves:
            ctx.tracer.emit(Phase.ANALYZE, "analyze.done", refs=[event.id] + sorted(analysis.expected_moves),
                            event_id=event.id,
                            expected_moves={k: v.q50 for k, v in sorted(analysis.expected_moves.items())},
                            orders=[{"id": e.subentity_id, "order": e.order, "peak": e.peak, "peak_day": e.peak_day,
                                     "path": [h.interaction_id for h in e.path]} for e in analysis.transmission])
        return SharedResult(parsed=parsed, classifications=classifications, recall=recall,
                            induction=induction, model=model, analysis=analysis)
