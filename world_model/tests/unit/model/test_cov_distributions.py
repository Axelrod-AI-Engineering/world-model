"""Distributions: summaries, densities, links, closed-form quantiles, and refits (coverage)."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest
from scipy import stats

from axelrod_wm.model.distributions import (
    QUANTILE_LEVELS,
    Beta,
    DistSummary,
    Gamma,
    Gaussian,
    Link,
    LinkKalmanUpdater,
    LogNormal,
    Observation,
    density_of_samples,
    family_link,
    from_link,
    from_link_moments,
    link_derivative_inverse,
    parse_distribution,
    prior_from_native,
    summarize_columns,
    summarize_samples,
    to_link,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_dist_summary_map_applies_a_monotone_map():
    s = Gaussian(mu=1.0, sigma=0.5).summary()
    m = s.map(lambda v: 2.0 * v + 1.0)
    assert m.quantiles() == pytest.approx([2.0 * q + 1.0 for q in s.quantiles()])
    assert m.mean == pytest.approx(3.0)
    assert m.sd == pytest.approx(1.0)        # |f(mu+sd) - f(mu-sd)| / 2 = 2 * sd


def test_summarize_columns_matches_numpy_and_rounds():
    x = np.array([[0.0, 1.0], [1.0, 3.0], [2.0, 5.0], [3.0, 7.0]])
    out = summarize_columns(x, digits=3)
    assert len(out) == 2
    assert out[0].mean == 1.5 and out[1].mean == 4.0
    assert out[0].sd == pytest.approx(round(float(np.std(x[:, 0])), 3))
    assert out[1].q50 == pytest.approx(4.0)
    assert out[0].q05 == pytest.approx(round(float(np.quantile(x[:, 0], 0.05)), 3))


def test_summarize_columns_one_dimensional_and_empty():
    one = summarize_columns(np.array([1.0, 2.0, 3.0]))
    assert len(one) == 1 and one[0].mean == 2.0 and one[0].q50 == 2.0
    empty = summarize_columns(np.zeros((0, 3)))
    assert len(empty) == 3 and all(s.mean == 0.0 and s.q95 == 0.0 for s in empty)


def test_summarize_samples_empty_is_zero():
    s = summarize_samples(np.array([]))
    assert s.quantiles() == [0.0] * 7 and s.mean == 0.0 and s.sd == 0.0


def test_density_of_samples_peaks_at_one_and_rejects_degenerate_input():
    rng = np.random.default_rng(0)
    pts = density_of_samples(rng.normal(size=500), n=11)
    assert len(pts) == 11
    assert max(p[1] for p in pts) == pytest.approx(1.0)
    xs = [p[0] for p in pts]
    assert xs == sorted(xs)
    assert density_of_samples(np.array([1.0])) == []                    # fewer than two finite values
    assert density_of_samples(np.array([np.nan, 2.0])) == []           # the nan is dropped
    assert density_of_samples(np.full(10, 3.0)) == []                  # no spread


def test_to_and_from_link_scalars_and_clipping():
    assert to_link(2.0, "identity") == 2.0 and isinstance(to_link(2.0, "identity"), float)
    assert to_link(math.e, Link.LOG) == pytest.approx(1.0)
    assert to_link(0.0, Link.LOG) == pytest.approx(math.log(1e-12))
    assert to_link(0.5, Link.LOGIT) == pytest.approx(0.0)
    assert to_link(1.0, Link.LOGIT) == pytest.approx(math.log((1 - 1e-9) / 1e-9), rel=1e-6)
    assert from_link(0.0, Link.LOGIT) == pytest.approx(0.5)
    assert from_link(1e6, Link.LOG) == pytest.approx(math.exp(700.0))  # capped
    assert from_link(-1.5, "identity") == -1.5


def test_link_derivative_inverse_matches_numeric_derivative():
    for link, eta in ((Link.IDENTITY, 0.3), (Link.LOG, 0.3), (Link.LOGIT, 0.3)):
        h = 1e-6
        num = (from_link(eta + h, link) - from_link(eta - h, link)) / (2 * h)
        assert link_derivative_inverse(eta, link) == pytest.approx(num, rel=1e-6)
    assert link_derivative_inverse(0.0, "logit") == pytest.approx(0.25)


@pytest.mark.parametrize("dist, ref", [
    (Gaussian(mu=1.5, sigma=0.7), stats.norm(1.5, 0.7)),
    (Beta(alpha=3.0, beta=7.0), stats.beta(3.0, 7.0)),
    (LogNormal(mu=0.3, sigma=0.4), stats.lognorm(0.4, scale=math.exp(0.3))),
    (Gamma(k=4.0, theta=2.5), stats.gamma(4.0, scale=2.5)),
])
def test_closed_forms_against_scipy(dist, ref):
    assert dist.mean() == pytest.approx(ref.mean())
    assert dist.var() == pytest.approx(ref.var())
    assert dist.sd() == pytest.approx(ref.std())
    q = np.asarray(QUANTILE_LEVELS)
    assert np.allclose(dist.quantile(q), ref.ppf(q))
    xs = ref.ppf(np.array([0.2, 0.5, 0.8]))
    assert np.allclose(dist.logpdf(xs), ref.logpdf(xs))
    s = dist.summary()
    assert s.mean == pytest.approx(ref.mean())
    assert s.quantiles() == pytest.approx(list(ref.ppf(q)))
    m, sd = dist.link_summary()
    lm, lv = dist.link_moments()
    assert (m, sd) == pytest.approx((lm, math.sqrt(lv)))
    pts = dist.density_points(n=9)
    assert len(pts) == 9 and max(p[1] for p in pts) == pytest.approx(1.0)
    assert pts[0][0] == pytest.approx(float(ref.ppf(0.005)), rel=1e-5, abs=1e-6)


def test_lognormal_link_moments_are_exact():
    d = LogNormal(mu=0.2, sigma=0.3)
    assert d.link_moments() == (0.2, pytest.approx(0.09))
    again = LogNormal.from_link_moments(0.2, 0.09)
    assert again.mu == 0.2 and again.sigma == pytest.approx(0.3)
    assert LogNormal.from_link_moments(0.0, -1.0).sigma == pytest.approx(1e-6)   # floored variance


def test_gamma_link_moments_and_refit():
    d = Gamma(k=4.0, theta=2.5)
    m, v = d.link_moments()
    assert m == pytest.approx(math.log(10.0)) and v == pytest.approx(0.25)
    g = Gamma.from_link_moments(m, v)
    assert g.k == pytest.approx(4.0) and g.mean() == pytest.approx(10.0)
    assert Gamma.from_link_moments(0.0, 0.0).k == pytest.approx(1e9)            # capped shape


def test_beta_refit_clamps_concentration():
    tight = Beta.from_link_moments(0.0, 1e-20)
    assert tight.alpha + tight.beta == pytest.approx(1e7)
    loose = Beta.from_link_moments(0.0, 1e6)
    assert loose.alpha + loose.beta == pytest.approx(0.5)
    assert loose.mean() == pytest.approx(0.5)


def test_gaussian_with_zero_sigma_has_no_density_picture():
    assert Gaussian(mu=1.0, sigma=0.0).density_points() == []


def test_density_points_handles_failures():
    class Broken(Gaussian):
        def quantile(self, q):
            raise ValueError("no quantiles")

    assert Broken(mu=0.0, sigma=1.0).density_points() == []

    class Flat(Gaussian):
        def logpdf(self, x):
            return np.full(np.shape(x), -np.inf)

    assert Flat(mu=0.0, sigma=1.0).density_points() == []

    class Infinite(Gaussian):
        def quantile(self, q):
            return np.array([0.0, np.inf])

    assert Infinite(mu=0.0, sigma=1.0).density_points() == []


def test_family_link_prior_from_native_and_parse():
    assert family_link("beta") is Link.LOGIT
    assert family_link("gamma") is Link.LOG
    p = prior_from_native("lognormal", 50.0, 0.2)
    assert isinstance(p, LogNormal) and p.mu == pytest.approx(math.log(50.0)) and p.sigma == pytest.approx(0.2)
    g = prior_from_native("gaussian", 3.0, 0.5)
    assert isinstance(g, Gaussian) and g.mu == 3.0 and g.sigma == pytest.approx(0.5)
    b = from_link_moments("beta", 0.0, 0.1)
    assert isinstance(b, Beta) and b.mean() == pytest.approx(0.5)
    assert parse_distribution(g) is g
    parsed = parse_distribution({"family": "gamma", "k": 2.0, "theta": 3.0})
    assert isinstance(parsed, Gamma) and parsed.mean() == 6.0


def test_kalman_update_with_zero_variances_keeps_the_mean():
    prior = Gaussian(mu=1.0, sigma=0.0)
    post = LinkKalmanUpdater().update(prior, Observation(value=5.0, noise_sd=0.0, observed_at=NOW), scale=1.0)
    assert post.mu == pytest.approx(1.0)


def test_shift_adds_extra_variance():
    s = LinkKalmanUpdater().shift(Gaussian(mu=0.0, sigma=1.0), 2.0, extra_var_link=3.0)
    assert s.mu == 2.0 and s.sigma == pytest.approx(2.0)


def test_dist_summary_forbids_extra_fields():
    with pytest.raises(ValueError):
        DistSummary(mean=0, sd=0, q05=0, q10=0, q25=0, q50=0, q75=0, q90=0, q95=0, extra=1)


def test_summarize_samples_matches_numpy():
    x = np.arange(101, dtype=float)
    s = summarize_samples(x.reshape(1, -1))                 # raveled
    assert s.mean == 50.0 and s.q50 == 50.0 and s.q05 == pytest.approx(5.0) and s.q95 == pytest.approx(95.0)
    assert s.sd == pytest.approx(float(np.std(x)))


def test_posterior_updater_interface_stubs_return_nothing():
    from axelrod_wm.model.distributions import PosteriorUpdater

    u = LinkKalmanUpdater()
    g = Gaussian(mu=0.0, sigma=1.0)
    assert PosteriorUpdater.update(u, g, Observation(value=1.0, noise_sd=1.0, observed_at=NOW), 1.0) is None
    assert PosteriorUpdater.shift(u, g, 1.0) is None
