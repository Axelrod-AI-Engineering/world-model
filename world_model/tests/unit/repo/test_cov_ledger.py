"""The event ledger: reading up to a recorded time, adopting another ledger's entries, and set_base."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from axelrod_wm.repo.ledger import EventLedger, LedgerKind
from axelrod_wm.repo.snapshots import MemoryBackend

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _ledger() -> EventLedger:
    return EventLedger(MemoryBackend(), clock=lambda: T0, version=lambda: 7)


def test_read_stops_after_the_given_recorded_time():
    led = _ledger()
    for k in range(4):
        led.append(LedgerKind.ANNOTATION, {"k": k}, recorded_at=T0 + timedelta(days=k))
    got = [e.payload["k"] for e in led.read(0, until_recorded=T0 + timedelta(days=1))]
    assert got == [0, 1]
    assert [e.payload["k"] for e in led.read(2)] == [2, 3]
    assert led.entries[0].state_version == 7


def test_adopt_copies_entries_and_moves_the_next_seq():
    src = _ledger()
    for k in range(3):
        src.append(LedgerKind.THESIS, {"k": k})
    dst = _ledger()
    dst.adopt(src.entries)
    assert dst.next_seq == 4
    assert [e.payload["k"] for e in dst.of_kind(LedgerKind.THESIS)] == [0, 1, 2]
    dst.adopt([])
    assert dst.next_seq == 4
    dst.set_base(10)
    assert dst.next_seq == 11
    dst.set_base(2)                     # never moves backwards
    assert dst.next_seq == 11
    assert dst.append(LedgerKind.OUTCOME, {}).seq == 11
