"""O(1)-per-day kernel regressors (§6.4).

A channel's regressor is phi(t) = sum_{tau>=1} g(tau) * dz_src(t - tau). With the linear ramp and
the geometric tail of `step_response`, summing by parts gives phi(t) = sum_tau h(tau) * z_src(t - tau),
where h is a boxcar of height 1/l on [d, d + l - 1] followed by the tail -(1 - lam) * lam**(tau - d - l).
So phi(t) = S(t) / l + T(t) with two running sums:

    S(t+1) = S(t) + z(t + 1 - d) - z(t + 1 - d - l)
    T(t+1) = lam * T(t) - (1 - lam) * z(t + 1 - d - l)

and z = 0 before the history starts. Daily propagation, the fold's regressors, and the Monte Carlo
forecasts all use this, so every channel costs O(1) per day.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.model.temporal import KernelSpec, kernel_days

if TYPE_CHECKING:
    from axelrod_wm.memory.working import DeviationSeries

# DECISION: the tail of a warm start is summed back to the start of the kept history, or until
# lam**k drops below this (the rest of a decaying tail is negligible).
TAIL_EPS = 1e-12


class KernelRecursion(BaseModel):
    """O(1)-per-day evaluation of a channel's regressor (see the module docstring)."""

    model_config = ConfigDict(extra="forbid")

    d: int
    l: int
    lam: float
    S: float = 0.0
    T: float = 0.0

    def phi(self) -> float:
        return self.S / self.l + self.T

    def advance(self, z_history: DeviationSeries, t: int) -> None:
        """Move from day t to t + 1."""
        a = z_history[t + 1 - self.d]
        b = z_history[t + 1 - self.d - self.l]
        self.S = self.S + a - b
        self.T = self.lam * self.T - (1.0 - self.lam) * b

    def advanced(self, z_history: DeviationSeries, t: int) -> KernelRecursion:
        """A copy moved from day t to t + 1 (stored states change only through the mutator)."""
        out = self.model_copy()
        out.advance(z_history, t)
        return out

    @classmethod
    def warm_start(cls, d: int, l: int, lam: float, z_history: DeviationSeries, t: int) -> KernelRecursion:
        """Build S and T for day t directly from the history (used after a kernel changes)."""
        d = max(1, int(d))
        l = max(1, int(l))
        S = 0.0
        for tau in range(d, d + l):
            S += z_history[t - tau]
        T = 0.0
        if lam < 1.0:
            first = z_history.first_day
            k = 0
            w = 1.0
            acc = 0.0
            while True:
                day = t - d - l - k
                if day < first or w < TAIL_EPS:
                    break
                acc += w * z_history[day]
                w *= lam
                k += 1
            T = -(1.0 - lam) * acc
        return cls(d=d, l=l, lam=float(lam), S=S, T=T)

    @classmethod
    def for_kernel(cls, kernel: KernelSpec, z_history: DeviationSeries, t: int, min_delay: int = 1,
                   multiplier: float = 1.0) -> KernelRecursion:
        """Warm start at the kernel's mean parameters (optionally scaled by `multiplier`)."""
        d, l, dur = kernel.means()
        dd, ll, lam = kernel_days(d * multiplier, l * multiplier,
                                  None if dur is None else dur * multiplier, min_delay)
        return cls.warm_start(dd, ll, lam, z_history, t)


def mean_kernel_days(kernel: KernelSpec, min_delay: int = 1, multiplier: float = 1.0) -> tuple[int, int, float]:
    d, l, dur = kernel.means()
    return kernel_days(d * multiplier, l * multiplier, None if dur is None else dur * multiplier, min_delay)


def phi_direct(d: int, l: int, lam: float, z: np.ndarray) -> np.ndarray:
    """phi(t) for t = 0..len(z) - 1 by the direct convolution with `step_response`, given z for
    days 0.. (z = 0 before day 0). The reference the recursion is tested against."""
    n = len(z)
    g = np.zeros(n + 1)
    tau = np.arange(n + 1)
    rising = (tau >= d) & (tau <= d + l - 1)
    g[rising] = (tau[rising] - d + 1) / l
    after = tau >= d + l
    g[after] = lam ** (tau[after] - (d + l - 1)).astype(float)
    dz = np.diff(np.concatenate([[0.0], np.asarray(z, dtype=float)]))
    out = np.zeros(n)
    for t in range(1, n):
        k = np.arange(1, t + 1)
        out[t] = float(np.dot(g[k], dz[t - k]))
    return out


def phi_recursive(d: int, l: int, lam: float, z: np.ndarray, t0: int = 0) -> np.ndarray:
    """phi(t) for t = t0..len(z) - 1 by the recursion, given z for days 0.. (z = 0 before day 0)."""
    z = np.asarray(z, dtype=float)
    n = len(z)

    def zat(day: int) -> float:
        return float(z[day]) if 0 <= day < n else 0.0

    S = sum(zat(t0 - tau) for tau in range(d, d + l))
    T = 0.0
    if lam < 1.0:
        acc, w, k = 0.0, 1.0, 0
        while t0 - d - l - k >= 0 and w >= TAIL_EPS:
            acc += w * zat(t0 - d - l - k)
            w *= lam
            k += 1
        T = -(1.0 - lam) * acc
    out = np.zeros(max(n - t0, 0))
    for i, t in enumerate(range(t0, n)):
        out[i] = S / l + T
        a, b = zat(t + 1 - d), zat(t + 1 - d - l)
        S += a - b
        T = lam * T - (1.0 - lam) * b
    return out


# ---------------------------------------------------------------------------------------------
# Vectorized recursions for Monte Carlo propagation (§8.5)
# ---------------------------------------------------------------------------------------------

def warm_start_batch(d: np.ndarray, l: np.ndarray, lam: np.ndarray, hist_rev: np.ndarray,
                     src: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """S and T at day 0 for every (sample, channel).

    d, l, lam: [S, C] sampled integer delay and lag and tail factor.
    hist_rev:  [N, K] the real history of each source, newest first: hist_rev[i, k] = z_i(-k).
    src:       [C] the history row of each channel's source.
    Returns S, T of shape [S, C]."""
    n_src, K = hist_rev.shape
    S_, C = d.shape
    # prefix sums over lags: cs[i, k] = sum_{j < k} z_i(-j)
    cs = np.zeros((n_src, K + 1))
    np.cumsum(hist_rev, axis=1, out=cs[:, 1:])
    lo = np.clip(d, 0, K)
    hi = np.clip(d + l, 0, K)
    rows = np.broadcast_to(src[None, :], d.shape)
    S = cs[rows, hi] - cs[rows, lo]
    T = np.zeros_like(S)
    decaying = lam < 1.0
    if np.any(decaying):
        cols = np.nonzero(decaying.any(axis=0))[0]
        for c in cols:
            mask = decaying[:, c]
            start = (d[mask, c] + l[mask, c])                  # tau where the tail starts
            lam_c = lam[mask, c]
            z = hist_rev[src[c]]
            # sum_k lam^k z(-(start + k)), truncated at the history start
            max_k = int(K - start.min()) if K > start.min() else 0
            if max_k <= 0:
                continue
            k = np.arange(max_k)
            idx = start[:, None] + k[None, :]                  # [m, max_k]
            valid = idx < K
            vals = np.where(valid, z[np.clip(idx, 0, K - 1)], 0.0)
            w = lam_c[:, None] ** k[None, :]
            T[mask, c] = -(1.0 - lam_c) * np.sum(w * vals, axis=1)
    return S, T
