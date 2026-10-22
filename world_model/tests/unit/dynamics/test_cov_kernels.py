"""Kernel recursions: copies, warm starts at a kernel's means, warm starts mid-history, batched tails."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axelrod_wm.dynamics.kernels import (
    KernelRecursion,
    mean_kernel_days,
    phi_direct,
    phi_recursive,
    warm_start_batch,
)
from axelrod_wm.model.temporal import KernelSpec
from tests.unit.dynamics.kit import tiny_engine


def _series(z):
    eng = tiny_engine(z={"a.x": list(z)})
    return eng.wm.deviations.series("a.x")


def test_advanced_returns_a_moved_copy():
    rng = np.random.default_rng(3)
    z = rng.normal(size=40)
    series = _series(z)
    rec = KernelRecursion.warm_start(3, 4, 0.9, series, 20)
    nxt = rec.advanced(series, 20)
    assert nxt is not rec and rec.phi() == pytest.approx(phi_direct(3, 4, 0.9, z)[20])
    assert nxt.phi() == pytest.approx(phi_direct(3, 4, 0.9, z)[21])


def test_for_kernel_uses_the_mean_parameters_scaled():
    rng = np.random.default_rng(4)
    z = rng.normal(size=60)
    series = _series(z)
    k = KernelSpec.model_validate({"delay_days": 3, "lag_days": 5, "duration_days": 20})
    rec = KernelRecursion.for_kernel(k, series, 50)
    assert (rec.d, rec.l, rec.lam) == (3, 5, pytest.approx(math.exp(-3 / 20)))
    assert rec.phi() == pytest.approx(phi_direct(3, 5, math.exp(-3 / 20), z)[50])
    twice = KernelRecursion.for_kernel(k, series, 50, min_delay=2, multiplier=2.0)
    assert (twice.d, twice.l) == (6, 10) and twice.lam == pytest.approx(math.exp(-3 / 40))
    perm = KernelRecursion.for_kernel(KernelSpec.model_validate({"delay_days": 3, "lag_days": 5}), series, 50,
                                      multiplier=2.0)
    assert perm.lam == 1.0 and perm.T == 0.0
    assert mean_kernel_days(k, multiplier=2.0) == (6, 10, pytest.approx(math.exp(-3 / 40)))


def test_phi_recursive_warm_started_mid_history_matches_direct():
    rng = np.random.default_rng(5)
    z = rng.normal(size=80)
    full = phi_direct(2, 3, 0.8, z)
    part = phi_recursive(2, 3, 0.8, z, t0=30)
    assert np.allclose(part, full[30:])
    assert phi_recursive(2, 3, 0.8, z, t0=100).size == 0


def test_warm_start_batch_skips_columns_whose_tail_starts_past_the_history():
    hist_rev = np.array([[1.0, 2.0, 3.0, 4.0]])
    d = np.array([[3, 1]])
    l = np.array([[2, 1]])
    lam = np.array([[0.5, 0.5]])
    S, T = warm_start_batch(d, l, lam, hist_rev, np.array([0, 0]))
    # column 0: boxcar on lags 3..4 (only lag 3 is kept); its tail starts at lag 5, beyond the history
    assert S[0, 0] == 4.0 and T[0, 0] == 0.0
    # column 1: boxcar on lag 1; tail from lag 2: -(1 - .5) * (3 + .5 * 4)
    assert S[0, 1] == 2.0 and T[0, 1] == pytest.approx(-0.5 * (3.0 + 0.5 * 4.0))
