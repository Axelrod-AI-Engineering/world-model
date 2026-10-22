"""Long-term learning forgets retired values: frontier entries about them decay."""

from __future__ import annotations

from axelrod_wm.memory.frontier import CoMovement, CoMovementStatus
from tests.conftest import real_event

ENTRIES = "ltm.correlation_frontier.entries"


def test_frontier_entries_about_a_retired_value_decay(warm_engine):
    eng = warm_engine
    now = eng.wm.clock
    subs = sorted(eng.wm.graph.entities["delta"].subentity_ids)
    other = "inflation.headline_cpi"
    with eng.mutator.begin("frontier", at=now) as txn:
        txn.add(ENTRIES, CoMovement(id="CM-live", earlier_id=subs[0], later_id=other, lag_days=3, sign=1,
                                    first_seen=now, last_seen=now))
        txn.add(ENTRIES, CoMovement(id="CM-later", earlier_id=other, later_id=subs[0], lag_days=3, sign=1,
                                    first_seen=now, last_seen=now, status=CoMovementStatus.PROMOTION_PROPOSED))
        txn.add(ENTRIES, CoMovement(id="CM-done", earlier_id=subs[0], later_id=other, lag_days=5, sign=-1,
                                    first_seen=now, last_seen=now, status=CoMovementStatus.DECAYED))
        txn.add(ENTRIES, CoMovement(id="CM-elsewhere", earlier_id=other, later_id="asset_prices.equity_index",
                                    lag_days=3, sign=1, first_seen=now, last_seen=now))
    eng.learning.run(real_event([{"op": "retire_entity", "entity_id": "delta", "reason": "illustrative"}],
                                "GUE-RD"), now, 0)
    entries = eng.ltm.correlation_frontier.entries
    assert entries["CM-live"].status == CoMovementStatus.DECAYED
    assert entries["CM-later"].status == CoMovementStatus.DECAYED
    assert entries["CM-done"].status == CoMovementStatus.DECAYED
    assert entries["CM-elsewhere"].status == CoMovementStatus.HOLDING
