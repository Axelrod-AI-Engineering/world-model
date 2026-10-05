"""The correlation frontier tester (§8.7, Figure 3): observe, hold, verify, promote."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from axelrod_wm.core.distributions import Beta, Gaussian
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.core.interaction import EdgeDynamics, EdgeType
from axelrod_wm.core.temporal import KernelSpec, gamma_from_mean
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
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.learning import FoldResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

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
    """FRONTIER_PROMOTION: a learned causal edge with low weight (§8.7 step 4)."""
    slope, se = co.response.slope()
    sd = max(0.2, 2.0 * se) if se == se and se != float("inf") else 0.5
    if slope != slope:
        slope = 0.0
    step_days = ctx.step_days
    kernel = KernelSpec(delay=gamma_from_mean(max(co.lag_steps, 0) * step_days), lag=gamma_from_mean(step_days),
                        duration=None)
    label = "co-moves with" if co.sign > 0 else "moves against"
    op = AddInteraction(source=ConcreteTarget(subentity_id=co.earlier_id), target=ConcreteTarget(subentity_id=co.later_id),
                        label=label, polarity=1 if slope >= 0 else -1, edge_type=EdgeType.LEARNED_CAUSAL,
                        dynamics=EdgeDynamics(effect=Gaussian(mu=float(slope), sigma=float(sd)), kernel=kernel),
                        existence=Beta(alpha=1.0, beta=3.0))
    return GraphUpdateEvent(id=f"GUE-PROMOTE-{co.id}", kind=EventKind.REAL, event_type="frontier_promotion",
                            occurred_at=ctx.now, recorded_at=ctx.now, ops=[op], produced_by="engine", confidence=0.6)


@register("frontier", "residual_comovement")
class ResidualCoMovementFrontier(FrontierTester):
    def __init__(self, config: Any = None, promotion_test: PromotionTest | None = None) -> None:
        self.config = config
        self.promotion_test = promotion_test or ThresholdPromotionTest(config)

    def test(self, fold: FoldResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn) -> FrontierResult:
        res = FrontierResult()
        if ctx.initializing or not fold.innovations:
            return res
        cfg = ctx.config.frontier
        w, L = int(cfg.window_steps), int(cfg.max_lag_steps)
        dev = wm.deviations
        graph = wm.graph
        t = fold.step
        today = ctx.now.date()
        movers = []
        for b in sorted(fold.innovations):
            innov = dev.window_innovation(b, t, w)
            if abs(innov) >= float(cfg.min_innovation):
                movers.append((b, innov))
        all_subs = sorted(graph.subentities)
        for b, innov in movers:
            best: dict[str, tuple[float, int, int]] = {}
            for lag in range(0, L + 1):
                for a in all_subs:
                    if a == b:
                        continue
                    change = dev.window_change(a, t - lag, w)
                    if abs(change) < float(cfg.min_source_move):
                        continue
                    if graph.interaction_between(a, b) or ltm.frontier.is_blocked(a, b, ctx.now):
                        continue
                    score = abs(change * innov)
                    sign = 1 if change * innov > 0 else -1
                    if a not in best or score > best[a][0]:
                        best[a] = (score, lag, sign)
            ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[: int(cfg.max_candidates_per_target)]
            for a, (score, lag, sign) in ranked:
                self._hold(a, b, lag, sign, t, today, wm, ltm, ctx, txn, res)
        return res

    def _hold(self, a: str, b: str, lag: int, sign: int, t: int, today: Any, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn, res: FrontierResult) -> None:
        cfg = ctx.config.frontier
        rec = ctx.recognition
        dev = wm.deviations
        co = ltm.frontier.get(a, b)
        if co is not None and co.status in (CoMovementStatus.DECAYED, CoMovementStatus.PROMOTED):
            co = None
        if co is None:
            cm_id = txn.new_id("CM")
            h_id = txn.new_id("H")
            co = CoMovement(id=cm_id, earlier_id=a, later_id=b, lag_steps=lag, sign=sign, support=1.0, consistent=0,
                            first_seen=ctx.now, last_seen=ctx.now, last_episode_day=today, hypothesis_id=h_id,
                            ambiguous_direction=lag == 0)
            co = backfilled(co, dev, t, int(cfg.window_steps), int(cfg.backfill_steps))
            txn.add("frontier", co)
            txn.add("hypotheses", Hypothesis(id=h_id, kind=HypothesisKind.INTERACTION_PRESENT,
                                             statement=comovement_statement(wm.graph, a, b, sign), source_id=a, target_id=b,
                                             probability=1.0 / (1.0 + rec + 1.0), scored_at=ctx.now,
                                             half_life_days=float(ctx.config.hypotheses.half_life_days),
                                             origin=Origin.INFERENCE, comovement_id=cm_id))
            res.logged.append(cm_id)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.logged", refs=[cm_id, a, b], comovement_id=cm_id, earlier=a,
                            later=b, support=1.0, lag=lag, sign=sign)
            return
        if co.status != CoMovementStatus.HOLDING:
            return
        x, y, r = comovement_pair(dev, co.earlier_id, co.later_id, co.lag_steps, t, int(cfg.window_steps))
        fields: dict[str, Any] = {"corr": co.corr.pushed(x, y), "response": co.response.pushed(x, r), "last_seen": ctx.now}
        if co.last_episode_day != today:
            support = co.support
            if abs(lag - co.lag_steps) <= 1 and sign == co.sign:
                fields["consistent"] = co.consistent + 1
                support = co.support + 1.0
            else:
                fields["inconsistent"] = co.inconsistent + 1
                support = max(0.0, co.support - 1.0)
            fields["support"] = support
            fields["last_episode_day"] = today
            fields["seeded"] = False
            fields["verified_days"] = list(co.verified_days) + [today]
            res.tested.append(co.id)
        txn.update("frontier", co.id, **fields)
        co = ltm.frontier.entries[co.id]
        if co.hypothesis_id and co.hypothesis_id in wm.hypotheses:
            txn.update("hypotheses", co.hypothesis_id, probability=co.support / (co.support + rec + 1.0))
        ctx.tracer.emit(Phase.FRONTIER, "frontier.verified", refs=[co.id, co.earlier_id, co.later_id], comovement_id=co.id,
                        support=round(co.support, 3), lag=co.lag_steps, sign=co.sign, corr=round(co.corr.corr(), 3),
                        consistent=co.consistent, inconsistent=co.inconsistent)
        cfg_d = {"min_corr": cfg.min_corr, "min_consistency": cfg.min_consistency}
        if self.promotion_test.passes(co, rec, cfg_d):
            ev = promotion_event(co, ctx)
            txn.update("frontier", co.id, status=CoMovementStatus.PROMOTION_PROPOSED)
            res.proposals.append(ev.id)
            res.proposal_events.append({"kind": "frontier_promotion", "event": ev.model_dump(mode="json"),
                                        "reason": f"support {co.support:.1f}, corr {co.corr.corr():.2f}",
                                        "subject_id": co.id})
            ctx.tracer.emit(Phase.FRONTIER, "frontier.promotion_proposed", refs=[co.id, co.earlier_id, co.later_id],
                            comovement_id=co.id, support=round(co.support, 3), lag=co.lag_steps, sign=co.sign,
                            ambiguous_direction=co.ambiguous_direction)


def decay_frontier(wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn,
                   since: Any) -> list[str]:
    """Decay at consolidation (§8.7 step 5). Returns the ids that became DECAYED."""
    from axelrod_wm.core.hypothesis import HypothesisStatus

    cfg = ctx.config.frontier
    out = []
    for cid, co in sorted(ltm.frontier.entries.items()):
        if co.status != CoMovementStatus.HOLDING:
            continue
        if co.seeded:
            continue
        if since is not None and co.last_seen.date() > since:
            continue
        start = co.last_seen.date() if since is None else max(since, co.last_seen.date())
        days = max((ctx.now.date() - start).days, 0)
        support = co.support * 0.5 ** (days / float(cfg.half_life_days))
        if support < float(cfg.remove_below):
            txn.update("frontier", cid, support=support, status=CoMovementStatus.DECAYED)
            if co.hypothesis_id and co.hypothesis_id in wm.hypotheses:
                txn.update("hypotheses", co.hypothesis_id, status=HypothesisStatus.EXPIRED)
            out.append(cid)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.decayed", refs=[cid, co.earlier_id, co.later_id], comovement_id=cid,
                            support=round(support, 3), lag=co.lag_steps, sign=co.sign)
        elif abs(support - co.support) > 1e-12:
            txn.update("frontier", cid, support=support)
    return out

