"""Kernel learning: delay, lag, and duration (§8.6, default grid_rescale, run at consolidation)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from axelrod_wm.core.temporal import Bitemporal, TimeState
from axelrod_wm.engine.learning import MAX_TIME_STATES, KernelUpdater
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.regressors import level_noise_of, obs_noise_of, regressor_cache
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


def target_fit_sse(wm: WorkingMemory, ctx: ProcessContext, target: str, steps: list[int],
                   multipliers: dict[str, float] | None = None, cache: Any = None,
                   overrides: dict[str, tuple[float, bool]] | None = None) -> tuple[float, int]:
    """Sum of squared one-step prediction errors of the target's changes, holding effects at their
    posterior means (the level's random walk is differenced out). Channels can be rescaled
    (kernel multipliers), given another effect mean, or switched off via `overrides`
    (key -> (effect mean, exists)). Returns (sse, number of terms).

    # DECISION: the fold's one-step predictive log-likelihood is approximated on first
    # differences, which removes the local level; only the argmax over multipliers is used."""
    graph = wm.graph
    dev = wm.deviations
    cache = cache or regressor_cache(wm, ctx)
    multipliers = multipliers or {}
    overrides = overrides or {}
    obs = dev.z.get(target, {})
    sse, n = 0.0, 0
    chans = graph.in_channel_items(target)
    for st in steps:
        prev = max((s for s in obs if s < st), default=None)
        if prev is None or st not in obs:
            continue
        dz = obs[st] - obs[prev]
        pred = 0.0
        for key, inter, s, _t, dyn in chans:
            params = inter.parameters if key == inter.id else []
            mean, on = overrides.get(key, (dyn.effect.mean(), True))
            if not on:
                continue
            m = multipliers.get(key, 1.0)
            phi_now, _ = cache.phi(key, s, dyn, params, st, m)
            phi_prev, _ = cache.phi(key, s, dyn, params, prev, m)
            pred += mean * (phi_now - phi_prev)
        sse += (dz - pred) ** 2
        n += 1
    return sse, n


@register("kernel_updater", "grid_rescale")
class GridRescaleKernelUpdater(KernelUpdater):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn) -> list[str]:
        cfg = ctx.config.kernel_update
        min_reg = float(ctx.config.learning.min_regressor)
        dev = wm.deviations
        now_step = dev.step_of(ctx.now)
        window = int(cfg.window_steps)
        cache = regressor_cache(wm, ctx)
        changed: list[str] = []
        for key, inter, s, t, dyn in wm.graph.channel_items():
            if key != inter.id:
                continue  # reverse channels share the interaction's learning schedule
            obs_steps = [st for st in sorted(dev.z.get(t, {})) if now_step - window < st <= now_step]
            params = inter.parameters
            informative = [st for st in obs_steps if abs(cache.phi(key, s, dyn, params, st)[0]) >= min_reg]
            if len(informative) < int(cfg.min_observations):
                continue
            scores = {}
            for m in cfg.multipliers:
                sse, n = target_fit_sse(wm, ctx, t, informative, {key: float(m)}, cache)
                scores[float(m)] = sse
            best = min(sorted(scores), key=lambda m: (scores[m], abs(math.log(m))))
            # DECISION: move only when the rescaled kernel beats the current one by min_log_lik_gain
            # (log likelihood with the target's one-step noise). Weekly consolidations on noisy data
            # otherwise random-walk the kernel means.
            tsub = wm.graph.subentities[t]
            sigma2 = level_noise_of(tsub, ctx) ** 2 + 2.0 * obs_noise_of(tsub, wm, ltm) ** 2
            gain = 0.5 * (scores.get(1.0, scores[best]) - scores[best]) / max(sigma2, 1e-9)
            if gain < float(cfg.min_log_lik_gain):
                best = 1.0
            factor = best ** float(cfg.step)
            cv_old = dyn.kernel.cv()
            cv_new = max(float(cfg.min_cv), cv_old * float(cfg.cv_shrink))
            if abs(factor - 1.0) < 1e-9 and abs(cv_new - cv_old) < 1e-9:
                continue
            before = dyn.kernel.shorthand()
            kernel = dyn.kernel.rescaled(factor, cv=cv_new)
            fields = {"forward": dyn.model_copy(update={"kernel": kernel})}
            if inter.reverse is not None:
                fields["reverse"] = inter.reverse.model_copy(update={"kernel": inter.reverse.kernel.rescaled(factor, cv=cv_new)})
            txn.update("interactions", inter.id, **fields)
            after = kernel.shorthand()
            ts = TimeState(at=Bitemporal(valid_at=ctx.now, recorded_at=ctx.now),
                           values={"delay_days": after["delay_days"], "lag_days": after["lag_days"],
                                   "duration_days": after["duration_days"] if after["duration_days"] is not None else -1.0,
                                   "kernel_cv": cv_new, "multiplier": best},
                           note="kernel update")
            txn.append_to("interactions", inter.id, "time_states", ts, keep_last=MAX_TIME_STATES)
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
