"""The daily model's predict and record steps (§8.6.1, D13).

Every day an update run covers, `predict(day)` advances every subentity's state to that day before
any of the day's events are folded in, and `record(day)` closes the day: it keeps a point for every
subentity (observed or predicted), refits the posteriors of those not observed, logs channel
activity, and advances every ChannelState to the next day. This is how effects reach subentities
that no source reports.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.dynamics.kernels import KernelRecursion, mean_kernel_days
from axelrod_wm.dynamics.regressors import clip_of, level_noise_of, min_delay_of, moderator_terms
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.memory.working import (
    ActivityRecord,
    ChannelState,
    DeviationPoint,
    activity_key,
    point_key,
    ripple_correction,
)
from axelrod_wm.model.distributions import Gaussian, from_link_moments
from axelrod_wm.model.interaction import (
    REVERSE_SUFFIX,
    Direction,
    EdgeDynamics,
    Interaction,
    ParameterBinding,
    base_interaction_id,
)
from axelrod_wm.model.temporal import Bitemporal, TimeState
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.model.entity import Subentity
    from axelrod_wm.model.graph import CausalGraph
    from axelrod_wm.repo.mutator import MutationTxn

MAX_TIME_STATES = 260          # newest time states kept per subentity and interaction (§6.6, §6.7)
WEEK_DAYS = 7


class DailyPropagator(ABC):
    @abstractmethod
    def predict(self, day: int, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn) -> None:
        """Advance every subentity's state to `day`, before that day's events are folded in."""

    @abstractmethod
    def record(self, day: int, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn) -> dict[str, float]:
        """After the day's events: write a DeviationPoint for every subentity, refit the posteriors of
        those not observed today, log activity, advance every ChannelState to day + 1, and return
        the day's moves (subentity -> change in z)."""


registry("daily_propagator", DailyPropagator)


# ---------------------------------------------------------------------------------------------
# Shared helpers (the fold uses them too)
# ---------------------------------------------------------------------------------------------

@dataclass
class InChannel:
    key: str
    inter: Interaction
    source: str
    dyn: EdgeDynamics
    params: list[ParameterBinding] = field(default_factory=list)

    @property
    def side(self) -> str:
        return "reverse" if self.key.endswith(REVERSE_SUFFIX) else "forward"


def in_channel_index(graph: CausalGraph) -> dict[str, list[InChannel]]:
    """Target subentity -> its in-channels (one pass over the graph)."""
    out: dict[str, list[InChannel]] = {}
    for inter in graph.active_interactions():
        for key, s, t, dyn in inter.channel_items():
            params = list(inter.parameters) if key == inter.id else []
            out.setdefault(t, []).append(InChannel(key, inter, s, dyn, params))
    return out


def channel_sources(graph: CausalGraph) -> dict[str, tuple[str, str, EdgeDynamics, Interaction]]:
    """Channel id -> (source, target, dynamics, interaction) for active channels."""
    out = {}
    for inter in graph.active_interactions():
        for key, s, t, dyn in inter.channel_items():
            out[key] = (s, t, dyn, inter)
    return out


def pair_key(a: str, b: str) -> str:
    return f"{a}|{b}" if a <= b else f"{b}|{a}"


def state_prior(sub: Subentity, names: list[str], means: list[float], variances: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """theta and P for [level, effects...], with the kept off-diagonal covariances (Subentity.state_cov)."""
    k = len(names)
    theta = np.asarray(means, dtype=float)
    P = np.diag(np.asarray(variances, dtype=float))
    if k > 1 and sub.state_cov:
        for a in range(k):
            for b in range(a + 1, k):
                c = sub.state_cov.get(pair_key(names[a], names[b]))
                if c is None:
                    continue
                lim = 0.999 * math.sqrt(max(P[a, a] * P[b, b], 0.0))
                P[a, b] = P[b, a] = max(-lim, min(lim, c))
    return theta, P


def refit_effect(dist: Any, mean: float, var: float) -> Any:
    """An effect distribution with the given native mean and variance (moment matching)."""
    var = max(float(var), 1e-12)
    if isinstance(dist, Gaussian) or dist.family == "gaussian":
        return Gaussian(mu=float(mean), sigma=math.sqrt(var))
    m = float(mean)
    if dist.family in ("lognormal", "gamma") and m > 1e-9:
        s2 = math.log1p(var / (m * m))
        return from_link_moments(dist.family, math.log(m) - (0.5 * s2 if dist.family == "lognormal" else 0.0), s2)
    return from_link_moments(dist.family, m, var)


def channel_phi_today(wm: WorkingMemory, key: str, day: int) -> float:
    """phi_c(day) from the channel's state (which sync_channel_states keeps at the processing day)."""
    cs = wm.channels.get(key)
    if cs is not None and cs.day == day:
        return cs.recursion.phi()
    rec = wm.channel_phi.get(f"{key}|{day}")
    if rec is not None:
        return float(rec)
    return 0.0


@dataclass
class Prediction:
    names: list[str]                  # "level" then channel keys
    theta: np.ndarray
    P: np.ndarray
    H: np.ndarray
    additive: float                   # additive moderator inputs
    channels: list[InChannel]

    @property
    def z(self) -> float:
        return float(self.H @ self.theta) + self.additive

    @property
    def var(self) -> float:
        return max(float(self.H @ self.P @ self.H), 1e-12)


def predict_state(sub: Subentity, chans: list[InChannel], wm: WorkingMemory, day: int,
                  clip: tuple[float, float]) -> Prediction:
    """The current state of [level, in-channel effects] and its regressors on `day`."""
    names = ["level"]
    means = [sub.level_mean]
    variances = [max(sub.level_var, 1e-12)]
    h = [1.0]
    additive = 0.0
    dev = wm.deviations
    for ch in chans:
        phi = channel_phi_today(wm, ch.key, day)
        mult, add = moderator_terms(ch.params, dev, day, clip) if ch.params else (1.0, 0.0)
        additive += add
        names.append(ch.key)
        means.append(ch.dyn.effect.mean())
        variances.append(max(ch.dyn.effect.var(), 1e-12))
        h.append(mult * phi)
    if wm.ripple_judgments:
        additive += ripple_correction(wm, sub.id, day)
    theta, P = state_prior(sub, names, means, variances)
    return Prediction(names, theta, P, np.asarray(h, dtype=float), additive, list(chans))


def time_state_due(states: list[TimeState], wm: WorkingMemory, day: int, every: int = WEEK_DAYS) -> bool:
    if not states:
        return True
    return wm.deviations.day_of(states[-1].at.valid_at) <= day - every


def subentity_time_state(sub: Subentity, point: DeviationPoint, at: Any, now: Any, day: int,
                         source_event_id: str | None = None, y: float | None = None) -> TimeState:
    values = {"mean": sub.posterior.mean(), "sd": sub.posterior.sd(), "z": point.z, "level": point.level,
              "day": float(day)}
    if point.innovation is not None:
        values["innovation"] = point.innovation
    if y is not None:
        values["y"] = y
    return TimeState(at=Bitemporal(valid_at=at, recorded_at=now), values=values, source_event_id=source_event_id)


def interaction_time_state(inter: Interaction, at: Any, now: Any, source_event_id: str | None = None,
                           phi: float | None = None) -> TimeState:
    values = {"effect_mean": inter.forward.effect.mean(), "effect_sd": inter.forward.effect.sd(),
              "existence_mean": inter.existence.mean(), "significance": inter.significance_mean()}
    if phi is not None:
        values["phi"] = phi
    return TimeState(at=Bitemporal(valid_at=at, recorded_at=now), values=values, source_event_id=source_event_id)


# ---------------------------------------------------------------------------------------------
# Channel states
# ---------------------------------------------------------------------------------------------

def _window_phi(wm: WorkingMemory, key: str, source: str, rec: KernelRecursion, day: int, width: int,
                txn: MutationTxn) -> None:
    """Recompute channel_phi for days day - width .. day - 1 with a (new) kernel."""
    dev = wm.deviations
    start = max(day - width, dev.first_kept_day, 0)
    if start >= day:
        return
    series = dev.series(source)
    r = KernelRecursion.warm_start(rec.d, rec.l, rec.lam, series, start, acc=rec.acc)
    for t in range(start, day):
        txn.put("wm.channel_phi", f"{key}|{t}", r.phi())
        r.advance(series, t)


def build_channel_state(wm: WorkingMemory, key: str, source: str, dyn: EdgeDynamics, day: int,
                        ctx: ProcessContext, txn: MutationTxn) -> ChannelState:
    """Warm-start a channel's regressor at `day` and add (or replace) its ChannelState. The window's
    channel_phi values are recomputed so that it never mixes two kernels (§8.6.1)."""
    d, l, lam = mean_kernel_days(dyn.kernel, min_delay_of(ctx))
    rec = KernelRecursion.warm_start(d, l, lam, wm.deviations.series(source), day, acc=dyn.kernel.accumulates)
    cs = ChannelState(channel_id=key, recursion=rec, day=day)
    txn.replace("wm.channels", cs)
    _window_phi(wm, key, source, rec, day, int(ctx.config.abduction.window_days), txn)
    return cs


def ensure_channel_states(inter: Interaction, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn,
                          day: int | None = None) -> list[str]:
    """Build the ChannelStates of one interaction (and its :rev channel) at the current day: used when
    an interaction is created or its kernel or direction changes."""
    day = ctx.day if day is None else day
    out = []
    for key, s, _t, dyn in inter.channel_items():
        build_channel_state(wm, key, s, dyn, day, ctx, txn)
        out.append(key)
    if inter.direction != Direction.BIDIRECTIONAL and (inter.id + REVERSE_SUFFIX) in wm.channels:
        txn.remove("wm.channels", inter.id + REVERSE_SUFFIX)
    return out


def sync_channel_states(wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn, day: int) -> list[str]:
    """Bring every ChannelState to `day`: build missing ones, rebuild those whose mean kernel changed,
    advance stale ones, and drop those of channels that no longer exist. Returns rebuilt channel ids."""
    dev = wm.deviations
    live = channel_sources(wm.graph)
    rebuilt: list[str] = []
    min_delay = min_delay_of(ctx)
    for key in sorted(wm.channels):
        if key not in live:
            txn.remove("wm.channels", key)
    for key in sorted(live):
        s, _t, dyn, _inter = live[key]
        cs = wm.channels.get(key)
        want = mean_kernel_days(dyn.kernel, min_delay)
        acc = dyn.kernel.accumulates
        lam = 1.0 if acc else want[2]
        if cs is None or (cs.recursion.d, cs.recursion.l) != want[:2] or abs(cs.recursion.lam - lam) > 1e-12 \
                or cs.recursion.acc != acc or cs.day > day:
            build_channel_state(wm, key, s, dyn, day, ctx, txn)
            rebuilt.append(key)
        elif cs.day < day:
            rec = cs.recursion.model_copy()
            series = dev.series(s)
            for t in range(cs.day, day):
                rec.advance(series, t)
            txn.update("wm.channels", key, recursion=rec, day=day)
    return rebuilt


# ---------------------------------------------------------------------------------------------
# kalman_predict
# ---------------------------------------------------------------------------------------------

@register("daily_propagator", "kalman_predict")
class KalmanPredict(DailyPropagator):
    """The predict and record steps of the daily dynamic linear regression (§8.6.1)."""

    def __init__(self, config: Any = None, move_threshold: float = 0.05) -> None:
        self.config = config
        self.move_threshold = float(move_threshold)

    # -- predict -----------------------------------------------------------------------------
    def predict(self, day: int, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn) -> None:
        cfg = ctx.config
        graph = wm.graph
        q_b2 = float(cfg.learning.effect_process_noise) ** 2
        sync_channel_states(wm, ctx, txn, day)
        # 1. process noise on every channel's effect
        if q_b2 > 0:
            for inter in graph.active_interactions():
                if inter.fixed:
                    continue                     # an identity's weight does not drift (accounting, identity, stock-flow)
                fields = {"forward.effect": refit_effect(inter.forward.effect, inter.forward.effect.mean(),
                                                         inter.forward.effect.var() + q_b2)}
                if inter.direction == Direction.BIDIRECTIONAL and inter.reverse is not None:
                    fields["reverse.effect"] = refit_effect(inter.reverse.effect, inter.reverse.effect.mean(),
                                                            inter.reverse.effect.var() + q_b2)
                txn.update("wm.graph.interactions", inter.id, **fields)
        # 1-3. level noise, the predicted state, and the provisional point
        index = in_channel_index(graph)
        clip = clip_of(ctx)
        for sid in sorted(graph.subentities):
            sub = graph.subentities[sid]
            q_a = level_noise_of(sub, ctx)
            txn.update("wm.graph.subentities", sid, level_var=float(sub.level_var + q_a * q_a))
            pred = predict_state(sub, index.get(sid, []), wm, day, clip)
            key = point_key(sid, day)
            point = DeviationPoint(z=pred.z, var=pred.var, level=float(sub.level_mean))
            if key in wm.deviations.points:
                txn.replace("wm.deviations.points", point, key=key)
            else:
                txn.add("wm.deviations.points", point, key=key)

    # -- record ------------------------------------------------------------------------------
    def record(self, day: int, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn) -> dict[str, float]:
        graph = wm.graph
        dev = wm.deviations
        clip = clip_of(ctx)
        end = dev.day_end(day)
        index: dict[str, list[InChannel]] | None = None
        moves: dict[str, float] = {}
        # 4. a point for every subentity; refit the posteriors of those not observed today
        for sid in sorted(graph.subentities):
            sub = graph.subentities[sid]
            p = dev.point(sid, day)
            if p is None:                      # created today, after the predict step
                if index is None:
                    index = in_channel_index(graph)
                pred = predict_state(sub, index.get(sid, []), wm, day, clip)
                p = DeviationPoint(z=pred.z, var=pred.var, level=float(sub.level_mean))
                txn.add("wm.deviations.points", p, key=point_key(sid, day))
            if not p.observed:
                post = from_link_moments(sub.posterior.family, sub.anchor + sub.scale * p.z,
                                         (sub.scale ** 2) * p.var)
                txn.update("wm.graph.subentities", sid, posterior=post)
            if time_state_due(sub.history, wm, day):
                txn.append_to("wm.graph.subentities", sid, "history",
                              subentity_time_state(graph.subentities[sid], p, end, ctx.now, day),
                              keep_last=MAX_TIME_STATES)
            moves[sid] = p.z - dev.z(sid, day - 1)
        # weekly time states for interactions the fold did not annotate this week (§6.7)
        for inter in graph.active_interactions():
            if time_state_due(inter.time_states, wm, day):
                txn.append_to("wm.graph.interactions", inter.id, "time_states",
                              interaction_time_state(inter, end, ctx.now), keep_last=MAX_TIME_STATES)
        # 5. activity
        self._activity(day, wm, ctx, txn, clip)
        # 6. advance every channel to day + 1
        live = channel_sources(graph)
        for key in sorted(wm.channels):
            cs = wm.channels[key]
            if key not in live:
                txn.remove("wm.channels", key)
                continue
            src = live[key][0]
            rec = cs.recursion.model_copy()
            series = dev.series(src)
            for t in range(cs.day, day + 1):
                rec.advance(series, t)
            txn.update("wm.channels", key, recursion=rec, day=day + 1)
        moved = {k: round(v, 4) for k, v in sorted(moves.items()) if abs(v) >= self.move_threshold}
        ctx.tracer.emit(Phase.DAILY, "daily.propagated", refs=sorted(moved), day=day,
                        date=dev.date_of(day).isoformat(), moved=moved)
        return moves

    def _activity(self, day: int, wm: WorkingMemory, ctx: ProcessContext, txn: MutationTxn,
                  clip: tuple[float, float]) -> None:
        cfg = ctx.config
        dev = wm.deviations
        width = int(cfg.abduction.window_days)
        min_c = float(cfg.abduction.min_edge_contribution)
        for key, inter, _s, t, dyn in wm.graph.channel_items():
            phi = channel_phi_today(wm, key, day)
            txn.put("wm.channel_phi", f"{key}|{day}", phi)
            old = wm.channel_phi.get(f"{key}|{day - width}")
            if old is None:
                if day - width < max(dev.first_kept_day, 0):
                    old = 0.0
                else:
                    s = wm.graph.interactions[inter.id].channel_items()
                    src = next(x[1] for x in s if x[0] == key)
                    d, l, lam = mean_kernel_days(dyn.kernel, min_delay_of(ctx))
                    old = KernelRecursion.warm_start(d, l, lam, dev.series(src), day - width,
                                                     acc=dyn.kernel.accumulates).phi()
            params = list(inter.parameters) if key == inter.id else []
            mult = moderator_terms(params, dev, day, clip)[0] if params else 1.0
            cc = dyn.effect.mean() * mult * (phi - float(old))
            if abs(cc) >= min_c:
                rec = ActivityRecord(day=day, channel_id=key, contribution_change=float(cc),
                                     target_move=dev.window_change(t, day, width), target_id=t)
                txn.replace("wm.activity_log", rec, key=activity_key(day, key))
        # instance activations: the share of each instance's interactions active in the window
        active = {base_interaction_id(r.channel_id) for r in wm.activity_log.values() if r.day > day - width}
        for iid in sorted(wm.graph.instances):
            inst = wm.graph.instances[iid]
            if inst.transient:
                continue
            ids = inst.interaction_ids
            act = len(active & set(ids)) / len(ids) if ids else 0.0
            if abs(act - inst.activation) > 1e-12:
                txn.update("wm.graph.instances", iid, activation=act)
