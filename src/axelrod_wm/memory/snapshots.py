"""Persistence, versions, snapshots, and the state hash (§9, D8).

# DECISION: the state hash is a sharded Merkle hash. Each record's digest is SHA-256 of its canonical
# JSON (sorted keys, compact separators, ints written as floats); large records keep one digest per
# field, and a list field of records (time states, evidence, history) is the digest of its items'
# digests, cached per item, so appending one time state re-hashes one item. Records are grouped into
# shards (daily collections by day, the rest by a stable hash of the key), shards into collections,
# and collections into the root. It covers everything except wm.forecast_layer, and each commit
# re-hashes only the fields, shards, and collections it touched, so daily processing stays fast
# however long the history grows.
# DECISION: snapshot blobs preserve dict insertion order and exact floats (model_dump_json),
# so a restored state is bit-identical to the live one.
# DECISION: the memory backend keeps ledger entries as JSON lines, and the files backend keeps its
# append handles open; neither holds the whole ledger as Python objects.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import zlib
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.core.serialization import sha256_text
from axelrod_wm.core.taxonomy import Taxonomy, TaxonomyKind
from axelrod_wm.events.ledger import LedgerEntry, LedgerKind
from axelrod_wm.memory.frontier import CorrelationFrontier
from axelrod_wm.memory.long_term import (
    InteractionGeneralizations,
    LongTermMemory,
    ObjectGeneralizations,
    PriorStates,
)
from axelrod_wm.memory.working import DeviationHistory, WorkingMemory

if TYPE_CHECKING:
    from axelrod_wm.events.ledger import EventLedger

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class StateVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    seq: int                  # ledger seq of the ChangeSet that produced this version
    state_hash: str
    recorded_at: datetime
    cause: str


def empty_state(origin: date | None = None) -> tuple[WorkingMemory, LongTermMemory]:
    """Version 0: the empty state. Construction writes everything else through the mutator."""
    wm = WorkingMemory(clock=EPOCH, last_processed_day=-1, graph=CausalGraph(),
                       deviations=DeviationHistory(origin_date=origin or EPOCH.date()))
    ltm = LongTermMemory(
        object_generalizations=ObjectGeneralizations(
            taxonomy=Taxonomy(kind=TaxonomyKind.OBJECT, root_id="", nodes={})),
        interaction_generalizations=InteractionGeneralizations(
            taxonomy=Taxonomy(kind=TaxonomyKind.INTERACTION, root_id="", nodes={})),
        correlation_frontier=CorrelationFrontier(),
        prior_states=PriorStates(),
    )
    return wm, ltm


# ---------------------------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------------------------

class StorageBackend(ABC):
    @abstractmethod
    def append_ledger(self, entry: LedgerEntry) -> None: ...

    @abstractmethod
    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]: ...

    @abstractmethod
    def save_snapshot(self, version: StateVersion, blob: bytes) -> None: ...

    @abstractmethod
    def load_snapshot(self, version: int) -> bytes: ...

    @abstractmethod
    def versions(self) -> list[StateVersion]: ...

    @abstractmethod
    def append_version(self, version: StateVersion) -> None: ...

    @abstractmethod
    def snapshot_versions(self) -> list[int]: ...

    @abstractmethod
    def reset(self) -> None: ...

    def close(self) -> None:  # noqa: B027  (an optional hook: in-memory backends have nothing to close)
        """Make everything written so far durable (files backends flush and close their handles)."""

    def last_seq(self) -> int:
        last = 0
        for e in self.read_ledger(0):
            last = e.seq
        return last

    def version_info(self, version: int) -> StateVersion | None:
        for v in self.versions():
            if v.version == version:
                return v
        return None

    def flush(self) -> None:
        return None

    def trace_dir(self) -> Path | None:
        return None


class MemoryBackend(StorageBackend):
    """Keeps the ledger (as JSON lines), versions, and snapshots in memory (tests)."""

    def __init__(self, **_: object) -> None:
        self.reset()

    def reset(self) -> None:
        self._ledger: list[tuple[int, str]] = []
        self._versions: list[StateVersion] = []
        self._version_index: dict[int, StateVersion] = {}
        self._snapshots: dict[int, bytes] = {}

    def append_ledger(self, entry: LedgerEntry) -> None:
        self._ledger.append((entry.seq, entry.model_dump_json()))

    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]:
        rows = self._ledger
        # entries are appended in seq order: skip quickly to the first one after since_seq
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if rows[mid][0] <= since_seq:
                lo = mid + 1
            else:
                hi = mid
        for i in range(lo, len(rows)):
            yield LedgerEntry.model_validate_json(rows[i][1])

    def last_seq(self) -> int:
        return self._ledger[-1][0] if self._ledger else 0

    def save_snapshot(self, version: StateVersion, blob: bytes) -> None:
        self._snapshots[version.version] = blob

    def load_snapshot(self, version: int) -> bytes:
        return self._snapshots[version]

    def versions(self) -> list[StateVersion]:
        return list(self._versions)

    def version_info(self, version: int) -> StateVersion | None:
        return self._version_index.get(version)

    def append_version(self, version: StateVersion) -> None:
        self._versions.append(version)
        self._version_index[version.version] = version

    def snapshot_versions(self) -> list[int]:
        return sorted(self._snapshots)


class FilesBackend(StorageBackend):
    """var/axelrod/ledger.jsonl, versions.jsonl, snapshots/v000123.json.gz, traces/<run_id>.jsonl."""

    def __init__(self, path: str | Path = "var/axelrod", **_: object) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "snapshots").mkdir(exist_ok=True)
        self._versions_cache: list[StateVersion] | None = None
        self._version_index: dict[int, StateVersion] = {}
        self._ledger_fh: Any = None
        self._versions_fh: Any = None
        self._last_seq: int | None = None

    @property
    def ledger_path(self) -> Path:
        return self.path / "ledger.jsonl"

    @property
    def versions_path(self) -> Path:
        return self.path / "versions.jsonl"

    def trace_dir(self) -> Path:
        d = self.path / "traces"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _close(self) -> None:
        for fh in (self._ledger_fh, self._versions_fh):
            if fh is not None:
                fh.close()
        self._ledger_fh = self._versions_fh = None

    def close(self) -> None:
        self._close()

    def flush(self) -> None:
        for fh in (self._ledger_fh, self._versions_fh):
            if fh is not None:
                fh.flush()

    def reset(self) -> None:
        self._close()
        for p in (self.ledger_path, self.versions_path):
            if p.exists():
                p.unlink()
        snap = self.path / "snapshots"
        if snap.exists():
            shutil.rmtree(snap)
        snap.mkdir(parents=True, exist_ok=True)
        self._versions_cache = []
        self._version_index = {}
        self._last_seq = 0

    def append_ledger(self, entry: LedgerEntry) -> None:
        if self._ledger_fh is None:
            # DECISION: line-buffered, so every committed entry reaches the file even when a CLI
            # process exits without closing its storage (a lost version record breaks `resume`)
            self._ledger_fh = self.ledger_path.open("a", buffering=1)
        self._ledger_fh.write(entry.model_dump_json() + "\n")
        self._last_seq = entry.seq

    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]:
        self.flush()
        if not self.ledger_path.exists():
            return
        with self.ledger_path.open() as fh:
            for line in fh:
                if not line.strip():
                    continue
                if since_seq > 0:
                    # cheap pre-check on the seq field, which model_dump_json writes first
                    head = line[:40]
                    try:
                        seq = int(head.split('"seq":', 1)[1].split(",", 1)[0])
                    except (IndexError, ValueError):
                        seq = None
                    if seq is not None and seq <= since_seq:
                        continue
                e = LedgerEntry.model_validate_json(line)
                if e.seq > since_seq:
                    yield e

    def last_seq(self) -> int:
        if self._last_seq is None:
            self._last_seq = super().last_seq()
        return self._last_seq

    def save_snapshot(self, version: StateVersion, blob: bytes) -> None:
        (self.path / "snapshots" / f"v{version.version:06d}.json.gz").write_bytes(blob)

    def load_snapshot(self, version: int) -> bytes:
        return (self.path / "snapshots" / f"v{version:06d}.json.gz").read_bytes()

    def versions(self) -> list[StateVersion]:
        if self._versions_cache is None:
            self.flush()
            self._versions_cache = []
            self._version_index = {}
            if self.versions_path.exists():
                with self.versions_path.open() as fh:
                    for line in fh:
                        if line.strip():
                            v = StateVersion.model_validate_json(line)
                            self._versions_cache.append(v)
                            self._version_index[v.version] = v
        return list(self._versions_cache)

    def version_info(self, version: int) -> StateVersion | None:
        self.versions()
        return self._version_index.get(version)

    def append_version(self, version: StateVersion) -> None:
        self.versions()
        assert self._versions_cache is not None
        self._versions_cache.append(version)
        self._version_index[version.version] = version
        if self._versions_fh is None:
            self._versions_fh = self.versions_path.open("a", buffering=1)
        self._versions_fh.write(version.model_dump_json() + "\n")

    def snapshot_versions(self) -> list[int]:
        d = self.path / "snapshots"
        if not d.exists():
            return []
        return sorted(int(p.name[1:7]) for p in d.glob("v*.json.gz"))


# ---------------------------------------------------------------------------------------------
# State hash
# ---------------------------------------------------------------------------------------------

def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_from_json(raw: str | bytes) -> str:
    # ints and floats canonicalize alike, so a float field holding 0 and 0.0 hash equal
    data = json.loads(raw, parse_int=float)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _value_digest(value: Any) -> str:
    from axelrod_wm.core.serialization import to_jsonable

    if isinstance(value, BaseModel):
        return _digest_text(_canonical_from_json(value.model_dump_json()))
    return _digest_text(_canonical_from_json(json.dumps(to_jsonable(value))))


DAY_FIRST = {"wm.activity_log"}                                     # key "<day>|<channel id>"
DAY_LAST = {"wm.deviations.points", "wm.channel_phi"}              # key "<id>|<day>"
DAY_SHARD = 16
HASH_SHARDS = 64


def shard_of(part: str, key: str) -> str:
    try:
        if part in DAY_LAST:
            return f"d{int(key.rpartition('|')[2]) // DAY_SHARD}"
        if part in DAY_FIRST:
            return f"d{int(key.partition('|')[0]) // DAY_SHARD}"
    except ValueError:
        pass
    return f"h{zlib.crc32(key.encode('utf-8')) % HASH_SHARDS}"


_PARTS: tuple[set[str], set[str], set[str], set[str]] | None = None


def _hashed_parts() -> tuple[set[str], set[str], set[str], set[str]]:
    global _PARTS
    if _PARTS is None:
        from axelrod_wm.control.mutator import LISTS, RECORDS, SINGLETONS, VALUES

        rec = {p for p in RECORDS if not p.startswith("wm.forecast_layer")}
        singles = {p for p in SINGLETONS if not p.startswith("wm.forecast_layer")}
        _PARTS = (rec, set(VALUES), set(LISTS), singles)
    return _PARTS


class StateHasher:
    """Sharded Merkle hash over every part of the state except the forecast layer."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, dict[str, str]]] = {}   # part -> shard -> key -> digest
        self.fields: dict[str, dict[str, dict[str, str]]] = {}    # part -> key -> field -> digest
        self.shard_digest: dict[str, dict[str, str]] = {}         # part -> shard -> digest
        self.part_digest: dict[str, str] = {}
        self._items: dict[tuple[str, str], dict[str, dict[int, tuple[Any, str]]]] = {}   # list-field item digests
        self._ready = False

    # -- helpers -------------------------------------------------------------------------------
    @staticmethod
    def _roots(wm: WorkingMemory, ltm: LongTermMemory):
        from axelrod_wm.control.mutator import _Roots

        return _Roots(wm, ltm)

    def _field_digest(self, part: str, key: str, cls: type, name: str, value: Any) -> str:
        from axelrod_wm.control.mutator import field_adapter

        if isinstance(value, list) and value and isinstance(value[0], BaseModel):
            per_record = self._items.setdefault((part, key), {})
            old = per_record.get(name, {})
            new: dict[int, tuple[Any, str]] = {}
            digests = []
            for item in value:
                hit = old.get(id(item))
                if hit is not None and hit[0] is item:
                    d = hit[1]
                else:
                    d = _digest_text(_canonical_from_json(item.model_dump_json()))
                new[id(item)] = (item, d)
                digests.append(d)
            per_record[name] = new
            return _digest_text("[" + ",".join(digests) + "]")
        return _digest_text(_canonical_from_json(field_adapter(cls, name).dump_json(value)))

    def _record_digest(self, part: str, key: str, obj: BaseModel, field: str | None) -> str:
        from axelrod_wm.control.mutator import FIELD_HASHED

        if part not in FIELD_HASHED:
            return _digest_text(_canonical_from_json(obj.model_dump_json()))
        fd = self.fields.setdefault(part, {})
        cur = fd.get(key)
        cls = type(obj)
        if cur is None or field is None:
            cur = {}
            for name in cls.model_fields:
                cur[name] = self._field_digest(part, key, cls, name, getattr(obj, name))
            fd[key] = cur
        else:
            cur[field] = self._field_digest(part, key, cls, field, getattr(obj, field))
        return _digest_text(json.dumps(cur, sort_keys=True, separators=(",", ":")))

    def _set(self, part: str, key: str, digest_: str | None, dirty_shards: dict[str, set[str]]) -> None:
        sh = shard_of(part, key)
        bucket = self.objects.setdefault(part, {}).setdefault(sh, {})
        if digest_ is None:
            bucket.pop(key, None)
            self.fields.get(part, {}).pop(key, None)
            self._items.pop((part, key), None)
        else:
            bucket[key] = digest_
        dirty_shards.setdefault(part, set()).add(sh)

    def _finish_parts(self, dirty_shards: dict[str, set[str]]) -> None:
        for part, shards in dirty_shards.items():
            sd = self.shard_digest.setdefault(part, {})
            objs = self.objects.setdefault(part, {})
            for sh in shards:
                bucket = objs.get(sh)
                if not bucket:
                    sd.pop(sh, None)
                    objs.pop(sh, None)
                else:
                    sd[sh] = _digest_text(json.dumps(bucket, sort_keys=True, separators=(",", ":")))
            self.part_digest[part] = _digest_text(json.dumps(sd, sort_keys=True, separators=(",", ":")))

    # -- full and incremental -------------------------------------------------------------
    def full(self, wm: WorkingMemory, ltm: LongTermMemory) -> str:
        self.objects, self.fields, self.shard_digest, self.part_digest = {}, {}, {}, {}
        self._items = {}
        roots = self._roots(wm, ltm)
        rec, vals, lists, singles = _hashed_parts()
        dirty: dict[str, set[str]] = {}
        for part in sorted(rec):
            mapping = roots.target(part)
            dirty.setdefault(part, set())
            for key, obj in mapping.items():
                self._set(part, key, self._record_digest(part, key, obj, None), dirty)
        for part in sorted(vals):
            owner, attr = roots.owner(part)
            dirty.setdefault(part, set())
            for key, value in getattr(owner, attr).items():
                self._set(part, key, _value_digest(value), dirty)
        self._finish_parts(dirty)
        for part in sorted(lists | singles):
            self.part_digest[part] = _value_digest(roots.target(part))
        self._ready = True
        return self.root()

    def update(self, wm: WorkingMemory, ltm: LongTermMemory, dirty: set[tuple[str, str, str | None]]) -> str:
        if not self._ready:
            return self.full(wm, ltm)
        roots = self._roots(wm, ltm)
        rec, vals, lists, singles = _hashed_parts()
        dirty_shards: dict[str, set[str]] = {}
        for item in sorted(dirty, key=lambda t: (t[0], t[1], t[2] or "")):
            part, key = item[0], item[1]
            field = item[2] if len(item) > 2 else None
            if part in rec:
                obj = roots.target(part).get(key)
                self._set(part, key, None if obj is None else self._record_digest(part, key, obj, field), dirty_shards)
            elif part in vals:
                owner, attr = roots.owner(part)
                mapping = getattr(owner, attr)
                self._set(part, key, _value_digest(mapping[key]) if key in mapping else None, dirty_shards)
            elif part in lists or part in singles:
                self.part_digest[part] = _value_digest(roots.target(part))
            # forecast-layer parts are not hashed
        self._finish_parts(dirty_shards)
        return self.root()

    def root(self) -> str:
        return sha256_text(json.dumps(self.part_digest, sort_keys=True, separators=(",", ":")))


def state_hash(wm: WorkingMemory, ltm: LongTermMemory) -> str:
    return StateHasher().full(wm, ltm)


# ---------------------------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------------------------

def dump_state(wm: WorkingMemory, ltm: LongTermMemory) -> bytes:
    text = '{"wm":' + wm.model_dump_json() + ',"ltm":' + ltm.model_dump_json() + "}"
    return gzip.compress(text.encode("utf-8"), compresslevel=5, mtime=0)


def load_state(blob: bytes) -> tuple[WorkingMemory, LongTermMemory]:
    data = json.loads(gzip.decompress(blob).decode("utf-8"))
    return WorkingMemory.model_validate(data["wm"]), LongTermMemory.model_validate(data["ltm"])


class RestoreError(RuntimeError):
    pass


class SnapshotStore:
    def __init__(self, storage: StorageBackend, ledger: EventLedger,
                 empty: Callable[[], tuple[WorkingMemory, LongTermMemory]] | None = None) -> None:
        self.storage = storage
        self.ledger = ledger
        self.empty = empty or empty_state

    def save(self, wm: WorkingMemory, ltm: LongTermMemory, version: StateVersion) -> None:
        self.storage.save_snapshot(version, dump_state(wm, ltm))

    def version_info(self, version: int) -> StateVersion | None:
        return self.storage.version_info(version)

    def restore(self, version: int, verify: bool = True) -> tuple[WorkingMemory, LongTermMemory]:
        from axelrod_wm.control.mutator import ChangeSet, apply_changeset

        target = self.version_info(version) if version > 0 else None
        if version > 0 and target is None:
            raise RestoreError(f"unknown version {version}")
        snaps = [v for v in self.storage.snapshot_versions() if v <= version]
        if snaps:
            base = max(snaps)
            wm, ltm = load_state(self.storage.load_snapshot(base))
            info = self.version_info(base)
            start_seq = info.seq if info is not None else 0
        else:
            base = 0
            wm, ltm = self.empty()
            start_seq = 0
        if base < version:
            applied_to = base
            for entry in self.ledger.read(start_seq):
                if entry.kind != LedgerKind.CHANGESET:
                    continue
                cs = ChangeSet.model_validate(entry.payload)
                if cs.version_after == cs.version_before:
                    continue                      # forecast layer only
                if cs.version_after > version:
                    break
                apply_changeset(wm, ltm, cs)
                applied_to = cs.version_after
            if applied_to != version:
                raise RestoreError(f"cannot restore version {version}: its change sets are not in this ledger "
                                   f"(reached {applied_to} from snapshot {base})")
        if verify and target is not None:
            got = state_hash(wm, ltm)
            if got != target.state_hash:
                raise RestoreError(f"hash mismatch restoring version {version}: {got[:12]} != {target.state_hash[:12]}")
        return wm, ltm

    def as_of(self, recorded_at: datetime) -> tuple[WorkingMemory, LongTermMemory, int]:
        """The highest version whose cause is a consolidation and whose recorded_at is at or before
        `recorded_at`, so a frozen state is always a whole processed day (§9)."""
        best = 0
        for v in self.storage.versions():
            if v.cause.startswith("consolidation:") and v.recorded_at <= recorded_at and v.version > best:
                best = v.version
        wm, ltm = self.restore(best)
        return wm, ltm, best
