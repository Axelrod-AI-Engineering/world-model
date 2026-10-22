"""Scoring metrics: CRPS, pinball loss, interval coverage, sign probabilities."""

from __future__ import annotations

import math

import numpy as np

from axelrod_wm.model.distributions import QUANTILE_LEVELS, DistSummary


def crps_samples(samples: np.ndarray, y: float) -> float:
    """CRPS of an empirical distribution: E|X - y| - 0.5 E|X - X'|."""
    x = np.sort(np.asarray(samples, dtype=float).ravel())
    n = x.size
    if n == 0:
        return float("nan")
    term1 = float(np.mean(np.abs(x - y)))
    i = np.arange(1, n + 1)
    term2 = float(np.sum((2 * i - n - 1) * x)) / (n * n)
    return term1 - term2


def pinball(q: float, level: float, y: float) -> float:
    d = y - q
    return max(level * d, (level - 1.0) * d)


def crps_quantiles(s: DistSummary, y: float) -> float:
    """Approximate CRPS as twice the mean pinball loss over the stored quantile levels."""
    qs = s.quantiles()
    return 2.0 * float(np.mean([pinball(q, lv, y) for q, lv in zip(qs, QUANTILE_LEVELS)]))


def covered(s: DistSummary, y: float, band: str) -> bool:
    lo, hi = {"50": (s.q25, s.q75), "80": (s.q10, s.q90), "90": (s.q05, s.q95)}[band]
    return lo <= y <= hi


def prob_positive(s: DistSummary) -> float:
    """P(X > 0) by linear interpolation of the CDF through the stored quantiles."""
    qs = s.quantiles()
    levels = list(QUANTILE_LEVELS)
    if 0.0 <= qs[0]:
        return 1.0 - levels[0] * (0.0 if qs[0] > 0 else 1.0)
    if 0.0 >= qs[-1]:
        return 1.0 - levels[-1] if qs[-1] >= 0 else 0.0
    for (q0, l0), (q1, l1) in zip(zip(qs[:-1], levels[:-1]), zip(qs[1:], levels[1:])):
        if q0 <= 0.0 <= q1:
            f = l0 if q1 == q0 else l0 + (l1 - l0) * (0.0 - q0) / (q1 - q0)
            return 1.0 - f
    return 0.5


def finite(x: float) -> bool:
    return x is not None and math.isfinite(x)
