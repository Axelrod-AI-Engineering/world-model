"""Paths the history replay takes (and which the cached init snapshot otherwise hides from a test run): a seed
pattern counted during initialization, and a kernel update on an interaction with a reverse channel."""

from __future__ import annotations

import numpy as np
import pytest

from axelrod_wm.dynamics.kernels import phi_recursive
from axelrod_wm.memory.working import ActivityRecord
from axelrod_wm.model.distributions import Gaussian
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec
from tests.conftest import constructed_engine, observe_event, run_days
from tests.unit.dynamics.test_daily_model import CPI, OIL, _native
from tests.unit.learning.test_cov_abduction import _count


def test_during_initialization_a_seed_pattern_counts_without_a_dated_record(warm_engine):
    eng = warm_engine
    g = eng.wm.graph
    p0 = eng.ltm.object_generalizations.patterns["S11"]
    support0, counted0 = p0.support, list(p0.counted_days)
    recs = [ActivityRecord(day=60, channel_id=iid, contribution_change=0.6, target_move=0.7,
                           target_id=g.interactions[iid].target_id) for iid in g.instances["inst-S11"].interaction_ids]
    eng.initializing = True
    try:
        res = _count(eng, 60, recs)
    finally:
        eng.initializing = False
    p = eng.ltm.object_generalizations.patterns["S11"]
    assert "S11" in res.supported_pattern_ids
    assert p.support == support0 + 1.0 and p.last_counted_day == 60
    assert list(p.counted_days) == counted0            # the dated record is for live days only


def test_a_kernel_update_rescales_the_reverse_channel_alike():
    from axelrod_wm.dynamics.daily import ensure_channel_states

    eng = constructed_engine(build=True)
    prior = KernelSpec.model_validate({"delay_days": 14, "lag_days": 28, "duration_days": None})
    rev = KernelSpec.model_validate({"delay_days": 10, "lag_days": 20, "duration_days": None})
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.update("wm.graph.interactions", "e08", forward=EdgeDynamics(effect=Gaussian(mu=0.8, sigma=0.1), kernel=prior),
                   reverse=EdgeDynamics(effect=Gaussian(mu=0.1, sigma=0.1), kernel=rev))
        txn.update("wm.graph.subentities", OIL, level_noise=0.3, obs_noise=0.01)
        txn.update("wm.graph.subentities", CPI, level_noise=0.01, obs_noise=0.05)
        ensure_channel_states(eng.wm.graph.interactions["e08"], eng.wm, eng.context(learn=True, now=eng.wm.clock),
                              txn, day=0)
    rng = np.random.default_rng(5)
    days = 150
    z_oil = np.zeros(days)
    for t in range(1, days):
        z_oil[t] = z_oil[t - 1] + ((1.5 if (t // 60) % 2 == 0 else -1.5) if t % 60 == 0 else 0.0) + rng.normal(0, 0.02)
    z_cpi = 0.8 * phi_recursive(28, 56, 1.0, z_oil) + rng.normal(0, 0.05, days)
    dev = eng.wm.deviations

    def events(d):
        return [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, z_oil[d]), CPI: _native(eng, CPI, z_cpi[d])},
                              dev.date_of(d))]

    run_days(eng, days - 1, events)
    e08 = eng.wm.graph.interactions["e08"]
    assert any(ts.note == "kernel update" for ts in e08.time_states)
    # the reverse kernel takes the forward's factor and its uncertainty
    factor = e08.forward.kernel.means()[0] / prior.means()[0]
    assert e08.reverse.kernel.means()[0] / rev.means()[0] == pytest.approx(factor)
    assert e08.reverse.kernel.cv() == pytest.approx(e08.forward.kernel.cv())
    assert e08.forward.kernel.cv() < prior.cv()
