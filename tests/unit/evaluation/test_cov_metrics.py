"""Scoring metrics: CRPS, pinball loss, interval coverage, and the probability of a positive change."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axelrod_wm.evaluation.metrics import (
    covered,
    crps_quantiles,
    crps_samples,
    finite,
    pinball,
    prob_positive,
)
from axelrod_wm.model.distributions import DistSummary


def dist(*qs: float) -> DistSummary:
    q05, q10, q25, q50, q75, q90, q95 = qs
    return DistSummary(mean=q50, sd=1.0, q05=q05, q10=q10, q25=q25, q50=q50, q75=q75, q90=q90, q95=q95)


def test_crps_of_samples():
    assert math.isnan(crps_samples(np.array([]), 0.0))
    assert crps_samples(np.array([2.0]), 0.0) == pytest.approx(2.0)          # a point mass: |x - y|
    # two points {0, 2}, y = 1: E|X-y| = 1, 0.5 E|X-X'| = 0.5
    assert crps_samples(np.array([2.0, 0.0]), 1.0) == pytest.approx(0.5)


def test_pinball_and_quantile_crps():
    assert pinball(1.0, 0.9, 2.0) == pytest.approx(0.9)
    assert pinball(1.0, 0.9, 0.0) == pytest.approx(0.1)
    d = dist(0, 0, 0, 0, 0, 0, 0)
    assert crps_quantiles(d, 0.0) == 0.0
    assert crps_quantiles(d, 1.0) == pytest.approx(2.0 * np.mean([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]))


def test_covered_by_band():
    d = dist(-3, -2, -1, 0, 1, 2, 3)
    assert covered(d, 0.5, "50") and not covered(d, 1.5, "50")
    assert covered(d, 1.5, "80") and not covered(d, 2.5, "80")
    assert covered(d, 2.5, "90") and not covered(d, 3.5, "90")


def test_prob_positive():
    assert prob_positive(dist(1, 2, 3, 4, 5, 6, 7)) == 1.0
    assert prob_positive(dist(0, 2, 3, 4, 5, 6, 7)) == pytest.approx(0.95)        # the lowest quantile at zero
    assert prob_positive(dist(-7, -6, -5, -4, -3, -2, -1)) == 0.0
    assert prob_positive(dist(-7, -6, -5, -4, -3, -2, 0)) == pytest.approx(0.05)  # the highest at zero
    assert prob_positive(dist(-3, -2, -1, 1, 2, 3, 4)) == pytest.approx(1.0 - 0.375)  # halfway from 0.25 to 0.5
    # a flat stretch at zero right after an undefined quantile reads the level where it starts
    assert prob_positive(dist(-1, float("nan"), 0, 0, 1, 2, 3)) == pytest.approx(0.75)
    assert prob_positive(dist(*[float("nan")] * 7)) == 0.5                      # nothing to read


def test_finite():
    assert finite(1.0)
    assert not finite(float("inf")) and not finite(float("nan")) and not finite(None)
