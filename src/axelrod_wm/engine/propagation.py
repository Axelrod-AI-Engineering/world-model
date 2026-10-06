"""Propagation of perturbations along interactions (§8.5, D6, D7).

The default ``mc_impulse`` propagator simulates the same daily model the filter uses (§8.6), forward
from the current state, with Monte Carlo draws of every uncertain parameter. Each channel's regressor
is a kernel recursion (§6.4): every sample and channel warm-starts its running sums from the real
history (shared by all samples) and advances them in O(1) per day, so past events keep unfolding in
every forecast. All random draws come from per-channel and per-subentity substreams of the given
generator, keyed by stable names, so runs with and without shocks (or with different channel sets,
or fewer samples) share common random numbers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import Beta, DistSummary, Link, from_link, summarize_samples
from axelrod_wm.core.interaction import EdgeDynamics, ParameterBinding, ParameterForm
from axelrod_wm.engine.kernels import warm_start_batch
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.rng import substream
from axelrod_wm.events.graph_update import Persistence


class ShockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subentity_id: str
    size: float                    # standardized units
    size_sd: float = 0.0
    start_day: int = 1             # day 0 is now; shocks start on day 1 or later
    persistence: Persistence = Persistence.STEP
    intervention: bool = False     # do(): ignore in-channels of this subentity while held
    hold_days: int | None = None


class Channel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    source_id: str
    target_id: str
    dynamics: EdgeDynamics
    existence: Beta
    parameters: list[ParameterBinding] = []
    forced: bool | None = None     # True/False forces existence on or off (scenarios, absent relations)
    key: str | None = None         # channel key; "<interaction id>:rev" for a reverse channel

    @property
    def channel_key(self) -> str:
        return self.key or self.interaction_id


class InitialState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    z_now: float                       # today's deviation (filtered or predicted)
    drift: float = 0.0                 # per-day trend of the local level (from prefill)
    level_noise: float | None = None   # the subentity's learned level noise; None uses the config


class PropagationSystem(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    subentity_ids: list[str]
    channels: list[Channel]
    horizon_days: int
    initial: dict[str, InitialState] = {}    # missing entries start at z = 0
    history: Any = None                      # DeviationHistory: the real past, shared by every sample (read-only)
    today: int = 0                           # day index of "now" in the history
    min_delay_days: int = 1


class PropagationResult:
    def __init__(self, subentity_index: dict[str, int], channel_index: dict[str, int], z: np.ndarray,
                 channel_contrib: np.ndarray | None, channels: list[Channel] | None = None) -> None:
        self.subentity_index = subentity_index
        self.channel_index = channel_index
        self.z = z                                  # [samples, subentities, horizon_days + 1]; day 0 is now
        self.channel_contrib = channel_contrib      # [samples, channels, horizon_days + 1]
        self.channels = channels or []

    @property
    def n_samples(self) -> int:
        return int(self.z.shape[0])

    @property
    def horizon_days(self) -> int:
        return int(self.z.shape[2]) - 1

    horizon_steps = horizon_days

    def has(self, subentity_id: str) -> bool:
        return subentity_id in self.subentity_index

    def z_of(self, subentity_id: str) -> np.ndarray:
        """[samples, days] standardized deviations (zeros if the subentity is not in the run)."""
        i = self.subentity_index.get(subentity_id)
        if i is None:
            return np.zeros((self.z.shape[0], self.z.shape[2]))
        return self.z[:, i, :]

    def contrib_of(self, channel_key: str) -> np.ndarray:
        c = self.channel_index.get(channel_key)
        if c is None or self.channel_contrib is None:
            return np.zeros((self.z.shape[0], self.z.shape[2]))
        return self.channel_contrib[:, c, :]

    def median_z(self, subentity_id: str, day: int | None = None) -> float:
        zz = self.z_of(subentity_id)
        t = self.horizon_days if day is None else day
        return float(np.median(zz[:, t]))

    def summary(self, subentity_id: str, anchor: float, scale: float, link: Link) -> list[DistSummary]:
        zz = self.z_of(subentity_id).astype(float)
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
        return PropagationResult(dict(self.subentity_index), dict(self.channel_index), z, contrib, self.channels)

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
        days = max(r.z.shape[2] for r in results)
        zs, cs = [], []
        for r in results:
            z = np.zeros((r.z.shape[0], len(sids), days), dtype=r.z.dtype)
            for j, s in enumerate(sids):
                z[:, j, : r.z.shape[2]] = r.z_of(s)
            zs.append(z)
            c = np.zeros((r.z.shape[0], len(keys), days), dtype=r.z.dtype)
            for j, k in enumerate(keys):
                c[:, j, : r.z.shape[2]] = r.contrib_of(k)
            cs.append(c)
        return PropagationResult({s: i for i, s in enumerate(sids)}, {k: i for i, k in enumerate(keys)},
                                 np.concatenate(zs, axis=0), np.concatenate(cs, axis=0), None)


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

    def __init__(self, S: int, C: int) -> None:
        self.exists = np.ones((S, C))
        self.beta = np.zeros((S, C))
        self.d = np.ones((S, C), dtype=np.int64)
        self.l = np.ones((S, C), dtype=np.int64)
        self.lam = np.ones((S, C))
        self.mods: list[tuple[int, int, str, np.ndarray, float | None]] = []   # (channel, mod idx, form, gamma, thr)


def _to_days(x: np.ndarray, floor: int) -> np.ndarray:
    return np.maximum(np.rint(np.asarray(x, dtype=float)), floor).astype(np.int64)


@register("propagator", "mc_impulse")
class McImpulsePropagator(Propagator):
    """Monte Carlo simulation of the daily dynamic linear model (D7)."""

    deterministic = False

    def __init__(self, config: Any = None, *, min_delay_days: int | None = None,
                 moderator_clip: tuple[float, float] | list[float] | None = None,
                 include_level_noise: bool | None = None,
                 level_process_noise: float | None = None, drift_damping: float | None = None) -> None:
        self.min_delay_days = int(min_delay_days if min_delay_days is not None
                                  else _cfg(config, "propagation.min_delay_days", 1))
        clip = moderator_clip if moderator_clip is not None else _cfg(config, "propagation.moderator_clip", [0.0, 3.0])
        self.moderator_clip = (float(clip[0]), float(clip[1]))
        self.include_level_noise = bool(include_level_noise if include_level_noise is not None
                                        else _cfg(config, "propagation.include_level_noise", True))
        self.level_process_noise = float(level_process_noise if level_process_noise is not None
                                         else _cfg(config, "learning.level_process_noise", 0.04))
        self.drift_damping = float(drift_damping if drift_damping is not None
                                   else _cfg(config, "prefill.drift_damping", 0.985))

    # -- parameter draws -------------------------------------------------------------------
    def _draw(self, system: PropagationSystem, idx: dict[str, int], S: int,
              rng: np.random.Generator) -> _Params:
        chans = system.channels
        P = _Params(S, len(chans))
        floor = max(1, int(system.min_delay_days), self.min_delay_days)
        for c, ch in enumerate(chans):
            key = ch.channel_key
            dyn = ch.dynamics
            if self.deterministic:
                P.exists[:, c] = float(ch.forced) if ch.forced is not None else ch.existence.mean()
                P.beta[:, c] = dyn.effect.mean()
                d, l, dur = dyn.kernel.means()
                P.d[:, c] = max(floor, int(round(d)))
                P.l[:, c] = max(1, int(round(l)))
                P.lam[:, c] = 1.0 if dur is None else float(np.exp(-3.0 / max(dur, 1e-9)))
            else:
                if ch.forced is not None:
                    P.exists[:, c] = float(ch.forced)
                else:
                    p = ch.existence.sample(S, substream(rng, key, "p"))
                    u = substream(rng, key, "u").random(S)
                    P.exists[:, c] = (u < p).astype(float)
                P.beta[:, c] = dyn.effect.sample(S, substream(rng, key, "effect"))
                P.d[:, c] = _to_days(dyn.kernel.delay.sample(S, substream(rng, key, "delay")), floor)
                P.l[:, c] = _to_days(dyn.kernel.lag.sample(S, substream(rng, key, "lag")), 1)
                if dyn.kernel.duration is None:
                    P.lam[:, c] = 1.0
                else:
                    D = np.maximum(dyn.kernel.duration.sample(S, substream(rng, key, "duration")), 1e-9)
                    P.lam[:, c] = np.exp(-3.0 / D)
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
        H = int(system.horizon_days)
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

        src = np.array([idx[ch.source_id] for ch in system.channels], dtype=np.int64)
        tgt = np.array([idx[ch.target_id] for ch in system.channels], dtype=np.int64)

        # initial state
        z = np.zeros((S, N, H + 1))
        drift = np.zeros(N)
        lvl_sd = np.full(N, self.level_process_noise)
        for sid, init in system.initial.items():
            i = idx.get(sid)
            if i is None:
                continue
            z[:, i, 0] = init.z_now
            drift[i] = init.drift
            if init.level_noise is not None:
                lvl_sd[i] = init.level_noise

        # the real history of each source, newest first: hist[r, k] = z_src(today - k); hist[r, 0] = z_now
        src_ids = sorted(set(int(x) for x in src))
        row_of = {i: r for r, i in enumerate(src_ids)}
        rows = np.array([row_of[int(i)] for i in src], dtype=np.int64)
        hist_rev = np.zeros((max(len(src_ids), 1), 1))
        if C:
            dl_max = int(np.max(P.d + P.l))
            hist_ = system.history
            today = int(system.today)
            if hist_ is not None:
                first = max(int(getattr(hist_, "first_kept_day", 0)), 0)
                K = max(today - first + 1, 1)
            else:
                K = 1
            K = max(K, 1)
            hist_rev = np.zeros((len(src_ids), K))
            for r, i in enumerate(src_ids):
                sid = subs[i]
                if hist_ is not None:
                    vals = hist_.array(sid, today - K + 1, today)        # oldest .. today
                    hist_rev[r, :] = np.asarray(vals[::-1], dtype=float)
                hist_rev[r, 0] = z[0, i, 0]                              # today's value as given
            S_sum, T_sum = warm_start_batch(P.d, P.l, P.lam, hist_rev, rows)
        else:
            dl_max = 0
            S_sum = np.zeros((S, 0))
            T_sum = np.zeros((S, 0))
        Kh = hist_rev.shape[1]
        s_idx = np.arange(S)[:, None]
        src_b = np.broadcast_to(src[None, :], (S, C)) if C else np.zeros((S, 0), dtype=np.int64)
        rows_b = np.broadcast_to(rows[None, :], (S, C)) if C else np.zeros((S, 0), dtype=np.int64)
        lf = P.l.astype(float)
        one_minus_lam = 1.0 - P.lam

        def z_src(u: np.ndarray) -> np.ndarray:
            """z of each channel's source on day u ([S, C]); history for u <= 0, simulated otherwise."""
            pos = u >= 0
            if pos.all():
                return z[s_idx, src_b, u]
            k = np.clip(-u, 0, Kh - 1)
            past = np.where(-u < Kh, hist_rev[rows_b, k], 0.0)
            if not pos.any():
                return past
            now = z[s_idx, src_b, np.clip(u, 0, H)]
            return np.where(pos, now, past)

        m0, add0 = self._multipliers(P, z[:, :, 0], S, C)
        contrib0 = P.exists * P.beta * m0 * (S_sum / lf + T_sum) if C else np.zeros((S, 0))
        a = z[:, :, 0].copy()
        if C:
            np.add.at(a, (slice(None), tgt), -contrib0)
        for c, val in add0:
            a[:, tgt[c]] -= val

        # level noise: per-subentity streams of shape [S, H] (prefix-consistent in S)
        noise = None
        if self.include_level_noise and not self.deterministic and H > 0:
            noise = np.zeros((S, N, H))
            for sid, i in idx.items():
                noise[:, i, :] = substream(rng, "level", sid).standard_normal((S, H))

        # shocks
        u_in = np.zeros((S, N, H + 1))
        hold = np.zeros((N, H + 1), dtype=bool)
        hold_val = np.zeros((S, N, H + 1))
        for k, sh in enumerate(shocks):
            i = idx[sh.subentity_id]
            if self.deterministic or sh.size_sd <= 0:
                size = np.full(S, sh.size)
            else:
                size = sh.size + sh.size_sd * substream(rng, "shock", sh.subentity_id, k).standard_normal(S)
            start = max(int(sh.start_day), 1)
            if start > H:
                continue
            if sh.intervention:
                end = H + 1 if sh.hold_days is None else min(H + 1, start + int(sh.hold_days))
                hold[i, start:end] = True
                hold_val[:, i, start:end] += size[:, None]
            elif sh.persistence == Persistence.PULSE:
                u_in[:, i, start] += size
            else:
                u_in[:, i, start:] += size[:, None]

        exo = None
        if exogenous:
            exo = np.zeros((S, N, H + 1))
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
        damp = self.drift_damping
        for t in range(1, H + 1):
            if C:
                # advance every channel's running sums from day t - 1 to day t
                va = z_src(t - P.d)
                vb = z_src(t - P.d - P.l) if t <= dl_max + H else z[s_idx, src_b, t - P.d - P.l]
                S_sum = S_sum + va - vb
                T_sum = P.lam * T_sum - one_minus_lam * vb
            a = a + drift[None, :] * (damp ** t)
            if noise is not None:
                a = a + lvl_sd[None, :] * noise[:, :, t - 1]
            zt = a + u_in[:, :, t]
            if exo is not None:
                zt = zt + exo[:, :, t]
            if C:
                m, add = self._multipliers(P, z[:, :, t - 1], S, C)
                contrib = P.exists * P.beta * m * (S_sum / lf + T_sum)
                np.add.at(zt, (slice(None), tgt), contrib)
                for c, val in add:
                    zt[:, tgt[c]] += val
                if contrib_rec is not None:
                    contrib_rec[:, :, t] = contrib
            if hold[:, t].any():
                held = hold[:, t]
                zt[:, held] = z_now[:, held] + hold_val[:, held, t]
            z[:, :, t] = zt
        cindex = {ch.channel_key: c for c, ch in enumerate(system.channels)}
        return PropagationResult(idx, cindex, z, contrib_rec, list(system.channels))


def source_history(system: PropagationSystem, sid: str, z_now: float) -> np.ndarray:
    """The real history of one subentity, newest first (index 0 is today, set to z_now)."""
    hist = system.history
    today = int(system.today)
    if hist is None:
        return np.array([z_now])
    first = max(int(getattr(hist, "first_kept_day", 0)), 0)
    K = max(today - first + 1, 1)
    out = np.asarray(hist.array(sid, today - K + 1, today)[::-1], dtype=float)
    out[0] = z_now
    return out


def contribution_paths(params: _Params, c: int, hist_rev: np.ndarray, src_path: np.ndarray) -> np.ndarray:
    """exists * beta * phi(t), t = 0..H, for one channel and every sample: each sample's recursion is
    warm-started from the real history and advanced along the source's simulated path ([S, H + 1])."""
    S, n_days = src_path.shape
    H = n_days - 1
    d, l, lam = params.d[:, c], params.l[:, c], params.lam[:, c]
    S0, T0 = warm_start_batch(d[:, None], l[:, None], lam[:, None], hist_rev[None, :], np.array([0]))
    s_sum, t_sum = S0[:, 0].copy(), T0[:, 0].copy()
    K = hist_rev.shape[0]
    rows = np.arange(S)
    lf = l.astype(float)

    def z_at(u: np.ndarray) -> np.ndarray:
        past = np.where(-u < K, hist_rev[np.clip(-u, 0, K - 1)], 0.0)
        now = src_path[rows, np.clip(u, 0, H)]
        return np.where(u >= 0, now, past)

    out = np.zeros((S, H + 1))
    out[:, 0] = s_sum / lf + t_sum
    for t in range(1, H + 1):
        va = z_at(t - d)
        vb = z_at(t - d - l)
        s_sum = s_sum + va - vb
        t_sum = lam * t_sum - (1.0 - lam) * vb
        out[:, t] = s_sum / lf + t_sum
    return out * (params.exists[:, c] * params.beta[:, c])[:, None]


@register("propagator", "deterministic_mean")
class DeterministicMeanPropagator(McImpulsePropagator):
    """One sample, at mean parameters, with existence fixed at its mean and no level noise."""

    deterministic = True
