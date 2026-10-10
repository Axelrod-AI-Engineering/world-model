"""The event ledger: every input and every resulting ChangeSet (§9, D8)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable, Iterator

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from axelrod_wm.repo.snapshots import StorageBackend


class LedgerKind(StrEnum):
    CONSTRUCTION = "construction"
    UPDATE = "update"                  # an update run's request, state changes, and report
    MARKET_EVENT = "market_event"
    PROPOSAL = "proposal"
    REVIEW_DECISION = "review_decision"
    CHANGESET = "changeset"
    THESIS = "thesis"
    FORECAST = "forecast"
    EVALUATION = "evaluation"
    DECISION = "decision"
    OUTCOME = "outcome"
    CONSOLIDATION = "consolidation"


class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    kind: LedgerKind
    recorded_at: datetime
    occurred_at: datetime | None = None
    state_version: int
    payload: dict


class EventLedger:
    """Append-only log. Entries live in the storage backend; the ledger keeps only the next seq.

    # DECISION: a session that starts from a cached init snapshot may begin its ledger after the
    # history's entries (set_base); restoring a version older than its first snapshot then fails
    # with a clear error instead of replaying a history it does not hold.
    """

    def __init__(self, storage: StorageBackend, clock: Callable[[], datetime],
                 version: Callable[[], int]) -> None:
        self.storage = storage
        self._clock = clock
        self._version = version
        self.next_seq = storage.last_seq() + 1

    def append(self, kind: LedgerKind, payload: BaseModel | dict[str, Any], *,
               occurred_at: datetime | None = None, recorded_at: datetime | None = None,
               state_version: int | None = None) -> LedgerEntry:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        entry = LedgerEntry.model_construct(seq=self.next_seq, kind=kind, recorded_at=recorded_at or self._clock(),
                                            occurred_at=occurred_at,
                                            state_version=self._version() if state_version is None else state_version,
                                            payload=data)
        self.next_seq += 1
        self.storage.append_ledger(entry)
        return entry

    def read(self, since_seq: int = 0, until_recorded: datetime | None = None) -> Iterator[LedgerEntry]:
        for e in self.storage.read_ledger(since_seq):
            if until_recorded is not None and e.recorded_at > until_recorded:
                break
            yield e

    @property
    def entries(self) -> list[LedgerEntry]:
        """Every entry this ledger holds (reads the storage; avoid on long runs)."""
        return list(self.storage.read_ledger(0))

    def of_kind(self, kind: LedgerKind, since_seq: int = 0) -> list[LedgerEntry]:
        return [e for e in self.read(since_seq) if e.kind == kind]

    def adopt(self, entries: list[LedgerEntry]) -> None:
        """Load entries from another ledger (e.g. the cached initialization) into this one."""
        for e in entries:
            self.storage.append_ledger(e)
            self.next_seq = max(self.next_seq, e.seq + 1)

    def set_base(self, last_seq: int) -> None:
        """Continue numbering after `last_seq` (entries up to it live elsewhere)."""
        self.next_seq = max(self.next_seq, int(last_seq) + 1)
