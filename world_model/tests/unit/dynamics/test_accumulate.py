"""Accumulating kernels (a stock integrating a flow) and piecewise moderators (state-dependent responses), Oct 18:
the recursion against the direct convolution, the Monte Carlo propagator, the daily model, kernel learning, and the
synthetic world."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pytest

from axelrod_wm.dynamics.kernels import (
    KernelRecursion,
    phi_direct,
    phi_recursive,
    tail_weights,
    warm_start_batch,
)
from axelrod_wm.dynamics.propagation import (
    Channel,
    DeterministicMeanPropagator,
    McImpulsePropagator,
    PropagationSystem,
    ShockInput,
    _Params,
    contribution_paths,
)
from axelrod_wm.dynamics.regressors import moderator_terms
from axelrod_wm.engine.engine import build_engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, load_vocabulary
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.memory.working import DeviationHistory, DeviationPoint, point_key
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.interaction import EdgeDynamics, ParameterBinding, ParameterForm
from axelrod_wm.model.temporal import KernelSpec
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.world import SyntheticWorld, TruthSpec
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config, observe_event, run_days
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, world
from tests.unit.model.test_identities import bank


def acc_kernel(delay=1, period=10):
    return KernelSpec.model_validate({"delay_days": delay, "lag_days": period, "duration_days": None,
                                      "shape": "accumulate"})


def test_an_accumulating_kernel_has_no_duration():
    assert acc_kernel().accumulates and not KernelSpec.model_validate({"delay_days": 1, "lag_days": 1}).accumulates
    with pytest.raises(ValueError, match="no duration"):
        KernelSpec.model_validate({"delay_days": 1, "lag_days": 5, "duration_days": 9, "shape": "accumulate"})
    assert acc_kernel().rescaled(2.0).accumulates


def test_the_recursion_integrates_like_the_direct_convolution():
    rng = np.random.default_rng(3)
    z = rng.normal(size=60)
    for d, l in ((1, 1), (2, 7), (3, 10)):
        direct = phi_direct(d, l, 1.0, z, acc=True)
        assert np.allclose(phi_recursive(d, l, 1.0, z, acc=True), direct)
        assert np.allclose(phi_recursive(d, l, 0.5, z, t0=20, acc=True), direct[20:])     # lam is ignored
    step = np.ones(40)
    # a flow held one unit up adds 1 / l per day after the delay: one full unit per period
    assert phi_direct(1, 10, 1.0, step, acc=True)[21] == pytest.approx(2.1)        # 21 days at 1 / 10


class Series:
    def __init__(self, z, first=0):
        self.z, self.first_day = z, first

    def __getitem__(self, day):
        return float(self.z[day]) if 0 <= day < len(self.z) else 0.0


def test_warm_starts_and_batches_match_the_recursion():
    rng = np.random.default_rng(5)
    z = rng.normal(size=80)
    s = Series(z)
    rec = KernelRecursion.warm_start(2, 9, 0.3, s, 50, acc=True)
    assert rec.acc and rec.lam == 1.0 and rec.kappa == pytest.approx(1 / 9)
    assert rec.phi() == pytest.approx(phi_direct(2, 9, 1.0, z, acc=True)[50])
    for t in range(50, 70):
        rec.advance(s, t)
    assert rec.phi() == pytest.approx(phi_direct(2, 9, 1.0, z, acc=True)[70])
    k = KernelRecursion.for_kernel(acc_kernel(2, 9), s, 50)
    assert k.acc and k.phi() == pytest.approx(phi_direct(2, 9, 1.0, z, acc=True)[50])
    assert KernelRecursion(d=1, l=4, lam=0.5).kappa == -0.5
    hist_rev = z[50::-1][None, :]                                    # newest first, day 50 is "today"
    d, l = np.array([[2, 2]]), np.array([[9, 9]])
    lam, acc = np.array([[1.0, 0.6]]), np.array([[True, False]])
    S, T = warm_start_batch(d, l, lam, hist_rev, np.array([0, 0]), tail_weights(l, lam, acc))
    ramp = KernelRecursion.warm_start(2, 9, 0.6, s, 50)
    assert S[0, 0] / 9 + T[0, 0] == pytest.approx(rec_phi := phi_direct(2, 9, 1.0, z, acc=True)[50])
    assert S[0, 1] / 9 + T[0, 1] == pytest.approx(ramp.phi()) and rec_phi != ramp.phi()
    S2, T2 = warm_start_batch(d, l, lam, hist_rev, np.array([0, 0]))          # without kappa: ramps only
    assert T2[0, 0] == 0.0 and T2[0, 1] == pytest.approx(T[0, 1])


def chan(src, tgt, beta, kernel, params=()):
    return Channel(interaction_id=f"{src}->{tgt}", source_id=src, target_id=tgt,
                   dynamics=EdgeDynamics(effect=Gaussian(mu=beta, sigma=0.05), kernel=kernel),
                   existence=Beta(alpha=1e6, beta=1.0), parameters=list(params))


def test_propagation_accumulates_a_flow_into_its_stock():
    """A flow one sd up from day 1: the stock rises by the weight every period, exactly, in every sample."""
    system = PropagationSystem(subentity_ids=["f", "s"], horizon_days=41,
                               channels=[chan("f", "s", 0.2, acc_kernel(1, 10))])
    shock = [ShockInput(subentity_id="f", size=1.0, start_day=1)]
    for prop in (DeterministicMeanPropagator(include_level_noise=False),
                 McImpulsePropagator(include_level_noise=False)):
        res = prop.propagate(system, shock, 8, make_rng(1), record_contributions=True)
        assert np.allclose(res.z_of("s")[:, 21], 0.2 * 2.0) and np.allclose(res.z_of("s")[:, 41], 0.2 * 4.0)
    params = _Params(2, 1)
    params.beta[:, 0], params.l[:, 0], params.acc[:, 0] = 0.2, 10, True
    path = np.ones((2, 12))
    path[:, 0] = 0.0
    out = contribution_paths(params, 0, np.array([0.0, 0.0]), path)
    assert out[0, 11] == pytest.approx(0.2)                          # ten days of a flow one sd up: one period


def test_a_scenario_can_still_turn_a_stock_flow_link_off():
    system = PropagationSystem(subentity_ids=["f", "s"], horizon_days=20,
                               channels=[chan("f", "s", 0.2, acc_kernel(1, 10)).model_copy(update={"forced": False})])
    res = DeterministicMeanPropagator(include_level_noise=False).propagate(
        system, [ShockInput(subentity_id="f", size=1.0)], 1, make_rng(1))
    assert np.allclose(res.z_of("s"), 0.0)


def piecewise(thr=0.0, gamma=0.5, side="above"):
    return ParameterBinding(name="rises and falls", moderator_id="m", form=ParameterForm.PIECEWISE,
                            coefficient=Gaussian(mu=gamma, sigma=0.0), threshold=thr, side=side)


def test_a_piecewise_moderator_changes_the_size_by_state():
    k = KernelSpec.model_validate({"delay_days": 1, "lag_days": 1})
    prop = DeterministicMeanPropagator(include_level_noise=False)
    for side, m_size, expect in (("above", 1.0, 1.0), ("above", -1.0, 0.5), ("below", -1.0, 1.0),
                                 ("below", 1.0, 0.5)):
        system = PropagationSystem(subentity_ids=["x", "y", "m"], horizon_days=6,
                                   channels=[chan("x", "y", 1.0, k, [piecewise(side=side)])])
        res = prop.propagate(system, [ShockInput(subentity_id="x", size=1.0), ShockInput(subentity_id="m", size=m_size)],
                             1, make_rng(1))
        assert res.median_z("y", 6) == pytest.approx(expect, abs=1e-6), (side, m_size)


def test_moderator_terms_read_the_piecewise_side():
    dev = DeviationHistory(origin_date=date(2024, 1, 1))
    dev.points[point_key("m", 4)] = DeviationPoint(z=-1.0, var=0.0, level=0.0)
    assert moderator_terms([piecewise()], dev, 5, (0.0, 3.0)) == (0.5, 0.0)
    assert moderator_terms([piecewise(side="below")], dev, 5, (0.0, 3.0)) == (1.0, 0.0)


def bank_engine(tmp_path):
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects={"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None}]})
    eng = build_engine(make_config(), MemoryBackend(), NullTracer(), vocab=load_vocabulary(tax))
    Initializer(eng).construct(ConstructionSpec.load(world(tmp_path, bank()), tax), tax, start=date(2024, 1, 1),
                               vocab=load_vocabulary(tax))
    return eng


def test_the_daily_model_accumulates_and_keeps_identity_weights_fixed(tmp_path):
    eng = bank_engine(tmp_path)
    g = eng.wm.graph
    fixed = {iid: g.interactions[iid].forward for iid in ("w-income", "acme.id.cet1:acme.capital", "w-assets")}
    assert eng.wm.channels["w-income"].recursion.acc
    # income reported one sd above its level (1.2 against 1.0, scale 0.2) every day; capital is never reported
    run_days(eng, 60, events=lambda d: [observe_event(f"inc{d}", {"acme.income": 1.2, "acme.cet1": 12.0},
                                                      date(2024, 1, 1) + timedelta(days=d))])
    dev = eng.wm.deviations
    day = int(eng.wm.last_processed_day)
    cap = [dev.z("acme.capital", t) for t in (day - 30, day)]
    assert cap[1] > cap[0] > 0.05                                    # the stock keeps rising while the flow stays up
    for iid, before in fixed.items():
        after = eng.wm.graph.interactions[iid].forward
        assert after.effect == before.effect and after.kernel == before.kernel, iid


def test_a_rebuilt_channel_state_keeps_its_accumulation(tmp_path):
    from axelrod_wm.dynamics.daily import sync_channel_states

    eng = bank_engine(tmp_path)
    cs = eng.wm.channels["w-income"]
    ctx = eng.context(learn=True, now=eng.wm.clock, processing_day=0)
    with eng.mutator.begin("test", at=eng.wm.clock) as txn:
        txn.replace("wm.channels", cs.model_copy(update={"recursion": cs.recursion.model_copy(update={"acc": False})}))
    with eng.mutator.begin("test", at=eng.wm.clock) as txn:
        assert "w-income" in sync_channel_states(eng.wm, ctx, txn, 0)
    assert eng.wm.channels["w-income"].recursion.acc


def test_the_synthetic_world_accumulates_and_reads_piecewise_states(tmp_path):
    spec = ConstructionSpec.load(world(tmp_path, bank()), _taxonomy(tmp_path, attrs=ATTRS))
    truth = TruthSpec(effect_multiplier_sd=0.5, ar_coefficient=0.0, noise_sd={"default": 0.0})
    w = SyntheticWorld(spec, truth, seed=1, origin=date(2026, 1, 5),
                       scripted_shocks=[(datetime(2026, 1, 6, 12), [{"subentity": "acme.income", "delta": 1.0}])])
    w.advance(datetime(2026, 4, 30, 12))
    ch = {c.id: c for c in w.channels}
    assert ch["w-income"].beta == pytest.approx(0.2) and ch["w-income"].kappa == pytest.approx(1 / 91)
    day = w.day_of(datetime(2026, 4, 30, 12))
    # 2-day delay: after 2 + 91 days the stock is one weight (0.2 sd) up, then the cet1 ratio follows by identity
    assert w.z_at("acme.capital", 1 + 2 + 91) == pytest.approx(0.2, abs=0.01)
    assert w.z_at("acme.capital", day) > w.z_at("acme.capital", 60) > 0
    assert w.z_at("acme.cet1", day) == pytest.approx(2.0 * w.z_at("acme.capital", day - 1), abs=0.02)
    # a sign flip by state: the tariff reaches reinvestment through a piecewise moderator
    assert any(m[1] == "piecewise" and m[4] == "below" for m in ch["s-reinvest"].mods)
    w2 = SyntheticWorld(spec, truth, seed=1, origin=date(2026, 1, 5),
                        scripted_shocks=[(datetime(2026, 1, 6, 12), [{"subentity": "macro.tariff", "delta": 1.0}])])
    w2.advance(datetime(2026, 2, 28, 12))
    # nim sits at its level (z 0 > -2): not below 2.0, so the reinvestment response is reversed
    assert w2.z_at("acme.reinvest", 50) < 0
