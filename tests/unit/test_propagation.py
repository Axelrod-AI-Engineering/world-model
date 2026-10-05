"""Propagation (§8.5): one edge, feedback loops, forced existence, interventions, history, rng."""

from __future__ import annotations

import numpy as np
import pytest

from axelrod_wm.core.distributions import Beta, Gaussian
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.temporal import KernelSpec, step_response
from axelrod_wm.engine.propagation import (
    Channel,
    DeterministicMeanPropagator,
    InitialState,
    McImpulsePropagator,
    PropagationSystem,
    ShockInput,
)
from axelrod_wm.engine.rng import make_rng


def chan(src: str, tgt: str, beta: float, delay=7, lag=21, duration=None, sigma=0.0, forced=True, key=None):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=sigma),
                       kernel=KernelSpec.model_validate({"delay_days": delay, "lag_days": lag, "duration_days": duration}))
    return Channel(interaction_id=key or f"{src}->{tgt}", source_id=src, target_id=tgt, dynamics=dyn,
                   existence=Beta(alpha=1e6, beta=1.0), forced=forced, key=key)


def test_one_edge_step_shock_gives_beta_s_g():
    beta, s = 0.6, 2.0
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", beta, 14, 28, 70)],
                               step_days=7, horizon_steps=20)
    res = DeterministicMeanPropagator().propagate(system, [ShockInput(subentity_id="a", size=s, start_step=1)], 1,
                                                  make_rng(1))
    g = step_response(14, 28, 70, 20, 7)
    zb = res.z_of("b")[0]
    expected = np.array([beta * s * g[t - 1] if t >= 1 else 0.0 for t in range(21)])
    assert np.allclose(zb, expected, atol=1e-12)
    assert np.allclose(res.z_of("a")[0][1:], s)


def test_two_node_feedback_loop_stays_finite():
    system = PropagationSystem(subentity_ids=["a", "b"],
                               channels=[chan("a", "b", 0.5, 7, 7), chan("b", "a", 0.5, 7, 7)],
                               step_days=7, horizon_steps=60)
    res = DeterministicMeanPropagator().propagate(system, [ShockInput(subentity_id="a", size=1.0, start_step=1)], 1,
                                                  make_rng(1))
    assert np.all(np.isfinite(res.z))
    assert abs(res.z_of("a")[0][-1]) < 10


def test_forced_existence_switches_edges():
    on = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, forced=True)], step_days=7,
                           horizon_steps=10)
    off = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, forced=False)], step_days=7,
                            horizon_steps=10)
    shock = [ShockInput(subentity_id="a", size=1.0, start_step=1)]
    p = McImpulsePropagator(include_level_noise=False)
    assert p.propagate(on, shock, 50, make_rng(2)).median_z("b") > 0.9
    assert p.propagate(off, shock, 50, make_rng(2)).median_z("b") == 0.0


def test_interventions_cut_in_channels():
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, 7, 0)], step_days=7,
                               horizon_steps=10, initial={"b": InitialState(z_now=0.3)})
    shocks = [ShockInput(subentity_id="a", size=2.0, start_step=1),
              ShockInput(subentity_id="b", size=0.5, start_step=1, intervention=True, hold_steps=6)]
    res = DeterministicMeanPropagator().propagate(system, shocks, 1, make_rng(3))
    zb = res.z_of("b")[0]
    assert np.allclose(zb[1:7], 0.8)          # held at z_now + change, ignoring a's shock
    assert zb[8] > 2.0                        # released: the in-channel acts again


def test_history_keeps_unfolding_without_shocks():
    """A source step three steps ago still reaches the target over the forecast."""
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 0.5, 7, 70)], step_days=7,
                               horizon_steps=15,
                               initial={"a": InitialState(z_now=1.0, past_dz=[0.0, 1.0, 0.0, 0.0]),
                                        "b": InitialState(z_now=0.0)})
    res = DeterministicMeanPropagator().propagate(system, [], 1, make_rng(4))
    zb = res.z_of("b")[0]
    assert zb[0] == pytest.approx(0.0)
    assert zb[-1] > 0.4 and np.all(np.diff(zb[:12]) >= -1e-12)


def test_same_rng_same_output_and_common_random_numbers():
    chans = [chan("a", "b", 0.5, sigma=0.2, forced=None), chan("b", "c", -0.4, sigma=0.2, forced=None)]
    chans = [c.model_copy(update={"existence": Beta(alpha=8, beta=2)}) for c in chans]
    system = PropagationSystem(subentity_ids=["a", "b", "c"], channels=chans, step_days=7, horizon_steps=12)
    p = McImpulsePropagator()
    shock = [ShockInput(subentity_id="a", size=1.0, start_step=1)]
    r1 = p.propagate(system, shock, 200, make_rng(9, "k"))
    r2 = p.propagate(system, shock, 200, make_rng(9, "k"))
    assert np.array_equal(r1.z, r2.z)
    base = p.propagate(system, [], 200, make_rng(9, "k"))
    eff = r1.minus(base)
    assert np.allclose(eff.z_of("a")[:, 1:], 1.0)           # noise cancels sample by sample
    small = p.propagate(system, shock, 50, make_rng(9, "k"))
    assert np.allclose(small.z, r1.z[:50])                   # prefix-consistent in the sample count
