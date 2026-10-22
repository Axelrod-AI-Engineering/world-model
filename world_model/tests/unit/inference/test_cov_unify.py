"""Unification (unify.py, §8.9.4): which networks are rivals, how scenarios branch on open hypotheses and are
weighed, how samples are split among them, and the forecast's edge cases (short runs, no scenarios)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from axelrod_wm.dynamics.propagation import Channel, PropagationResult
from axelrod_wm.dynamics.regressors import graph_channels
from axelrod_wm.inference.records import ForecastScenario, Network, NetworkKind
from axelrod_wm.inference.unify import (
    ChannelsAndRivalsUnifier,
    PatternAndSignRivalDetector,
    SupportFitTrackWeighter,
    UniformWeighter,
    largest_remainder,
    network_log_fit,
)
from axelrod_wm.model.distributions import Beta, Gaussian
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.model.interaction import EdgeDynamics
from axelrod_wm.model.temporal import KernelSpec
from tests.conftest import START, constructed_engine, oil_thesis

NOW = START + timedelta(days=30)
CPI = "inflation.headline_cpi"


def _ch(src, tgt, beta, key=None):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=0.05),
                       kernel=KernelSpec.model_validate({"delay_days": 7, "lag_days": 14, "duration_days": None}))
    key = key or f"{src}>{tgt}"
    return Channel(interaction_id=key, source_id=src, target_id=tgt, dynamics=dyn, existence=Beta(alpha=9, beta=1),
                   key=key)


def _net(nid, channels, **kw):
    subs = sorted({s for c in channels for s in (c.source_id, c.target_id)})
    return Network(id=nid, kind=NetworkKind.RESIDUAL, instance_id=None, pattern_id=None, subentity_ids=subs,
                   channels=channels, relevance=kw.pop("relevance", 1.0), **kw)


@pytest.fixture(scope="module")
def eng():
    return constructed_engine(build=True)


def _ctx(eng, horizon=None):
    ctx = eng.context(learn=False, now=NOW)
    ctx.scope = "T-u"
    if horizon is not None:
        ctx.notes["horizon_days"] = horizon
    return ctx


# -- rivals ---------------------------------------------------------------------------------------------
def test_networks_disagreeing_on_a_sign_or_on_an_edge_are_rivals(eng):
    det = PatternAndSignRivalDetector()
    a = _net("NW-a", [_ch("x", "y", 0.5)])
    b = _net("NW-b", [_ch("x", "y", -0.4)])                    # the same pair, the opposite sign
    c = _net("NW-c", [_ch("x", "y", -0.2)])                    # rivals a, and (through a) joins b's group
    d = _net("NW-d", [_ch("p", "q", 0.3)], forced_present=["e1"])
    e = _net("NW-e", [_ch("q", "r", 0.3)], forced_absent=["e1"])   # says d's edge is absent
    f = _net("NW-f", [_ch("x", "y", 0.9)])                     # agrees with a: rivals only b and c
    assert det.groups([a, b, c, d, e, f], eng.ltm) == [["NW-a", "NW-b", "NW-c", "NW-f"], ["NW-d", "NW-e"]]
    assert det.groups([a, f, d], eng.ltm) == []


# -- weights ---------------------------------------------------------------------------------------------
def test_the_fit_skips_targets_outside_the_graph(eng):
    ctx = _ctx(eng)
    assert network_log_fit(_net("NW-g", [_ch(CPI, "ghost.value", 0.5)]), eng.wm, eng.ltm, ctx) == 0.0


def test_branched_hypotheses_weigh_scenarios_by_p_or_one_minus_p(eng):
    ctx = _ctx(eng)
    h = Hypothesis(id="H-w", kind=HypothesisKind.INTERACTION_PRESENT, statement="e43", interaction_id="e43",
                   probability=0.3, scored_at=NOW, origin="human")
    eng.wm.hypotheses["H-w"] = h
    try:
        sc = [ForecastScenario(id="S1", name="on", weight=0.0, network_ids=[], branched_hypothesis_ids={"H-w": True}),
              ForecastScenario(id="S2", name="off", weight=0.0, network_ids=[],
                               branched_hypothesis_ids={"H-w": False, "H-gone": True})]
        w = SupportFitTrackWeighter().weights(sc, [], eng.wm, eng.ltm, ctx)
    finally:
        del eng.wm.hypotheses["H-w"]
    assert w == pytest.approx([0.3, 0.7 * 0.5])                 # an unknown hypothesis counts as a coin flip
    assert UniformWeighter().weights(sc, [], eng.wm, eng.ltm, ctx) == [1.0, 1.0]


@pytest.mark.parametrize("total, weights, counts", [
    (10, [0.5, 0.5], [5, 5]),
    (10, [0.95, 0.05], [9, 1]),         # 9 and 0, and 5% is owed a sample
    (100, [0.995, 0.005], [100, 0]),    # under 1% gets no guaranteed sample
    (100, [0.985, 0.015], [99, 1]),     # 1.5% floors to 1
    (10, [0.991, 0.009], [10, 0]),
    (2, [0.4, 0.3, 0.3], [0, 1, 1]),    # every weight gets one, too many: the first loses its sample back
    (3, [0.9, 0.05, 0.05], [1, 1, 1]),
])
def test_largest_remainder_splits_samples_and_keeps_the_total(total, weights, counts):
    out = largest_remainder(total, weights)
    assert out == counts and sum(out) == total


def test_a_weight_over_one_percent_gets_a_sample_even_when_it_floors_to_zero():
    assert largest_remainder(20, [0.98, 0.02]) == [19, 1]
    assert largest_remainder(10, [0.97, 0.03]) == [9, 1]


# -- plan: branching on an open hypothesis -----------------------------------------------------------------
def test_an_open_valuable_uncertain_hypothesis_on_a_network_edge_branches_the_scenarios(eng):
    ctx = _ctx(eng)
    chans = graph_channels(eng.wm, {"e43"})
    net = _net("NW-1", list(chans.values()))
    h = Hypothesis(id="H-b", kind=HypothesisKind.INTERACTION_PRESENT, statement="e43", interaction_id="e43",
                   probability=0.4, informational_value=1.0, scored_at=NOW, origin="human")
    eng.wm.hypotheses["H-b"] = h
    try:
        out = ChannelsAndRivalsUnifier().plan([net], eng.wm, eng.ltm, ctx)
    finally:
        del eng.wm.hypotheses["H-b"]
    assert [(s.name, s.forced_existence, s.branched_hypothesis_ids) for s in out] == [
        ("H-b present", {"e43": True}, {"H-b": True}), ("H-b absent", {"e43": False}, {"H-b": False})]
    assert [s.weight for s in out] == pytest.approx([0.4, 0.6])
    assert all(s.network_ids == ["NW-1"] for s in out)


# -- combine ---------------------------------------------------------------------------------------------
def _result(sids, z):
    return PropagationResult({s: i for i, s in enumerate(sids)}, {}, np.asarray(z, dtype=float), None)


def test_a_network_without_an_isolated_run_adds_nothing_to_the_decomposition(eng):
    ctx = _ctx(eng, horizon=2)
    th = oil_thesis(NOW, targets=[CPI], horizon_days=2)
    on = _result([CPI], [[[0.0, 0.5, 1.0]], [[0.0, 0.5, 1.0]]])
    off = _result([CPI], np.zeros((2, 1, 3)))
    sc = [ForecastScenario(id="SC-1", name="one", weight=1.0, network_ids=["NW-1"])]
    fc = ChannelsAndRivalsUnifier().combine(th, sc, {"SC-1": on}, {"SC-1": off}, {}, [], ctx)
    assert fc.targets == [CPI] and len(fc.effect_summary[CPI]) == 3
    assert fc.effect_summary[CPI][-1].q50 == pytest.approx(1.0)
    assert fc.decomposition[CPI] == {"NW-1": 0.0, "coupling": pytest.approx(1.0)}


def test_without_scenarios_the_forecast_holds_todays_level(eng):
    ctx = _ctx(eng, horizon=3)
    th = oil_thesis(NOW, targets=[CPI], horizon_days=3)
    net = _net("NW-1", [_ch(CPI, "inflation.core_cpi", 0.5)])
    fc = ChannelsAndRivalsUnifier().combine(th, [], {}, {}, {}, [net], ctx)
    assert fc.targets == [CPI] and fc.scenarios == [] and fc.decomposition == {} and fc.isolated == {}
    z0 = eng.wm.deviations.z_at(CPI, ctx.today) or 0.0
    assert all(s.q50 == pytest.approx(z0) for s in fc.z_summary[CPI])
    assert all(s.q50 == 0.0 for s in fc.effect_summary[CPI])
    assert [n.id for n in fc.networks] == ["NW-1"]
