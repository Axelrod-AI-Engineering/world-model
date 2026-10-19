"""Propagation: soft bounds, result algebra, parameter draws, moderators, shocks, exogenous inputs,
history, and the coupled-run helpers (closed forms where they exist)."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from axelrod_wm.dynamics.propagation import (
    BOUND_WIDTH_SD,
    Channel,
    DeterministicMeanPropagator,
    InitialState,
    McImpulsePropagator,
    PropagationResult,
    PropagationSystem,
    Propagator,
    ShockInput,
    _cfg,
    contribution_paths,
    soft_bound,
    source_history,
)
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.events.graph_update import Persistence
from axelrod_wm.memory.working import DeviationHistory, DeviationPoint, point_key
from axelrod_wm.model.distributions import Beta, Gaussian, Link
from axelrod_wm.model.interaction import EdgeDynamics, ParameterBinding, ParameterForm
from axelrod_wm.model.temporal import KernelSpec, step_response


def chan(src, tgt, beta, delay=1, lag=1, duration=None, sigma=0.0, forced=True, params=(), existence=None):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=sigma),
                       kernel=KernelSpec.model_validate({"delay_days": delay, "lag_days": lag, "duration_days": duration}))
    return Channel(interaction_id=f"{src}->{tgt}", source_id=src, target_id=tgt, dynamics=dyn,
                   existence=existence or Beta(alpha=1e6, beta=1.0), forced=forced, parameters=list(params))


def quiet():
    return DeterministicMeanPropagator(include_level_noise=False)


def param(form, gamma=1.0, thr=None, mod="m"):
    return ParameterBinding(name="p", moderator_id=mod, form=form, coefficient=Gaussian(mu=gamma, sigma=0.0),
                            threshold=thr)


# ----- soft bounds ------------------------------------------------------------------------------

def test_soft_bound_closed_form():
    z = np.array([-10.0, 0.0, 0.5, 10.0])
    assert np.array_equal(soft_bound(z, None, None), z)
    hi = soft_bound(z, None, 1.0)
    assert hi == pytest.approx(1.0 - BOUND_WIDTH_SD * np.logaddexp(0.0, (1.0 - z) / BOUND_WIDTH_SD))
    assert hi[0] == pytest.approx(-10.0) and hi[3] == pytest.approx(1.0)
    both = soft_bound(z, -1.0, 1.0)
    assert both[0] == pytest.approx(-1.0) and both[3] == pytest.approx(1.0, abs=1e-3) and abs(both[1]) < 1e-3


# ----- results ----------------------------------------------------------------------------------

def _res():
    z = np.arange(2 * 2 * 3, dtype=float).reshape(2, 2, 3)
    c = np.ones((2, 1, 3))
    return PropagationResult({"a": 0, "b": 1}, {"k": 0}, z, c)


def test_result_accessors():
    r = _res()
    assert r.n_samples == 2 and r.horizon_days == 2 and r.horizon_steps == 2
    assert r.has("a") and not r.has("q")
    assert np.array_equal(r.z_of("q"), np.zeros((2, 3)))
    assert np.array_equal(r.contrib_of("k"), np.ones((2, 3)))
    assert np.array_equal(r.contrib_of("q"), np.zeros((2, 3)))
    assert np.array_equal(PropagationResult({"a": 0}, {}, np.zeros((1, 1, 2)), None).contrib_of("k"), np.zeros((1, 2)))
    assert r.median_z("a") == pytest.approx(np.median([2.0, 8.0]))
    assert r.median_z("a", day=0) == pytest.approx(3.0)
    zs = r.z_summary("b")
    assert len(zs) == 3 and zs[0].mean == pytest.approx(6.0)
    s = r.summary("a", anchor=1.0, scale=2.0, link=Link.IDENTITY)
    assert s[1].mean == pytest.approx(1.0 + 2.0 * 4.0)
    logs = r.summary("a", anchor=0.0, scale=0.1, link=Link.LOG)
    assert logs[0].q50 == pytest.approx((1.0 + math.exp(0.6)) / 2)


def test_result_minus_and_concat():
    r = _res()
    other = PropagationResult({"a": 0}, {}, np.ones((2, 1, 3)), None)
    d = r.minus(other)
    assert np.array_equal(d.z[:, 0, :], r.z[:, 0, :] - 1.0) and np.array_equal(d.z[:, 1, :], r.z[:, 1, :])
    assert np.array_equal(d.channel_contrib, r.channel_contrib)
    no_c = PropagationResult({"a": 0}, {}, np.ones((2, 1, 3)), None).minus(r)
    assert no_c.channel_contrib is None and np.array_equal(no_c.z[:, 0, :], 1.0 - r.z[:, 0, :])
    short = PropagationResult({"b": 0, "c": 1}, {"k2": 0}, np.full((1, 2, 2), 5.0), np.full((1, 1, 2), 7.0))
    cat = PropagationResult.concat([r, short, _res()])
    assert cat.subentity_index == {"a": 0, "b": 1, "c": 2} and cat.channel_index == {"k": 0, "k2": 1}
    assert np.array_equal(cat.z[3:], np.concatenate([_res().z, np.zeros((2, 1, 3))], axis=1))
    assert cat.z.shape == (5, 3, 3)
    assert np.array_equal(cat.z[2, 1], [5.0, 5.0, 0.0]) and np.array_equal(cat.z[2, 0], [0.0, 0.0, 0.0])
    assert np.array_equal(cat.channel_contrib[2], [[0.0, 0.0, 0.0], [7.0, 7.0, 0.0]])


def test_propagator_interface_stub():
    assert Propagator.propagate(quiet(), None, [], 1, make_rng(0)) is None


# ----- config -----------------------------------------------------------------------------------

def test_cfg_reads_objects_and_dicts():
    assert _cfg(None, "a.b", 7) == 7
    assert _cfg({"a": {"b": 3}}, "a.b", 7) == 3
    assert _cfg({"a": {"b": None}}, "a.b", 7) == 7
    assert _cfg({"a": None}, "a.b", 7) == 7

    class Obj:
        propagation = {"min_delay_days": 4, "moderator_clip": [0.5, 2.0], "include_level_noise": False}

    p = McImpulsePropagator(Obj())
    assert p.min_delay_days == 4 and p.moderator_clip == (0.5, 2.0) and not p.include_level_noise
    assert p.level_process_noise == 0.04 and p.drift_damping == 0.985


# ----- draws ------------------------------------------------------------------------------------

def test_mc_draws_existence_kernels_and_moderators_from_substreams():
    ch = chan("a", "b", 0.5, delay=10, lag=5, duration=30, sigma=0.1, forced=None, existence=Beta(alpha=2, beta=2),
              params=[param(ParameterForm.MULTIPLICATIVE, mod="m"), param(ParameterForm.ADDITIVE, mod="gone")])
    system = PropagationSystem(subentity_ids=["a", "b", "m"], channels=[ch], horizon_days=5)
    p = McImpulsePropagator(include_level_noise=False)
    P = p._draw(system, {"a": 0, "b": 1, "m": 2}, 4000, make_rng(1))
    assert set(np.unique(P.exists)) <= {0.0, 1.0} and P.exists.mean() == pytest.approx(0.5, abs=0.03)
    assert P.beta.mean() == pytest.approx(0.5, abs=0.01) and P.beta.std() == pytest.approx(0.1, abs=0.01)
    assert P.d.min() >= 1 and P.d.mean() == pytest.approx(10.0, abs=0.2)
    assert np.all(P.lam < 1.0) and np.all(P.lam > 0.0)
    assert len(P.mods) == 1 and P.mods[0][1] == 2          # the moderator not in the index is skipped
    det = DeterministicMeanPropagator()._draw(system, {"a": 0, "b": 1, "m": 2}, 1, make_rng(1))
    assert det.exists[0, 0] == pytest.approx(0.5) and det.beta[0, 0] == 0.5
    assert (det.d[0, 0], det.l[0, 0]) == (10, 5) and det.lam[0, 0] == pytest.approx(math.exp(-0.1))
    assert det.mods[0][3].tolist() == [1.0]


def test_forced_off_in_mc_and_permanent_kernel():
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, forced=False)], horizon_days=3)
    P = McImpulsePropagator()._draw(system, {"a": 0, "b": 1}, 3, make_rng(0))
    assert P.exists.tolist() == [[0.0]] * 3 and P.lam.tolist() == [[1.0]] * 3


# ----- moderators -------------------------------------------------------------------------------

def _moderated(form, m_z, thr=None, gamma=1.0):
    system = PropagationSystem(subentity_ids=["a", "b", "m"],
                               channels=[chan("a", "b", 1.0, params=[param(form, gamma, thr)])], horizon_days=4,
                               initial={"m": InitialState(z_now=m_z)})
    return quiet().propagate(system, [ShockInput(subentity_id="a", size=1.0, start_day=1)], 1, make_rng(0))


def test_moderator_forms_shape_the_edge():
    # delay 1, lag 1: a's step on day 1 reaches b from day 2; the moderator m stays at its z_now
    assert _moderated(ParameterForm.MULTIPLICATIVE, 0.5).z_of("b")[0, 2] == pytest.approx(1.5)
    assert _moderated(ParameterForm.MULTIPLICATIVE, 5.0).z_of("b")[0, 2] == pytest.approx(3.0)   # clipped
    assert _moderated(ParameterForm.THRESHOLD, 0.5).z_of("b")[0, 2] == pytest.approx(1.0)
    assert _moderated(ParameterForm.THRESHOLD, 0.5, thr=1.0).z_of("b")[0, 2] == 0.0
    add = _moderated(ParameterForm.ADDITIVE, 0.5, gamma=0.4).z_of("b")[0]
    assert add[0] == 0.0 and add[1] == pytest.approx(0.0) and add[2] == pytest.approx(1.0)


def test_additive_moderator_moves_the_target_from_today():
    system = PropagationSystem(subentity_ids=["a", "b", "m"],
                               channels=[chan("a", "b", 1.0, params=[param(ParameterForm.ADDITIVE, 0.4)])],
                               horizon_days=3, initial={"m": InitialState(z_now=0.5), "b": InitialState(z_now=0.2)})
    zb = quiet().propagate(system, [], 1, make_rng(0)).z_of("b")[0]
    # today's additive input (0.2) is part of z_now; later days add it back, so b holds at 0.2
    assert zb == pytest.approx([0.2, 0.2, 0.2, 0.2])


# ----- state, history, shocks, exogenous inputs, bounds -----------------------------------------

def test_no_channels_drift_and_level_noise():
    system = PropagationSystem(subentity_ids=["a"], channels=[], horizon_days=3,
                               initial={"a": InitialState(z_now=1.0, drift=0.1), "ghost": InitialState(z_now=9.0)})
    res = McImpulsePropagator(include_level_noise=False, drift_damping=0.5).propagate(system, [], 2, make_rng(0))
    za = res.z_of("a")[0]
    assert za == pytest.approx([1.0, 1.05, 1.075, 1.0875])
    assert not res.has("ghost") and res.channel_contrib is None
    noisy = PropagationSystem(subentity_ids=["a"], channels=[], horizon_days=50,
                              initial={"a": InitialState(z_now=0.0, level_noise=0.0)})
    assert np.all(McImpulsePropagator().propagate(noisy, [], 3, make_rng(0)).z == 0.0)
    loud = noisy.model_copy(update={"initial": {"a": InitialState(z_now=0.0, level_noise=1.0)}})
    zz = McImpulsePropagator().propagate(loud, [], 200, make_rng(0)).z_of("a")[:, -1]
    assert np.std(zz) == pytest.approx(math.sqrt(50), rel=0.15)        # a random walk of 50 unit steps


def test_shocks_pulse_late_noisy_and_extra_subentity():
    system = PropagationSystem(subentity_ids=["a"], channels=[], horizon_days=4)
    shocks = [ShockInput(subentity_id="a", size=1.0, start_day=2, persistence=Persistence.PULSE),
              ShockInput(subentity_id="new", size=2.0, start_day=0),
              ShockInput(subentity_id="a", size=5.0, start_day=9)]
    res = quiet().propagate(system, shocks, 1, make_rng(0))
    assert res.z_of("a")[0].tolist() == [0.0, 0.0, 1.0, 0.0, 0.0]
    assert res.z_of("new")[0].tolist() == [0.0, 2.0, 2.0, 2.0, 2.0]          # start_day floors at 1
    held = [ShockInput(subentity_id="a", size=1.0, start_day=1, intervention=True)]
    assert quiet().propagate(system, held, 1, make_rng(0)).z_of("a")[0].tolist() == [0.0, 1, 1, 1, 1]
    mc = McImpulsePropagator(include_level_noise=False)
    sizes = mc.propagate(system, [ShockInput(subentity_id="a", size=1.0, size_sd=0.5)], 4000, make_rng(2)).z_of("a")[:, 1]
    assert sizes.mean() == pytest.approx(1.0, abs=0.03) and sizes.std() == pytest.approx(0.5, abs=0.03)


def test_exogenous_paths():
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[], horizon_days=3)
    exo = {"a": np.array([9.0, 1.0, 2.0, 3.0, 4.0, 5.0]), "b": np.array([[0.0, 1.0]]), "zz": np.ones(4)}
    res = quiet().propagate(system, [], 1, make_rng(0), exogenous=exo)
    assert res.z_of("a")[0].tolist() == [0.0, 1.0, 2.0, 3.0]      # day 0 is now; extra days ignored
    assert res.z_of("b")[0].tolist() == [0.0, 1.0, 0.0, 0.0]


def test_bounds_bend_and_count_hits():
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0)], horizon_days=4,
                               bounds={"b": (None, 0.5), "ghost": (0.0, 1.0)})
    res = quiet().propagate(system, [ShockInput(subentity_id="a", size=3.0)], 1, make_rng(0))
    zb = res.z_of("b")[0]
    assert zb[-1] == pytest.approx(soft_bound(np.array([3.0]), None, 0.5)[0])
    assert res.bound_hits == {"b": 1.0}


def _history(sid, values, first=0):
    h = DeviationHistory(origin_date=date(2026, 1, 1), first_kept_day=first)
    for d, v in enumerate(values):
        h.points[point_key(sid, d)] = DeviationPoint(z=v, var=0.0, level=0.0)
    return h


def test_history_unfolds_through_the_kernel():
    hist = _history("a", [0.0] * 5 + [1.0] * 6)                   # a stepped up on day 5; today is day 10
    system = PropagationSystem(subentity_ids=["a", "b"], channels=[chan("a", "b", 1.0, delay=3, lag=10)],
                               horizon_days=6, history=hist, today=10, initial={"a": InitialState(z_now=1.0)})
    zb = quiet().propagate(system, [], 1, make_rng(0)).z_of("b")[0]
    g = step_response(3, 10, None, 30)
    # b starts at 0 (z_now) and moves by beta * (g(t + 5) - g(5)) as the past step keeps arriving
    assert zb == pytest.approx([g[t + 5] - g[5] for t in range(7)])


def test_source_history_and_contribution_paths():
    hist = _history("a", [0.5, 1.0, 2.0], first=1)
    system = PropagationSystem(subentity_ids=["a"], channels=[], horizon_days=2, history=hist, today=2)
    assert source_history(system, "a", 9.0).tolist() == [9.0, 1.0]
    assert source_history(system.model_copy(update={"history": None}), "a", 4.0).tolist() == [4.0]
    ch = chan("a", "b", 2.0, delay=1, lag=1)
    sys2 = PropagationSystem(subentity_ids=["a", "b"], channels=[ch], horizon_days=3)
    P = quiet()._draw(sys2, {"a": 0, "b": 1}, 1, make_rng(0))
    src_path = np.array([[1.0, 3.0, 4.0, 5.0]])
    out = contribution_paths(P, 0, np.array([1.0, 7.0]), src_path)
    # phi(t) = z(t - 1); day 0 reads yesterday from the history (7), then the simulated path
    assert out.tolist() == [[14.0, 2.0, 6.0, 8.0]]
    far = contribution_paths(P, 0, np.array([1.0]), src_path)
    assert far[0, 0] == 0.0
