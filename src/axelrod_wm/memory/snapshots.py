"""Persistence, versions, snapshots, and the state hash (§9, D8).

# DECISION: the state hash is a Merkle hash: SHA-256 of the canonical JSON of per-object
# digests, each digest being SHA-256 of that object's canonical JSON (sorted keys, compact
# separators, floats rounded to 12 significant digits). It covers everything except
# wm.forecast_layer, and lets each commit re-hash only the objects it touched.
# DECISION: snapshot blobs preserve dict insertion order and exact floats (model_dump_json),
# so a restored state is bit-identical to the live one.
"""

from __future__ import annotations

import gzip
import json
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.core.serialization import canonical_json, sha256_text
from axelrod_wm.core.taxonomy import AttributeVocabulary, Taxonomy, TaxonomyKind
from axelrod_wm.evaluation.reliability import ReliabilityBook
from axelrod_wm.events.ledger import LedgerEntry, LedgerKind
from axelrod_wm.memory.episodes import EpisodeStore
from axelrod_wm.memory.explanations import ExplanationStore
from axelrod_wm.memory.frontier import CorrelationFrontier
from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.patterns import PatternStore
from axelrod_wm.memory.working import DeviationHistory, WorkingMemory

if TYPE_CHECKING:
    from axelrod_wm.events.ledger import EventLedger

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class StateVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    seq: int                  # ledger seq of the ChangeSet that produced this version
    state_hash: str
    recorded_at: datetime
    cause: str


def empty_state(step_days: float = 7.0) -> tuple[WorkingMemory, LongTermMemory]:
    """Version 0: the empty state. Construction writes everything else through the mutator."""
    wm = WorkingMemory(clock=EPOCH, graph=CausalGraph(),
                       deviations=DeviationHistory(origin_date=EPOCH, step_days=step_days))
    ltm = LongTermMemory(
        episodes=EpisodeStore(),
        object_taxonomy=Taxonomy(kind=TaxonomyKind.OBJECT, root_id="", nodes={}),
        interaction_taxonomy=Taxonomy(kind=TaxonomyKind.INTERACTION, root_id="", nodes={}),
        attributes=AttributeVocabulary(kinds={}),
        patterns=PatternStore(),
        explanations=ExplanationStore(),
        frontier=CorrelationFrontier(),
        reliability=ReliabilityBook(),
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

    def trace_dir(self) -> Path | None:
        return None


class MemoryBackend(StorageBackend):
    """Keeps the ledger, versions, and snapshots in memory (tests)."""

    def __init__(self, **_: object) -> None:
        self.reset()

    def reset(self) -> None:
        self._ledger: list[LedgerEntry] = []
        self._versions: list[StateVersion] = []
        self._snapshots: dict[int, bytes] = {}

    def append_ledger(self, entry: LedgerEntry) -> None:
        self._ledger.append(entry)

    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]:
        return iter([e for e in self._ledger if e.seq > since_seq])

    def save_snapshot(self, version: StateVersion, blob: bytes) -> None:
        self._snapshots[version.version] = blob

    def load_snapshot(self, version: int) -> bytes:
        return self._snapshots[version]

    def versions(self) -> list[StateVersion]:
        return list(self._versions)

    def append_version(self, version: StateVersion) -> None:
        self._versions.append(version)

    def snapshot_versions(self) -> list[int]:
        return sorted(self._snapshots)


class FilesBackend(StorageBackend):
    """var/axelrod/ledger.jsonl, versions.jsonl, snapshots/v000123.json.gz, traces/<run_id>.jsonl."""

    def __init__(self, path: str | Path = "var/axelrod", **_: object) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "snapshots").mkdir(exist_ok=True)
        self._versions_cache: list[StateVersion] | None = None

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

    def reset(self) -> None:
        for p in (self.ledger_path, self.versions_path):
            if p.exists():
                p.unlink()
        snap = self.path / "snapshots"
        if snap.exists():
            shutil.rmtree(snap)
        snap.mkdir(parents=True, exist_ok=True)
        self._versions_cache = []

    def append_ledger(self, entry: LedgerEntry) -> None:
        with self.ledger_path.open("a") as fh:
            fh.write(entry.model_dump_json() + "\n")

    def read_ledger(self, since_seq: int = 0) -> Iterator[LedgerEntry]:
        if not self.ledger_path.exists():
            return iter(())
        out = []
        with self.ledger_path.open() as fh:
            for line in fh:
                if line.strip():
                    e = LedgerEntry.model_validate_json(line)
                    if e.seq > since_seq:
                        out.append(e)
        return iter(out)

    def save_snapshot(self, version: StateVersion, blob: bytes) -> None:
        (self.path / "snapshots" / f"v{version.version:06d}.json.gz").write_bytes(blob)

    def load_snapshot(self, version: int) -> bytes:
        return (self.path / "snapshots" / f"v{version:06d}.json.gz").read_bytes()

    def versions(self) -> list[StateVersion]:
        if self._versions_cache is None:
            self._versions_cache = []
            if self.versions_path.exists():
                with self.versions_path.open() as fh:
                    for line in fh:
                        if line.strip():
                            self._versions_cache.append(StateVersion.model_validate_json(line))
        return list(self._versions_cache)

    def append_version(self, version: StateVersion) -> None:
        self.versions()
        assert self._versions_cache is not None
        self._versions_cache.append(version)
        with self.versions_path.open("a") as fh:
            fh.write(version.model_dump_json() + "\n")

    def snapshot_versions(self) -> list[int]:
        d = self.path / "snapshots"
        if not d.exists():
            return []
        return sorted(int(p.name[1:7]) for p in d.glob("v*.json.gz"))


# ---------------------------------------------------------------------------------------------
# State hash
# ---------------------------------------------------------------------------------------------

HASH_KEYED = {
    "entities": ("wm", "graph.entities"),
    "subentities": ("wm", "graph.subentities"),
    "interactions": ("wm", "graph.interactions"),
    "instances": ("wm", "graph.instances"),
    "super_interactions": ("wm", "graph.super_interactions"),
    "hypotheses": ("wm", "hypotheses"),
    "pending_refinements": ("wm", "pending_refinements"),
    "patterns": ("ltm", "patterns.patterns"),
    "generalizations.object": ("ltm", "object_taxonomy.nodes"),
    "generalizations.interaction": ("ltm", "interaction_taxonomy.nodes"),
    "frontier": ("ltm", "frontier.entries"),
    "episodes": ("ltm", "episodes.episodes"),
    "entity_memories": ("ltm", "entity_memories"),
    "explanations": ("ltm", "explanations.explanations"),
}

HASH_SINGLETONS = {
    "wm.clock": ("wm", "clock"),
    "wm.activity_log": ("wm", "activity_log"),
    "wm.fold_accumulators": ("wm", "fold_accumulators"),
    "wm.episode_buffer": ("wm", "episode_buffer"),
    "wm.ids": ("wm", "ids"),
    "wm.decision_variables": ("wm", "decision_variables"),
    "wm.pending_episode_tags": ("wm", "pending_episode_tags"),
    "wm.last_consolidated": ("wm", "last_consolidated"),
    "wm.missing_relation_log": ("wm", "missing_relation_log"),
    "wm.graph.entity_link_labels": ("wm", "graph.entity_link_labels"),
    "ltm.reliability": ("ltm", "reliability"),
    "ltm.frontier.blocked_until": ("ltm", "frontier.blocked_until"),
    "ltm.attributes": ("ltm", "attributes"),
    "ltm.patterns.super_interaction_labels": ("ltm", "patterns.super_interaction_labels"),
    "ltm.patterns.palettes": ("ltm", "patterns.palettes"),
    "ltm.object_taxonomy.root_id": ("ltm", "object_taxonomy.root_id"),
    "ltm.interaction_taxonomy.root_id": ("ltm", "interaction_taxonomy.root_id"),
    "ltm.object_taxonomy.kind": ("ltm", "object_taxonomy.kind"),
    "ltm.interaction_taxonomy.kind": ("ltm", "interaction_taxonomy.kind"),
}


def _get(root: object, dotted: str) -> object:
    cur = root
    for part in dotted.split("."):
        cur = getattr(cur, part)
    return cur


def _digest_value(value: object) -> str:
    return sha256_text(canonical_json(value))


class StateHasher:
    """Merkle hash over every part of the state except the forecast layer."""

    def __init__(self) -> None:
        self.digests: dict[str, dict[str, str]] = {}

    def _part_keyed(self, wm: WorkingMemory, ltm: LongTermMemory, part: str, obj_id: str) -> None:
        root, path = HASH_KEYED[part]
        mapping = _get(wm if root == "wm" else ltm, path)
        bucket = self.digests.setdefault(part, {})
        obj = mapping.get(obj_id)  # type: ignore[union-attr]
        if obj is None:
            bucket.pop(obj_id, None)
        else:
            bucket[obj_id] = _digest_value(obj)

    def _part_dev(self, wm: WorkingMemory, kind: str, sid: str) -> None:
        bucket = self.digests.setdefault(f"wm.deviations.{kind}", {})
        series = getattr(wm.deviations, kind).get(sid)
        if series is None:
            bucket.pop(sid, None)
        else:
            bucket[sid] = _digest_value({str(k): v for k, v in series.items()})

    def _part_single(self, wm: WorkingMemory, ltm: LongTermMemory, part: str) -> None:
        root, path = HASH_SINGLETONS[part]
        value = _get(wm if root == "wm" else ltm, path)
        self.digests.setdefault(part, {})["_"] = _digest_value(value)

    def _dev_meta(self, wm: WorkingMemory) -> None:
        self.digests.setdefault("wm.deviations.meta", {})["_"] = _digest_value(
            {"origin_date": wm.deviations.origin_date.isoformat(), "step_days": wm.deviations.step_days})

    def full(self, wm: WorkingMemory, ltm: LongTermMemory) -> str:
        self.digests = {}
        for part, (root, path) in HASH_KEYED.items():
            mapping = _get(wm if root == "wm" else ltm, path)
            self.digests[part] = {}
            for obj_id in mapping:  # type: ignore[union-attr]
                self._part_keyed(wm, ltm, part, obj_id)
        for kind in ("z", "innovation"):
            self.digests[f"wm.deviations.{kind}"] = {}
            for sid in getattr(wm.deviations, kind):
                self._part_dev(wm, kind, sid)
        self._dev_meta(wm)
        for part in HASH_SINGLETONS:
            self._part_single(wm, ltm, part)
        return self.root()

    def update(self, wm: WorkingMemory, ltm: LongTermMemory, dirty: set[tuple[str, str]]) -> str:
        if not self.digests:
            return self.full(wm, ltm)
        for part, obj_id in sorted(dirty):
            if part in HASH_KEYED:
                self._part_keyed(wm, ltm, part, obj_id)
            elif part in ("wm.deviations.z", "wm.deviations.innovation"):
                kind = part.rsplit(".", 1)[1]
                if obj_id == "*":
                    self.digests[part] = {}
                    for sid in getattr(wm.deviations, kind):
                        self._part_dev(wm, kind, sid)
                else:
                    self._part_dev(wm, kind, obj_id)
            elif part == "wm.deviations.meta":
                self._dev_meta(wm)
            elif part in HASH_SINGLETONS:
                self._part_single(wm, ltm, part)
            # forecast-layer parts are not hashed
        return self.root()

    def root(self) -> str:
        return sha256_text(canonical_json(self.digests))


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
        for v in self.storage.versions():
            if v.version == version:
                return v
        return None

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
            for entry in self.ledger.read(start_seq):
                if entry.kind != LedgerKind.CHANGESET:
                    continue
                cs = ChangeSet.model_validate(entry.payload)
                if cs.version_after > version:
                    break
                apply_changeset(wm, ltm, cs)
        if verify and target is not None:
            got = state_hash(wm, ltm)
            if got != target.state_hash:
                raise RestoreError(f"hash mismatch restoring version {version}: {got[:12]} != {target.state_hash[:12]}")
        return wm, ltm

    def as_of(self, recorded_at: datetime) -> tuple[WorkingMemory, LongTermMemory, int]:
        """The highest version whose recorded_at is at or before `recorded_at`."""
        best = 0
        for v in self.storage.versions():
            if v.recorded_at <= recorded_at and v.version > best:
                best = v.version
        wm, ltm = self.restore(best)
        return wm, ltm, best
