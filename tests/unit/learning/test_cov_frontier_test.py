"""The correlation frontier at its edges (§8.7): a promotion from an overflowing response is a flat edge, a
live entry is verified at its own stored lag (off the lag grid), and entries whose hypothesis is gone still
verify and decay."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from axelrod_wm.learning.frontier_test import decay_frontier, promotion_event
from axelrod_wm.memory.frontier import CoMovement, CoMovementStatus, RunningCorr
from axelrod_wm.memory.working import DeviationPoint, point_key
from tests.conftest import START, constructed_engine

ENTRIES = "ltm.correlation_frontier.entries"
GAS, OIL, BCONF = "resources_energy.gas_price", "resources_energy.oil_price", "confidence.business_confidence"


def test_an_overflowing_response_promotes_a_flat_edge(m1_engine):
    resp = RunningCorr()
    for x, y in ((1e308, 1e308), (-1e308, -1e308), (1e308, -1e308)):
        resp = resp.pushed(x, y)
    slope, se = resp.slope()
    assert slope != slope and se != se          # NaN: the moments overflowed
    co = CoMovement(id="CM-x", earlier_id=GAS, later_id=BCONF, lag_days=0, sign=1, response=resp,
                    first_seen=START, last_seen=START)
    ctx = m1_engine.context(learn=True, now=START)
    ev = promotion_event(co, ctx)
    op = ev.ops[0]
    assert op.polarity == 1 and op.dynamics.effect.mu == 0.0 and op.dynamics.effect.sigma == 0.5
    assert op.dynamics.kernel.duration is None


def _pt(z, innovation=None):
    return DeviationPoint(z=z, var=0.01, level=z, innovation=innovation, observed=innovation is not None)


def test_a_live_entry_off_the_lag_grid_is_verified_at_its_stored_lag():
    eng = constructed_engine(build=True)
    cfg = eng.config.frontier
    w = int(cfg.window_days)
    t = 200
    lag = 4
    assert lag not in cfg.lag_grid_days
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.add("wm.deviations.points", _pt(3.0, innovation=3.0), key=point_key(BCONF, t))
        txn.add("wm.deviations.points", _pt(2.0), key=point_key(GAS, t - lag))
        txn.add("wm.deviations.points", _pt(0.0), key=point_key(GAS, t - lag - w))
        # the stored lag on GAS has both ends of its window; OIL has none
        txn.add(ENTRIES, CoMovement(id="CM-gas", earlier_id=GAS, later_id=BCONF, lag_days=lag, sign=1,
                                    support=1.0, first_seen=START, last_seen=START, hypothesis_id="H-gone"))
        txn.add(ENTRIES, CoMovement(id="CM-oil", earlier_id=OIL, later_id=BCONF, lag_days=6, sign=1,
                                    support=1.0, first_seen=START, last_seen=START))
    fold = SimpleNamespace(innovations={BCONF: 3.0}, day=t)
    ctx = eng.context(learn=True, now=eng.wm.deviations.day_end(t))
    with eng.mutator.begin("frontier", at=ctx.now) as txn:
        res = eng.components["frontier"].test(fold, eng.wm, eng.ltm, ctx, txn)
    assert res.tested == ["CM-gas"] and res.logged == []
    entries = eng.ltm.correlation_frontier.entries
    gas = entries["CM-gas"]
    assert gas.last_verified_day == t and gas.consistent == 1 and gas.support == 2.0
    assert "H-gone" not in eng.wm.hypotheses
    assert entries["CM-oil"].last_verified_day is None and entries["CM-oil"].support == 1.0


def test_entries_whose_hypothesis_is_gone_still_decay(m1_engine):
    eng = m1_engine
    dev = eng.wm.deviations
    seen = dev.day_end(10)
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.add(ENTRIES, CoMovement(id="CM-weak", earlier_id=GAS, later_id=BCONF, lag_days=3, sign=1, support=0.4,
                                    first_seen=seen, last_seen=seen, hypothesis_id="H-gone"))
        txn.add(ENTRIES, CoMovement(id="CM-strong", earlier_id=OIL, later_id=BCONF, lag_days=3, sign=1, support=5.0,
                                    first_seen=seen, last_seen=seen, hypothesis_id="H-gone-too"))
    day = 10 + int(eng.config.frontier.evidence_spacing_days) + 1
    ctx = eng.context(learn=True, now=seen + timedelta(days=day - 10))
    with eng.mutator.begin("decay", at=ctx.now) as txn:
        out = decay_frontier(day, eng.wm, eng.ltm, ctx, txn)
    entries = eng.ltm.correlation_frontier.entries
    factor = 0.5 ** (1.0 / float(eng.config.frontier.half_life_days))
    assert out == ["CM-weak"] and entries["CM-weak"].status == CoMovementStatus.DECAYED
    assert entries["CM-strong"].status == CoMovementStatus.HOLDING
    assert entries["CM-strong"].support == 5.0 * factor
    assert not eng.wm.hypotheses
