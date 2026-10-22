"""Kernel learning (grid_rescale, §8.6.2): delay, lag, and duration move toward the truth over several
consolidations, and the channel's state is rebuilt with a warm start."""

from __future__ import annotations

import numpy as np

from axelrod_wm.dynamics.kernels import mean_kernel_days, phi_recursive
from axelrod_wm.model.distributions import Gaussian
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec
from tests.conftest import constructed_engine, observe_event, run_days
from tests.unit.dynamics.test_daily_model import CPI, OIL, _native


def test_kernel_means_move_toward_a_slower_truth():
    from axelrod_wm.dynamics.daily import ensure_channel_states

    eng = constructed_engine(build=True)
    prior = KernelSpec.model_validate({"delay_days": 14, "lag_days": 28, "duration_days": None})
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.update("wm.graph.interactions", "e08", forward=EdgeDynamics(effect=Gaussian(mu=0.8, sigma=0.1), kernel=prior))
        txn.update("wm.graph.subentities", OIL, level_noise=0.3, obs_noise=0.01)
        txn.update("wm.graph.subentities", CPI, level_noise=0.01, obs_noise=0.05)
        ensure_channel_states(eng.wm.graph.interactions["e08"], eng.wm, eng.context(learn=True, now=eng.wm.clock),
                              txn, day=0)
    rng = np.random.default_rng(5)
    days = 420
    z_oil = np.zeros(days)
    for t in range(1, days):            # oil jumps every 60 days, alternating sign
        jump = (1.5 if (t // 60) % 2 == 0 else -1.5) if t % 60 == 0 else 0.0
        z_oil[t] = z_oil[t - 1] + jump + rng.normal(0, 0.02)
    truth = (28, 56)                    # twice as slow as the prior
    z_cpi = 0.8 * phi_recursive(truth[0], truth[1], 1.0, z_oil) + np.cumsum(rng.normal(0, 0.01, days)) \
        + rng.normal(0, 0.05, days)
    dev = eng.wm.deviations
    delays = [prior.means()[0]]

    def events(d):
        return [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, z_oil[d]), CPI: _native(eng, CPI, z_cpi[d])},
                              dev.date_of(d))]

    for _ in range(days // 30):
        run_days(eng, 30, events)       # the kernel updater runs at consolidation every kernel_update.every_days
        delays.append(eng.wm.graph.interactions["e08"].forward.kernel.means()[0])
    target = float(truth[0])
    # moved toward the truth (the {0.5, 1, 2} grid moves in factors of sqrt(2)) and never past it by much
    assert delays[-1] > 1.3 * delays[0], delays
    assert abs(np.log(delays[-1] / target)) < abs(np.log(delays[0] / target)), delays
    assert delays[-1] < 2.0 * target, delays
    e08 = eng.wm.graph.interactions["e08"]
    assert e08.forward.kernel.cv() < 0.3                                  # uncertainty shrinks
    assert any(ts.note == "kernel update" for ts in e08.time_states)
    # the channel's state was rebuilt for the new kernel (a warm start) and is at the next day
    cs = eng.wm.channels["e08"]
    assert (cs.recursion.d, cs.recursion.l) == mean_kernel_days(e08.forward.kernel)[:2]
    assert cs.day == eng.wm.last_processed_day + 1
