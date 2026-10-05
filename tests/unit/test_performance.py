"""The performance task (§8.9): isolation, unification, decomposition, determinism, the forecast layer."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from axelrod_wm.engine.interfaces import PrefilledModel
from axelrod_wm.engine.performance.couple import UnionGraphCoupler
from axelrod_wm.engine.performance.records import Network, NetworkKind
from axelrod_wm.engine.regressors import build_system, graph_channels
from axelrod_wm.memory.snapshots import state_hash
from tests.conftest import START, constructed_engine, make_config, oil_thesis, warm_taxonomies

NOW = START + timedelta(days=30)


@pytest.fixture(scope="module")
def posed():
    eng = constructed_engine(build=True)
    warm_taxonomies(eng)
    v, ids, h = eng.version, dict(eng.wm.ids.counters), eng.state_hash
    fc = eng.performance.run(oil_thesis(NOW), NOW)
    return eng, fc, v, ids, h


def _net(fc, pid):
    return next(n for n in fc.networks if n.pattern_id == pid)


def test_isolation_selects_s2_with_the_highest_reach(posed):
    eng, fc, *_ = posed
    reaches = {n.pattern_id: n for n in fc.networks if n.pattern_id}
    assert "S2" in reaches and "S1" in reaches
    assert any(n.kind == NetworkKind.RESIDUAL for n in fc.networks)


def test_isolation_keeps_rivals_and_a_residual_with_uncovered_edges(posed):
    eng, fc, *_ = posed
    pats = {n.pattern_id for n in fc.networks}
    assert {"S8", "S9"} <= pats
    residual = next(n for n in fc.networks if n.kind == NetworkKind.RESIDUAL)
    assert "e20" in residual.channel_ids          # oil -> input costs belongs to no superentity
    for n in fc.networks:
        if n.pattern_id:
            assert "e20" not in n.channel_ids


def test_rival_scenarios_weights_and_signs(posed):
    eng, fc, *_ = posed
    assert len(fc.scenarios) >= 2
    assert sum(s.weight for s in fc.scenarios) == pytest.approx(1.0, abs=1e-9)
    s8 = next(s for s in fc.scenarios if "S8" in s.name)
    s9 = next(s for s in fc.scenarios if "S9" in s.name)
    rate = "interest_rates.us_policy_rate"
    assert s8.effect_summary[rate][-1].q50 > s9.effect_summary[rate][-1].q50
    assert s8.forced_existence["e43"] is True and s9.forced_existence["e43"] is False
    assert fc.effect_summary["inflation.headline_cpi"][-1].q50 > 0


def test_decomposition_lists_each_network_and_coupling(posed):
    eng, fc, *_ = posed
    top = max(fc.scenarios, key=lambda s: s.weight)
    for target, parts in fc.decomposition.items():
        assert "coupling" in parts
        assert set(parts) - {"coupling"} == set(top.network_ids)


def test_explanation_has_paths_and_ordered_key_interactions(posed):
    eng, fc, *_ = posed
    ex = eng.wm.forecast_layer.by_thesis["T-01"].explanation
    assert len(ex.top_paths) >= 3
    assert ex.id == f"EX-{fc.id}" and fc.explanation_id == ex.id
    vals = [v for _, v in ex.key_interactions]
    assert vals == sorted(vals, reverse=True)
    assert ex.key_interactions[0][0] == "e08"
    by_target: dict[str, float] = {}
    for p in ex.top_paths:
        by_target[p.target_id] = by_target.get(p.target_id, 0.0) + p.share
    assert all(abs(v - 1.0) <= 0.05 for v in by_target.values())


def test_forecast_layer_bumps_no_version_and_leaves_ids_and_hash(posed):
    eng, fc, v, ids, h = posed
    assert fc.based_on_version == v == eng.version
    assert eng.wm.ids.counters == ids
    assert state_hash(eng.wm, eng.ltm) == h
    assert eng.wm.forecast_layer.pose_counts["T-01"] >= 1


def test_posing_twice_is_reproducible(posed):
    eng, fc, *_ = posed
    again = eng.performance.run(oil_thesis(NOW), NOW)
    assert again.id != fc.id and again.id.startswith("FC-T-01-")
    assert again.summary == fc.summary and again.effect_summary == fc.effect_summary
    assert [s.weight for s in again.scenarios] == [s.weight for s in fc.scenarios]


def test_baseline_thesis_has_zero_effect(posed):
    eng, *_ = posed
    base = eng.performance.run(oil_thesis(NOW, "T-00", delta=0.0, horizon_days=182, targets=[]), NOW)
    assert base.is_baseline
    for sid, s in base.effect_summary.items():
        assert s[-1].q50 == pytest.approx(0.0, abs=1e-9)
    assert set(base.targets) >= set(eng.config.hypotheses.watch_list)


def test_union_counts_a_shared_edge_once():
    eng = constructed_engine(build=True)
    ctx = eng.context(learn=False, now=NOW)
    ctx.scope, ctx.notes["horizon_steps"] = "T-u", 20
    chans = graph_channels(eng.wm, {"e01", "e25", "e26", "e15"})
    model = PrefilledModel(channels=chans, analog_evidence={}, network_episodes={}, drifts={}, instance_ids=[], notes=[])
    a = Network(id="NW-a", kind=NetworkKind.SUPERENTITY, instance_id=None, pattern_id=None, relevance=1.0,
                subentity_ids=[], channels=[chans["e01"], chans["e25"], chans["e26"]])
    b = Network(id="NW-b", kind=NetworkKind.SUPERENTITY, instance_id=None, pattern_id=None, relevance=0.5,
                subentity_ids=[], channels=[chans["e25"], chans["e26"], chans["e15"]])
    for n in (a, b):
        n.subentity_ids = sorted({s for c in n.channels for s in (c.source_id, c.target_id)})
    from axelrod_wm.engine.propagation import ShockInput

    shock = [ShockInput(subentity_id="interest_rates.us_policy_rate", size=1.0, start_step=1)]
    prop = eng.components["propagator"]
    coupled = UnionGraphCoupler(eng.config, prop).couple([a, b], {}, shock, model, ctx)
    union = [chans[k] for k in sorted(chans)]
    direct = prop.propagate(build_system(union, eng.wm, ctx, 20, extra_subentities=["interest_rates.us_policy_rate"]),
                            shock, eng.config.propagation.samples, ctx.child_rng("couple", "T-u"),
                            record_contributions=True)
    for sid in ("business_investment.capex_growth", "credit_availability.credit_growth"):
        assert np.allclose(coupled.z_of(sid), direct.z_of(sid))


def test_unifier_swaps_through_config():
    cfg = make_config(components={"unifier": "weighted_mixture", "coupler": "iterative_block",
                                  "isolator": "k_hop", "scenario_weighter": "uniform", "prefiller": "none",
                                  "recaller": "recency", "propagator": "deterministic_mean"})
    eng = constructed_engine(build=True, config=cfg)
    warm_taxonomies(eng)
    fc = eng.performance.run(oil_thesis(NOW), NOW)
    assert sum(s.weight for s in fc.scenarios) == pytest.approx(1.0)
    assert fc.effect_summary["inflation.headline_cpi"][-1].q50 > 0
