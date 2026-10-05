"""Kernels: delay, lag, duration, and the minimum delay (§6.4)."""

from __future__ import annotations

import numpy as np

from axelrod_wm.core.distributions import Beta, Gaussian
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.temporal import KernelSpec, step_response, step_response_batch
from axelrod_wm.engine.propagation import (
    Channel,
    DeterministicMeanPropagator,
    PropagationSystem,
    ShockInput,
)


def test_zero_before_delay_and_peak_at_delay_plus_lag():
    g = step_response(delay=14, lag=28, duration=70, n_steps=30, step_days=7)
    assert np.all(g[:2] == 0.0)             # tau < d = 2 steps
    assert g[2] == 0.0                      # onset
    assert np.argmax(g) == 6                # peak at d + l = 2 + 4
    assert g[6] == 1.0
    assert np.all(np.diff(g[6:]) < 0)       # decays over the duration
    assert g[6 + 10] == np.exp(-3.0) or abs(g[16] - np.exp(-3.0)) < 1e-12


def test_permanent_when_duration_is_none():
    g = step_response(delay=7, lag=14, duration=None, n_steps=20, step_days=7)
    assert np.all(g[3:] == 1.0)


def test_zero_lag_jumps_to_one():
    g = step_response(delay=7, lag=0, duration=None, n_steps=5, step_days=7)
    assert list(g[:3]) == [0.0, 1.0, 1.0]


def test_batch_matches_scalar():
    gb = step_response_batch(np.array([2.0]), np.array([4.0]), np.array([10.0]), 30)
    g = step_response(14, 28, 70, 30, 7)
    assert np.allclose(gb[0], g)


def test_shorthand_turns_means_into_gammas():
    k = KernelSpec.model_validate({"delay_days": 7, "lag_days": 30, "duration_days": None})
    assert k.means() == (7.0, 30.0, None)
    assert abs(k.delay.sd() / k.delay.mean() - 0.3) < 1e-9


def test_minimum_delay_enforced():
    """A kernel with no delay and no lag still acts one step later (min_delay_steps = 1)."""
    dyn = EdgeDynamics(effect=Gaussian(mu=1.0, sigma=0.0),
                       kernel=KernelSpec.model_validate({"delay_days": 0, "lag_days": 0, "duration_days": None}))
    ch = Channel(interaction_id="x", source_id="a", target_id="b", dynamics=dyn, existence=Beta(alpha=1e6, beta=1.0),
                 forced=True)
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[ch], step_days=7, horizon_steps=4)
    res = DeterministicMeanPropagator().propagate(system, [ShockInput(subentity_id="a", size=1.0, start_step=1)], 1,
                                                  np.random.default_rng(0))
    zb = res.z_of("b")[0]
    assert zb[1] == 0.0 and zb[2] == 1.0
