"""Distributions: sampling moments, links, link_kalman, refits, JSON round trips (§6.3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from axelrod_wm.core.distributions import (
    DIST_ADAPTER,
    Beta,
    Gamma,
    Gaussian,
    Link,
    LinkKalmanUpdater,
    LogNormal,
    Observation,
    from_link,
    to_link,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("dist", [Gaussian(mu=1.5, sigma=0.7), Beta(alpha=3.0, beta=7.0),
                                  LogNormal(mu=0.3, sigma=0.4), Gamma(k=4.0, theta=2.5)])
def test_sampling_moments(dist):
    x = dist.sample(200_000, np.random.default_rng(1))
    assert abs(x.mean() - dist.mean()) < 0.02 * max(abs(dist.mean()), dist.sd())
    assert abs(x.var() - dist.var()) / dist.var() < 0.03
    qs = dist.quantile(np.array([0.1, 0.5, 0.9]))
    emp = np.quantile(x, [0.1, 0.5, 0.9])
    assert np.allclose(qs, emp, rtol=0.02, atol=0.01 * dist.sd())


@pytest.mark.parametrize("link, x", [(Link.IDENTITY, np.array([-2.0, 0.0, 3.5])),
                                     (Link.LOG, np.array([0.01, 1.0, 250.0])),
                                     (Link.LOGIT, np.array([0.001, 0.5, 0.97]))])
def test_link_round_trips(link, x):
    assert np.allclose(from_link(to_link(x, link), link), x)


def test_link_kalman_matches_closed_form_for_gaussians():
    prior = Gaussian(mu=2.0, sigma=0.5)
    obs = Observation(value=3.0, noise_sd=0.8, observed_at=NOW)
    scale = 0.25
    post = LinkKalmanUpdater().update(prior, obs, scale, process_noise_sd=0.4)
    v = 0.5**2 + (0.4 * scale) ** 2
    r = (0.8 * scale) ** 2
    k = v / (v + r)
    assert post.mu == pytest.approx(2.0 + k * (3.0 - 2.0))
    assert post.sigma**2 == pytest.approx((1 - k) * v)


@pytest.mark.parametrize("dist", [Beta(alpha=9.0, beta=1.0), Beta(alpha=2.0, beta=5.0),
                                  Gamma(k=44.4, theta=0.2), Gamma(k=3.0, theta=4.0)])
def test_beta_and_gamma_refits_within_two_percent(dist):
    m, v = dist.link_moments()
    again = type(dist).from_link_moments(m, v)
    assert again.mean() == pytest.approx(dist.mean(), rel=0.02)
    assert again.var() == pytest.approx(dist.var(), rel=0.02)
    # a Kalman step refits to the delta-method native moments
    post = LinkKalmanUpdater().update(dist, Observation(value=float(dist.mean()) * 1.05, noise_sd=0.5,
                                                        observed_at=NOW), scale=0.1)
    m2, v2 = post.link_moments()
    native_mean = float(from_link(m2, dist.link))
    assert post.mean() == pytest.approx(native_mean, rel=0.02)


def test_shift_moves_in_link_space():
    d = LogNormal(mu=np.log(75.0), sigma=0.08)
    s = LinkKalmanUpdater().shift(d, np.log(1.35))
    assert float(np.exp(s.mu)) == pytest.approx(75.0 * 1.35)


def test_json_round_trip_of_the_union():
    for d in (Gaussian(mu=1, sigma=2), Beta(alpha=2, beta=3), LogNormal(mu=0.1, sigma=0.2), Gamma(k=2, theta=3)):
        text = json.dumps(DIST_ADAPTER.dump_python(d, mode="json"))
        again = DIST_ADAPTER.validate_json(text)
        assert type(again) is type(d) and again == d
