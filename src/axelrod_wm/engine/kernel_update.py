"""Kernel learning: delay, lag, and duration (§8.6.2, default grid_rescale, run at consolidation
every kernel_update.every_days)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from axelrod_wm.core.temporal import Bitemporal, TimeState
from axelrod_wm.engine.daily import MAX_TIME_STATES, ensure_channel_states, in_channel_index
from axelrod_wm.engine.kernels import KernelRecursion, mean_kernel_days
from axelrod_wm.engine.learning import KernelUpdater
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.regressors import clip_of, level_noise_of, min_delay_of, moderator_terms, obs_noise_of
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


def phi_path(wm: WorkingMemory, source: str, kernel: Any, start: int, end: int, min_delay: int,
             multiplier: float = 1.0) -> dict[int, float]:
    """phi(t) for t in [start, end] at the kernel's mean parameters scaled by `multiplier`."""
    d, l, lam = mean_kernel_days(kernel, min_delay, multiplier)
    series = wm.deviations.series(source)
    rec = KernelRecursion.warm_start(d, l, lam, series, start)
    out: dict[int, float] = {}
    for t in range(start, end + 1):
        out[t] = rec.phi()
        rec.advance(series, t)
    return out


def target_log_lik(wm: WorkingMemory, target: str, days: list[int], phis: dict[str, dict[int, float]],
                   means: dict[str, float], mods: dict[str, dict[int, float]], level_noise: float,
                   obs_noise: float) -> float:
    """One-step predictive log likelihood of the target's observed changes between consecutive
    observations, with effects held at their posterior means.

    # DECISION: the fold's one-step predictive log-likelihood is computed on first differences between
    # observed days, which removes the local level; its variance is the level noise accumulated over
    # the gap plus twice the observation noise."""
    dev = wm.deviations
    ll = 0.0
    for a, b in zip(days[:-1], days[1:]):
        dz = dev.z(target, b) - dev.z(target, a)
        pred = 0.0
        for key, path in phis.items():
            m = mods.get(key)
            mb = m.get(b, 1.0) if m else 1.0
            ma = m.get(a, 1.0) if m else 1.0
            pred += means[key] * (mb * path.get(b, 0.0) - ma * path.get(a, 0.0))
        var = level_noise * level_noise * (b - a) + 2.0 * obs_noise * obs_noise
        ll += -0.5 * (dz - pred) ** 2 / var - 0.5 * math.log(2 * math.pi * var)
    return ll


@register("kernel_updater", "grid_rescale")
class GridRescaleKernelUpdater(KernelUpdater):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        cfg = ctx.config.kernel_update
        min_reg = float(ctx.config.learning.min_regressor)
        min_delay = min_delay_of(ctx)
        clip = clip_of(ctx)
        dev = wm.deviations
        today = ctx.today
        start = max(today - int(cfg.window_days) + 1, dev.first_kept_day)
        index = in_channel_index(wm.graph)
        changed: list[str] = []
        for target in sorted(index):
            chans = index[target]
            observed = dev.observed_days(target, start, today)
            if len(observed) < int(cfg.min_observations):
                continue
            tsub = wm.graph.subentities[target]
            q_a = level_noise_of(tsub, ctx)
            r = obs_noise_of(tsub, wm, ctx.vocab)
            base = {ch.key: phi_path(wm, ch.source, ch.dyn.kernel, start, today, min_delay) for ch in chans}
            means = {ch.key: ch.dyn.effect.mean() for ch in chans}
            # moderators scale phi on each day (at the moderator's z the day before)
            mods = {ch.key: {d: moderator_terms(ch.params, dev, d, clip)[0] for d in observed}
                    for ch in chans if ch.params}
            for ch in chans:
                if ch.key != ch.inter.id:
                    continue       # reverse channels share the interaction's learning schedule
                informative = [d for d in observed if abs(base[ch.key].get(d, 0.0)) >= min_reg]
                if len(informative) < int(cfg.min_observations):
                    continue
                scores: dict[float, float] = {}
                for m in cfg.multipliers:
                    phis = dict(base)
                    phis[ch.key] = phi_path(wm, ch.source, ch.dyn.kernel, start, today, min_delay, float(m))
                    scores[float(m)] = target_log_lik(wm, target, observed, phis, means, mods, q_a, r)
                best = max(sorted(scores), key=lambda m: (scores[m], -abs(math.log(m))))
                # DECISION: move only when the rescaled kernel beats the current one by min_log_lik_gain.
                # Weekly consolidations on noisy data otherwise random-walk the kernel means.
                gain = scores[best] - scores.get(1.0, scores[best])
                if gain < float(cfg.min_log_lik_gain):
                    best = 1.0
                factor = best ** float(cfg.step)
                dyn = ch.dyn
                cv_old = dyn.kernel.cv()
                cv_new = max(float(cfg.min_cv), cv_old * float(cfg.cv_shrink))
                if abs(factor - 1.0) < 1e-9 and abs(cv_new - cv_old) < 1e-9:
                    continue
                inter = wm.graph.interactions[ch.inter.id]
                before = dyn.kernel.shorthand()
                kernel = dyn.kernel.rescaled(factor, cv=cv_new)
                fields: dict[str, Any] = {"forward.kernel": kernel}
                if inter.reverse is not None:
                    fields["reverse.kernel"] = inter.reverse.kernel.rescaled(factor, cv=cv_new)
                old_days = mean_kernel_days(dyn.kernel, min_delay)
                txn.update("wm.graph.interactions", inter.id, **fields)
                after = kernel.shorthand()
                ts = TimeState(at=Bitemporal(valid_at=ctx.now, recorded_at=ctx.now),
                               values={"delay_days": after["delay_days"], "lag_days": after["lag_days"],
                                       "duration_days": after["duration_days"] if after["duration_days"] is not None else -1.0,
                                       "kernel_cv": cv_new, "multiplier": best},
                               note="kernel update")
                txn.append_to("wm.graph.interactions", inter.id, "time_states", ts, keep_last=MAX_TIME_STATES)
                if mean_kernel_days(kernel, min_delay) != old_days:
                    # the channel's state is rebuilt with a warm start at the next day to process (§8.6.2)
                    ensure_channel_states(wm.graph.interactions[inter.id], wm, ctx, txn, day=today + 1)
                changed.append(inter.id)
                ctx.tracer.emit(Phase.CONSOLIDATE, "kernel.updated", refs=[inter.id], interaction_id=inter.id,
                                before=before, after=after, best_multiplier=best)
        return changed


@register("kernel_updater", "none")
class NoKernelUpdater(KernelUpdater):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, wm, ltm, ctx, txn) -> list[str]:  # type: ignore[override]
        return []
