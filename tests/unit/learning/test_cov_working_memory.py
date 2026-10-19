"""Working-memory learning at its edges: the proposal kind reaches the parser, the reviewer's ripple
weights (scaled by the values upstream, replaced on a second approval), and the day's close (stale
hypotheses expire, stale non-soft refinements and finished ripples go, old points are pruned)."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import numpy as np

from axelrod_wm.learning.working_memory import judge_ripple, reset_and_prune
from axelrod_wm.memory.working import DeviationPoint, PendingRefinement, RippleJudgment, point_key, ripple_key
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind, HypothesisStatus
from tests.conftest import START, close_day, predict_day, real_event


class RecordingTxn:
    def __init__(self):
        self.calls = []

    def add(self, coll, obj, key=None):
        self.calls.append(("add", coll, key, obj))

    def replace(self, coll, obj, key=None):
        self.calls.append(("replace", coll, key, obj))


def _hop(target, iid):
    return SimpleNamespace(target_id=target, interaction_id=iid)


def _shared(transmission, z, result=True):
    res = SimpleNamespace(z_of=lambda sid: z.get(sid, np.zeros((0, 0)))) if result else None
    return SimpleNamespace(analysis=SimpleNamespace(result=res, transmission=transmission),
                           parsed=SimpleNamespace(processing_day=7))


def test_learn_hands_the_proposal_kind_to_the_parser(warm_engine):
    eng = warm_engine
    rec = eng.learning.working.learn(real_event([{"op": "annotate_interaction", "interaction_id": "e01", "note": "n",
                                                  "valid_from": START.isoformat()}], "GUE-PK"), eng.wm.clock, 0,
                                     proposal_kind="missing_relation")
    assert rec.shared.parsed.origin_hint == "missing_relation"


def test_no_ripple_weights_or_no_analysis_store_nothing():
    txn = RecordingTxn()
    wm = SimpleNamespace(ripple_judgments={})
    assert judge_ripple(SimpleNamespace(ripple={}, id="E"), _shared([], {}), wm, txn) == []
    assert judge_ripple(SimpleNamespace(ripple={"a.x": 0.5}, id="E"), _shared([], {}, result=False), wm, txn) == []
    assert txn.calls == []


def test_ripple_weights_scale_by_the_values_upstream_and_replace_a_stored_judgment():
    ev = SimpleNamespace(id="E", ripple={"b.y": 0.5, "c.z": 0.4, "d.w": 1.0, "e.v": 0.3, "f.u": 0.2, "g.t": 1.7})
    trans = [
        SimpleNamespace(subentity_id="b.y", order=1, path=[_hop("b.y", "e1:fwd")]),
        SimpleNamespace(subentity_id="c.z", order=2, path=[_hop("b.y", "e1:fwd"), _hop("c.z", "e2:fwd")]),
        SimpleNamespace(subentity_id="d.w", order=1, path=[_hop("d.w", "e3")]),          # weight 1: as expected
        SimpleNamespace(subentity_id="e.v", order=0, path=[]),                         # the shocked value itself
        SimpleNamespace(subentity_id="f.u", order=1, path=[_hop("f.u", "e4")]),          # no simulated path
        SimpleNamespace(subentity_id="h.s", order=1, path=[_hop("h.s", "e5")]),          # no weight given
    ]
    z = {"b.y": np.array([[0.0, 1.0, 2.0], [0.0, 3.0, 4.0]]), "c.z": np.array([[1.0, 1.0], [3.0, 3.0]])}
    wm = SimpleNamespace(ripple_judgments={ripple_key("E", "c.z"): object()})
    txn = RecordingTxn()
    out = judge_ripple(ev, _shared(trans, z), wm, txn)
    assert out == ["b.y", "c.z"]
    (a_kind, a_coll, a_key, a_j), (r_kind, _, r_key, r_j) = txn.calls
    assert (a_kind, a_coll, a_key) == ("add", "wm.ripple_judgments", "E|b.y")
    assert a_j.path == [0.0, 2.0, 3.0] and a_j.weight == 0.5 and a_j.start_day == 7 and a_j.via == ["e1"]
    # c.z's expected ripple is scaled by b.y's weight upstream; its own weight is stored, not applied
    assert (r_kind, r_key) == ("replace", "E|c.z")
    assert r_j.path == [1.0, 1.0] and r_j.weight == 0.4 and r_j.order == 2 and r_j.via == ["e1", "e2"]


def _pending(pid, expires, soft=False):
    return PendingRefinement.model_validate({
        "id": pid, "op": {"op": "annotate_interaction", "interaction_id": "e01", "note": "n",
                          "valid_from": START.isoformat()},
        "end": "target", "reached": 0, "node_id": "gen:obj:root", "candidates": {}, "evidence": [],
        "source_event_id": "GUE-X", "created_at": START, "expires_at": expires, "soft": soft})


def test_closing_a_day_drops_what_has_gone_stale(warm_engine):
    eng = warm_engine
    dev = eng.wm.deviations
    d = eng.wm.last_processed_day + 1
    end = dev.day_end(d)
    old = end - timedelta(days=200)
    hyp = dict(kind=HypothesisKind.INTERACTION_PRESENT, statement="s", source_id="inflation.headline_cpi",
               target_id="asset_prices.equity_index", probability=0.2, origin=Origin.INFERENCE, half_life_days=14.0)
    with eng.mutator.begin("stale", at=eng.wm.clock) as txn:
        txn.add("wm.hypotheses", Hypothesis(id="H-stale", scored_at=old, **hyp))
        txn.add("wm.hypotheses", Hypothesis(id="H-fresh", scored_at=end, informational_value=1.0, **hyp))
        txn.add("wm.hypotheses", Hypothesis(id="H-owned", scored_at=old, comovement_id="CM-1", **hyp))
        txn.add("wm.hypotheses", Hypothesis(id="H-closed", scored_at=old, status=HypothesisStatus.REFUTED, **hyp))
        txn.add("wm.pending_refinements", _pending("P-old", old))
        txn.add("wm.pending_refinements", _pending("P-soft", old, soft=True))
        txn.add("wm.pending_refinements", _pending("P-live", end + timedelta(days=5)))
        txn.add("wm.ripple_judgments", RippleJudgment(event_id="E", subentity_id="a.x", weight=0.5, start_day=d - 3,
                                                      path=[0.1, 0.2, 0.3, 0.4]), key="E|a.x")
        txn.add("wm.ripple_judgments", RippleJudgment(event_id="E", subentity_id="b.y", weight=0.5, start_day=d - 1,
                                                      path=[0.1, 0.2, 0.3, 0.4]), key="E|b.y")
        txn.set("wm.pending_episode_tags", ["decision-outcome"])
    predict_day(eng, d)
    _moves, report = close_day(eng, d)
    hs = eng.wm.hypotheses
    assert report.hypotheses_expired == ["H-stale"]
    assert hs["H-stale"].status == HypothesisStatus.EXPIRED
    assert hs["H-fresh"].status == hs["H-owned"].status == HypothesisStatus.OPEN
    assert hs["H-closed"].status == HypothesisStatus.REFUTED
    assert set(eng.wm.pending_refinements) == {"P-soft", "P-live"}
    assert set(eng.wm.ripple_judgments) == {"E|b.y"}
    assert eng.wm.pending_episode_tags == []


def test_pruning_drops_points_older_than_the_kept_history(warm_engine):
    eng = warm_engine
    wm = eng.wm
    keep = eng.config.keep_days(_longest(eng))
    day = keep + 40
    sid = "inflation.headline_cpi"
    with eng.mutator.begin("pts", at=wm.clock) as txn:
        for k in (0, 1, day - keep + 1):
            txn.add("wm.deviations.points", DeviationPoint(z=0.1, var=0.01, level=0.1), key=point_key(sid, k))
    ctx = eng.context(learn=True, now=wm.clock)
    with eng.mutator.begin("prune", at=wm.clock) as txn:
        pruned = reset_and_prune(day, ctx, txn)
    assert pruned == 2      # days 0 and 1; the other values have no points there
    assert wm.deviations.first_kept_day == day - keep + 1
    assert point_key(sid, 0) not in wm.deviations.points and point_key(sid, day - keep + 1) in wm.deviations.points


def _longest(eng):
    from axelrod_wm.dynamics.kernels import mean_kernel_days

    min_delay = max(1, int(eng.config.propagation.min_delay_days))
    out = 0
    for _k, _i, _s, _t, dyn in eng.wm.graph.channel_items():
        d, l, _ = mean_kernel_days(dyn.kernel, min_delay)
        out = max(out, d + l)
    return out
