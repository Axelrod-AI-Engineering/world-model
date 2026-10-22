"""Kernels on the daily grid: the step response, the O(1) recursion, and the minimum delay (§6.4)."""

from __future__ import annotations

import numpy as np

from axelrod_wm.dynamics.kernels import KernelRecursion, phi_direct, phi_recursive, warm_start_batch
from axelrod_wm.dynamics.propagation import (
    Channel,
    DeterministicMeanPropagator,
    PropagationSystem,
    ShockInput,
)
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec, kernel_days, step_response


class _Series:
    """A DeviationSeries stand-in over an array of days 0..n-1 (0 before day 0 and after the end)."""

    def __init__(self, z: np.ndarray, first_day: int = 0) -> None:
        self.z = np.asarray(z, dtype=float)
        self.first_day = first_day

    def __getitem__(self, day: int) -> float:
        return float(self.z[day]) if 0 <= day < len(self.z) else 0.0


def test_zero_before_delay_peak_at_delay_plus_lag_minus_one():
    g = step_response(14, 28, 70.0, 200)
    assert np.all(g[:14] == 0.0)
    assert g[14] == 1.0 / 28                     # the ramp starts at the delay
    assert np.argmax(g) == 14 + 28 - 1           # peak 1 at d + l - 1
    assert g[41] == 1.0
    assert np.all(np.diff(g[41:]) < 0)           # fades over the duration
    assert abs(g[41 + 70] - np.exp(-3.0)) < 1e-12   # about 95% gone after one duration


def test_permanent_when_duration_is_none():
    g = step_response(7, 14, None, 60)
    assert np.all(g[20:] == 1.0)


def test_kernel_days_rounds_and_floors():
    assert kernel_days(0.2, 0.0, None) == (1, 1, 1.0)          # delay at least one day, lag at least one
    d, l, lam = kernel_days(7.4, 29.6, 30.0, min_delay=1)
    assert (d, l) == (7, 30) and abs(lam - np.exp(-0.1)) < 1e-12
    assert kernel_days(3, 5, None, min_delay=5)[0] == 5


def test_shorthand_turns_means_into_gammas():
    k = KernelSpec.model_validate({"delay_days": 7, "lag_days": 30, "duration_days": None})
    assert k.means() == (7.0, 30.0, None)
    assert abs(k.delay.sd() / k.delay.mean() - 0.3) < 1e-9


def test_recursion_matches_direct_convolution_on_random_histories():
    rng = np.random.default_rng(3)
    for d, l, dur in [(1, 1, None), (7, 30, None), (14, 60, 270.0), (3, 5, 10.0), (45, 30, None)]:
        z = np.cumsum(rng.normal(0, 0.3, 400))
        lam = 1.0 if dur is None else float(np.exp(-3.0 / dur))
        direct = phi_direct(d, l, lam, z)
        rec = phi_recursive(d, l, lam, z)
        assert np.max(np.abs(direct - rec)) < 1e-9


def test_warm_start_matches_and_advances():
    rng = np.random.default_rng(5)
    z = np.cumsum(rng.normal(0, 0.4, 300))
    series = _Series(z)
    for d, l, dur in [(7, 30, None), (14, 60, 270.0), (2, 3, 20.0)]:
        lam = 1.0 if dur is None else float(np.exp(-3.0 / dur))
        direct = phi_direct(d, l, lam, z)
        r = KernelRecursion.warm_start(d, l, lam, series, 150)
        assert abs(r.phi() - direct[150]) < 1e-9
        for t in range(150, 250):
            r.advance(series, t)
            assert abs(r.phi() - direct[t + 1]) < 1e-9


def test_warm_start_batch_matches_scalar_warm_starts():
    rng = np.random.default_rng(7)
    hist = np.cumsum(rng.normal(0, 0.3, (3, 200)), axis=1)      # 3 sources, days 0..199
    today = 199
    hist_rev = hist[:, ::-1]                                       # newest first: hist_rev[i, k] = z_i(today - k)
    d = np.array([[3, 7], [5, 1]])
    l = np.array([[10, 2], [4, 30]])
    lam = np.array([[1.0, np.exp(-0.1)], [np.exp(-0.3), 1.0]])
    src = np.array([0, 2])
    S, T = warm_start_batch(d, l, lam, hist_rev, src)
    for s in range(2):
        for c in range(2):
            r = KernelRecursion.warm_start(int(d[s, c]), int(l[s, c]), float(lam[s, c]), _Series(hist[src[c]]), today)
            assert abs(S[s, c] - r.S) < 1e-9 and abs(T[s, c] - r.T) < 1e-9


def test_minimum_delay_enforced():
    """A kernel with no delay and no lag still acts one day later (min_delay_days = 1)."""
    dyn = EdgeDynamics(effect=Gaussian(mu=1.0, sigma=0.0),
                       kernel=KernelSpec.model_validate({"delay_days": 0, "lag_days": 0, "duration_days": None}))
    ch = Channel(interaction_id="x", source_id="a", target_id="b", dynamics=dyn, existence=Beta(alpha=1e6, beta=1.0),
                 forced=True)
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[ch], horizon_days=5)
    res = DeterministicMeanPropagator(include_level_noise=False).propagate(
        system, [ShockInput(subentity_id="a", size=1.0, start_day=1)], 1, np.random.default_rng(0))
    zb = res.z_of("b")[0]
    assert zb[1] == 0.0 and abs(zb[2] - 1.0) < 1e-12
