"""Working-memory learning: what the world is like now (§8.6).

It runs at two cadences, and every run is one commit to working memory:

- per vetted event (`learn`): the shared process reads the event (any new structure, the values it
  reports, the ripple it should cause), then the fold updates the observed values and the effects of
  their incoming interactions;
- per day: `open_day` predicts the day before its events (yesterday's moves ripple through the
  interactions); `record_day` records every value after them; `close_day` re-estimates the interactions'
  timing (kernels), rescores the hypothesis frontier, expires stale refinements, prunes old data, and
  moves the clock to the end of the day.

It never writes long-term memory. What long-term learning needs from an event (its classifications, the
moves the graph did not explain, the decisions it observed) leaves in a WorkingMemoryRecord.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.kernels import mean_kernel_days
from axelrod_wm.learning.fold import FoldResult
from axelrod_wm.memory.working import RippleJudgment, point_key, ripple_key
from axelrod_wm.model.hypothesis import HypothesisStatus
from axelrod_wm.shared.process import SharedResult

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.learning.consolidate import ConsolidationReport
    from axelrod_wm.repo.mutator import MutationTxn


class WorkingMemoryRecord(BaseModel):
    """What one event's working-memory commit hands to long-term learning."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event_id: str
    shared: SharedResult
    fold: FoldResult
    version: int                       # the state version after the commit
    changeset_id: str | None = None    # None if the event changed nothing
    commit: Any = None                 # the ChangeSet itself
    headline: str | None = None
    proposal_events: list[dict] = []   # hedges this event settled: refinement proposals for review


class WorkingMemoryLearning:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    # -- per event -----------------------------------------------------------------------------
    def learn(self, event: GraphUpdateEvent, now: datetime, processing_day: int | None = None, *,
              headline: str | None = None, proposal_kind: str | None = None, proposal_id: str | None = None,
              vetted_by: str | None = None) -> WorkingMemoryRecord:
        """Read one vetted event and fold it into the current state: one commit to working memory."""
        eng = self.engine
        ctx = eng.context(learn=True, now=now, processing_day=processing_day)
        if headline:
            ctx.notes["headline"] = headline
        if proposal_kind:
            ctx.notes["proposal_kind"] = proposal_kind
        message = f"{event.id} · {headline}" if headline else event.id
        with ctx.mutator.begin(cause=event.id, at=now, process="learn.working", message=message[:160],
                               proposal_id=proposal_id, vetted_by=vetted_by) as txn:
            shared = eng.shared.run(event, ctx, txn, incorporate=False)
            fold = eng.components["folder"].fold(shared.parsed, shared.analysis, eng.wm, ctx, txn)
            # hedged fuzzy ends weigh the event as evidence; one that resolves raises a proposal
            hedged = eng.components["refiner"].weigh_hedges(event, shared.parsed, fold, eng.wm, ctx, txn)
            # what the reviewer said of the ripple, value by value (Oct 9)
            judge_ripple(event, shared, eng.wm, txn)
        cs = eng.mutator.last_changeset
        mine = cs if cs is not None and cs.cause == event.id and cs.process == "learn.working" else None
        return WorkingMemoryRecord(event_id=event.id, shared=shared, fold=fold, version=eng.version,
                                   changeset_id=mine.id if mine is not None else None, commit=mine, headline=headline,
                                   proposal_events=hedged)

    # -- per day -------------------------------------------------------------------------------
    def open_day(self, d: int) -> None:
        """The day's prediction, before its events: yesterday's moves ripple through the interactions,
        so every value has a predicted deviation, observed or not (§8.6.1)."""
        eng = self.engine
        dev = eng.wm.deviations
        at = dev.day_start(d)
        day = dev.date_of(d).isoformat()
        ctx = eng.context(learn=True, now=at, processing_day=d)
        with eng.mutator.begin(f"predict:{day}", at=at, process="day.predict", message=f"Day opens · {day}") as txn:
            eng.components["daily_propagator"].predict(d, eng.wm, ctx, txn)

    def record_day(self, d: int, ctx: ProcessContext) -> dict[str, float]:
        """After the day's events: a point for every value, and each unobserved value's posterior."""
        eng = self.engine
        dev = eng.wm.deviations
        day = dev.date_of(d).isoformat()
        with eng.mutator.begin(f"record:{day}", at=dev.day_end(d), process="day.record",
                               message=f"Day recorded · {day}") as txn:
            return eng.components["daily_propagator"].record(d, eng.wm, ctx, txn)

    def close_day(self, d: int, ctx: ProcessContext, report: ConsolidationReport) -> None:
        """After long-term learning has distilled the day: timing, hypotheses, stale refinements,
        pruning, and the clock. The day's last commit (snapshots freeze whole days at it)."""
        eng = self.engine
        comp = eng.components
        cfg = ctx.config
        wm, ltm = eng.wm, eng.ltm
        dev = wm.deviations
        day = dev.date_of(d).isoformat()
        with ctx.mutator.begin(f"close:{day}", at=ctx.now, process="day.close", message=f"Day closes · {day}") as txn:
            # the interactions' timing (delay, lag, duration), every kernel_update.every_days
            every = max(1, int(cfg.kernel_update.every_days))
            if (d + 1) % every == 0:
                report.kernels_updated = comp["kernel_updater"].update(wm, ltm, ctx, txn)
            # the hypothesis frontier: rescore what today's news touched; expire what has gone stale
            # DECISION: hypotheses are not re-scored during the history replay (§8.13); their VOI needs
            # forecasts, and nothing reads them until the replay ends.
            touched = ctx.notes.get("non_routine_touched") or set()
            if touched and not ctx.initializing and comp.get("hypothesis_scorer") is not None:
                comp["hypothesis_scorer"].rescore_touched(set(touched), wm, ltm, ctx, txn)
            for hid in sorted(wm.hypotheses):
                h = wm.hypotheses[hid]
                if h.status != HypothesisStatus.OPEN:
                    continue
                age = (ctx.now - (h.created_at or h.scored_at)).total_seconds() / 86400.0
                if h.current_value(ctx.now) < 0.01 and age > 4 * h.half_life_days and not h.comovement_id:
                    txn.update("wm.hypotheses", hid, status=HypothesisStatus.EXPIRED)
                    report.hypotheses_expired.append(hid)
            # refinements nobody resolved in time. DECISION (Oct 8): a hedge drawn as soft interactions does not
            # expire: its interactions carry its weight in every forecast, so it ends only by review
            for pid in sorted(wm.pending_refinements):
                pend = wm.pending_refinements[pid]
                if pend.expires_at <= ctx.now and not pend.soft:
                    txn.remove("wm.pending_refinements", pid)
            # ripple judgments whose expected ripple has run its course
            for key in sorted(wm.ripple_judgments):
                j = wm.ripple_judgments[key]
                if d >= j.start_day + len(j.path) - 1:
                    txn.remove("wm.ripple_judgments", key)
            report.pruned_points = reset_and_prune(d, ctx, txn)
            txn.set("wm.clock", dev.day_end(d))
            txn.set("wm.last_processed_day", d)


def judge_ripple(event: GraphUpdateEvent, shared: SharedResult, wm: Any, txn: MutationTxn) -> list[str]:
    """Store the reviewer's weight on each value's ripple (event.ripple: subentity id -> probability it arrives).

    DECISION (Oct 9): the weight is the probability that the ripple reaches the value, given that it reaches the
    values upstream. The daily prediction carries a weighted value's correction downstream through the
    interactions by itself, so a value's stored path is the analysis's expected ripple scaled by the weights of the
    values upstream on its main path; only its own weight is applied to it."""
    if not event.ripple:
        return []
    import numpy as np

    analysis = shared.analysis
    if analysis.result is None:
        return []
    weights = {sid: float(min(1.0, max(0.0, w))) for sid, w in event.ripple.items()}
    day = int(shared.parsed.processing_day)
    out: list[str] = []
    for t in analysis.transmission or []:
        w = weights.get(t.subentity_id)
        if w is None or w >= 1.0 or t.order < 1:
            continue
        upstream = 1.0
        for hop in t.path[:-1]:
            upstream *= weights.get(hop.target_id, 1.0)
        paths = analysis.result.z_of(t.subentity_id)
        if not paths.size:
            continue
        med = np.median(paths, axis=0) * upstream
        key = ripple_key(event.id, t.subentity_id)
        j = RippleJudgment(event_id=event.id, subentity_id=t.subentity_id, weight=w, start_day=day,
                           path=[round(float(x), 5) for x in med], order=int(t.order),
                           via=[h.interaction_id.split(":")[0] for h in t.path])
        if key in wm.ripple_judgments:
            txn.replace("wm.ripple_judgments", j, key=key)
        else:
            txn.add("wm.ripple_judgments", j, key=key)
        out.append(t.subentity_id)
    return out


def reset_and_prune(day: int, ctx: ProcessContext, txn: MutationTxn) -> int:
    """Clear the day's scratch lists, drop unpinned forecasts, and prune activity and deviation points
    older than what any kernel still reads (§8.12 step 10). Returns the number of points pruned."""
    wm = ctx.wm
    dev = wm.deviations
    if wm.fold_accumulators:
        txn.clear("wm.fold_accumulators")
    if wm.episode_buffer:
        txn.clear("wm.episode_buffer")
    if wm.pending_episode_tags:
        txn.clear("wm.pending_episode_tags")
    fl = wm.forecast_layer
    unpinned = [t for t in sorted(fl.by_thesis) if t not in fl.pinned]
    for tid in unpinned:
        txn.remove("wm.forecast_layer.by_thesis", tid)
    if unpinned:
        txn.set("wm.forecast_layer.order", [t for t in fl.order if t not in unpinned])
    # the activity window
    width = int(ctx.config.abduction.window_days)
    for key in sorted(wm.activity_log):
        if wm.activity_log[key].day <= day - width:
            txn.remove("wm.activity_log", key)
    for key in sorted(wm.channel_phi):
        if int(key.rpartition("|")[2]) <= day - width:
            txn.remove("wm.channel_phi", key)
    # deviation points older than history.keep_days
    longest = 0
    min_delay = max(1, int(ctx.config.propagation.min_delay_days))
    for _key, _inter, _s, _t, dyn in wm.graph.channel_items():
        d, l, _lam = mean_kernel_days(dyn.kernel, min_delay)
        longest = max(longest, d + l)
    keep = ctx.config.keep_days(longest)
    cutoff = day - keep
    pruned = 0
    if cutoff >= dev.first_kept_day:
        sids = sorted(wm.graph.subentities)
        for d in range(dev.first_kept_day, cutoff + 1):
            for sid in sids:
                k = point_key(sid, d)
                if k in dev.points:
                    txn.remove("wm.deviations.points", k)
                    pruned += 1
        txn.set("wm.deviations.first_kept_day", cutoff + 1)
    return pruned
