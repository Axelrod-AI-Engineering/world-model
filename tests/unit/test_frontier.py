"""The correlation frontier (§8.7): log, verify, propose; inconsistency; decay; rejection blocks."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from axelrod_wm.core.hypothesis import HypothesisStatus
from axelrod_wm.engine.frontier_test import decay_frontier
from axelrod_wm.memory.frontier import CoMovementStatus, pair_key
from tests.conftest import START, constructed_engine, real_event
from tests.unit.test_fold import _native

GAS, BCONF = "resources_energy.gas_price", "confidence.business_confidence"
OIL, CCONF = "resources_energy.oil_price", "confidence.consumer_confidence"


def _feed(eng, weeks: int, seed: int = 0, block_after: int | None = None):
    """Gas jumps every 8 weeks (alternating sign) and business confidence moves the other way a
    week later: a planted lag-1 relation. Oil and consumer confidence move independently at random
    every week: an inconsistent pair."""
    rng = np.random.default_rng(seed)
    with eng.mutator.begin("noise", now=START) as txn:
        for sid in (GAS, BCONF, OIL, CCONF):     # as if learned from history (§8.12)
            txn.update("subentities", sid, level_noise=0.3)
    z = {GAS: 0.0, BCONF: 0.0, OIL: 0.0, CCONF: 0.0}
    results = []
    for t in range(weeks):
        k = t // 8
        if t % 8 == 0 and t > 0:
            z[GAS] += 2.0 * (1 if k % 2 else -1)
        if t % 8 == 1 and t > 1:
            z[BCONF] -= 2.0 * (1 if k % 2 else -1)
        z[OIL] += rng.choice([-1.0, 1.0])
        z[CCONF] += rng.choice([-1.0, 1.0])
        for sid in (GAS, BCONF):
            z[sid] += rng.normal(0, 0.03)
        at = START + timedelta(days=7 * t, hours=1)
        ops = [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid},
                "value": _native(eng, sid, v), "observed_at": at.isoformat()} for sid, v in z.items()]
        results.append(eng.learning.run(real_event(ops, f"GUE-{t}", at, produced_by="data_feed",
                                                   event_type="data_release"), at))
    return results


def _proposals(results):
    return [p for r in results for p in r.proposal_events if p["kind"] == "frontier_promotion"]


def test_planted_relation_is_logged_verified_and_proposed():
    eng = constructed_engine(build=True)
    results = _feed(eng, 40)
    entries = eng.ltm.frontier.for_pair(GAS, BCONF)
    assert entries, "the planted pair was never logged"
    co = entries[0]
    assert co.sign == -1 and co.consistent >= 3 and co.support > 3
    props = [p for p in _proposals(results) if p.get("subject_id") == co.id]
    assert props, "no promotion proposal"
    assert co.status == CoMovementStatus.PROMOTION_PROPOSED
    op = props[0]["event"]["ops"][0]
    assert op["edge_type"] == "learned_causal" and op["existence"] == {"family": "beta", "alpha": 1.0, "beta": 3.0}
    # the proposal came after recognition + 1 = 4 consistent episodes at the earliest
    assert len(co.verified_days) >= 3
    h = eng.wm.hypotheses[co.hypothesis_id]
    assert h.probability > 0.4


def test_inconsistent_pair_is_not_proposed():
    eng = constructed_engine(build=True)
    results = _feed(eng, 40)
    subjects = {p.get("subject_id") for p in _proposals(results)}
    for co in eng.ltm.frontier.for_pair(OIL, CCONF):
        assert co.id not in subjects


def test_decay_removes_stale_entries():
    eng = constructed_engine(build=True)
    _feed(eng, 14)
    live = [co for co in eng.ltm.frontier.entries.values() if co.status == CoMovementStatus.HOLDING]
    assert live
    later = START + timedelta(days=7 * 14 + 365)
    ctx = eng.context(learn=True, now=later)
    with eng.mutator.begin("decay", now=later) as txn:
        decayed = decay_frontier(eng.wm, eng.ltm, ctx, txn, (START + timedelta(days=7 * 14)).date())
    assert set(decayed) >= {co.id for co in live}
    for cid in decayed:
        co = eng.ltm.frontier.entries[cid]
        assert co.status == CoMovementStatus.DECAYED
        assert eng.wm.hypotheses[co.hypothesis_id].status == HypothesisStatus.EXPIRED


def test_rejection_blocks_the_pair():
    eng = constructed_engine(build=True)
    with eng.mutator.begin("block", now=START) as txn:
        txn.merge("ltm.frontier.blocked_until", {pair_key(GAS, BCONF): START + timedelta(days=3650)})
    _feed(eng, 30)
    assert not eng.ltm.frontier.for_pair(GAS, BCONF)
