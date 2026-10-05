"""Helpers shared by the fold, the frontier, kernel learning, and propagation set-up.

phi_c(t) = sum_{tau >= 1} gbar_c(tau) * dz_src(t - tau) times the moderator multiplier at its mean
(§8.6), where gbar is the step response at mean kernel parameters.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.core.interaction import EdgeDynamics, Interaction, ParameterBinding, ParameterForm
from axelrod_wm.core.taxonomy import default_obs_noise
from axelrod_wm.core.temporal import step_response
from axelrod_wm.engine.propagation import Channel, InitialState, PropagationSystem

if TYPE_CHECKING:
    from axelrod_wm.core.entity import Subentity
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import DeviationHistory, WorkingMemory


def mean_kernel(dyn: EdgeDynamics, n_steps: int, step_days: float, min_delay_steps: float,
                multiplier: float = 1.0) -> np.ndarray:
    d, l, dur = dyn.kernel.means()
    d, l = d * multiplier, l * multiplier
    dur = dur * multiplier if dur is not None else None
    d = max(d / step_days, min_delay_steps) * step_days
    return step_response(d, l, dur, n_steps, step_days, dyn.kernel.shape)


def phi_from_increments(g: np.ndarray, incs: np.ndarray) -> float:
    """incs are dz for steps t-W..t-1 (oldest first); g[tau] for tau = 0..W."""
    n = min(len(incs), len(g) - 1)
    if n <= 0:
        return 0.0
    return float(np.dot(g[1: n + 1], incs[::-1][:n]))


def moderator_terms(params: list[ParameterBinding], dev: DeviationHistory, step: int,
                    clip: tuple[float, float]) -> tuple[float, float]:
    """(multiplier, additive input) at mean coefficients, from moderators' deviations at step - 1."""
    mult, add = 1.0, 0.0
    for p in params:
        z = dev.z_at(p.moderator_id, step - 1) or 0.0
        gam = p.coefficient.mean()
        if p.form == ParameterForm.MULTIPLICATIVE:
            mult *= min(max(1.0 + gam * z, clip[0]), clip[1])
        elif p.form == ParameterForm.THRESHOLD:
            mult *= 1.0 if z > (p.threshold if p.threshold is not None else 0.0) else 0.0
        else:
            add += gam * z
    return mult, add


class RegressorCache:
    """Caches mean kernels and increment histories within one event."""

    def __init__(self, dev: DeviationHistory, window: int, step_days: float, min_delay_steps: float,
                 clip: tuple[float, float]) -> None:
        self.dev = dev
        self.window = window
        self.step_days = step_days
        self.min_delay = min_delay_steps
        self.clip = clip
        self._incs: dict[tuple[str, int], np.ndarray] = {}
        self._kern: dict[tuple[str, float], np.ndarray] = {}

    def increments(self, sid: str, end_step: int) -> np.ndarray:
        key = (sid, end_step)
        v = self._incs.get(key)
        if v is None:
            v = self._incs[key] = self.dev.increments(sid, end_step, self.window)
        return v

    def kernel(self, key: str, dyn: EdgeDynamics, multiplier: float = 1.0) -> np.ndarray:
        k = (key, multiplier)
        g = self._kern.get(k)
        if g is None:
            g = self._kern[k] = mean_kernel(dyn, self.window, self.step_days, self.min_delay, multiplier)
        return g

    def phi(self, channel_key: str, source_id: str, dyn: EdgeDynamics, params: list[ParameterBinding],
            step: int, multiplier: float = 1.0) -> tuple[float, float]:
        """(phi including the moderator multiplier, additive moderator input) at `step`."""
        g = self.kernel(channel_key, dyn, multiplier)
        raw = phi_from_increments(g, self.increments(source_id, step - 1))
        mult, add = moderator_terms(params, self.dev, step, self.clip)
        return raw * mult, add


def regressor_cache(wm: WorkingMemory, ctx: ProcessContext) -> RegressorCache:
    cfg = ctx.config
    clip = (float(cfg.propagation.moderator_clip[0]), float(cfg.propagation.moderator_clip[1]))
    return RegressorCache(wm.deviations, int(cfg.propagation.kernel_window_steps), ctx.step_days,
                          float(cfg.propagation.min_delay_steps), clip)


def obs_noise_of(sub: Subentity, wm: WorkingMemory, ltm: LongTermMemory | None) -> float:
    if sub.obs_noise is not None:
        return float(sub.obs_noise)
    vocab = ltm.attributes if ltm is not None else None
    return default_obs_noise(sub.attribute_kind, vocab, sub.id in wm.decision_variables)


def level_noise_of(sub: Subentity, ctx: ProcessContext) -> float:
    if sub.level_noise is not None:
        return float(sub.level_noise)
    return float(ctx.config.learning.level_process_noise)


def channel_of(inter: Interaction, key: str, source: str, target: str, dyn: EdgeDynamics,
               forced: bool | None = None) -> Channel:
    return Channel(interaction_id=inter.id, source_id=source, target_id=target, dynamics=dyn,
                   existence=inter.existence, parameters=list(inter.parameters) if key == inter.id else [],
                   forced=forced, key=key)


def graph_channels(wm: WorkingMemory, keys: set[str] | None = None) -> dict[str, Channel]:
    """Channels (plain posterior dynamics) for active interactions, optionally limited to `keys`."""
    out: dict[str, Channel] = {}
    for key, inter, s, t, dyn in wm.graph.channel_items():
        if keys is not None and key not in keys:
            continue
        if s not in wm.graph.subentities or t not in wm.graph.subentities:
            continue
        out[key] = channel_of(inter, key, s, t, dyn)
    return out


def initial_states(subentity_ids: list[str], wm: WorkingMemory, ctx: ProcessContext,
                   drifts: dict[str, float] | None = None) -> dict[str, InitialState]:
    dev = wm.deviations
    step = dev.step_of(ctx.now)
    window = int(ctx.config.propagation.kernel_window_steps)
    out: dict[str, InitialState] = {}
    for sid in subentity_ids:
        sub = wm.graph.subentities.get(sid)
        z = dev.z_at(sid, step)
        incs = dev.increments(sid, step, window) if z is not None else np.zeros(0)
        out[sid] = InitialState(z_now=float(z) if z is not None else 0.0,
                                drift=float((drifts or {}).get(sid, 0.0)),
                                level_noise=float(sub.level_noise) if sub is not None and sub.level_noise is not None else None,
                                past_dz=[float(x) for x in incs] if len(incs) else [])
    return out


def build_system(channels: list[Channel], wm: WorkingMemory, ctx: ProcessContext, horizon_steps: int,
                 extra_subentities: list[str] | None = None, drifts: dict[str, float] | None = None) -> PropagationSystem:
    sids: list[str] = []
    for ch in channels:
        for s in (ch.source_id, ch.target_id):
            if s not in sids:
                sids.append(s)
        for p in ch.parameters:
            if p.moderator_id not in sids:
                sids.append(p.moderator_id)
    for s in extra_subentities or []:
        if s not in sids and s in wm.graph.subentities:
            sids.append(s)
    return PropagationSystem(subentity_ids=sids, channels=channels, step_days=ctx.step_days,
                             horizon_steps=int(horizon_steps), initial=initial_states(sids, wm, ctx, drifts))


def horizon_for(ctx: ProcessContext) -> int:
    h = ctx.notes.get("horizon_steps")
    return int(h) if h is not None else int(ctx.config.time.horizon_steps)


def steps_until(ctx: ProcessContext, at, minimum: int = 1) -> int:
    days = (at - ctx.now).total_seconds() / 86400.0
    return max(minimum, int(math.ceil(days / ctx.step_days - 1e-9)))


def frame_payload(result: Any, step: int, threshold: float = 0.05) -> tuple[dict[str, float], dict[str, float]]:
    """Median z per subentity and median flow per channel at a step, above a threshold."""
    zs = np.median(result.z[:, :, step], axis=0)
    z = {sid: round(float(zs[i]), 4) for sid, i in result.subentity_index.items() if abs(zs[i]) >= threshold}
    flow: dict[str, float] = {}
    if result.channel_contrib is not None:
        fs = np.median(result.channel_contrib[:, :, step], axis=0)
        flow = {k: round(float(fs[c]), 4) for k, c in result.channel_index.items() if abs(fs[c]) >= threshold}
    return z, flow


def emit_frames(ctx: ProcessContext, phase: Any, run_id: str, result: Any, refs: list[str] | None = None) -> None:
    """propagation.frame events, at most horizon_steps + 1 per run."""
    if result is None or not getattr(ctx.tracer, "enabled", True):
        return
    for t in range(result.z.shape[2]):
        z, flow = frame_payload(result, t)
        ctx.tracer.emit(phase, "propagation.frame", refs=refs or [], run_id=run_id, step=t, z=z, flow=flow)
