"""Hypotheses and value of information (§8.11, D4)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from axelrod_wm.dynamics.propagation import Channel, Propagator, ShockInput
from axelrod_wm.dynamics.regressors import build_system, graph_channels
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.memory.entity_memory import action_of
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec, gamma_from_mean
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn

BUCKET_Z = 0.75
SENSITIVITY_TTL_DAYS = 7.0


class _FrozenHistory:
    """Read-through memo of a DeviationHistory for a stretch of work during which it cannot change (one
    consolidation's re-scoring runs many propagations over the same past). Same values, read once."""

    def __init__(self, history: Any) -> None:
        self._h = history
        self._memo: dict[tuple[str, int, int], list[float]] = {}

    def array(self, subentity_id: str, start: int, end: int) -> list[float]:
        key = (subentity_id, int(start), int(end))
        out = self._memo.get(key)
        if out is None:
            out = self._memo[key] = self._h.array(subentity_id, start, end)
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(self._h, name)


def context_bucket(context: dict[str, float]) -> str:
    """e.g. "inflation.headline_cpi>+0.75", or "neutral"."""
    parts = []
    for sid in sorted(context):
        z = context[sid]
        if abs(z) >= BUCKET_Z:
            parts.append(f"{sid}>{'+' if z > 0 else '-'}{BUCKET_Z:.2f}")
    return "&".join(parts) if parts else "neutral"


def current_bucket(decision_id: str, wm: WorkingMemory, ctx: ProcessContext) -> str:
    today = ctx.today
    ctxs = {}
    for _key, _inter, s, _t, _d in wm.graph.in_channel_items(decision_id):
        z = wm.deviations.z_at(s, today)
        if z is not None:
            ctxs[s] = z
    return context_bucket(ctxs)


class HypothesisScorer(ABC):
    @abstractmethod
    def score(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> float: ...

    @abstractmethod
    def rescore_touched(self, entity_ids: set[str], wm: WorkingMemory, ltm: LongTermMemory,
                        ctx: ProcessContext, txn: MutationTxn) -> list[str]: ...


registry("hypothesis_scorer", HypothesisScorer)


def thesis_shocks(thesis_json: dict, wm: WorkingMemory, ctx: ProcessContext) -> list[ShockInput]:
    """Standardized shocks of a stored thesis at the current posteriors."""
    from axelrod_wm.dynamics.regressors import days_until
    from axelrod_wm.events.thesis import Thesis
    from axelrod_wm.shared.parse import change_size

    th = Thesis.model_validate(thesis_json)
    out = []
    for op in th.event.ops:
        if getattr(op, "op", None) != "change_value" or getattr(op.target, "kind", "") != "concrete":
            continue
        sub = wm.graph.subentities.get(op.target.subentity_id)
        if sub is None:
            continue
        size, sd = change_size(sub, op.mode, op.delta, op.delta_sd)
        hold = int(math.ceil(op.window_days)) if op.window_days else None
        out.append(ShockInput(subentity_id=sub.id, size=size, size_sd=sd, start_day=days_until(ctx, op.at, 1),
                              persistence=op.persistence, intervention=op.intervention, hold_days=hold))
    return out


@register("hypothesis_scorer", "forecast_sensitivity_voi")
class ForecastSensitivityVOI(HypothesisScorer):
    def __init__(self, config: Any = None, propagator: Propagator | None = None) -> None:
        self.config = config
        self.propagator = propagator
        self._history: _FrozenHistory | None = None    # set while rescore_touched runs

    # -- probability -----------------------------------------------------------------------
    def probability(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> float:
        rec = ctx.recognition
        if h.kind in (HypothesisKind.INTERACTION_PRESENT, HypothesisKind.INTERACTION_ABSENT):
            if h.comovement_id and h.comovement_id in ltm.correlation_frontier.entries:
                co = ltm.correlation_frontier.entries[h.comovement_id]
                p = co.support / (co.support + rec + 1.0)
            else:
                inter = self._interaction(h, wm)
                if inter is None:
                    return h.probability
                p = inter.existence.mean()
            return p if h.kind == HypothesisKind.INTERACTION_PRESENT else 1.0 - p
        if h.kind == HypothesisKind.ENTITY_DECISION and h.decision_subentity_id:
            sub = wm.graph.subentities.get(h.decision_subentity_id)
            if sub is None:
                return h.probability
            mem = ltm.entity_memories.get(sub.entity_id)
            prof = mem.profiles.get(sub.id) if mem is not None else None
            if prof is None:
                return h.probability
            from axelrod_wm.learning.fold import native_scale

            action = action_of(h.decision_change or 0.0, native_scale(sub))
            return prof.p_action(current_bucket(sub.id, wm, ctx), action)
        return h.probability

    @staticmethod
    def _interaction(h: Hypothesis, wm: WorkingMemory) -> Any:
        if h.interaction_id and h.interaction_id in wm.graph.interactions:
            return wm.graph.interactions[h.interaction_id]
        if h.source_id and h.target_id:
            for iid in wm.graph.interaction_between(h.source_id, h.target_id):
                return wm.graph.interactions[iid]
        return None

    # -- sensitivity -----------------------------------------------------------------------
    def _references(self, h: Hypothesis, wm: WorkingMemory, ctx: ProcessContext) -> list[list[ShockInput]]:
        refs: list[list[ShockInput]] = []
        layer = wm.forecast_layer
        order = [t for t in reversed(layer.order) if t in layer.by_thesis]
        pinned = [t for t in order if t in layer.pinned]
        for tid in (pinned + [t for t in order if t not in pinned])[:3]:
            view = layer.by_thesis[tid]
            if view.thesis:
                shocks = [s for s in thesis_shocks(view.thesis, wm, ctx) if not s.intervention]
                if shocks:
                    refs.append(shocks)
        if refs:
            return refs
        sid = h.source_id if h.kind != HypothesisKind.ENTITY_DECISION else h.decision_subentity_id
        if sid is None:
            inter = self._interaction(h, wm)
            sid = inter.source_id if inter is not None else None
        if sid is None or sid not in wm.graph.subentities:
            return []
        return [[ShockInput(subentity_id=sid, size=1.0, start_day=1)]]

    def _hyp_channel(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> Channel | None:
        inter = self._interaction(h, wm)
        if inter is not None:
            return Channel(interaction_id=inter.id, source_id=inter.source_id, target_id=inter.target_id,
                           dynamics=inter.forward, existence=inter.existence, parameters=list(inter.parameters),
                           key=inter.id)
        if not (h.source_id and h.target_id):
            return None
        slope, sd, lag = 0.3, 0.2, 1
        if h.comovement_id and h.comovement_id in ltm.correlation_frontier.entries:
            co = ltm.correlation_frontier.entries[h.comovement_id]
            s, se = co.response.slope()
            if math.isfinite(s) and abs(s) > 1e-9:
                slope = s
            elif co.sign < 0:
                slope = -0.3
            sd = max(0.2, 2 * se) if math.isfinite(se) else 0.5
            lag = co.lag_days
        width = int(ctx.config.frontier.window_days)
        kernel = KernelSpec(delay=gamma_from_mean(max(lag, 1)), lag=gamma_from_mean(width))
        return Channel(interaction_id=f"hyp:{h.id}", source_id=h.source_id, target_id=h.target_id,
                       dynamics=EdgeDynamics(effect=Gaussian(mu=slope, sigma=sd), kernel=kernel),
                       existence=Beta(alpha=1.0, beta=1.0), key=f"hyp:{h.id}")

    def sensitivity(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> float:
        cfg = ctx.config
        watch = dict(cfg.hypotheses.watch_list)
        refs = self._references(h, wm, ctx)
        if not refs or self.propagator is None:
            return 0.0
        H = int(cfg.time.horizon_days)
        n = int(cfg.hypotheses.reference_samples)
        total = 0.0
        for k, shocks in enumerate(refs):
            seeds = [s.subentity_id for s in shocks]
            ends = [x for x in (h.source_id, h.target_id, h.decision_subentity_id) if x]
            near = wm.graph.neighborhood(seeds + ends, 3, 0.0)
            keys = {key for key, _i, s, t, _d in wm.graph.channel_items() if s in near and t in near}
            chans = graph_channels(wm, keys)
            if h.kind == HypothesisKind.ENTITY_DECISION:
                sid = h.decision_subentity_id
                if sid not in wm.graph.subentities:
                    return 0.0
                sub = wm.graph.subentities[sid]
                hold = int(math.ceil(h.decision_window_days or 90))
                from axelrod_wm.shared.parse import change_size

                size, _ = change_size(sub, "absolute", h.decision_change or 0.0)
                on = shocks + [ShockInput(subentity_id=sid, size=size, start_day=1, intervention=True, hold_days=hold)]
                off = shocks
                system = self._frozen(build_system(list(chans.values()), wm, ctx, H, extra_subentities=sorted(watch) + [sid]))
                r_on = self.propagator.propagate(system, on, n, ctx.child_rng("voi", h.id, k))
                r_off = self.propagator.propagate(system, off, n, ctx.child_rng("voi", h.id, k))
            else:
                hc = self._hyp_channel(h, wm, ltm, ctx)
                if hc is None:
                    return 0.0
                base = [c for key, c in sorted(chans.items()) if key != hc.channel_key]
                sys_on = self._frozen(build_system(base + [hc.model_copy(update={"forced": True})], wm, ctx, H,
                                                   extra_subentities=sorted(watch)))
                sys_off = self._frozen(build_system(base + [hc.model_copy(update={"forced": False})], wm, ctx, H,
                                                    extra_subentities=sorted(watch)))
                r_on = self.propagator.propagate(sys_on, shocks, n, ctx.child_rng("voi", h.id, k))
                r_off = self.propagator.propagate(sys_off, shocks, n, ctx.child_rng("voi", h.id, k))
            s = 0.0
            for sid, wgt in sorted(watch.items()):
                if r_on.has(sid) and r_off.has(sid):
                    s += float(wgt) * abs(r_on.median_z(sid, H) - r_off.median_z(sid, H))
            total += s
        return total / len(refs)

    def _frozen(self, system: Any) -> Any:
        if self._history is not None and system.history is self._history._h:  # noqa: SLF001
            system.history = self._history
        return system

    def score(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> float:
        p = self.probability(h, wm, ltm, ctx)
        return self.sensitivity(h, wm, ltm, ctx) * 4.0 * p * (1.0 - p)

    def rescore(self, h: Hypothesis, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                txn: MutationTxn | None, force: bool = False) -> Hypothesis:
        p = min(max(self.probability(h, wm, ltm, ctx), 0.0), 1.0)
        # DECISION: sensitivity is recomputed at most weekly (or when forced); p updates every time. The
        # week runs from when the sensitivity was computed (sensitivity_at), not from the last re-score,
        # and a sensitivity of zero is a result like any other, kept for the week.
        age = (ctx.now - h.sensitivity_at).total_seconds() / 86400.0 if h.sensitivity_at is not None else None
        fields: dict[str, Any] = {"probability": p, "scored_at": ctx.now}
        if force or age is None or age >= SENSITIVITY_TTL_DAYS:
            sens = self.sensitivity(h, wm, ltm, ctx)
            fields["sensitivity_at"] = ctx.now
        else:
            sens = h.sensitivity
        voi = sens * 4.0 * p * (1.0 - p)
        fields.update(informational_value=voi, sensitivity=sens)
        if txn is not None:
            txn.update("wm.hypotheses", h.id, **fields)
        ctx.tracer.emit(Phase.EXPLAIN, "hypothesis.scored", refs=[h.id] + list(h.subject_entity_ids), hypothesis_id=h.id,
                        voi=round(voi, 6), probability=round(p, 6), sensitivity=round(sens, 6))
        return h.model_copy(update=fields)

    def rescore_touched(self, entity_ids: set[str], wm: WorkingMemory, ltm: LongTermMemory,
                        ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        out = []
        self._history = _FrozenHistory(wm.deviations)
        try:
            for hid in sorted(wm.hypotheses):
                h = wm.hypotheses[hid]
                if h.status != HypothesisStatus.OPEN:
                    continue
                subj = set(h.subject_entity_ids)
                if not subj:
                    inter = self._interaction(h, wm)
                    if inter is not None:
                        subj = {inter.source_id.split(".")[0], inter.target_id.split(".")[0]}
                if subj & entity_ids:
                    self.rescore(h, wm, ltm, ctx, txn)
                    out.append(hid)
        finally:
            self._history = None
        return out
