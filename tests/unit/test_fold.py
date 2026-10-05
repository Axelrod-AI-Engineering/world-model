"""The kalman_edge fold (§8.6), on data simulated from the model it filters."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from axelrod_wm.core.distributions import Beta, Gaussian, from_link
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.interaction import EdgeDynamics, Interaction
from axelrod_wm.core.temporal import KernelSpec, step_response
from tests.conftest import START, constructed_engine, real_event

OIL, GAS, CPI = "resources_energy.oil_price", "resources_energy.gas_price", "inflation.headline_cpi"


def _native(eng, sid, z):
    sub = eng.wm.graph.subentities[sid]
    return float(from_link(sub.anchor + sub.scale * z, sub.posterior.link))


def _setup(eng, prior_mu=0.2, fake_mu=0.6):
    fast = KernelSpec.model_validate({"delay_days": 7, "lag_days": 7, "duration_days": None})
    with eng.mutator.begin("setup", now=START) as txn:
        e08 = eng.wm.graph.interactions["e08"]
        txn.update("interactions", "e08", forward=EdgeDynamics(effect=Gaussian(mu=prior_mu, sigma=0.3), kernel=fast))
        txn.add("interactions", Interaction(
            id="fake", source_id=GAS, target_id=CPI, label="fake", origin=Origin.HUMAN,
            existence=Beta(alpha=5, beta=5), forward=EdgeDynamics(effect=Gaussian(mu=fake_mu, sigma=0.1), kernel=fast),
            created_at=START))
        # the sources move 0.6 sd per step; the model's level noise says so (data from the model itself)
        for sid in (OIL, GAS):
            txn.update("subentities", sid, level_noise=0.6, obs_noise=0.01)
        assert e08.existence.mean() > 0.85


def _simulate(eng, beta_true=0.8, steps=150, seed=0):
    """Weekly observations from the model's own equations (level random walk + beta * phi + noise)."""
    rng = np.random.default_rng(seed)
    g = step_response(7, 7, None, 104, 7)
    z_oil = np.zeros(steps)
    z_gas = np.zeros(steps)
    for t in range(1, steps):          # mean-reverting sources, as in the synthetic world
        z_oil[t] = 0.5 * z_oil[t - 1] + rng.normal(0, 0.6)
        z_gas[t] = 0.5 * z_gas[t - 1] + rng.normal(0, 0.6)
    level = np.cumsum(rng.normal(0, 0.10, steps))
    dz = np.diff(z_oil, prepend=z_oil[0])
    innovations = []
    for t in range(steps):
        phi = sum(g[tau] * dz[t - tau] for tau in range(1, min(t, 104) + 1))
        z_cpi = level[t] + beta_true * phi + rng.normal(0, 0.05)
        at = START + timedelta(days=7 * t, hours=1)
        ops = [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid}, "value": _native(eng, sid, z),
                "observed_at": at.isoformat()} for sid, z in ((OIL, z_oil[t]), (GAS, z_gas[t]), (CPI, z_cpi))]
        res = eng.learning.run(real_event(ops, f"GUE-{t}", at, produced_by="data_feed", event_type="data_release"), at)
        if t > 10:
            innovations.append(res.fold.innovations[CPI])
    return np.array(innovations)


def test_fold_learns_effect_existence_and_calibrated_innovations():
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
    assert abs(innov.mean()) < 0.15
    assert abs(innov.std() - 1.0) < 0.15
    # every update left a time state and the deviation history
    assert len(e08.time_states) > 100
    assert len(eng.wm.deviations.z[CPI]) == 150


def test_fold_records_activity_and_accumulators():
    eng = constructed_engine(build=True)
    _setup(eng, prior_mu=0.8)
    _simulate(eng, steps=12, seed=3)
    assert eng.wm.fold_accumulators["e08"][1] > 0
    assert any(r.interaction_id == "e08" for r in eng.wm.activity_log)
    insts = [i for i in eng.wm.graph.instances.values() if i.pattern_id == "S2"]
    assert insts and insts[0].activation > 0
