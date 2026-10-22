"""Isolation (isolate.py, §8.9.1): channels outside the prefilled model, instances with missing or retired edges,
the residual and context networks' fallbacks, patterns bound only for one question, and the k-hop baseline."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest

from axelrod_wm.engine.context import GraphOverlay
from axelrod_wm.inference.isolate import (
    BoundSuperentityIsolator,
    KHopIsolator,
    channel_for,
    instance_channels,
    network_seeds,
    residual_network,
    watch_network,
)
from axelrod_wm.inference.records import NetworkKind
from axelrod_wm.model.superentity import SuperentityInstance
from tests.conftest import START, constructed_engine, make_config, oil_thesis

NOW = START + timedelta(days=30)
OIL = "resources_energy.oil_price"


def _setup(config=None, thesis=None, overlay=True):
    eng = constructed_engine(build=True, config=config)
    th = thesis or oil_thesis(NOW)
    ctx = eng.context(learn=False, now=NOW)
    ctx.scope = th.id
    ctx.overlay = GraphOverlay(eng.wm, scope=th.id) if overlay else None
    ctx.notes["horizon_days"] = int(th.horizon_days)
    ctx.notes["targets"] = list(th.targets)
    shared = eng.shared.run(th.event, ctx, txn=None)
    return eng, ctx, shared


@pytest.fixture(scope="module")
def oil():
    return _setup()


def _without_model_channels(shared):
    return shared.model.model_copy(update={"channels": {}})


def test_a_channel_outside_the_prefilled_model_comes_from_the_graph(oil):
    eng, _ctx, shared = oil
    model = _without_model_channels(shared)
    plain = channel_for("e43", eng.wm, model, set())
    assert plain.interaction_id == "e43" and plain.forced is None
    forced = channel_for("e43", eng.wm, model, set(), forced=False)
    assert forced.forced is False and forced.dynamics == plain.dynamics
    assert channel_for("no_such_edge", eng.wm, model, set()) is None


def test_instance_channels_skip_missing_retired_repeated_and_dangling_edges():
    eng, _ctx, shared = _setup()
    wm = eng.wm
    e43 = wm.graph.interactions["e43"]
    wm.graph.interactions["e-retired"] = e43.model_copy(update={"id": "e-retired", "retired_at": NOW})
    wm.graph.interactions["e-dangling"] = e43.model_copy(update={"id": "e-dangling", "source_id": "ghost.value"})
    inst = SuperentityInstance(id="inst-t", pattern_id="S8", bindings={},
                               interaction_ids=["e43", "no_such_edge", "e-retired", "e43", "e-dangling"],
                               absent_interaction_ids=["e44"])
    chans = instance_channels(inst, wm, _without_model_channels(shared), set())
    assert [c.channel_key for c in chans] == ["e43", "e44"]
    assert chans[0].forced is None and chans[1].forced is False          # the absent edge is forced off


def test_without_an_analysis_the_residual_is_the_significant_neighbourhood(oil):
    eng, ctx, shared = oil
    bare = shared.model_copy(update={"analysis": shared.analysis.model_copy(update={"result": None})})
    r = residual_network(bare, [], [OIL], eng.wm, ctx, 3)
    assert r is not None and r.kind == NetworkKind.RESIDUAL and r.id == f"NW-{ctx.scope}-3"
    min_sig = float(ctx.config.isolation.residual_min_significance)
    near = eng.wm.graph.neighborhood([OIL], int(ctx.config.isolation.residual_hops), min_sig)
    for c in r.channels:
        assert c.source_id in near and c.target_id in near
        assert eng.wm.graph.interactions[c.interaction_id].significance_mean() >= min_sig
    # every channel already held by a kept network leaves nothing
    assert residual_network(bare, [r], [OIL], eng.wm, ctx, 4) is None


def test_the_context_network_needs_something_to_watch_and_a_path_to_it(oil):
    eng, ctx, shared = oil
    assert watch_network(shared, [], [], eng.wm, ctx, k=1) is None
    assert watch_network(shared, [], ["exxonmobil"], eng.wm, ctx, k=1, max_hops=0) is None
    net = watch_network(shared, [], ["exxonmobil"], eng.wm, ctx, k=1)
    assert net is not None and net.name == "Context paths"
    assert any(s.startswith("exxonmobil.") for s in net.subentity_ids)


def test_unknown_and_composite_patterns_are_not_networks(oil):
    eng, ctx, shared = oil
    iso = eng.components["isolator"]
    args = ([OIL], {"resources_energy"}, {}, eng.wm, eng.ltm, ctx, shared.model)
    assert iso._candidate("S999", 0.5, *args) is None
    assert eng.ltm.object_generalizations.patterns["S10"].sub_pattern_ids
    assert iso._candidate("S10", 0.5, *args) is None                       # a composite: its parts are networks


@pytest.mark.parametrize("overlay", [True, False])
def test_a_pattern_with_no_instance_is_bound_for_this_question_only(overlay):
    eng, ctx, shared = _setup(overlay=overlay)
    iso = eng.components["isolator"]
    everyone = set(eng.wm.graph.entities)
    assert not any(i.pattern_id == "HP1" for i in eng.wm.graph.instances.values())
    c = iso._candidate("HP1", 0.4, [OIL], everyone, {}, eng.wm, eng.ltm, ctx, shared.model)
    inst = c["instance"]
    assert inst.transient and inst.pattern_id == "HP1" and inst.id not in eng.wm.graph.instances
    if overlay:
        assert ctx.overlay.graph.instances[inst.id] is inst and ctx.overlay.created["instances"] == [inst.id]
    else:
        assert inst.id == f"inst-{ctx.scope}-x"
    # no distances given: no reach, so the relevance is half the attention
    assert c["reach"] == 0.0 and c["relevance"] == pytest.approx(0.2)
    # its members come from the bound entities, as the instance is not in the graph
    with_dist = iso._candidate("HP1", 0.4, [OIL], everyone, {s: 1.0 for s in eng.wm.graph.subentities},
                               eng.wm, eng.ltm, ctx, shared.model)
    assert with_dist["reach"] == pytest.approx(math.exp(-1.0))


def test_a_pattern_recalled_twice_is_isolated_once(oil):
    eng, ctx, shared = oil
    iso = eng.components["isolator"]
    once = iso.isolate(shared, eng.wm, eng.ltm, ctx)
    twice = shared.model_copy(update={"recall": shared.recall.model_copy(
        update={"superentities": shared.recall.superentities + shared.recall.superentities[:2]})})
    again = iso.isolate(twice, eng.wm, eng.ltm, ctx)
    assert [n.pattern_id for n in again] == [n.pattern_id for n in once]


def test_the_k_hop_baseline_falls_back_to_the_plain_neighbourhood():
    cfg = make_config(isolation={"residual_min_significance": 1e9})
    eng, ctx, shared = _setup(config=cfg)
    assert residual_network(shared, [], [OIL], eng.wm, ctx, 1) is None
    nets = KHopIsolator(cfg).isolate(shared, eng.wm, eng.ltm, ctx)
    assert len(nets) == 1 and nets[0].relevance == 1.0 and nets[0].name == "Residual"
    near = eng.wm.graph.neighborhood(network_seeds(shared, eng.wm, ctx), int(ctx.config.isolation.reach_hops), 0.0)
    assert OIL in nets[0].subentity_ids and set(nets[0].subentity_ids) <= near


def test_the_k_hop_baseline_is_empty_without_seeds():
    cfg = make_config(isolation={"residual_min_significance": 1e9})
    eng, ctx, shared = _setup(config=cfg, thesis=oil_thesis(NOW, delta=0))
    assert not shared.parsed.shocks
    assert KHopIsolator(cfg).isolate(shared, eng.wm, eng.ltm, ctx) == []
    assert isinstance(BoundSuperentityIsolator(cfg).isolate(shared, eng.wm, eng.ltm, ctx), list)


def test_an_instance_bound_to_unknown_entities_has_no_members_and_no_reach():
    eng, ctx, shared = _setup()
    inst = SuperentityInstance(id="inst-HP2", pattern_id="HP2", bindings={"a": "ghost_actor"}, interaction_ids=[])
    with eng.mutator.begin("test", at=eng.wm.clock) as txn:
        txn.add("instances", inst)
    iso = eng.components["isolator"]
    c = iso._candidate("HP2", 0.3, [OIL], {"ghost_actor"}, {s: 0.0 for s in eng.wm.graph.subentities},
                       eng.wm, eng.ltm, ctx, shared.model)
    assert c["instance"].id == "inst-HP2" and c["reach"] == 0.0 and c["relevance"] == pytest.approx(0.15)


def test_rivals_are_compared_on_the_instance_of_the_network_they_rival(oil):
    eng, ctx, shared = oil
    nets = eng.components["isolator"].isolate(shared, eng.wm, eng.ltm, ctx)
    by_pattern = {n.pattern_id: n for n in nets if n.pattern_id}
    assert {"S8", "S9"} <= set(by_pattern)                    # rivals both kept, S9 anchored to S8's members
    assert by_pattern["S9"].instance_id == "inst-S9"


def test_a_faint_edge_inside_the_neighbourhood_stays_out_of_the_residual():
    from axelrod_wm.model.distributions import Beta

    eng, ctx, shared = _setup()
    wm = eng.wm
    e43 = wm.graph.interactions["e43"]
    wm.graph.interactions["e-faint"] = e43.model_copy(update={"id": "e-faint", "source_id": OIL,
                                                              "target_id": "inflation.headline_cpi",
                                                              "existence": Beta(alpha=1e-3, beta=1e6)})
    bare = shared.model_copy(update={"analysis": shared.analysis.model_copy(update={"result": None})})
    r = residual_network(bare, [], [OIL], wm, ctx, 1)
    assert "inflation.headline_cpi" in wm.graph.neighborhood([OIL], int(ctx.config.isolation.residual_hops),
                                                             float(ctx.config.isolation.residual_min_significance))
    assert r is not None and "e-faint" not in {c.interaction_id for c in r.channels}
