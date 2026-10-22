"""The correlation frontier on the daily grid (§8.7): log, verify at most once per spacing, propose;
inconsistency; decay; rejection blocks."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from axelrod_wm.learning.frontier_test import decay_frontier
from axelrod_wm.memory.frontier import CoMovementStatus, pair_key
from axelrod_wm.model.hypothesis import HypothesisStatus
from tests.conftest import constructed_engine as _constructed
from tests.conftest import make_config, observe_event, run_days
from tests.unit.dynamics.test_daily_model import _native

GAS, BCONF = "resources_energy.gas_price", "confidence.business_confidence"


def constructed_engine(build: bool = True):
    # level noise stays as set below: entity memories (which learn it) are written after the test ends
    return _constructed(build=build, config=make_config(entity_memory={"entry_every_days": 1000}))
OIL, CCONF = "resources_energy.oil_price", "confidence.consumer_confidence"


def _feed(eng, days: int, seed: int = 0, every: int = 20, size: float = 3.0):
    """Gas jumps every `every` days (alternating sign) and business confidence moves the other way
    seven days later: a planted relation. Oil and consumer confidence move independently at random
    every few days: an inconsistent pair. All four are observed daily."""
    rng = np.random.default_rng(seed)
    with eng.mutator.begin("noise", at=eng.wm.clock) as txn:
        for sid in (GAS, BCONF, OIL, CCONF):     # as if learned from history (§8.12)
            txn.update("wm.graph.subentities", sid, level_noise=0.1, obs_noise=0.05)
    z = {GAS: 0.0, BCONF: 0.0, OIL: 0.0, CCONF: 0.0}
    path: dict[int, dict[str, float]] = {}
    for d in range(days):
        k = d // every
        if d % every == 0 and d > 0:
            z[GAS] += size * (1 if k % 2 else -1)
        if d % every == 7 and d > 7:
            z[BCONF] -= size * (1 if k % 2 else -1)
        if d % 5 == 0:
            z[OIL] += float(rng.choice([-1.0, 1.0]))
            z[CCONF] += float(rng.choice([-1.0, 1.0]))
        path[d] = {sid: v + float(rng.normal(0, 0.03)) for sid, v in z.items()}
    dev = eng.wm.deviations
    proposals: list[dict] = []

    def events(d):
        return [observe_event(f"GUE-{d}", {sid: _native(eng, sid, v) for sid, v in path[d].items()}, dev.date_of(d))]

    orig = eng.learning.run

    def run(event, now, day, **kw):
        res = orig(event, now, day, **kw)
        proposals.extend(p for p in res.proposal_events if p["kind"] == "frontier_promotion")
        return res

    eng.learning.run = run
    run_days(eng, days, events)
    eng.learning.run = orig
    return proposals


def test_planted_relation_is_logged_verified_with_spacing_and_proposed():
    eng = constructed_engine(build=True)
    proposals = _feed(eng, 100)
    entries = eng.ltm.correlation_frontier.for_pair(GAS, BCONF)
    assert entries, "the planted pair was never logged"
    co = entries[0]
    assert co.earlier_id == GAS and co.sign == -1
    assert co.consistent >= 3 and co.support > 3
    # verified at most once per evidence_spacing_days, although each shock kept it moving for weeks
    spacing = eng.config.frontier.evidence_spacing_days
    assert all(b - a >= spacing for a, b in zip(co.verified_days, co.verified_days[1:]))
    props = [p for p in proposals if p.get("subject_id") == co.id]
    assert props, "no promotion proposal"
    assert co.status == CoMovementStatus.PROMOTION_PROPOSED
    op = props[0]["event"]["ops"][0]
    assert op["edge_type"] == "learned_causal" and op["existence"] == {"family": "beta", "alpha": 1.0, "beta": 3.0}
    assert op["dynamics"]["kernel"]["delay"]["family"] == "gamma"
    h = eng.wm.hypotheses[co.hypothesis_id]
    assert h.probability > 0.4


def test_one_long_shock_verifies_at_most_once_per_spacing():
    eng = constructed_engine(build=True)
    _feed(eng, 34, every=1000)          # one gas jump never repeats: nothing to verify
    eng2 = constructed_engine(build=True)
    _feed(eng2, 34, every=20)           # one planted episode (gas on day 20, confidence on day 27)
    for co in eng2.ltm.correlation_frontier.for_pair(GAS, BCONF):
        assert co.consistent + co.inconsistent <= 1


def test_inconsistent_pair_is_not_proposed():
    eng = constructed_engine(build=True)
    proposals = _feed(eng, 110)
    subjects = {p.get("subject_id") for p in proposals}
    for co in eng.ltm.correlation_frontier.for_pair(OIL, CCONF):
        assert co.id not in subjects


def test_decay_removes_stale_entries():
    eng = constructed_engine(build=True)
    _feed(eng, 50)
    live = [co for co in eng.ltm.correlation_frontier.entries.values() if co.status == CoMovementStatus.HOLDING]
    assert live
    day = eng.wm.last_processed_day
    for k in range(1, 400):
        ctx = eng.context(learn=True, now=eng.wm.deviations.day_end(day + k), processing_day=day + k)
        with eng.mutator.begin(f"decay-{k}", at=ctx.now) as txn:
            decay_frontier(day + k, eng.wm, eng.ltm, ctx, txn)
    for co in live:
        co = eng.ltm.correlation_frontier.entries[co.id]
        assert co.status == CoMovementStatus.DECAYED
        assert eng.wm.hypotheses[co.hypothesis_id].status == HypothesisStatus.EXPIRED


def test_rejection_blocks_the_pair():
    eng = constructed_engine(build=True)
    with eng.mutator.begin("block", at=eng.wm.clock) as txn:
        txn.put("ltm.correlation_frontier.blocked_until", pair_key(GAS, BCONF), eng.wm.clock + timedelta(days=3650))
    _feed(eng, 60)
    assert not eng.ltm.correlation_frontier.for_pair(GAS, BCONF)
