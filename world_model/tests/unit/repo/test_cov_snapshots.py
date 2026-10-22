"""Storage backends, the hasher's lazy start, and restore failures."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import Iterator

import pytest

from axelrod_wm.repo.ledger import EventLedger, LedgerEntry, LedgerKind
from axelrod_wm.repo.snapshots import (
    FilesBackend,
    MemoryBackend,
    RestoreError,
    SnapshotStore,
    StateHasher,
    StateVersion,
    StorageBackend,
    state_hash,
)
from tests.conftest import constructed_engine

AT = datetime(2024, 1, 1, tzinfo=UTC)


def _sv(version: int, seq: int = 1, state_hash: str = "h") -> StateVersion:
    return StateVersion(version=version, seq=seq, state_hash=state_hash, recorded_at=AT, cause="c")


class _ListBackend(StorageBackend):
    """A backend that keeps only the abstract methods, so the base class's defaults apply."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.ledger: list[LedgerEntry] = []
        self.vs: list[StateVersion] = []
        self.snaps: dict[int, bytes] = {}

    def append_ledger(self, entry: LedgerEntry) -> None:
        self.ledger.append(entry)

    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]:
        return iter([e for e in self.ledger if e.seq > since_seq])

    def save_snapshot(self, version: StateVersion, blob: bytes) -> None:
        self.snaps[version.version] = blob

    def load_snapshot(self, version: int) -> bytes:
        return self.snaps[version]

    def versions(self) -> list[StateVersion]:
        return list(self.vs)

    def append_version(self, version: StateVersion) -> None:
        self.vs.append(version)

    def snapshot_versions(self) -> list[int]:
        return sorted(self.snaps)


def test_base_backend_defaults():
    b = _ListBackend()
    b.append_version(_sv(1))
    b.append_version(_sv(2, seq=4))
    assert b.version_info(2).seq == 4
    assert b.version_info(3) is None
    assert b.flush() is None and b.trace_dir() is None
    b.close()
    led = EventLedger(b, clock=lambda: AT, version=lambda: 0)
    led.append(LedgerKind.THESIS, {})
    led.append(LedgerKind.THESIS, {})
    assert b.last_seq() == 2


def test_memory_backend_has_no_trace_dir_and_flushes_nothing():
    b = MemoryBackend()
    assert b.trace_dir() is None and b.flush() is None


def test_files_backend_trace_dir_and_reset(tmp_path):
    b = FilesBackend(tmp_path / "store")
    td = b.trace_dir()
    assert td == tmp_path / "store" / "traces" and td.is_dir()
    led = EventLedger(b, clock=lambda: AT, version=lambda: 0)
    led.append(LedgerKind.THESIS, {"k": 1})
    b.append_version(_sv(1))
    b.save_snapshot(_sv(1), b"blob")
    b.reset()
    assert not b.ledger_path.exists() and not b.versions_path.exists()
    assert b.snapshot_versions() == [] and b.versions() == [] and b.last_seq() == 0
    # reset also works when the snapshots folder is already gone
    shutil.rmtree(tmp_path / "store" / "snapshots")
    b.reset()
    assert (tmp_path / "store" / "snapshots").is_dir()


def test_files_backend_snapshot_versions_without_a_snapshots_folder(tmp_path):
    b = FilesBackend(tmp_path)
    shutil.rmtree(tmp_path / "snapshots")
    assert b.snapshot_versions() == []


def test_files_backend_reads_blank_lines_and_entries_whose_seq_is_not_first(tmp_path):
    # an entry written by another tool: seq is not among the first 40 characters, so the pre-check cannot read it
    def late_seq(seq: int) -> str:
        return ('{"payload":{"note":"' + "x" * 60 + '"},"kind":"thesis","recorded_at":"2024-01-01T00:00:00Z",'
                f'"occurred_at":null,"state_version":0,"seq":{seq}}}')

    (tmp_path / "ledger.jsonl").write_text("\n".join([late_seq(1), "", "   ", late_seq(2)]) + "\n")
    b = FilesBackend(tmp_path)
    assert [e.seq for e in b.read_ledger(0)] == [1, 2]
    assert [e.seq for e in b.read_ledger(1)] == [2]
    assert b.last_seq() == 2


def test_files_backend_versions_skip_blank_lines(tmp_path):
    (tmp_path / "versions.jsonl").write_text(_sv(1).model_dump_json() + "\n\n" + _sv(2, seq=3).model_dump_json() + "\n")
    b = FilesBackend(tmp_path)
    assert [v.version for v in b.versions()] == [1, 2]
    assert b.version_info(2).seq == 3


def test_hasher_update_before_full_hashes_everything():
    eng = constructed_engine()
    assert StateHasher().update(eng.wm, eng.ltm, set()) == state_hash(eng.wm, eng.ltm)


def test_restore_fails_when_the_ledger_lacks_the_change_sets():
    b = MemoryBackend()
    led = EventLedger(b, clock=lambda: AT, version=lambda: 0)
    b.append_version(_sv(3, seq=5))
    with pytest.raises(RestoreError, match="cannot restore version 3"):
        SnapshotStore(b, led).restore(3)


def test_restore_checks_the_hash_unless_told_not_to():
    eng = constructed_engine()
    good = eng.storage.version_info(1)
    eng.storage._version_index[1] = good.model_copy(update={"state_hash": "0" * 64})
    with pytest.raises(RestoreError, match="hash mismatch"):
        eng.snapshots.restore(1)
    wm, ltm = eng.snapshots.restore(1, verify=False)
    assert state_hash(wm, ltm) == good.state_hash
