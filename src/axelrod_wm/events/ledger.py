"""The event ledger: every input and every resulting ChangeSet (§9, D8)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable, Iterator

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from axelrod_wm.memory.snapshots import StorageBackend


class LedgerKind(StrEnum):
    CONSTRUCTION = "construction"
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
    """Append-only log. Entries are kept in memory for the session and written to storage."""

    def __init__(self, storage: StorageBackend, clock: Callable[[], datetime],
                 version: Callable[[], int]) -> None:
        self.storage = storage
        self._clock = clock
        self._version = version
        self.entries: list[LedgerEntry] = list(storage.read_ledger(0))
        self.next_seq = (self.entries[-1].seq + 1) if self.entries else 1

    def append(self, kind: LedgerKind, payload: BaseModel | dict[str, Any], *,
               occurred_at: datetime | None = None, recorded_at: datetime | None = None,
               state_version: int | None = None) -> LedgerEntry:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        entry = LedgerEntry(seq=self.next_seq, kind=kind, recorded_at=recorded_at or self._clock(),
                            occurred_at=occurred_at,
                            state_version=self._version() if state_version is None else state_version,
                            payload=data)
        self.next_seq += 1
        self.entries.append(entry)
        self.storage.append_ledger(entry)
        return entry

    def read(self, since_seq: int = 0, until_recorded: datetime | None = None) -> Iterator[LedgerEntry]:
        for e in self.entries:
            if e.seq <= since_seq:
                continue
            if until_recorded is not None and e.recorded_at > until_recorded:
                break
            yield e

    def of_kind(self, kind: LedgerKind) -> list[LedgerEntry]:
        return [e for e in self.entries if e.kind == kind]

    def adopt(self, entries: list[LedgerEntry]) -> None:
        """Load entries from another ledger (e.g. the cached initialization) into this one."""
        for e in entries:
            self.entries.append(e)
            self.storage.append_ledger(e)
        self.next_seq = (self.entries[-1].seq + 1) if self.entries else 1
