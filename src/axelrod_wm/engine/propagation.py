"""Propagation of perturbations along interactions (§8.5, D6, D7).

The default ``mc_impulse`` propagator simulates the same dynamic linear model that the fold
filters (§8.6), forward from the current state, with Monte Carlo draws of every uncertain
parameter. All random draws come from per-channel and per-subentity substreams of the given
generator, keyed by stable names, so runs with and without shocks (or with different channel
sets, or fewer samples) share common random numbers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Beta, DistSummary, Link, from_link, summarize_samples
from axelrod_wm.core.interaction import EdgeDynamics, ParameterBinding, ParameterForm
from axelrod_wm.core.temporal import step_response_batch
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.rng import substream
from axelrod_wm.events.graph_update import Persistence


class ShockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subentity_id: str
    size: float                    # standardized units
    size_sd: float = 0.0
    start_step: int = 1            # step 0 is now; shocks start at step 1 or later
    persistence: Persistence = Persistence.STEP
    intervention: bool = False     # do(): ignore in-channels of this subentity while held
    hold_steps: int | None = None


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    source_id: str
    target_id: str
    dynamics: EdgeDynamics
    existence: Beta
    parameters: list[ParameterBinding] = []
    forced: bool | None = None     # True/False forces existence on or off (scenarios, absent relations)
    key: str | None = None         # channel key; "<interaction id>~r" for a reverse channel

    @property
    def channel_key(self) -> str:
        return self.key or self.interaction_id


class InitialState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    z_now: float                       # current filtered deviation
    drift: float = 0.0                 # per-step trend of the local level (from prefill)
    level_noise: float | None = None   # the subentity's learned level noise; None uses the config
    past_dz: list[float] = []          # last kernel_window_steps increments, oldest first


class PropagationSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subentity_ids: list[str]
    channels: list[Channel]
    step_days: float
    horizon_steps: int
    initial: dict[str, InitialState] = {}    # missing entries start at z = 0 with no history


class PropagationResult:
    def __init__(self, subentity_index: dict[str, int], channel_index: dict[str, int], z: np.ndarray,
                 channel_contrib: np.ndarray | None, channels: list[Channel] | None = None,
                 step_days: float = 7.0) -> None:
        self.subentity_index = subentity_index
        self.channel_index = channel_index
        self.z = z                                  # [samples, subentities, horizon_steps + 1]
        self.channel_contrib = channel_contrib      # [samples, channels, horizon_steps + 1]
        self.channels = channels or []
        self.step_days = step_days

    @property
    def n_samples(self) -> int:
        return int(self.z.shape[0])

    @property
    def horizon_steps(self) -> int:
        return int(self.z.shape[2]) - 1

    def has(self, subentity_id: str) -> bool:
        return subentity_id in self.subentity_index

    def z_of(self, subentity_id: str) -> np.ndarray:
        """[samples, steps] standardized deviations (zeros if the subentity is not in the run)."""
        i = self.subentity_index.get(subentity_id)
        if i is None:
            return np.zeros((self.z.shape[0], self.z.shape[2]))
        return self.z[:, i, :]

    def contrib_of(self, channel_key: str) -> np.ndarray:
        c = self.channel_index.get(channel_key)
        if c is None or self.channel_contrib is None:
            return np.zeros((self.z.shape[0], self.z.shape[2]))
        return self.channel_contrib[:, c, :]

    def median_z(self, subentity_id: str, step: int | None = None) -> float:
        zz = self.z_of(subentity_id)
        t = self.horizon_steps if step is None else step
        return float(np.median(zz[:, t]))

    def summary(self, subentity_id: str, anchor: float, scale: float, link: Link) -> list[DistSummary]:
        zz = self.z_of(subentity_id)
        x = from_link(anchor + scale * zz, link)
        x = np.asarray(x, dtype=float)
        return [summarize_samples(x[:, t]) for t in range(zz.shape[1])]

    def z_summary(self, subentity_id: str) -> list[DistSummary]:
        zz = self.z_of(subentity_id)
        return [summarize_samples(zz[:, t]) for t in range(zz.shape[1])]

    def minus(self, other: PropagationResult) -> PropagationResult:
        """Sample-by-sample difference (an effect), over the subentities and channels of self."""
        z = np.zeros_like(self.z)
        for sid, i in self.subentity_index.items():
            z[:, i, :] = self.z[:, i, :] - other.z_of(sid)
        contrib = None
        if self.channel_contrib is not None:
            contrib = np.zeros_like(self.channel_contrib)
            for key, c in self.channel_index.items():
                contrib[:, c, :] = self.channel_contrib[:, c, :] - other.contrib_of(key)
        return PropagationResult(dict(self.subentity_index), dict(self.channel_index), z, contrib,
                                 self.channels, self.step_days)

    @staticmethod
    def concat(results: list[PropagationResult]) -> PropagationResult:
        """Concatenate samples of runs over (possibly) different subentity sets."""
        sids: list[str] = []
        for r in results:
            for s in r.subentity_index:
                if s not in sids:
                    sids.append(s)
        keys: list[str] = []
        for r in results:
            for k in r.channel_index:
                if k not in keys:
                    keys.append(k)
        steps = max(r.z.shape[2] for r in results)
        zs, cs = [], []
        for r in results:
            z = np.zeros((r.z.shape[0], len(sids), steps))
            for j, s in enumerate(sids):
                z[:, j, : r.z.shape[2]] = r.z_of(s)
            zs.append(z)
            c = np.zeros((r.z.shape[0], len(keys), steps))
            for j, k in enumerate(keys):
                c[:, j, : r.z.shape[2]] = r.contrib_of(k)
            cs.append(c)
        return PropagationResult({s: i for i, s in enumerate(sids)}, {k: i for i, k in enumerate(keys)},
                                 np.concatenate(zs, axis=0), np.concatenate(cs, axis=0),
                                 None, results[0].step_days if results else 7.0)


class Propagator(ABC):
    @abstractmethod
    def propagate(self, system: PropagationSystem, shocks: list[ShockInput], n_samples: int,
                  rng: np.random.Generator, *, record_contributions: bool = False,
                  exogenous: dict[str, np.ndarray] | None = None) -> PropagationResult: ...


registry("propagator", Propagator)


def _cfg(config: Any, path: str, default: Any) -> Any:
    cur = config
    for part in path.split("."):
        if cur is None:
            return default
        cur = getattr(cur, part, None) if not isinstance(cur, dict) else cur.get(part)
    return default if cur is None else cur


class _Params:
    """Per-run parameter draws (or means) for every channel."""

    def __init__(self, S: int, C: int, W: int) -> None:
        self.exists = np.ones((S, C))
        self.beta = np.zeros((S, C))
        self.g_rev = np.zeros((S, C, W))
        self.mods: list[tuple[int, int, str, np.ndarray, float | None]] = []   # (channel, mod idx, form, gamma, thr)


@register("propagator", "mc_impulse")
class McImpulsePropagator(Propagator):
    """Monte Carlo simulation of the dynamic linear model (D7)."""

    deterministic = False

    def __init__(self, config: Any = None, *, min_delay_steps: float | None = None,
                 moderator_clip: tuple[float, float] | list[float] | None = None,
                 kernel_window_steps: int | None = None, include_level_noise: bool | None = None,
                 level_process_noise: float | None = None, drift_damping: float | None = None) -> None:
        self.min_delay_steps = float(min_delay_steps if min_delay_steps is not None
                                     else _cfg(config, "propagation.min_delay_steps", 1))
        clip = moderator_clip if moderator_clip is not None else _cfg(config, "propagation.moderator_clip", [0.0, 3.0])
        self.moderator_clip = (float(clip[0]), float(clip[1]))
        self.window = int(kernel_window_steps if kernel_window_steps is not None
                          else _cfg(config, "propagation.kernel_window_steps", 104))
        self.include_level_noise = bool(include_level_noise if include_level_noise is not None
                                        else _cfg(config, "propagation.include_level_noise", True))
        self.level_process_noise = float(level_process_noise if level_process_noise is not None
                                         else _cfg(config, "learning.level_process_noise", 0.10))
        self.drift_damping = float(drift_damping if drift_damping is not None
                                   else _cfg(config, "prefill.drift_damping", 0.9))

    # -- parameter draws -------------------------------------------------------------------
    def _draw(self, system: PropagationSystem, idx: dict[str, int], S: int,
              rng: np.random.Generator) -> _Params:
        W = self.window
        chans = system.channels
        P = _Params(S, len(chans), W)
        sd = system.step_days
        for c, ch in enumerate(chans):
            key = ch.channel_key
            dyn = ch.dynamics
            if self.deterministic:
                P.exists[:, c] = float(ch.forced) if ch.forced is not None else ch.existence.mean()
                P.beta[:, c] = dyn.effect.mean()
                d, l, dur = dyn.kernel.means()
                d_s = np.full(S, max(d / sd, self.min_delay_steps))
                l_s = np.full(S, l / sd)
                D_s = np.full(S, np.inf if dur is None else dur / sd)
            else:
                if ch.forced is not None:
                    P.exists[:, c] = float(ch.forced)
                else:
                    p = ch.existence.sample(S, substream(rng, key, "p"))
                    u = substream(rng, key, "u").random(S)
                    P.exists[:, c] = (u < p).astype(float)
                P.beta[:, c] = dyn.effect.sample(S, substream(rng, key, "effect"))
                d_s = np.maximum(dyn.kernel.delay.sample(S, substream(rng, key, "delay")) / sd,
                                 self.min_delay_steps)
                l_s = dyn.kernel.lag.sample(S, substream(rng, key, "lag")) / sd
                if dyn.kernel.duration is None:
                    D_s = np.full(S, np.inf)
                else:
                    D_s = dyn.kernel.duration.sample(S, substream(rng, key, "duration")) / sd
            g = step_response_batch(d_s, l_s, D_s, W)               # [S, W + 1]
            P.g_rev[:, c, :] = g[:, 1:][:, ::-1]                      # tau = W..1
            for k, par in enumerate(ch.parameters):
                if par.moderator_id not in idx:
                    continue
                if self.deterministic:
                    gam = np.full(S, par.coefficient.mean())
                else:
                    gam = par.coefficient.sample(S, substream(rng, key, "mod", k))
                P.mods.append((c, idx[par.moderator_id], str(par.form), gam, par.threshold))
        return P

    def _multipliers(self, P: _Params, z_prev: np.ndarray, S: int, C: int) -> tuple[np.ndarray, list]:
        m = np.ones((S, C))
        additive = []
        lo, hi = self.moderator_clip
        for c, mi, form, gam, thr in P.mods:
            zm = z_prev[:, mi]
            if form == ParameterForm.MULTIPLICATIVE:
                m[:, c] *= np.clip(1.0 + gam * zm, lo, hi)
            elif form == ParameterForm.THRESHOLD:
                m[:, c] *= (zm > (thr if thr is not None else 0.0)).astype(float)
            else:
                additive.append((c, gam * zm))
        return m, additive

    # -- simulation ------------------------------------------------------------------------
    def propagate(self, system: PropagationSystem, shocks: list[ShockInput], n_samples: int,
                  rng: np.random.Generator, *, record_contributions: bool = False,
                  exogenous: dict[str, np.ndarray] | None = None) -> PropagationResult:
        S = 1 if self.deterministic else max(int(n_samples), 1)
        H = int(system.horizon_steps)
        W = self.window
        subs: list[str] = list(dict.fromkeys(system.subentity_ids))
        extra = [ch.source_id for ch in system.channels] + [ch.target_id for ch in system.channels]
        extra += [p.moderator_id for ch in system.channels for p in ch.parameters]
        extra += [s.subentity_id for s in shocks]
        for sid in extra:
            if sid not in subs:
                subs.append(sid)
        idx = {sid: i for i, sid in enumerate(subs)}
        N, C = len(subs), len(system.channels)
        P = self._draw(system, idx, S, rng)

        src = np.array([idx[ch.source_id] for ch in system.channels], dtype=int)
        tgt = np.array([idx[ch.target_id] for ch in system.channels], dtype=int)
        onehot = np.zeros((C, N))
        if C:
            onehot[np.arange(C), tgt] = 1.0

        # history of increments, positions p = t + W for t in [-W, H]
        dz = np.zeros((S, N, W + H + 1))
        z = np.zeros((S, N, H + 1))
        drift = np.zeros(N)
        lvl_sd = np.full(N, self.level_process_noise)
        for sid, init in system.initial.items():
            i = idx.get(sid)
            if i is None:
                continue
            past = np.asarray(init.past_dz[-W:], dtype=float) if init.past_dz else np.zeros(0)
            if past.size:
                dz[:, i, W - past.size + 1: W + 1] = past[None, :]
            z[:, i, 0] = init.z_now
            drift[i] = init.drift
            if init.level_noise is not None:
                lvl_sd[i] = init.level_noise

        def contributions(t: int, m: np.ndarray) -> np.ndarray:
            if C == 0:
                return np.zeros((S, 0))
            hist = dz[:, src, t: t + W]                                  # [S, C, W]: tau = W..1
            conv = np.einsum("scw,scw->sc", hist, P.g_rev, optimize=False)
            return P.exists * P.beta * m * conv

        m0, add0 = self._multipliers(P, z[:, :, 0], S, C)
        contrib0 = contributions(0, m0)
        a = z[:, :, 0] - contrib0 @ onehot
        for c, val in add0:
            a[:, tgt[c]] -= val

        # level noise: per-subentity streams of shape [S, H] (prefix-consistent in S)
        noise = np.zeros((S, N, H))
        if self.include_level_noise and not self.deterministic and H > 0:
            for sid, i in idx.items():
                noise[:, i, :] = substream(rng, "level", sid).standard_normal((S, H))

        # shocks
        u = np.zeros((S, N, H + 1))
        hold = np.zeros((N, H + 1), dtype=bool)
        hold_val = np.zeros((S, N, H + 1))
        for k, sh in enumerate(shocks):
            i = idx[sh.subentity_id]
            if self.deterministic or sh.size_sd <= 0:
                size = np.full(S, sh.size)
            else:
                size = sh.size + sh.size_sd * substream(rng, "shock", sh.subentity_id, k).standard_normal(S)
            start = max(int(sh.start_step), 1)
            if start > H:
                continue
            if sh.intervention:
                end = H + 1 if sh.hold_steps is None else min(H + 1, start + int(sh.hold_steps))
                hold[i, start:end] = True
                hold_val[:, i, start:end] += size[:, None]
            elif sh.persistence == Persistence.PULSE:
                u[:, i, start] += size
            else:
                u[:, i, start:] += size[:, None]

        exo = np.zeros((S, N, H + 1))
        if exogenous:
            for sid, arr in exogenous.items():
                i = idx.get(sid)
                if i is None:
                    continue
                arr = np.asarray(arr, dtype=float)
                if arr.ndim == 1:
                    arr = np.broadcast_to(arr, (S, arr.shape[0]))
                n = min(arr.shape[1], H + 1)
                exo[:, i, :n] += arr[:S, :n]

        contrib_rec = np.zeros((S, C, H + 1)) if record_contributions else None
        if contrib_rec is not None:
            contrib_rec[:, :, 0] = contrib0
        z_now = z[:, :, 0].copy()
        for t in range(1, H + 1):
            a = a + drift[None, :] * (self.drift_damping ** t)
            if self.include_level_noise and not self.deterministic:
                a = a + lvl_sd[None, :] * noise[:, :, t - 1]
            m, add = self._multipliers(P, z[:, :, t - 1], S, C)
            contrib = contributions(t, m)
            inflow = contrib @ onehot if C else np.zeros((S, N))
            for c, val in add:
                inflow[:, tgt[c]] += val
            zt = a + u[:, :, t] + inflow + exo[:, :, t]
            if hold[:, t].any():
                held = hold[:, t]
                zt[:, held] = z_now[:, held] + hold_val[:, held, t]
            dz[:, :, W + t] = zt - z[:, :, t - 1]
            z[:, :, t] = zt
            if contrib_rec is not None:
                contrib_rec[:, :, t] = contrib
        cindex = {ch.channel_key: c for c, ch in enumerate(system.channels)}
        return PropagationResult(idx, cindex, z, contrib_rec, list(system.channels), system.step_days)


@register("propagator", "deterministic_mean")
class DeterministicMeanPropagator(McImpulsePropagator):
    """One sample, at mean parameters, with existence fixed at its mean and no level noise."""

    deterministic = True
