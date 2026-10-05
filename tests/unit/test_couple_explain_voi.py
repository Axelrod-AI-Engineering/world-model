"""Couplers (§8.9.3), path attribution (§8.10), and value of information (§8.11)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from axelrod_wm.core.distributions import Beta, Gaussian
from axelrod_wm.core.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.core.interaction import EdgeDynamics
from axelrod_wm.core.temporal import KernelSpec
from axelrod_wm.engine.explain import top_paths
from axelrod_wm.engine.interfaces import PrefilledModel
from axelrod_wm.engine.performance.couple import IterativeBlockCoupler, UnionGraphCoupler
from axelrod_wm.engine.performance.records import Network, NetworkKind
from axelrod_wm.engine.propagation import Channel, ShockInput
from axelrod_wm.engine.regressors import graph_channels
from tests.conftest import START, constructed_engine, real_event, warm_taxonomies

NOW = START + timedelta(days=30)


def test_iterative_block_matches_union_graph_on_six_nodes():
    eng = constructed_engine(build=True)
    ctx = eng.context(learn=False, now=NOW)
    ctx.scope, ctx.notes["horizon_steps"] = "T-c", 26
    keys = {"e30", "e01", "e25", "e26", "e15"}
    chans = graph_channels(eng.wm, keys)
    model = PrefilledModel(channels=chans, analog_evidence={}, network_episodes={}, drifts={}, instance_ids=[], notes=[])
    n1 = Network(id="NW-1", kind=NetworkKind.SUPERENTITY, instance_id=None, pattern_id=None, relevance=1.0,
                 subentity_ids=[], channels=[chans["e30"], chans["e01"]])
    n2 = Network(id="NW-2", kind=NetworkKind.SUPERENTITY, instance_id=None, pattern_id=None, relevance=0.5,
                 subentity_ids=[], channels=[chans["e25"], chans["e26"], chans["e15"]])
    for n in (n1, n2):
        n.subentity_ids = sorted({s for c in n.channels for s in (c.source_id, c.target_id)})
    subs = set(n1.subentity_ids) | set(n2.subentity_ids)
    assert len(subs) == 6
    shock = [ShockInput(subentity_id="interest_rates.us_policy_rate", size=1.0, start_step=1)]
    prop = eng.components["propagator"]
    u = UnionGraphCoupler(eng.config, prop)
    it = IterativeBlockCoupler(eng.config, prop)
    eff_u = u.couple([n1, n2], {}, shock, model, ctx).minus(u.couple([n1, n2], {}, [], model, ctx))
    eff_i = it.couple([n1, n2], {}, shock, model, ctx).minus(it.couple([n1, n2], {}, [], model, ctx))
    for sid in sorted(subs):
        for t in (10, 26):
            a, b = eff_u.median_z(sid, t), eff_i.median_z(sid, t)
            assert abs(a - b) <= 0.05 + 0.1 * abs(a), (sid, t, a, b)


def _chain_channel(src, tgt, beta):
    dyn = EdgeDynamics(effect=Gaussian(mu=beta, sigma=0.05),
                       kernel=KernelSpec.model_validate({"delay_days": 7, "lag_days": 14, "duration_days": None}))
    return Channel(interaction_id=f"{src}{tgt}", source_id=src, target_id=tgt, dynamics=dyn,
                   existence=Beta(alpha=9, beta=1), key=f"{src}{tgt}")


def test_path_shares_on_a_linear_chain_sum_to_one():
    chans = [_chain_channel("a", "b", 0.8), _chain_channel("b", "c", 0.5), _chain_channel("c", "d", -0.6)]
    paths = top_paths(chans, [("a", 2.0)], ["b", "c", "d"], horizon=26, step_days=7, min_delay=1)
    for t in ("b", "c", "d"):
        share = sum(p.share for p in paths if p.target_id == t)
        assert abs(share - 1.0) <= 0.05
    d = next(p for p in paths if p.target_id == "d")
    assert d.interaction_ids == ["ab", "bc", "cd"] and d.gain == pytest.approx(2.0 * 0.8 * 0.5 * -0.6)


def _hyp(eng, p, hid="H-t"):
    return Hypothesis(id=hid, kind=HypothesisKind.INTERACTION_PRESENT, statement="e43 holds", interaction_id="e43",
                      source_id="inflation.headline_cpi", target_id="federal_reserve.policy_stance", probability=p,
                      scored_at=NOW, origin="human", half_life_days=14)


def test_voi_peaks_at_half_and_vanishes_at_certainty():
    eng = constructed_engine(build=True)
    scorer = eng.components["hypothesis_scorer"]
    ctx = eng.context(learn=False, now=NOW)
    vals = {}
    for alpha, beta in ((1.0, 1.0), (9.0, 1.0), (1e6, 1e-3), (1e-3, 1e6)):
        with eng.mutator.begin(f"e43-{alpha}", now=NOW) as txn:
            txn.update("interactions", "e43", existence=Beta(alpha=alpha, beta=beta))
        p = alpha / (alpha + beta)
        vals[round(p, 3)] = scorer.score(_hyp(eng, p), eng.wm, eng.ltm, ctx)
    assert vals[0.5] > vals[0.9] > 0
    assert vals[1.0] == pytest.approx(0.0, abs=1e-3) and vals[0.0] == pytest.approx(0.0, abs=1e-3)


def test_voi_halves_after_one_half_life():
    eng = constructed_engine(build=True)
    h = _hyp(eng, 0.5).model_copy(update={"informational_value": 0.8})
    assert h.current_value(NOW + timedelta(days=14)) == pytest.approx(0.4)
    assert h.current_value(NOW + timedelta(days=28)) == pytest.approx(0.2)


def test_hypotheses_rescore_when_an_update_touches_their_entities():
    eng = constructed_engine(build=True)
    warm_taxonomies(eng)
    with eng.mutator.begin("h", now=START) as txn:
        txn.add("hypotheses", _hyp(eng, 0.5).model_copy(update={"scored_at": START}))
    at = START + timedelta(days=10)
    eng.learning.run(real_event([{"op": "observe_value",
                                  "target": {"kind": "concrete", "subentity_id": "inflation.headline_cpi"},
                                  "value": 3.1, "observed_at": at.isoformat()}], "GUE-touch", at,
                                produced_by="data_feed", event_type="data_release"), at)
    h = eng.wm.hypotheses["H-t"]
    assert h.scored_at == at and h.informational_value > 0
    # an update elsewhere does not touch it
    later = at + timedelta(days=7)
    eng.learning.run(real_event([{"op": "observe_value",
                                  "target": {"kind": "concrete", "subentity_id": "climate_change.carbon_price"},
                                  "value": 71.0, "observed_at": later.isoformat()}], "GUE-far", later,
                                produced_by="data_feed", event_type="data_release"), later)
    assert eng.wm.hypotheses["H-t"].scored_at == at
    assert np.isfinite(h.informational_value)
