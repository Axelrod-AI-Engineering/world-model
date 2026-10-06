"""The daily model (§8.6.1, §8.6.2): predict, the kalman_edge fold, and record, on data simulated
from the model's own daily equations."""

from __future__ import annotations

import numpy as np

from axelrod_wm.core.distributions import Beta, Gaussian, from_link
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.interaction import EdgeDynamics, Interaction
from axelrod_wm.core.temporal import KernelSpec
from axelrod_wm.engine.kernels import phi_recursive
from tests.conftest import constructed_engine, observe_event, run_days

OIL, GAS, CPI = "resources_energy.oil_price", "resources_energy.gas_price", "inflation.headline_cpi"
FAST = {"delay_days": 7, "lag_days": 7, "duration_days": None}


def _native(eng, sid, z):
    sub = eng.wm.graph.subentities[sid]
    return float(from_link(sub.anchor + sub.scale * z, sub.posterior.link))


def _setup(eng, prior_mu=0.2, fake_mu=0.6):
    from axelrod_wm.engine.daily import ensure_channel_states

    fast = KernelSpec.model_validate(FAST)
    clock = eng.wm.clock
    with eng.mutator.begin("setup", at=clock) as txn:
        txn.update("wm.graph.interactions", "e08",
                   forward=EdgeDynamics(effect=Gaussian(mu=prior_mu, sigma=0.3), kernel=fast))
        txn.add("wm.graph.interactions", Interaction(
            id="fake", source_id=GAS, target_id=CPI, label="fake", origin=Origin.HUMAN,
            existence=Beta(alpha=5, beta=5), forward=EdgeDynamics(effect=Gaussian(mu=fake_mu, sigma=0.1), kernel=fast),
            created_at=clock))
        # the data come from the model itself: these are the true noises
        for sid in (OIL, GAS):
            txn.update("wm.graph.subentities", sid, level_noise=0.2, obs_noise=0.01)
        txn.update("wm.graph.subentities", CPI, level_noise=0.02, obs_noise=0.05)
        ctx = eng.context(learn=True, now=clock)
        for iid in ("e08", "fake"):
            ensure_channel_states(eng.wm.graph.interactions[iid], eng.wm, ctx, txn, day=0)


def _simulate(eng, beta_true=0.8, days=240, seed=0):
    """Daily observations of oil, gas, and CPI from the daily equations; returns CPI's innovations."""
    rng = np.random.default_rng(seed)
    # mean-reverting sources, as in the synthetic world; a random-walk source would make its regressor
    # a slowly moving level that no filter can tell apart from the target's own level
    z_oil = np.zeros(days)
    z_gas = np.zeros(days)
    for t in range(1, days):
        z_oil[t] = 0.95 * z_oil[t - 1] + rng.normal(0, 0.25)
        z_gas[t] = 0.95 * z_gas[t - 1] + rng.normal(0, 0.25)
    level = np.cumsum(rng.normal(0, 0.02, days))
    phi = phi_recursive(7, 7, 1.0, z_oil)
    z_cpi = level + beta_true * phi + rng.normal(0, 0.05, days)
    dev = eng.wm.deviations

    def events(d):
        vals = {OIL: _native(eng, OIL, z_oil[d]), GAS: _native(eng, GAS, z_gas[d]), CPI: _native(eng, CPI, z_cpi[d])}
        return [observe_event(f"GUE-{d}", vals, dev.date_of(d))]

    innovations = []
    for _ in range(days):
        run_days(eng, 1, events)
        d = eng.wm.last_processed_day
        if d > 30:
            innovations.append(dev.point(CPI, d).innovation)
    return np.array(innovations)


def test_daily_fold_learns_effect_existence_and_calibrated_innovations():
    eng = constructed_engine(build=True)
    _setup(eng)
    fake_before = eng.wm.graph.interactions["fake"].existence.mean()
    true_before = eng.wm.graph.interactions["e08"].existence.mean()
    innov = _simulate(eng)
    e08 = eng.wm.graph.interactions["e08"]
    mu, sd = e08.forward.effect.mean(), e08.forward.effect.sd()
    assert abs(mu - 0.8) <= 2 * sd + 1e-9, (mu, sd)
    assert e08.existence.mean() > true_before
    assert eng.wm.graph.interactions["fake"].existence.mean() < fake_before
    assert abs(innov.mean()) < 0.15, innov.mean()
    assert abs(innov.std() - 1.0) < 0.15, innov.std()
    # every processed day has a point for every subentity
    dev = eng.wm.deviations
    for d in range(eng.wm.last_processed_day + 1):
        for sid in eng.wm.graph.subentities:
            assert dev.point(sid, d) is not None


def test_unobserved_subentity_follows_its_parent_and_grows_uncertain():
    """No source reports CPI here; it moves only through daily propagation from oil, and its
    variance grows every day it goes unobserved."""
    eng = constructed_engine(build=True)
    _setup(eng, prior_mu=0.8)
    dev = eng.wm.deviations
    # observe oil at its anchor for 20 days, then 2 sd higher for 40 days; CPI is never observed
    def events(d):
        z = 0.0 if d < 20 else 2.0
        return [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, z)}, dev.date_of(d))]

    run_days(eng, 60, events)
    z_cpi = [dev.point(CPI, d).z for d in range(60)]
    var_cpi = [dev.point(CPI, d).var for d in range(60)]
    assert not any(dev.point(CPI, d).observed for d in range(60))
    assert abs(z_cpi[19]) < 0.05
    assert z_cpi[59] > 1.2                               # about 0.8 * 2 once the 7 + 7 day ramp is done
    assert all(b > a for a, b in zip(var_cpi[20:], var_cpi[21:]))
    # the posterior follows the predicted state
    sub = eng.wm.graph.subentities[CPI]
    m, _ = sub.posterior.link_moments()
    assert abs((m - sub.anchor) / sub.scale - z_cpi[59]) < 1e-6


def test_record_logs_activity_accumulators_and_activations():
    eng = constructed_engine(build=True)
    _setup(eng, prior_mu=0.8)
    dev = eng.wm.deviations
    z_oil = np.array([0.0 if d < 5 else 2.5 for d in range(20)])
    z_cpi = 0.8 * phi_recursive(7, 7, 1.0, z_oil)

    def events(d):
        return [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, z_oil[d]), CPI: _native(eng, CPI, z_cpi[d])},
                              dev.date_of(d))]

    reports = run_days(eng, 20, events)
    # activity: e08's contribution changed by far more than min_edge_contribution
    assert any(r.channel_id == "e08" for r in eng.wm.activity_log.values())
    # episodes carry the day's implied edge effects from the fold accumulators
    ep = eng.ltm.prior_states.episodes[reports[-1].episode_id]
    assert "e08" in ep.edge_effects and ep.edge_effects["e08"][1] > 0
    insts = [i for i in eng.wm.graph.instances.values() if i.pattern_id == "S2"]
    assert insts and insts[0].activation > 0
