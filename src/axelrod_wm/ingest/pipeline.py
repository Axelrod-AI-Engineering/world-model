"""The ingestion pipeline, end to end (§7.8): translate, refine, propose, review."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from axelrod_wm.events.graph_update import SPECIFICITY_NAMES, op_ends, target_specificity
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.ingest.translators import TranslationContext, TranslationResult
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController
    from axelrod_wm.control.review import Proposal


def op_summary(op: Any) -> str:
    """A short human-readable line for an op (used by traces and views)."""
    kind = op.op
    if kind == "add_entity":
        return f"add entity {op.name}"
    if kind == "add_subentity":
        return f"add {op.name} to {op.entity}"
    if kind == "observe_value":
        return f"observe {_end_label(op.target)} = {op.value:.4g}"
    if kind == "change_value":
        unit = {"relative": "%", "absolute": "", "standardized": " sd"}[str(op.mode)]
        delta = op.delta * 100 if str(op.mode) == "relative" else op.delta
        extra = " (held)" if op.intervention else ""
        return f"change {_end_label(op.target)} {delta:+.3g}{unit}{extra}"
    if kind == "add_interaction":
        return f"{_end_label(op.source)} → {_end_label(op.target)}: {op.label}"
    if kind == "reweight_interaction":
        return f"{'support' if op.supports else 'weaken'} {op.interaction_id} ({op.strength:.2g})"
    if kind == "annotate_interaction":
        return f"note on {op.interaction_id}: {op.note}"
    if kind == "propose_hypothesis":
        return f"hypothesis: {op.hypothesis.statement}"
    if kind == "propose_superentity":
        return f"admit {op.pattern.name}"
    if kind == "dissolve_superentity":
        return f"dissolve {op.pattern_id}"
    return kind


def _end_label(t: Any) -> str:
    if getattr(t, "kind", "") == "concrete":
        return t.subentity_id
    return t.entity_id or t.mention or t.generalization_id or t.attribute_kind or "?"


def op_ends_view(op: Any) -> list[dict]:
    out = []
    for end, t in op_ends(op):
        spec = target_specificity(t)
        ref = t.subentity_id if getattr(t, "kind", "") == "concrete" else (t.entity_id or t.generalization_id or "")
        out.append({"end": end, "level": SPECIFICITY_NAMES[int(spec)], "ref": ref,
                    "mention": getattr(t, "mention", None), "candidates": list(getattr(t, "candidate_entity_ids", []))})
    return out


class IngestionPipeline:
    """Translate, refine, and assess one market event, producing proposals (§7.8). Nothing is applied
    here: the update run folds world events on their day."""

    def __init__(self, controller: WorldModelController) -> None:
        self.controller = controller

    def translate(self, event: MarketEvent, now: datetime) -> TranslationResult:
        """Try the configured translators for the event's kind in order, until one returns events."""
        c = self.controller
        eng = c.engine
        tracer = eng.tracer

        def emit(kind: str, **payload: Any) -> None:
            tracer.emit(Phase.TRANSLATE, kind, refs=[event.id], **payload)

        tctx = TranslationContext(eng.wm, eng.ltm, eng.vocab, now, recent=lambda n: c.applied_events[-n:], emit=emit)
        result: TranslationResult | None = None
        for translator in c.translator_chain(str(event.kind)):
            result = translator.translate(event, tctx)
            if result.events:
                break
        return result or TranslationResult(market_event_id=event.id, events=[], rationale="no translator")

    def ingest(self, event: MarketEvent, now: datetime) -> list[Proposal]:
        with self.controller.engine.tracer.scoped(event.id):
            return self._ingest(event, now)

    def _ingest(self, event: MarketEvent, now: datetime) -> list[Proposal]:
        c = self.controller
        eng = c.engine
        tracer = eng.tracer
        tracer.set_context(sim_time=now, state_version=eng.version)
        c.market_events[event.id] = event
        tracer.emit(Phase.INGEST, "market_event.received", refs=[event.id], id=event.id, kind=str(event.kind),
                    channel=str(event.channel), headline=event.headline, source=event.source,
                    synthetic=event.synthetic, published_at=event.published_at.isoformat(),
                    update_id=event.update_id)
        result = self.translate(event, now)
        c.translations[event.id] = result
        if not result.events:
            c.market_status[event.id] = "no translation"
            return []
        tracer.emit(Phase.TRANSLATE, "translate.result", refs=[event.id] + [e.id for e in result.events],
                    market_event_id=event.id, rationale=result.rationale, spans=[list(s) for s in result.spans],
                    events=[{"id": e.id, "specificity": SPECIFICITY_NAMES[int(e.specificity())],
                             "ops": [{"index": i, "op": op.op, "summary": op_summary(op), "ends": op_ends_view(op)}
                                     for i, op in enumerate(e.ops)]} for e in result.events])
        c.market_status[event.id] = "translated"
        proposals = []
        for ev in result.events:
            ref = c.refine(ev, now)
            c.market_status[event.id] = "refined"
            proposals.append(c.propose("graph_update", ref.event, steps=ref.steps, pending=ref.pending,
                                       soft_support=ref.soft_support, market_event_id=event.id, world=True))
        return proposals
