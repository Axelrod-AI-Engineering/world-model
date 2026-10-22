"""Couplers (§8.9.3): block ordering, the round limit, values outside the graph, and boundary channels."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from axelrod_wm.dynamics.propagation import Channel, ShockInput
from axelrod_wm.engine.interfaces import PrefilledModel
from axelrod_wm.inference.couple import IterativeBlockCoupler, UnionGraphCoupler, union_channels
from axelrod_wm.inference.records import Network, NetworkKind
from axelrod_wm.model.distributions import Beta, Gamma, Gaussian
from axelrod_wm.model.interaction import EdgeDynamics, ParameterBinding
from axelrod_wm.model.temporal import KernelSpec
from tests.conftest import START, constructed_engine, make_config

NOW = START + timedelta(days=30)
H = 30
CPI = "inflation.headline_cpi"          # a real value, downstream of two toy values outside the graph


def _ch(src, tgt, beta, params=()):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=0.01),
                       kernel=KernelSpec.model_validate({"delay_days": 2, "lag_days": 3, "duration_days": None}))
    return Channel(interaction_id=f"{src}>{tgt}", source_id=src, target_id=tgt, dynamics=dyn,
                   existence=Beta(alpha=99, beta=1), key=f"{src}>{tgt}", parameters=list(params))


def _net(nid, relevance, subs, chans):
    return Network(id=nid, kind=NetworkKind.SUPERENTITY, instance_id=None, pattern_id=None, relevance=relevance,
                   subentity_ids=subs, channels=chans)


MODEL = PrefilledModel(channels={}, analog_evidence={}, network_episodes={}, drifts={}, instance_ids=[], notes=[])
SHOCK = [ShockInput(subentity_id="toy.a", size=1.0, start_day=1)]


@pytest.fixture(scope="module")
def setup():
    eng = constructed_engine(build=True, config=make_config(propagation={"samples": 16}))
    ctx = eng.context(learn=False, now=NOW)
    ctx.scope, ctx.notes["horizon_days"] = "T-cov", H
    return eng, ctx


def _effect(coupler, nets, ctx):
    return coupler.couple(nets, {}, SHOCK, MODEL, ctx).minus(coupler.couple(nets, {}, [], MODEL, ctx))


def _chain(downstream):
    # the upstream network (a -> b, moderated by a value nobody owns) is the LESS relevant one, so its block runs
    # second: in the first round the downstream block has no path for b yet and starts from b's level
    mod = ParameterBinding(name="toy moderator", moderator_id="toy.m", coefficient=Gamma(k=2.0, theta=0.05))
    up = _net("NW-up", 0.5, ["toy.a", "toy.b"], [_ch("toy.a", "toy.b", 0.8, [mod])])
    down = _net("NW-down", 1.0, [downstream], [_ch("toy.b", downstream, 0.5)])
    return [up, down]


def test_a_downstream_block_run_first_still_matches_the_union_graph(setup):
    eng, ctx = setup
    prop = eng.components["propagator"]
    nets = _chain(CPI)
    eff_u = _effect(UnionGraphCoupler(eng.config, prop), nets, ctx)
    eff_i = _effect(IterativeBlockCoupler(eng.config, prop), nets, ctx)
    assert eff_u.median_z(CPI, H) == pytest.approx(0.4, abs=0.02)
    for sid in ("toy.a", "toy.b", CPI):
        assert eff_i.median_z(sid, H) == pytest.approx(eff_u.median_z(sid, H), abs=0.02), sid
    # the moderator is in the upstream block's system but owned by no block, so it is not merged into the result
    assert "toy.m" in eff_u.subentity_index and "toy.m" not in eff_i.subentity_index


def test_one_round_leaves_the_later_upstream_block_unseen(setup):
    eng, ctx = setup
    prop = eng.components["propagator"]
    eff = _effect(IterativeBlockCoupler(eng.config, prop, max_rounds=1), _chain(CPI), ctx)
    assert eff.median_z("toy.b", H) == pytest.approx(0.8, abs=0.02)
    assert eff.median_z(CPI, H) == pytest.approx(0.0, abs=1e-9)      # no second round to carry b's move across


def test_a_value_outside_the_graph_without_channels_of_its_own_is_left_out(setup):
    eng, ctx = setup
    prop = eng.components["propagator"]
    eff = _effect(IterativeBlockCoupler(eng.config, prop), _chain("toy.c"), ctx)
    assert sorted(eff.subentity_index) == ["toy.a", "toy.b"]
    assert eff.median_z("toy.b", H) == pytest.approx(0.8, abs=0.02)


def test_a_boundary_channel_to_a_value_missing_from_the_graph_is_skipped():
    own_a, own_b = _ch("x.a", "x.a2", 0.3), _ch("x.b", "x.b2", 0.3)
    graph = SimpleNamespace(subentities={"x.a": object()},          # x.b is missing
                            channel_items=lambda: [("e-ab", None, "x.a", "x.b", None)])
    ctx = SimpleNamespace(wm=SimpleNamespace(graph=graph))
    nets = [_net("NW-a", 1.0, ["x.a", "x.a2"], [own_a]), _net("NW-b", 0.5, ["x.b", "x.b2"], [own_b])]
    out = union_channels(nets, {own_b.interaction_id: False}, MODEL, ctx)
    assert [c.channel_key for c in out] == ["x.a>x.a2", "x.b>x.b2"]
    assert [c.forced for c in out] == [None, False]
