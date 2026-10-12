"""Staged review (Oct 8 restructure): the person checks learning at its end, not its start.

An event's whole learning (intake's result, working memory, long-term memory) runs on a throwaway copy of the
state. The review shows everything that copy would commit:

- items: each operation of the event (new or retired structure, a moved or observed value, a collapse or an
  expansion), which the reviewer can select or deselect one by one; an item that needs another (a value of a
  new entity, an interaction to a new value) goes with it;
- the event's own moves, and the ripple they set off by order (first, second, third, ...) with the path each
  one travels, so the reviewer can judge the second- and third-order adjustments as well as the first;
- what the fold learned (values and the effects that feed them), and what long-term memory would learn
  (kinds, statistics, entity memories, the frontier, superentity support) and propose;
- the stages of the flowchart with their concrete input and output, and the staged graph itself, so the
  canvas can draw the new items with their own outline.

Deselecting items re-stages the event without them. Approving commits only the selected items, through the
ordinary path (controller.approve with `keep`).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterator

from pydantic import BaseModel, ConfigDict, Field

from axelrod_wm.events.graph_update import op_confidence as op_confidence_of
from axelrod_wm.flows import WORLD_MODEL, flow_path
from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.working import WorkingMemory
from axelrod_wm.model.ids import TEMP_PREFIX, strip_temp
from axelrod_wm.repo.ledger import EventLedger, LedgerKind
from axelrod_wm.repo.mutator import ChangeSet
from axelrod_wm.repo.snapshots import MemoryBackend, SnapshotStore, empty_state
from axelrod_wm.trace import RecordingTracer

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.repo.review import Proposal


class StagedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int                       # the operation's index in the proposal's event
    op: str
    action: str                      # add, retire, move, observe, collapse, expand, reweight, note, hypothesis
    what: str                        # entity, subentity, interaction, value, superentity, hypothesis
    label: str
    refs: list[str] = []             # what it makes or touches on the staged graph
    requires: list[int] = []         # items it cannot go without
    selected: bool = True
    confidence: float = 1.0          # the reviewer's confidence in it (its own, or the article's)
    own_confidence: bool = False     # True if set for this change alone
    hedge: str | None = None         # a fuzzy end's soft interaction: the hedge's key
    probability: float | None = None # its candidate's probability in the hedge


class Adjustment(BaseModel):
    """A value the event moves: its own move (order 0) or the ripple at first, second, third order."""

    model_config = ConfigDict(extra="forbid")

    subentity_id: str
    name: str
    order: int
    effect: float                    # sd at the horizon (order 0: the size of the move)
    peak: float
    peak_day: int = 0
    arrives_day: int = 0
    path: list[str] = []             # value names along the most significant path
    via: list[str] = []              # the interactions along it
    hops: list[str] = []             # the values along it, after the first (ids)
    weight: float = 1.0              # the reviewer's probability that it arrives (Oct 9)


class Learned(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str                        # value or effect
    ref: str
    name: str
    before: float | None
    after: float
    unit: str = ""


class StageIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    title: str
    input: str
    output: str
    ran: list[str] = []              # flowchart nodes this event reached
    status: str = "done"             # done, waiting (the review), next, skipped


class StagedReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    kind: str
    status: str
    event_id: str
    headline: str | None = None
    source: str | None = None
    world_event: bool
    keep: list[int]
    items: list[StagedItem]
    stages: list[StageIO]
    moves: list[Adjustment] = []
    ripple: list[Adjustment] = []
    learned: list[Learned] = []
    lessons: list[str] = []
    raises: list[dict] = []
    commits: list[dict] = []
    marks: dict[str, Any] = {}
    graph: dict | None = None
    version: int
    error: str | None = None
    article: dict | None = None      # the article it came from: text, source, and which phrase asked for which op
    recalled: list[dict] = []        # past days and superentities recall found, with their attention
    adjusted: list[dict] = []        # effects prefill adjusted from what followed those days
    pending: list[dict] = []         # ends that stay fuzzy: stored on approval, until a later article resolves them
    hedges: list[dict] = []          # hedges already held that this event moves (Oct 8)
    resolves: dict | None = None     # a refinement: the hedge it settles, with the evidence that carried its winner
    manual: dict | None = None       # a backend user's own addition (Oct 9): their reason, in place of an article
    confidence: float = 1.0          # the reviewer's confidence in the article's changes (Oct 8)
    evidence: dict | None = None     # a frontier promotion: the checks the pair passed, each with its articles
    bounds: dict = {}                # the checks' bounds from the config (Oct 9): commit_posterior, recognition
    paths: dict | None = Field(default=None, exclude=True)   # the transmission grid's source; served by /api/paths


# ---------------------------------------------------------------------------------------------------
# the sandbox: a copy of the state, throwaway storage, and a private tracer
# ---------------------------------------------------------------------------------------------------
class _NoHash:
    def update(self, *_: Any) -> str:
        return "staged"

    def full(self, *_: Any) -> str:
        return "staged"


def _copy_state(engine: Any) -> tuple[Any, Any]:
    """A fresh copy of the live state. The serialized state is kept per version, so staging the same proposal
    again (after each change to the selection) pays only for parsing it."""
    key = (engine.version, engine.state_hash)
    cached = getattr(engine, "_staging_copy", None)
    if cached is None or cached[0] != key:
        cached = (key, engine.wm.model_dump_json(), engine.ltm.model_dump_json())
        engine._staging_copy = cached
    return WorkingMemory.model_validate_json(cached[1]), LongTermMemory.model_validate_json(cached[2])


@contextmanager
def sandbox(engine: Any) -> Iterator[RecordingTracer]:
    """Run engine calls on a copy of the state. Commits go to a throwaway ledger and traces to a private
    tracer; on exit the live state, storage, ledger, tracer, and version come back untouched."""
    names = ("wm", "ltm", "version", "state_hash", "storage", "ledger", "snapshots", "tracer", "hasher")
    saved = {k: getattr(engine, k) for k in names}
    last = engine.mutator.last_changeset
    wm, ltm = _copy_state(engine)
    storage = MemoryBackend()
    tracer = RecordingTracer(run_id="staged")
    engine.storage = storage
    engine.ledger = EventLedger(storage, clock=lambda: engine.wm.clock, version=lambda: engine.version)
    engine.ledger.next_seq = saved["ledger"].next_seq
    engine.snapshots = SnapshotStore(storage, engine.ledger, empty_state)
    engine.hasher = _NoHash()
    engine.tracer = tracer
    engine.wm, engine.ltm = wm, ltm
    try:
        yield tracer
    finally:
        for k, v in saved.items():
            setattr(engine, k, v)
        engine.mutator.last_changeset = last
        engine.mutator._active = None


# ---------------------------------------------------------------------------------------------------
# items and their dependencies
# ---------------------------------------------------------------------------------------------------
def _requires(event: GraphUpdateEvent) -> dict[int, list[int]]:
    """Which ops each op needs: the op that defines a temp id it uses."""
    defines: dict[str, int] = {}
    for i, op in enumerate(event.ops):
        if op.op in ("add_entity", "add_subentity"):
            defines[op.temp_id] = i
    out: dict[int, list[int]] = {}
    for i, op in enumerate(event.ops):
        used = []
        if op.op == "add_subentity" and op.entity.startswith(TEMP_PREFIX):
            used.append(op.entity)
        for end in ("source", "target"):
            t = getattr(op, end, None)
            if t is not None and getattr(t, "kind", "") == "concrete" and t.subentity_id.startswith(TEMP_PREFIX):
                used.append(t.subentity_id)
        out[i] = sorted({defines[u] for u in used if u in defines and defines[u] != i})
    return out


def closure(event: GraphUpdateEvent, keep: list[int] | None) -> list[int]:
    """The kept ops, minus any whose requirements are not all kept."""
    n = len(event.ops)
    kept = set(range(n)) if keep is None else {i for i in keep if 0 <= i < n}
    req = _requires(event)
    changed = True
    while changed:
        changed = False
        for i in sorted(kept):
            if any(r not in kept for r in req.get(i, [])):
                kept.discard(i)
                changed = True
    return sorted(kept)


def subset(event: GraphUpdateEvent, keep: list[int]) -> GraphUpdateEvent:
    return event.model_copy(update={"ops": [event.ops[i] for i in keep]})


def with_confidence(event: GraphUpdateEvent, confidence: float | None = None,
                    op_confidence: dict[int, float | None] | None = None,
                    ripple: dict[str, float | None] | None = None) -> GraphUpdateEvent:
    """The event with the reviewer's confidences (Oct 8): the article's, and any change's own (by op index; None
    clears it, so the change follows the article again); and the probability each value's ripple arrives (Oct 9;
    None clears it, so the ripple arrives as the analysis expects)."""
    upd: dict[str, Any] = {}
    if ripple:
        weights = dict(event.ripple)
        for sid, w in ripple.items():
            if w is None or float(w) >= 1.0:
                weights.pop(sid, None)
            else:
                weights[sid] = float(max(0.0, w))
        upd["ripple"] = dict(sorted(weights.items()))
    if confidence is not None:
        upd["user_confidence"] = float(min(1.0, max(0.0, confidence)))
    if op_confidence:
        ops = list(event.ops)
        for i, c in op_confidence.items():
            if 0 <= int(i) < len(ops):
                ops[int(i)] = ops[int(i)].model_copy(update={"confidence": None if c is None else float(min(1.0, max(0.0, c)))})
        upd["ops"] = ops
    return event.model_copy(update=upd) if upd else event


def _names(event: GraphUpdateEvent, wm: Any) -> dict[str, str]:
    """Display names for ids and temp ids the event uses."""
    g = wm.graph
    out: dict[str, str] = {}
    ent_names: dict[str, str] = {}
    for op in event.ops:
        if op.op == "add_entity":
            ent_names[op.temp_id] = op.name
            out[op.temp_id] = op.name
    for op in event.ops:
        if op.op == "add_subentity":
            out[op.temp_id] = op.name
    for sid, s in g.subentities.items():
        out.setdefault(sid, s.name)
    for eid, e in g.entities.items():
        out.setdefault(eid, e.name)
    return out


def _end(t: Any, names: dict[str, str]) -> str:
    if getattr(t, "kind", "") == "concrete":
        return names.get(t.subentity_id, t.subentity_id)
    return t.mention or t.entity_id or t.generalization_id or "?"


def _item(i: int, op: Any, names: dict[str, str], wm: Any, ltm: Any) -> StagedItem:
    g = wm.graph
    k = op.op
    if k == "add_entity":
        return StagedItem(index=i, op=k, action="add", what="entity", label=f"New entity: {op.name}")
    if k == "add_subentity":
        owner = names.get(op.entity, op.entity)
        return StagedItem(index=i, op=k, action="add", what="subentity", label=f"New value: {owner} · {op.name} ({op.unit})")
    if k == "add_interaction":
        sign = "+" if op.polarity > 0 else "−"
        if op.hedge:
            pk = op.existence.mean() if op.existence is not None else None
            return StagedItem(index=i, op=k, action="hedge", what="interaction", hedge=op.hedge, probability=pk,
                              label=f"Fuzzy candidate: {_end(op.source, names)} → {_end(op.target, names)} ({op.label}, {sign})"
                                    + (f" · {pk:.0%}" if pk is not None else ""))
        return StagedItem(index=i, op=k, action="add", what="interaction",
                          label=f"New interaction: {_end(op.source, names)} → {_end(op.target, names)} ({op.label}, {sign})")
    if k == "change_value":
        unit = {"relative": "%", "absolute": "", "standardized": " sd"}[str(op.mode)]
        delta = op.delta * 100 if str(op.mode) == "relative" else op.delta
        return StagedItem(index=i, op=k, action="move", what="value",
                          label=f"Move {_end(op.target, names)} {delta:+.3g}{unit}")
    if k == "observe_value":
        sid = getattr(op.target, "subentity_id", "")
        unit = g.subentities[sid].unit if sid in g.subentities else ""
        return StagedItem(index=i, op=k, action="observe", what="value",
                          label=f"Observe {_end(op.target, names)} = {op.value:.4g} {unit}".rstrip())
    if k == "retire_entity":
        e = g.entities.get(op.entity_id)
        return StagedItem(index=i, op=k, action="retire", what="entity", refs=[op.entity_id],
                          label=f"Retire {e.name if e else op.entity_id}, with its values and interactions")
    if k == "retire_interaction":
        it = g.interactions.get(op.interaction_id)
        said = (f"{names.get(it.source_id, it.source_id)} → {names.get(it.target_id, it.target_id)} ({it.label})"
                if it else op.interaction_id)
        return StagedItem(index=i, op=k, action="retire", what="interaction", refs=[op.interaction_id],
                          label=f"Retire interaction {said}")
    if k == "propose_superentity":
        members = sorted(set(op.bindings.values()))
        said = ", ".join(names.get(m, m) for m in members)
        return StagedItem(index=i, op=k, action="collapse", what="superentity", refs=[op.pattern.id, *members],
                          label=f"Collapse {said} into “{op.pattern.name}”")
    if k == "dissolve_superentity":
        pat = ltm.object_generalizations.patterns.get(op.pattern_id)
        return StagedItem(index=i, op=k, action="expand", what="superentity", refs=[op.pattern_id],
                          label=f"Expand “{pat.name if pat else op.pattern_id}” into its constituents")
    if k == "reweight_interaction":
        it = g.interactions.get(op.interaction_id)
        said = (f"{names.get(it.source_id, it.source_id)} → {names.get(it.target_id, it.target_id)} ({it.label})"
                if it else op.interaction_id)
        return StagedItem(index=i, op=k, action="reweight", what="interaction", refs=[op.interaction_id],
                          label=f"{'Strengthen' if op.supports else 'Weaken'} the belief in {said}")
    if k == "annotate_interaction":
        return StagedItem(index=i, op=k, action="note", what="interaction", refs=[op.interaction_id],
                          label=f"Note on {op.interaction_id}: {op.note}")
    if k == "propose_hypothesis":
        return StagedItem(index=i, op=k, action="hypothesis", what="hypothesis",
                          label=f"Hypothesis: {op.hypothesis.statement}")
    return StagedItem(index=i, op=k, action=k, what="", label=k)


# ---------------------------------------------------------------------------------------------------
# staging
# ---------------------------------------------------------------------------------------------------
def stage(ctl: WorldModelController, proposal_id: str, keep: list[int] | None = None,
          with_graph: bool = True, confidence: float | None = None,
          op_confidence: dict[int, float | None] | None = None,
          ripple: dict[str, float | None] | None = None) -> StagedReview:
    """Run the proposal's learning on a copy of the state, with only the `keep` ops, and report every change
    it would make. Nothing live changes."""
    from axelrod_wm.control.controller import ControllerError

    with ctl.lock:
        p = ctl.proposals.get(proposal_id)
        if p is None:
            raise ControllerError(f"unknown proposal {proposal_id}")
        eng = ctl.engine
        live_wm, live_ltm = eng.wm, eng.ltm
        full = with_confidence(p.event, confidence, op_confidence, ripple)
        kept = closure(full, keep)
        event = subset(full, kept)
        names = _names(full, live_wm)
        req = _requires(full)
        items = []
        for i, op in enumerate(full.ops):
            it = _item(i, op, names, live_wm, live_ltm)
            it.requires = req.get(i, [])
            it.selected = i in kept
            it.confidence = round(op_confidence_of(full, op), 4)
            it.own_confidence = getattr(op, "confidence", None) is not None
            items.append(it)
        me = ctl.market_events.get(p.market_event_id) if p.market_event_id else None
        version = eng.version
        effects_applied = set(ctl._effects_applied)
        error = None
        result = None
        report = None
        changesets: list[ChangeSet] = []
        graph = None
        staged_wm = staged_ltm = None
        with sandbox(eng) as tracer:
            try:
                if event.ops:
                    result, report = _run(ctl, p, event, me)
            except Exception as exc:              # a staged run that fails is shown, not raised
                error = f"{type(exc).__name__}: {exc}"
            finally:
                ctl._effects_applied = effects_applied
            for entry in eng.ledger.storage.read_ledger(0):
                if entry.kind == LedgerKind.CHANGESET:
                    changesets.append(ChangeSet.model_validate(entry.payload))
            staged_wm, staged_ltm = eng.wm, eng.ltm
            evs = tracer.since(0)
            kinds = {e.kind for e in evs}
            if with_graph:
                from axelrod_wm.api.views import build_graph_view

                graph = build_graph_view(staged_wm, staged_ltm, ctl, version).model_dump(mode="json")
        review = _review(ctl, p, kept, items, result, report, changesets, live_wm, live_ltm, staged_wm, staged_ltm,
                         kinds, me, graph, version, error)
        for a in review.ripple:
            a.weight = float(full.ripple.get(a.subentity_id, 1.0))
        review.bounds = {"commit_posterior": float(eng.config.refinement.commit_posterior),
                         "recognition": int(eng.config.thresholds.recognition)}
        review.article = _article(ctl, p, me)
        review.pending = _pending(p, live_wm)
        review.hedges = _hedges(live_wm, staged_wm)
        review.resolves = _resolves(p, live_wm)
        if p.event.event_type == "manual_addition":
            review.manual = {"note": (p.event.evidence[0].excerpt if p.event.evidence else None) or "",
                             "by": p.decided_by or "a backend user"}
        review.confidence = round(float(event.user_confidence), 4)
        review.evidence = _evidence(ctl, p)
        review.recalled, review.adjusted = _recall(ctl, evs, live_wm, live_ltm)
        return review


def hedge_view(pend: Any, g: Any) -> dict:
    """A hedged fuzzy end in words (Oct 8): what it says, and each candidate's probability, with the open reserve."""
    op = pend.op
    ends = pend.ends or [pend.end]

    def name(cid: str) -> str:
        if cid == "__open__":
            return "one not in the graph yet"
        parts = []
        for c in cid.split("|"):
            parts.append(g.entities[c].name if c in g.entities else g.subentities[c].name if c in g.subentities else c)
        return " → ".join(parts) if len(parts) > 1 else parts[0]

    def said(end: str) -> str:
        t = getattr(op, "target" if end == "subject" else end, None)
        if getattr(t, "kind", "") == "concrete":
            return g.subentities[t.subentity_id].name if t.subentity_id in g.subentities else t.subentity_id
        return f"“{getattr(t, 'mention', None) or getattr(t, 'attribute_kind', None) or 'an end'}”"

    if hasattr(op, "source") and hasattr(op, "target"):
        label = f"{said('source')} → {said('target')} ({getattr(op, 'label', '')})"
    else:
        label = said("subject")
    post = pend.posterior()
    cands = [{"id": c, "name": name(c), "p": round(v, 4)} for c, v in sorted(post.items(), key=lambda kv: (kv[0] == "__open__", -kv[1]))]
    return {"id": pend.id, "key": pend.key, "label": label, "ends": ends, "soft": pend.soft, "support": pend.support,
            "status": pend.status, "candidates": cands}


def _pending(p: Proposal, wm: Any) -> list[dict]:
    """The proposal's fuzzy ends: each a hedge over its candidates, stored on approval."""
    out = []
    for pend in p.pending:
        v = hedge_view(pend, wm.graph)
        # the older fields the review reads: the candidates with a score each
        v["end"] = pend.end
        v["reached"] = str(pend.node_id)
        v["candidates"] = [{**c, "score": c["p"]} for c in v["candidates"]]
        out.append(v)
    return out


def _resolves(p: Proposal, wm: Any) -> dict | None:
    """For a refinement: the hedge it settles, and every check that moved it, oldest first."""
    pend = wm.pending_refinements.get(p.retires_pending_id or "")
    if str(p.kind) != "refinement" or pend is None:
        return None
    v = hedge_view(pend, wm.graph)
    names = {c["id"]: c["name"] for c in v["candidates"]}
    winner = max((c for c in v["candidates"] if c["id"] != "__open__"), key=lambda c: c["p"], default=None)
    v["winner"] = winner
    v["checks"] = [{"kind": ck.kind, "candidate": names.get(ck.candidate or "", ck.candidate), "weight": ck.weight,
                    "confidence": ck.confidence, "headline": ck.headline, "date": ck.at.date().isoformat(),
                    "p": (ck.posterior or {}).get(winner["id"]) if winner else None} for ck in pend.checks]
    return v


def _hedges(live_wm: Any, wm: Any) -> list[dict]:
    """How the event moves the hedges already held: each candidate's probability before and after, the evidence,
    and whether one now passes the bound (a resolution proposal follows)."""
    if wm is None:
        return []
    out = []
    for pid, after in sorted(wm.pending_refinements.items()):
        before = live_wm.pending_refinements.get(pid)
        if before is None or (after.alpha == before.alpha and after.status == before.status):
            continue
        v = hedge_view(after, wm.graph)
        prev = before.posterior()
        for c in v["candidates"]:
            c["before"] = round(prev.get(c["id"], 0.0), 4)
        # DECISION (Oct 9): new checks by identity, not by count (the stored list keeps only the newest 20)
        seen = {(ck.at, ck.event_id, ck.kind, ck.candidate) for ck in before.checks}
        new = [ck for ck in after.checks if (ck.at, ck.event_id, ck.kind, ck.candidate) not in seen]
        names = {c["id"]: c["name"] for c in v["candidates"]}
        v["evidence"] = [{"kind": ck.kind, "candidate": names.get(ck.candidate or "", ck.candidate), "weight": ck.weight,
                          "confidence": ck.confidence, "headline": ck.headline} for ck in new]
        v["resolves"] = after.status == "resolution_proposed" and before.status != "resolution_proposed"
        out.append(v)
    return out


def _article(ctl: WorldModelController, p: Proposal, me: Any) -> dict | None:
    """The article a proposal came from, with the spans of its text that asked for each operation."""
    if me is None:
        return None
    tr = ctl.translations.get(me.id)
    text = f"{me.headline}\n{me.body}" if me.body else me.headline
    return {"id": me.id, "headline": me.headline, "body": me.body, "source": me.source, "kind": str(me.kind),
            "published_at": me.published_at.isoformat(), "text": text,
            "spans": [list(sp) for sp in (getattr(tr, "spans", None) or [])],
            "rationale": getattr(tr, "rationale", "") or "", "full_text": getattr(me, "full_text", "") or ""}


def _evidence(ctl: WorldModelController, p: Proposal) -> dict | None:
    """For a frontier promotion, the articles behind it: at each spaced check the pair passed, the articles that moved
    the earlier value and those that reported the later one, inside the windows the check compared."""
    if str(p.kind) != "frontier_promotion" or not p.subject_id:
        return None
    eng = ctl.engine
    co = eng.ltm.correlation_frontier.entries.get(p.subject_id)
    if co is None:
        return None
    dev = eng.wm.deviations
    g = eng.wm.graph
    w = int(eng.config.frontier.window_days)
    touching: list[tuple[int, str, Any]] = []        # (day, which end, market event)
    for q in ctl.proposals.values():
        me = ctl.market_events.get(q.market_event_id) if q.market_event_id else None
        if me is None or str(q.status) not in ("approved", "auto_applied") or q.id == p.id:
            continue
        for op in q.event.ops:
            sid = getattr(getattr(op, "target", None), "subentity_id", None)
            if sid in (co.earlier_id, co.later_id):
                touching.append((dev.day_of(me.published_at), "earlier" if sid == co.earlier_id else "later", me))
                break

    def art(me: Any) -> dict:
        return {"id": me.id, "headline": me.headline, "source": me.source, "date": me.published_at.date().isoformat()}

    checks = []
    # DECISION (Oct 9): only the checks the pair passed; the day it was first seen is not a check. Entries from before
    # passed_days was kept fall back to every verified day after the first
    days = co.passed_days or [d for d in co.verified_days if d != (co.logged_day if co.logged_day is not None
                                                                     else min(co.verified_days, default=None))]
    for d in sorted(set(days)):
        before = [art(me) for (t, end, me) in touching if end == "earlier" and d - co.lag_days - w < t <= d - co.lag_days]
        after = [art(me) for (t, end, me) in touching if end == "later" and d - w < t <= d]
        if before and after:
            checks.append({"date": dev.day_start(d).date().isoformat(), "earlier": before[-2:], "later": after[-1:]})
    name = lambda sid: g.subentities[sid].name if sid in g.subentities else sid  # noqa: E731
    first = None
    if co.logged_day is not None:
        first = {"date": dev.day_start(co.logged_day).date().isoformat()}
    return {"earlier": name(co.earlier_id), "later": name(co.later_id), "lag_days": co.lag_days,
            "sign": co.sign, "corr": round(co.corr.corr(), 3), "support": round(co.support, 2), "checks": checks,
            "consistent": co.consistent, "inconsistent": co.inconsistent, "first_seen": first,
            "needed": int(eng.config.thresholds.recognition)}


def _recall(ctl: WorldModelController, evs: list[Any], wm: Any, ltm: Any) -> tuple[list[dict], list[dict]]:
    """What recall found (past days, superentities) and what prefill adjusted from them, in words."""
    eps = ltm.prior_states.episodes
    pats = ltm.object_generalizations.patterns
    g = wm.graph

    def headline_of(ep: Any) -> str:
        for gid in ep.trigger_event_ids:
            me = ctl.market_events.get(gid.removeprefix("GUE-"))
            if me is not None:
                return me.headline
        kinds = [t.replace("_", " ") for t in ep.event_types if t != "data_release"] or ["data releases"]
        return "a past day: " + ", ".join(dict.fromkeys(kinds))

    recalled, adjusted = [], []
    for e in evs:
        if e.kind == "recall.result":
            for x in e.payload.get("episodes", []):
                ep = eps.get(x["id"])
                if ep is not None:
                    recalled.append({"kind": "day", "id": ep.id, "day": ep.day.isoformat(), "label": headline_of(ep),
                                     "attention": x["attention"]})
            for x in e.payload.get("patterns", []):
                pat = pats.get(x["id"])
                if pat is not None:
                    recalled.append({"kind": "superentity", "id": pat.id, "label": pat.name, "attention": x["attention"]})
        elif e.kind == "prefill.adjusted":
            it = g.interactions.get(e.payload.get("interaction_id"))
            name = (f"{g.subentities[it.source_id].name} → {g.subentities[it.target_id].name}"
                    if it is not None and it.source_id in g.subentities and it.target_id in g.subentities
                    else e.payload.get("interaction_id"))
            adjusted.append({"interaction_id": e.payload.get("interaction_id"), "name": name,
                             "before": e.payload.get("effect_before"), "after": e.payload.get("effect_after"),
                             "from": [eps[a].day.isoformat() for a in e.payload.get("analog_ids", []) if a in eps]})
    recalled.sort(key=lambda r: -r["attention"])
    adjusted.sort(key=lambda a: -abs((a["after"] or 0) - (a["before"] or 0)))
    return recalled[:6], adjusted


def _run(ctl: WorldModelController, p: Proposal, event: GraphUpdateEvent, me: Any) -> tuple[Any, Any]:
    """What approval would do, on the sandbox: a world event's learning on its day (and the day's close, so
    long-term memory's daily distillation shows too); a model edit's structural commit."""
    eng = ctl.engine
    if not p.world_event:
        with eng.mutator.begin(cause=p.id, at=ctl.now, process="structural", proposal_id=p.id,
                               message=f"Staged {p.id}") as txn:
            ctl._apply_effects(p, txn)
            eng.structural.apply(event, ctl.now, str(p.kind))
        return None, None
    dev = eng.wm.deviations
    d = int(eng.wm.last_processed_day) + 1
    run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
    if run is None or run.predicted_day != d:
        eng.learning.open_day(d)
    published = me.published_at if me is not None else p.created_at
    now: datetime = max(published, dev.day_start(d))
    with eng.tracer.scoped(ctl.scope_of(p)):
        with eng.mutator.begin(cause=p.id, at=now, process="review", proposal_id=p.id,
                               message=f"Review effects of {p.id}") as txn:
            ctl._apply_effects(p, txn)
        result = eng.learning.run(event, now, d, headline=me.headline if me is not None else None,
                                  proposal_id=p.id, vetted_by="staged")
    report = eng.learning.close_day(d, dev.day_end(d))
    return result, report


def _review(ctl: WorldModelController, p: Proposal, kept: list[int], items: list[StagedItem], result: Any,
            report: Any, changesets: list[ChangeSet], live_wm: Any, live_ltm: Any, wm: Any, ltm: Any,
            kinds: set[str], me: Any, graph: dict | None, version: int, error: str | None) -> StagedReview:
    lg, sg = live_wm.graph, wm.graph if wm is not None else live_wm.graph

    def sub_name(sid: str) -> str:
        s = sg.subentities.get(sid) or lg.subentities.get(sid)
        if s is None:
            return sid
        e = sg.entities.get(s.entity_id) or lg.entities.get(s.entity_id)
        owner = e.name if e else s.entity_id
        # "Delta jet fuel cost" already names Delta; "Headline CPI" does not name Inflation
        said = {w.lower() for w in s.name.replace("(", " ").split()}
        if said & {w.lower() for w in owner.split()[:1]} or said & {a.lower() for a in (e.aliases if e else [])}:
            return s.name
        return f"{owner} · {s.name}"

    # the graph: new, retired, and moved items
    new_ents = sorted(set(sg.entities) - set(lg.entities))
    new_subs = sorted(set(sg.subentities) - set(lg.subentities))
    live_ints = {i.id for i in lg.active_interactions()}
    staged_ints = {i.id for i in sg.active_interactions()}
    new_ints = sorted(staged_ints - live_ints)
    retired_ints = sorted(live_ints - staged_ints)
    retired_ents = sorted(set(lg.entities) - set(sg.entities)
                          | {e for e in lg.entities if e in sg.entities and not getattr(sg.entities[e], "active", True)})
    lp = live_ltm.object_generalizations.patterns
    sp = ltm.object_generalizations.patterns if ltm is not None else lp
    collapsed = sorted(pid for pid, pat in sp.items() if str(pat.status) == "admitted"
                       and (pid not in lp or str(lp[pid].status) != "admitted"))
    expanded = sorted(pid for pid, pat in lp.items() if str(pat.status) == "admitted"
                      and pid in sp and str(sp[pid].status) != "admitted")
    # each item's refs on the staged graph
    temp_map = dict(getattr(getattr(result, "shared", None), "parsed", None).temp_map) if result is not None else {}
    for it in items:
        op = p.event.ops[it.index]
        if op.op in ("add_entity", "add_subentity"):
            final = temp_map.get(op.temp_id) or strip_temp(op.temp_id)
            it.refs = [final] if final in sg.entities or final in sg.subentities else []
        elif op.op == "add_interaction":
            ends = [temp_map.get(getattr(t, "subentity_id", ""), getattr(t, "subentity_id", ""))
                    for t in (op.source, op.target)]
            it.refs = [i for i in new_ints if [sg.interactions[i].source_id, sg.interactions[i].target_id] == ends]
        elif op.op in ("change_value", "observe_value"):
            sid = getattr(op.target, "subentity_id", "")
            it.refs = [temp_map.get(sid, sid)]
    # the event's moves and the ripple by order
    moves: list[Adjustment] = []
    ripple: list[Adjustment] = []
    if result is not None:
        parsed = result.shared.parsed
        for sh in parsed.shocks:
            moves.append(Adjustment(subentity_id=sh.subentity_id, name=sub_name(sh.subentity_id), order=0,
                                    effect=round(float(sh.size), 4), peak=round(float(sh.size), 4)))
        for sid, value, _noise, _at in parsed.observations:
            before = parsed.z_before.get(sid)
            after = wm.deviations.z(sid, int(wm.last_processed_day)) if wm is not None else None
            moves.append(Adjustment(subentity_id=sid, name=sub_name(sid), order=0,
                                    effect=round(float(after if after is not None else 0.0), 4),
                                    peak=round(float((after or 0.0) - (before or 0.0)), 4)))
        for t in result.shared.analysis.transmission or []:
            if t.order < 1:
                continue
            path = [sub_name(t.path[0].source_id)] + [sub_name(h.target_id) for h in t.path] if t.path else []
            ripple.append(Adjustment(subentity_id=t.subentity_id, name=sub_name(t.subentity_id), order=int(t.order),
                                     effect=round(float(t.effect), 4), peak=round(float(t.peak), 4),
                                     peak_day=int(t.peak_day), arrives_day=int(t.arrives_day), path=path,
                                     via=[h.interaction_id.split(":")[0] for h in t.path],
                                     hops=[h.target_id for h in t.path]))
        ripple.sort(key=lambda a: (a.order, -abs(a.peak)))
    # what the fold learned
    learned: list[Learned] = []
    if result is not None:
        for sid in result.fold.updated_subentities:
            s1 = sg.subentities.get(sid)
            s0 = lg.subentities.get(sid)
            if s1 is None:
                continue
            learned.append(Learned(kind="value", ref=sid, name=sub_name(sid),
                                   before=round(float(s0.posterior.summary().q50), 4) if s0 is not None else None,
                                   after=round(float(s1.posterior.summary().q50), 4), unit=s1.unit))
        for iid in result.fold.updated_interactions:
            i1 = sg.interactions.get(iid)
            i0 = lg.interactions.get(iid)
            if i1 is None:
                continue
            learned.append(Learned(kind="effect", ref=iid,
                                   name=f"{sub_name(i1.source_id)} → {sub_name(i1.target_id)}",
                                   before=round(float(i0.forward.effect.mean()), 4) if i0 is not None else None,
                                   after=round(float(i1.forward.effect.mean()), 4)))
    # evidence for or against a link moves the belief that it exists
    if wm is not None:
        for iid, i1 in sg.interactions.items():
            i0 = lg.interactions.get(iid)
            if i0 is not None and i1.active and abs(float(i1.existence.mean()) - float(i0.existence.mean())) > 1e-4:
                learned.append(Learned(kind="existence", ref=iid,
                                       name=f"{sub_name(i1.source_id)} → {sub_name(i1.target_id)}",
                                       before=round(float(i0.existence.mean()), 3),
                                       after=round(float(i1.existence.mean()), 3)))
    lessons = _lessons(changesets, live_wm, live_ltm, wm, ltm, sub_name)
    raises = []
    for pe in list(getattr(result, "proposal_events", []) or []) + list(getattr(report, "proposal_events", []) or []):
        ev = pe.get("event")
        ops = ev.ops if hasattr(ev, "ops") else (ev or {}).get("ops", [])
        raises.append({"kind": str(pe.get("kind")), "reason": pe.get("reason", ""), "ops": len(ops)})
    commits = [{"process": cs.process, "memory": cs.memory, "changes": len(cs.changes), "message": cs.message}
               for cs in changesets if cs.process not in ("day.predict", "day.record", "day.close")]
    marks = {"new": new_ents + new_subs + new_ints, "retired": retired_ents + retired_ints,
             "collapsed": collapsed, "expanded": expanded,
             "orders": {a.subentity_id: a.order for a in sorted(moves + ripple, key=lambda a: -a.order)},
             "learned": [x.ref for x in learned]}
    stages = _stages(p, kept, items, result, moves, ripple, learned, lessons, raises, changesets, kinds, me, error)
    return StagedReview(proposal_id=p.id, kind=str(p.kind), status=str(p.status), event_id=p.event.id,
                        headline=me.headline if me is not None else (p.reason or (items[0].label if items else None)),
                        source=me.source if me is not None else None,
                        world_event=p.world_event, keep=kept, items=items, stages=stages, moves=moves, ripple=ripple,
                        learned=learned, lessons=lessons, raises=raises, commits=commits, marks=marks, graph=graph,
                        version=version, error=error,
                        paths=_grid_source(result, ctl))


def _lessons(changesets: list[ChangeSet], live_wm: Any, live_ltm: Any, wm: Any, ltm: Any, sub_name: Any) -> list[str]:
    """What long-term memory would learn, in words."""
    if ltm is None:
        return []
    out: list[str] = []
    touched: dict[str, set[str]] = {}
    for cs in changesets:
        if cs.process in ("day.predict", "day.record", "day.close"):
            continue
        for ch in cs.changes:
            touched.setdefault(ch.collection, set()).add(ch.id)
    g0, g1 = live_wm.graph, wm.graph

    def item_name(iid: str) -> str:
        if iid in g1.entities or iid in g0.entities:
            return (g1.entities.get(iid) or g0.entities[iid]).name
        it = g1.interactions.get(iid) or g0.interactions.get(iid)
        if it is not None:
            short = lambda sid: (g1.subentities.get(sid) or g0.subentities.get(sid)).name  # noqa: E731
            return f"{short(it.source_id)} → {short(it.target_id)}"
        p = ltm.object_generalizations.patterns.get(iid)
        return p.name if p is not None else iid

    stats: list[str] = []
    for tax_name, col in (("object", "ltm.object_generalizations.taxonomy.nodes"),
                          ("interaction", "ltm.interaction_generalizations.taxonomy.nodes")):
        t0 = live_ltm.taxonomy(tax_name).nodes
        t1 = ltm.taxonomy(tax_name).nodes
        for gid in sorted(touched.get(col, set())):
            n1, n0 = t1.get(gid), t0.get(gid)
            if n1 is None:
                continue
            if n0 is None:
                parent = t1.get(n1.parent_id).name if getattr(n1, "parent_id", None) in t1 else "the root"
                out.append(f"A new kind, “{n1.name}”, splits off under “{parent}”")
                continue
            gained = [m for m in n1.instance_ids if m not in n0.instance_ids]
            lost = [m for m in n0.instance_ids if m not in n1.instance_ids]
            if gained:
                out.append(f"Kind “{n1.name}” gains {', '.join(item_name(m) for m in gained)}")
            if lost:
                out.append(f"Kind “{n1.name}” loses {', '.join(item_name(m) for m in lost)}")
            if not gained and not lost:
                stats.append(n1.name)
    if stats:
        out.append(f"Statistics update along {', '.join(dict.fromkeys(stats))}")
    p0, p1 = live_ltm.object_generalizations.patterns, ltm.object_generalizations.patterns
    for pid in sorted(touched.get("ltm.object_generalizations.patterns", set())):
        a, b = p0.get(pid), p1.get(pid)
        if b is None:
            continue
        if a is None:
            said = "admitted" if str(b.status) == "admitted" else f"recorded as a {b.status}"
            out.append(f"Superentity “{b.name}” is {said}")
        elif str(a.status) != str(b.status):
            out.append(f"Superentity “{b.name}”: {a.status} → {b.status}")
        elif float(b.support) - float(a.support) >= 0.5:      # a count; daily decay is not a lesson
            out.append(f"Superentity “{b.name}” gains support ({float(a.support):.1f} → {float(b.support):.1f})")
    mems = sorted(touched.get("ltm.entity_memories", set()))
    for m in mems:
        mem1, mem0 = ltm.entity_memories.get(m), live_ltm.entity_memories.get(m)
        new = (mem1.decisions[len(mem0.decisions):] if mem0 is not None else mem1.decisions) if mem1 is not None else []
        if new:
            from axelrod_wm.inference.voi import context_bucket
            from axelrod_wm.learning.fold import native_scale
            from axelrod_wm.memory.entity_memory import action_of

            for d in new:
                sub = g1.subentities.get(d.subentity_id) or g0.subentities.get(d.subentity_id)
                act = action_of(d.change, native_scale(sub)) if sub is not None else "decided"
                parts = [k.split(">") for k in context_bucket(d.context).split("&") if ">" in k]
                when = ("when " + ", ".join(f"{sub_name(sid)} was {'above' if sign.startswith('+') else 'below'} "
                                            "normal" for sid, sign in parts)) if parts else "in a neutral context"
                out.append(f"{item_name(m)}'s entity memory records a decision: it {act} "
                           f"{sub.name if sub is not None else d.subentity_id} {when}")
        else:
            out.append(f"{item_name(m)}'s entity memory gains an entry")
    fr0, fr1 = live_ltm.correlation_frontier.entries, ltm.correlation_frontier.entries
    new_pairs = [e for e in touched.get("ltm.correlation_frontier.entries", set()) if e in fr1 and e not in fr0]
    if new_pairs:
        out.append(f"The correlation frontier logs {len(new_pairs)} new co-movement pair(s), not yet causal")
    failed: list[str] = []
    for eid in sorted(touched.get("ltm.correlation_frontier.entries", set())):
        a, b = fr0.get(eid), fr1.get(eid)
        if a is None or b is None:
            continue
        when = "the same day" if b.lag_days == 0 else f"{b.lag_days} days later"
        if b.consistent > a.consistent:
            out.append(f"The co-movement {sub_name(b.earlier_id)} → {sub_name(b.later_id)} ({when}) gains strength: "
                       f"it passes another check (support {a.support:.1f} → {b.support:.1f}, correlation "
                       f"{a.corr.corr():.2f} → {b.corr.corr():.2f}); it is still a correlation, not a cause")
        elif b.inconsistent > a.inconsistent:
            failed.append(sub_name(b.earlier_id))
    if failed:
        out.append(f"{len(failed)} rival co-movement(s) fail their check and lose support (from "
                   f"{', '.join(failed)})")
    ex = [e for e in touched.get("ltm.prior_states.explanations", set())]
    if ex:
        out.append("The explanation of what was learned is stored with the prior states")
    return out


def _stages(p: Proposal, kept: list[int], items: list[StagedItem], result: Any, moves: list[Adjustment],
            ripple: list[Adjustment], learned: list[Learned], lessons: list[str], raises: list[dict],
            changesets: list[ChangeSet], kinds: set[str], me: Any, error: str | None) -> list[StageIO]:
    f = WORLD_MODEL
    ran = set(flow_path(f, kinds)) | {"event", "translate"} | ({"refine"} if p.refinement_steps else set())
    ran |= {n.id for n in f.nodes if n.kind == "decision" and n.id.startswith("q_")}   # every check runs; its answer varies
    adds = [it for it in items if it.selected and it.action == "add"]
    rets = [it for it in items if it.selected and it.action == "retire"]
    sel = [it for it in items if it.selected]
    orders = sorted({a.order for a in ripple})
    if adds:
        ran.add("classify")
    if p.world_event:
        intake_in = f"“{me.headline}” ({me.source})" if me is not None else "a market event"
    else:
        intake_in = "A backend user's edit" if p.event.produced_by == "human" else f"A proposal from learning ({p.kind})"
    intake_out = f"{len(p.event.ops)} operation(s)" + (
        f", {len(p.refinement_steps)} refinement step(s) from kinds to values" if p.refinement_steps else "") + (
        f", {len(p.pending)} fuzzy end(s) hedged across their candidates" if p.pending else "")

    def count(what: str, xs: list[StagedItem]) -> int:
        return sum(1 for x in xs if x.what == what)

    bits = []
    for what, word in (("entity", "entities"), ("subentity", "values"), ("interaction", "interactions")):
        if count(what, adds):
            bits.append(f"+{count(what, adds)} {word}")
        if count(what, rets):
            bits.append(f"−{count(what, rets)} {word}")
    if any(it.action == "collapse" for it in sel):
        bits.append("a collapse")
    if any(it.action == "expand" for it in sel):
        bits.append("an expansion")
    if moves:
        bits.append(f"{len(moves)} move(s) by the event")
    if ripple:
        bits.append(f"a ripple to {len(ripple)} value(s), orders {orders[0]}–{orders[-1]}")
    if learned:
        bits.append(f"{len(learned)} value(s) or effect(s) learned by the fold")
    working_out = "; ".join(bits) or "no change to working memory"
    lt_out = "; ".join(lessons[:3]) + (f"; and {len(lessons) - 3} more" if len(lessons) > 3 else "") if lessons else \
        "nothing new for long-term memory"
    if raises:
        lt_out += f"; raises {len(raises)} proposal(s) for later review"
    n_changes = sum(len(cs.changes) for cs in changesets if cs.process not in ("day.predict", "day.record", "day.close"))
    decided = str(p.status) not in ("pending", "deferred")
    out = [
        StageIO(phase="intake", title=f.phase("intake").title, input=intake_in, output=intake_out,
                ran=[n for n in ("event", "translate", "refine") if n in ran]),
        StageIO(phase="working", title=f.phase("working").title,
                input=f"{len(sel)} of {len(items)} operation(s) selected", output=working_out,
                ran=[n.id for n in f.nodes if n.phase == "working" and n.id in ran] or ["parse"]),
        StageIO(phase="long_term", title=f.phase("long_term").title,
                input="classified items, unexplained moves, observed decisions", output=lt_out,
                ran=[n.id for n in f.nodes if n.phase == "long_term" and n.id in ran] or ["kinds", "explain"]),
        StageIO(phase="review", title=f.phase("review").title, input=f"{n_changes} staged change(s)",
                output=f"{p.status}" if decided else "waiting for you: approve all, some, or none",
                ran=["check"], status="done" if decided else "waiting"),
        StageIO(phase="commit", title=f.phase("commit").title, input="the approved selection",
                output="committed" if decided and str(p.status) in ("approved", "auto_applied") else
                "after approval: a commit to working memory and one to long-term memory",
                status="done" if decided else "next"),
    ]
    if error:
        out[1].output = f"the staged run failed: {error}"
    return out


def format_review(r: StagedReview) -> str:
    """A staged review as text: the stages with their input and output, then every change."""
    order_name = {1: "first", 2: "second", 3: "third"}
    out = [f"{r.proposal_id} · {r.headline or r.event_id} · {r.status}"]
    if r.error:
        out.append(f"  staged run failed: {r.error}")
    for st in r.stages:
        if st.status == "skipped":
            continue
        out.append(f"  {st.title}: {st.input} → {st.output}")
    if r.article:
        out.append(f"  Article: “{r.article['headline']}” ({r.article['source']})")
        if r.article.get("rationale"):
            out.append(f"    {r.article['rationale']}")
    out.append("  Items:")
    for it in r.items:
        out.append(f"    [{'x' if it.selected else ' '}] {it.label}" + (
            f"  (needs {', '.join(str(i + 1) for i in it.requires)})" if it.requires else ""))
    for pd in r.pending:
        out.append(f"  Pending: {pd['label']}; candidates " + ", ".join(f"{c['name']} {c['score']:.2f}"
                                                                     for c in pd["candidates"]))
    if r.moves:
        out.append("  The event moves:")
        out += [f"    {a.name} {a.effect:+.2f} sd" for a in r.moves]
    if r.ripple:
        out.append("  The ripple:")
        for a in r.ripple:
            out.append(f"    {order_name.get(a.order, f'{a.order}th')} order: {a.name} {a.peak:+.2f} sd at its peak "
                       f"(day {a.peak_day}) via {' → '.join(a.path)}")
    if r.recalled:
        out.append("  Recalled: " + "; ".join(f"{x['label']}" + (f" ({x['day']})" if x.get("day") else "")
                                           + f" {x['attention']:.2f}" for x in r.recalled[:4]))
    for a in r.adjusted[:6]:
        out.append(f"  Adjusted from what followed: {a['name']} {a['before']:+.2f} → {a['after']:+.2f}")
    if len(r.adjusted) > 6:
        out.append(f"  … and {len(r.adjusted) - 6} more effects adjusted")
    if r.learned:
        out.append("  The fold learns:")
        for x in r.learned:
            before = f"{x.before:.3g}" if x.before is not None else "new"
            what = {"effect": "effect of ", "existence": "existence of "}.get(x.kind, "")
            out.append(f"    {what}{x.name}: {before} → {x.after:.3g} {x.unit}".rstrip())
    if r.lessons:
        out.append("  Long-term memory:")
        out += [f"    {x}" for x in r.lessons]
    if r.raises:
        out.append("  Raises for later review: " + "; ".join(f"{x['kind']} ({x['reason']})" for x in r.raises))
    return "\n".join(out)


__all__ = ["Adjustment", "Learned", "StageIO", "StagedItem", "StagedReview", "closure", "format_review", "sandbox", "stage", "subset"]


def _grid_source(result: Any, ctl: Any) -> dict | None:
    """The transmission grid's source for a staged event (inference/paths.py), from the analysis the staging ran."""
    an = getattr(getattr(result, "shared", None), "analysis", None)
    if an is None or an.result is None or not an.shocked:
        return None
    from axelrod_wm.inference.paths import source_of

    return source_of(an.shocked, an.channels, an.result.z_of, an.horizon_days, an.transmission_all,
                     int(ctl.engine.config.propagation.min_delay_days))
