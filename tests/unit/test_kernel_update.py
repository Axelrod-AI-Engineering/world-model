"""Kernel learning (grid_rescale, §8.6): delay, lag, and duration move toward the truth."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from axelrod_wm.core.distributions import Gaussian
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.temporal import KernelSpec, step_response
from tests.conftest import START, constructed_engine, real_event
from tests.unit.test_fold import CPI, OIL, _native


def test_kernel_means_move_toward_a_slower_truth():
    eng = constructed_engine(build=True)
    prior = KernelSpec.model_validate({"delay_days": 14, "lag_days": 28, "duration_days": None})
    with eng.mutator.begin("setup", now=START) as txn:
        txn.update("interactions", "e08", forward=EdgeDynamics(effect=Gaussian(mu=0.8, sigma=0.1), kernel=prior))
        txn.update("subentities", OIL, level_noise=0.6, obs_noise=0.01)
    rng = np.random.default_rng(5)
    g_true = step_response(28, 56, None, 104, 7)       # twice as slow
    steps = 120
    z_oil = np.zeros(steps)
    for t in range(1, steps):
        jump = (1.5 if (t // 8) % 2 == 0 else -1.5) if t % 8 == 0 else 0.0
        z_oil[t] = z_oil[t - 1] + jump + rng.normal(0, 0.05)
    level = np.cumsum(rng.normal(0, 0.03, steps))
    dz = np.diff(z_oil, prepend=z_oil[0])
    delays = [prior.means()[0]]
    kernel_updater = eng.components["kernel_updater"]
    for t in range(steps):
        phi = sum(g_true[tau] * dz[t - tau] for tau in range(1, min(t, 104) + 1))
        z_cpi = level[t] + 0.8 * phi + rng.normal(0, 0.05)
        at = START + timedelta(days=7 * t, hours=1)
        ops = [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid}, "value": _native(eng, sid, z),
                "observed_at": at.isoformat()} for sid, z in ((OIL, z_oil[t]), (CPI, z_cpi))]
        eng.learning.run(real_event(ops, f"GUE-{t}", at, produced_by="data_feed", event_type="data_release"), at)
        if t >= 26 and t % 13 == 0:
            ctx = eng.context(learn=True, now=at)
            with eng.mutator.begin(f"kernels-{t}", now=at) as txn:
                kernel_updater.update(eng.wm, eng.ltm, ctx, txn)
            delays.append(eng.wm.graph.interactions["e08"].forward.kernel.means()[0])
    truth = 28.0
    # moved toward the truth (the {0.5, 1, 2} grid moves in factors of sqrt(2)) and never past it by much
    assert delays[-1] > 1.3 * delays[0], delays
    assert abs(np.log(delays[-1] / truth)) < abs(np.log(delays[0] / truth)), delays
    assert delays[-1] < 2.0 * truth, delays
    k = eng.wm.graph.interactions["e08"].forward.kernel
    assert k.cv() < 0.3                                   # uncertainty shrinks
    assert any(ts.note == "kernel update" for ts in eng.wm.graph.interactions["e08"].time_states)
