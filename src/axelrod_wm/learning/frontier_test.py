"""The correlation frontier tester (§8.7, Figure 3): observe, hold, verify, promote."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.graph_update import AddInteraction, ConcreteTarget, EventKind, GraphUpdateEvent
from axelrod_wm.memory.frontier import (
    CoMovement,
    CoMovementStatus,
    FrontierResult,
    FrontierTester,
    PromotionTest,
    backfilled,
    comovement_pair,
    comovement_statement,
)
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.model.interaction import EdgeDynamics, EdgeType
from axelrod_wm.model.temporal import KernelSpec, gamma_from_mean
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.learning.fold import FoldResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn

registry("frontier", FrontierTester)
registry("promotion_test", PromotionTest)


@register("promotion_test", "threshold")
class ThresholdPromotionTest(PromotionTest):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def passes(self, co: CoMovement, recognition: float, cfg: dict) -> bool:
        total = co.consistent + co.inconsistent
        consistency = co.consistent / total if total else 0.0
        return (co.support > recognition and abs(co.corr.corr()) >= float(cfg["min_corr"])
                and consistency >= float(cfg["min_consistency"]))


def promotion_event(co: CoMovement, ctx: ProcessContext) -> GraphUpdateEvent:
    """FRONTIER_PROMOTION: a learned causal edge with low weight (§8.7 step 4). The kernel has delay
    max(1, lag_days), a lag of one window, and no duration."""
    slope, se = co.response.slope()
    sd = max(0.2, 2.0 * se) if se == se and se != float("inf") else 0.5
    if slope != slope:
        slope = 0.0
    width = int(ctx.config.frontier.window_days)
    kernel = KernelSpec(delay=gamma_from_mean(max(1, co.lag_days)), lag=gamma_from_mean(width), duration=None)
    label = "co-moves with" if co.sign > 0 else "moves against"
    op = AddInteraction(source=ConcreteTarget(subentity_id=co.earlier_id), target=ConcreteTarget(subentity_id=co.later_id),
                        label=label, polarity=1 if slope >= 0 else -1, edge_type=EdgeType.LEARNED_CAUSAL,
                        dynamics=EdgeDynamics(effect=Gaussian(mu=float(slope), sigma=float(sd)), kernel=kernel),
                        existence=Beta(alpha=1.0, beta=3.0))
    return GraphUpdateEvent(id=f"GUE-PROMOTE-{co.id}", kind=EventKind.REAL, event_type="frontier_promotion",
                            occurred_at=ctx.now, recorded_at=ctx.now, ops=[op], produced_by="engine", confidence=0.6)


def connected_pairs(graph: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for inter in graph.active_interactions():
        out.add((inter.source_id, inter.target_id))
        out.add((inter.target_id, inter.source_id))
    return out


@register("frontier", "residual_comovement")
class ResidualCoMovementFrontier(FrontierTester):
    """Pairs an unexplained move in one subentity with an earlier move in another (§8.7)."""

    def __init__(self, config: Any = None, promotion_test: PromotionTest | None = None) -> None:
        self.config = config
        self.promotion_test = promotion_test or ThresholdPromotionTest(config)

    def test(self, fold: FoldResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FrontierResult:
        res = FrontierResult()
        if ctx.initializing or not fold.innovations:
            return res
        cfg = ctx.config.frontier
        w = int(cfg.window_days)
        lags = sorted({int(x) for x in cfg.lag_grid_days})
        dev = wm.deviations
        graph = wm.graph
        t = int(fold.day)
        frontier = ltm.correlation_frontier
        # 1. observe
        movers = []
        for b in sorted(fold.innovations):
            innov = dev.window_innovation(b, t, w)
            if abs(innov) >= float(cfg.min_innovation):
                movers.append((b, innov))
        if not movers:
            return res
        pairs = connected_pairs(graph)
        all_subs = sorted(graph.subentities)
        # DECISION: a source counts only when its history covers the window (both ends have points);
        # otherwise a subentity created during the window would show its whole level as a "move".
        changes: dict[int, dict[str, float]] = {}
        for lag in lags:
            row = {}
            for a in all_subs:
                if dev.z_at(a, t - lag) is None or dev.z_at(a, t - lag - w) is None:
                    continue
                row[a] = dev.window_change(a, t - lag, w)
            changes[lag] = row
        min_move = float(cfg.min_source_move)
        for b, innov in movers:
            best: dict[str, tuple[float, int, int]] = {}
            for lag in lags:
                for a, change in changes[lag].items():
                    if a == b or abs(change) < min_move:
                        continue
                    if (a, b) in pairs or frontier.is_blocked(a, b, ctx.now):
                        continue
                    score = abs(change * innov)
                    if a not in best or score > best[a][0]:
                        best[a] = (score, lag, 1 if change * innov > 0 else -1)
            ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[: int(cfg.max_candidates_per_target)]
            held = set()
            for a, (_score, lag, sign) in ranked:
                self._hold(a, b, lag, sign, t, wm, ltm, ctx, txn, res)
                held.add(a)
            # DECISION: max_candidates_per_target caps how many new pairs are logged per target, not which
            # known pairs can be verified. A live entry for this target whose source moved by at least
            # min_source_move at the entry's stored lag is held (and verified) even outside the top k.
            for co in sorted(frontier.entries.values(), key=lambda c: c.id):
                if co.later_id != b or co.earlier_id in held or co.status != CoMovementStatus.HOLDING:
                    continue
                change = changes.get(co.lag_days, {}).get(co.earlier_id)
                if change is None:
                    if dev.z_at(co.earlier_id, t - co.lag_days) is None or \
                            dev.z_at(co.earlier_id, t - co.lag_days - w) is None:
                        continue
                    change = dev.window_change(co.earlier_id, t - co.lag_days, w)
                if abs(change) < min_move or frontier.is_blocked(co.earlier_id, b, ctx.now):
                    continue
                self._hold(co.earlier_id, b, co.lag_days, 1 if change * innov > 0 else -1, t, wm, ltm, ctx, txn, res)
                held.add(co.earlier_id)
        return res

    def _hold(self, a: str, b: str, lag: int, sign: int, t: int, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn, res: FrontierResult) -> None:
        cfg = ctx.config.frontier
        rec = ctx.recognition
        dev = wm.deviations
        w = int(cfg.window_days)
        entries = "ltm.correlation_frontier.entries"
        co = ltm.correlation_frontier.get(a, b)
        if co is not None and co.status in (CoMovementStatus.DECAYED, CoMovementStatus.PROMOTED):
            co = None
        if co is None:
            # 2. hold: a new entry takes the lag with the largest product, its sign, and support 1
            cm_id = txn.new_id("CM")
            h_id = txn.new_id("H")
            co = CoMovement(id=cm_id, earlier_id=a, later_id=b, lag_days=lag, sign=sign, support=1.0, consistent=0,
                            first_seen=ctx.now, last_seen=ctx.now, last_verified_day=t, hypothesis_id=h_id,
                            ambiguous_direction=lag == 0, verified_days=[t], logged_day=t)
            co = backfilled(co, dev, t, w, int(cfg.backfill_days))
            x, y, r = comovement_pair(dev, a, b, lag, t, w)
            co.corr.push(x, y)
            co.response.push(x, r)
            txn.add(entries, co)
            txn.add("wm.hypotheses", Hypothesis(id=h_id, kind=HypothesisKind.INTERACTION_PRESENT,
                                                statement=comovement_statement(wm.graph, a, b, sign), source_id=a,
                                                target_id=b, probability=1.0 / (1.0 + rec + 1.0), scored_at=ctx.now,
                                                half_life_days=float(ctx.config.hypotheses.half_life_days),
                                                origin=Origin.INFERENCE, comovement_id=cm_id))
            res.logged.append(cm_id)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.logged", refs=[cm_id, a, b], comovement_id=cm_id, earlier=a,
                            later=b, support=1.0, lag=lag, sign=sign)
            return
        if co.status != CoMovementStatus.HOLDING:
            return
        # 3. verify, at most once per evidence_spacing_days, at the stored lag
        spacing = int(cfg.evidence_spacing_days)
        if co.last_verified_day is not None and t - co.last_verified_day < spacing:
            txn.update(entries, co.id, last_seen=ctx.now)
            return
        x, y, r = comovement_pair(dev, co.earlier_id, co.later_id, co.lag_days, t, w)
        fields: dict[str, Any] = {"corr": co.corr.pushed(x, y), "response": co.response.pushed(x, r),
                                  "last_seen": ctx.now, "last_verified_day": t, "seeded": False,
                                  "verified_days": (list(co.verified_days) + [t])[-20:]}
        product_sign = 1 if x * y > 0 else -1
        if abs(x) >= float(cfg.min_source_move) and product_sign == co.sign:
            fields["consistent"] = co.consistent + 1
            fields["support"] = co.support + 1.0
            fields["passed_days"] = (list(co.passed_days) + [t])[-20:]
        else:
            fields["inconsistent"] = co.inconsistent + 1
            fields["support"] = max(0.0, co.support - 1.0)
        res.tested.append(co.id)
        txn.update(entries, co.id, **fields)
        co = ltm.correlation_frontier.entries[co.id]
        # 6. its hypothesis
        if co.hypothesis_id and co.hypothesis_id in wm.hypotheses:
            txn.update("wm.hypotheses", co.hypothesis_id, probability=co.support / (co.support + rec + 1.0))
        ctx.tracer.emit(Phase.FRONTIER, "frontier.verified", refs=[co.id, co.earlier_id, co.later_id], comovement_id=co.id,
                        support=round(co.support, 3), lag=co.lag_days, sign=co.sign, corr=round(co.corr.corr(), 3),
                        consistent=co.consistent, inconsistent=co.inconsistent, passed="consistent" in fields)
        # 4. promote
        cfg_d = {"min_corr": cfg.min_corr, "min_consistency": cfg.min_consistency}
        if self.promotion_test.passes(co, rec, cfg_d):
            ev = promotion_event(co, ctx)
            txn.update(entries, co.id, status=CoMovementStatus.PROMOTION_PROPOSED)
            res.proposals.append(ev.id)
            res.proposal_events.append({"kind": "frontier_promotion", "event": ev.model_dump(mode="json"),
                                        "reason": f"support {co.support:.1f}, corr {co.corr.corr():.2f}",
                                        "subject_id": co.id})
            ctx.tracer.emit(Phase.FRONTIER, "frontier.promotion_proposed", refs=[co.id, co.earlier_id, co.later_id],
                            comovement_id=co.id, support=round(co.support, 3), lag=co.lag_days, sign=co.sign,
                            ambiguous_direction=co.ambiguous_direction)


def decay_frontier(day: int, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                   txn: MutationTxn) -> list[str]:
    """Decay at consolidation (§8.7 step 5): entries not seen for more than evidence_spacing_days lose
    one day of half-life. Seeded entries are exempt until their first verification. Returns the ids
    that became DECAYED."""
    from axelrod_wm.model.hypothesis import HypothesisStatus

    cfg = ctx.config.frontier
    dev = wm.deviations
    factor = 0.5 ** (1.0 / float(cfg.half_life_days))
    spacing = int(cfg.evidence_spacing_days)
    out = []
    for cid, co in sorted(ltm.correlation_frontier.entries.items()):
        if co.status != CoMovementStatus.HOLDING or co.seeded:
            continue
        if day - dev.day_of(co.last_seen) <= spacing:
            continue
        support = co.support * factor
        if support < float(cfg.remove_below):
            txn.update("ltm.correlation_frontier.entries", cid, support=support, status=CoMovementStatus.DECAYED)
            if co.hypothesis_id and co.hypothesis_id in wm.hypotheses:
                txn.update("wm.hypotheses", co.hypothesis_id, status=HypothesisStatus.EXPIRED)
            out.append(cid)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.decayed", refs=[cid, co.earlier_id, co.later_id], comovement_id=cid,
                            support=round(support, 3), lag=co.lag_days, sign=co.sign)
        else:
            txn.update("ltm.correlation_frontier.entries", cid, support=support)
            if co.hypothesis_id and co.hypothesis_id in wm.hypotheses:
                rec = ctx.recognition
                txn.update("wm.hypotheses", co.hypothesis_id, probability=support / (support + rec + 1.0))
    return out
