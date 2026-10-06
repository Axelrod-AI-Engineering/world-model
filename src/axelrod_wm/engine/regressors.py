"""Helpers shared by the daily model, the fold, the frontier, kernel learning, and propagation set-up.

phi_c(t) is the channel's regressor at its mean kernel, kept current by its ChannelState (§6.4); the
moderator multiplier m_c uses the moderator's z on day t - 1 (§8.6.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.core.interaction import EdgeDynamics, Interaction, ParameterBinding, ParameterForm
from axelrod_wm.core.taxonomy import default_obs_noise
from axelrod_wm.engine.kernels import KernelRecursion, mean_kernel_days
from axelrod_wm.engine.propagation import Channel, InitialState, PropagationSystem

if TYPE_CHECKING:
    from axelrod_wm.core.entity import Subentity
    from axelrod_wm.core.taxonomy import AttributeVocabulary
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.working import DeviationHistory, WorkingMemory


def min_delay_of(ctx: ProcessContext) -> int:
    return max(1, int(ctx.config.propagation.min_delay_days))


def moderator_terms(params: list[ParameterBinding], dev: DeviationHistory, day: int,
                    clip: tuple[float, float]) -> tuple[float, float]:
    """(multiplier, additive input) at mean coefficients, from moderators' z on day - 1."""
    mult, add = 1.0, 0.0
    for p in params:
        z = dev.z(p.moderator_id, day - 1)
        gam = p.coefficient.mean()
        if p.form == ParameterForm.MULTIPLICATIVE:
            mult *= min(max(1.0 + gam * z, clip[0]), clip[1])
        elif p.form == ParameterForm.THRESHOLD:
            mult *= 1.0 if z > (p.threshold if p.threshold is not None else 0.0) else 0.0
        else:
            add += gam * z
    return mult, add


def clip_of(ctx: ProcessContext) -> tuple[float, float]:
    c = ctx.config.propagation.moderator_clip
    return float(c[0]), float(c[1])


def warm_recursion(dyn: EdgeDynamics, source_id: str, wm: WorkingMemory, day: int, min_delay: int = 1,
                   multiplier: float = 1.0) -> KernelRecursion:
    d, l, lam = mean_kernel_days(dyn.kernel, min_delay, multiplier)
    return KernelRecursion.warm_start(d, l, lam, wm.deviations.series(source_id), day)


def phi_at(wm: WorkingMemory, channel_id: str, source_id: str, dyn: EdgeDynamics, day: int,
           min_delay: int = 1) -> float:
    """The regressor phi_c(day) at the channel's mean kernel: from its ChannelState when it is at that
    day, else from the recorded channel_phi, else by a warm start from the history."""
    cs = wm.channels.get(channel_id)
    if cs is not None and cs.day == day:
        return cs.recursion.phi()
    rec = wm.channel_phi.get(f"{channel_id}|{day}")
    if rec is not None:
        return float(rec)
    return warm_recursion(dyn, source_id, wm, day, min_delay).phi()


def channel_regressor(wm: WorkingMemory, inter: Interaction, channel_id: str, source_id: str,
                      dyn: EdgeDynamics, day: int, ctx: ProcessContext) -> tuple[float, float]:
    """(m_c * phi_c(day), additive moderator input) for one channel on `day`."""
    params = list(inter.parameters) if channel_id == inter.id else []
    phi = phi_at(wm, channel_id, source_id, dyn, day, min_delay_of(ctx))
    mult, add = moderator_terms(params, wm.deviations, day, clip_of(ctx))
    return phi * mult, add


def obs_noise_of(sub: Subentity, wm: WorkingMemory, vocab: AttributeVocabulary | None) -> float:
    if sub.obs_noise is not None:
        return float(sub.obs_noise)
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
    """Today's deviation (filtered or predicted) for each subentity, its trend, and its level noise."""
    dev = wm.deviations
    today = ctx.today
    out: dict[str, InitialState] = {}
    for sid in subentity_ids:
        sub = wm.graph.subentities.get(sid)
        out[sid] = InitialState(z_now=dev.z(sid, today),
                                drift=float((drifts or {}).get(sid, 0.0)),
                                level_noise=float(sub.level_noise) if sub is not None and sub.level_noise is not None else None)
    return out


def build_system(channels: list[Channel], wm: WorkingMemory, ctx: ProcessContext, horizon_days: int,
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
    return PropagationSystem(subentity_ids=sids, channels=channels, horizon_days=int(horizon_days),
                             initial=initial_states(sids, wm, ctx, drifts), history=wm.deviations,
                             today=ctx.today, min_delay_days=min_delay_of(ctx))


def horizon_for(ctx: ProcessContext) -> int:
    h = ctx.notes.get("horizon_days")
    return int(h) if h is not None else int(ctx.config.time.horizon_days)


def days_until(ctx: ProcessContext, at: datetime | None, minimum: int = 1) -> int:
    """Whole days from now (day 0) to `at`; a time at or before now starts on day 1."""
    if at is None:
        return minimum
    dev = ctx.wm.deviations
    return max(minimum, dev.day_of(at) - ctx.today)


def frame_days(horizon: int, max_frames: int) -> list[int]:
    """At most max_frames days, evenly spaced over 0..horizon, always including the first and last."""
    if horizon <= 0:
        return [0]
    n = max(2, int(max_frames))
    if horizon + 1 <= n:
        return list(range(horizon + 1))
    out = sorted({int(round(i * horizon / (n - 1))) for i in range(n)})
    return out


def frame_payload(result: Any, day: int, threshold: float = 0.05) -> tuple[dict[str, float], dict[str, float]]:
    """Median z per subentity and median flow per channel on a day, above a threshold."""
    zs = np.median(result.z[:, :, day], axis=0)
    z = {sid: round(float(zs[i]), 4) for sid, i in result.subentity_index.items() if abs(zs[i]) >= threshold}
    flow: dict[str, float] = {}
    if result.channel_contrib is not None:
        fs = np.median(result.channel_contrib[:, :, day], axis=0)
        flow = {k: round(float(fs[c]), 4) for k, c in result.channel_index.items() if abs(fs[c]) >= threshold}
    return z, flow


def emit_frames(ctx: ProcessContext, phase: Any, run_id: str, result: Any, refs: list[str] | None = None) -> None:
    """propagation.frame events, at most propagation.max_frames per run (§10)."""
    if result is None or not getattr(ctx.tracer, "enabled", True) or getattr(ctx.tracer, "muted", 0):
        return
    if type(ctx.tracer).__name__ == "NullTracer":
        return
    H = result.z.shape[2] - 1
    for t in frame_days(H, int(ctx.config.propagation.max_frames)):
        z, flow = frame_payload(result, t)
        ctx.tracer.emit(phase, "propagation.frame", refs=refs or [], run_id=run_id, day=t, z=z, flow=flow)
