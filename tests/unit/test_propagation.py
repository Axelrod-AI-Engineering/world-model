"""Propagation on the daily grid (§8.5): one edge, feedback loops, forced existence, interventions,
history, rng, and the T-01 performance target."""

from __future__ import annotations

import time
from datetime import date

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
from axelrod_wm.memory.working import DeviationHistory, DeviationPoint, point_key


def chan(src: str, tgt: str, beta: float, delay=7, lag=21, duration=None, sigma=0.0, forced=True, key=None):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=sigma),
                       kernel=KernelSpec.model_validate({"delay_days": delay, "lag_days": lag, "duration_days": duration}))
    return Channel(interaction_id=key or f"{src}->{tgt}", source_id=src, target_id=tgt, dynamics=dyn,
                   existence=Beta(alpha=1e6, beta=1.0), forced=forced, key=key)


def quiet() -> DeterministicMeanPropagator:
    return DeterministicMeanPropagator(include_level_noise=False)


def test_one_edge_step_shock_gives_beta_s_g():
    beta, s, H = 0.6, 2.0, 160
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", beta, 14, 28, 70)], horizon_days=H)
    res = quiet().propagate(system, [ShockInput(subentity_id="a", size=s, start_day=1)], 1, make_rng(1))
    g = step_response(14, 28, 70.0, H)
    zb = res.z_of("b")[0]
    # a step on day 1 reaches b as beta * s * g(t - 1)
    expected = np.array([beta * s * g[t - 1] if t >= 1 else 0.0 for t in range(H + 1)])
    assert np.allclose(zb, expected, atol=1e-12)
    assert np.allclose(res.z_of("a")[0][1:], s)


def test_two_node_feedback_loop_stays_finite():
    system = PropagationSystem(subentity_ids=["a", "b"],
                               channels=[chan("a", "b", 0.5, 7, 7), chan("b", "a", 0.5, 7, 7)], horizon_days=400)
    res = quiet().propagate(system, [ShockInput(subentity_id="a", size=1.0, start_day=1)], 1, make_rng(1))
    assert np.all(np.isfinite(res.z))
    assert abs(res.z_of("a")[0][-1]) < 10


def test_forced_existence_switches_edges():
    on = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, forced=True)], horizon_days=60)
    off = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, forced=False)], horizon_days=60)
    shock = [ShockInput(subentity_id="a", size=1.0, start_day=1)]
    p = McImpulsePropagator(include_level_noise=False)
    assert p.propagate(on, shock, 50, make_rng(2)).median_z("b") > 0.9
    assert p.propagate(off, shock, 50, make_rng(2)).median_z("b") == 0.0


def test_interventions_cut_in_channels():
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, 7, 1)], horizon_days=60,
                               initial={"b": InitialState(z_now=0.3)})
    shocks = [ShockInput(subentity_id="a", size=2.0, start_day=1),
              ShockInput(subentity_id="b", size=0.5, start_day=1, intervention=True, hold_days=30)]
    res = quiet().propagate(system, shocks, 1, make_rng(3))
    zb = res.z_of("b")[0]
    assert np.allclose(zb[1:31], 0.8)          # held at z_now + change, ignoring a's shock
    assert zb[40] > 2.0                        # released: the in-channel acts again


def test_history_keeps_unfolding_without_shocks():
    """A source step 10 days ago keeps reaching the target over the forecast (the warm start)."""
    hist = DeviationHistory(origin_date=date(2026, 1, 1))
    today = 100
    for d in range(today + 1):
        za = 1.0 if d >= today - 10 else 0.0
        hist.points[point_key("a", d)] = DeviationPoint(z=za, var=0.0, level=za)
        hist.points[point_key("b", d)] = DeviationPoint(z=0.0, var=0.0, level=0.0)
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 0.5, 7, 30)], horizon_days=60,
                               initial={"a": InitialState(z_now=1.0), "b": InitialState(z_now=0.0)},
                               history=hist, today=today)
    res = quiet().propagate(system, [], 1, make_rng(4))
    zb = res.z_of("b")[0]
    assert zb[0] == pytest.approx(0.0)
    # the ramp completes over the forecast; the level absorbs the 4/30 of it already reached at day 0,
    # so every sample starts exactly at now
    assert zb[-1] == pytest.approx(0.5 * (1 - 4 / 30)) and np.all(np.diff(zb) >= -1e-12)


def test_same_rng_same_output_and_common_random_numbers():
    chans = [chan("a", "b", 0.5, sigma=0.2, forced=None), chan("b", "c", -0.4, sigma=0.2, forced=None)]
    chans = [c.model_copy(update={"existence": Beta(alpha=8, beta=2)}) for c in chans]
    system = PropagationSystem(subentity_ids=["a", "b", "c"], channels=chans, horizon_days=90)
    p = McImpulsePropagator()
    shock = [ShockInput(subentity_id="a", size=1.0, start_day=1)]
    r1 = p.propagate(system, shock, 200, make_rng(9, "k"))
    r2 = p.propagate(system, shock, 200, make_rng(9, "k"))
    assert np.array_equal(r1.z, r2.z)
    base = p.propagate(system, [], 200, make_rng(9, "k"))
    eff = r1.minus(base)
    assert np.allclose(eff.z_of("a")[:, 1:], 1.0)           # noise cancels sample by sample
    small = p.propagate(system, shock, 50, make_rng(9, "k"))
    assert np.allclose(small.z, r1.z[:50])                   # prefix-consistent in the sample count


def test_demo_size_propagation_is_fast():
    """About 60 channels, 300 samples, 270 days: one run is a small part of T-01's 10-second budget."""
    rng = np.random.default_rng(0)
    subs = [f"s{i}" for i in range(70)]
    chans = []
    for k in range(60):
        a, b = rng.choice(70, 2, replace=False)
        chans.append(chan(subs[a], subs[b], float(rng.normal(0, 0.4)), int(rng.integers(1, 30)),
                          int(rng.integers(1, 90)), None if k % 2 else 180.0, sigma=0.1, forced=None,
                          key=f"c{k}").model_copy(update={"existence": Beta(alpha=8, beta=2)}))
    system = PropagationSystem(subentity_ids=subs, channels=chans, horizon_days=270)
    t = time.perf_counter()
    McImpulsePropagator().propagate(system, [ShockInput(subentity_id="s0", size=2.0, start_day=58)], 300,
                                    make_rng(1), record_contributions=True)
    assert time.perf_counter() - t < 2.0
