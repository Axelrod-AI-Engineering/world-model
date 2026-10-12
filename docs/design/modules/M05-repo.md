# M05 · Repo (version control)

| | |
|---|---|
| Layer | 2 · State |
| Status | **Exists**; add branches as one mechanism, PROV-shaped change sets, and ledger-backed stores for service records |
| Code today | `repo/mutator.py`, `repo/ledger.py`, `repo/snapshots.py`, `repo/history.py`, `repo/review.py` (proposal types and the review policy) |
| Target | `axelrod_wm/repo/`: `mutator.py`, `ledger.py`, `snapshots.py`, `branches.py` (new), `history.py`, `provenance.py` (new), `records.py` (new: proposals, theses, forecasts, decisions as ledger-backed stores). `Proposal` and `ReviewPolicy` move to [M14](M14-services.md) and [M02](M02-ports.md). |

## Purpose

The world model works like version control. This module is the **one writer**. Every change to either memory goes through a transaction; each transaction becomes one `ChangeSet` in an append-only ledger; snapshots plus change sets reproduce any version, and its hash verifies it.

## Owns

- `GraphMutator`, `MutationTxn`, `ChangeSet`, `Change`, `apply_changeset`, `PROCESSES`.
- `EventLedger`, `LedgerEntry {seq, kind, recorded_at, occurred_at, state_version, payload}`, `LedgerKind`.
- `SnapshotStore`, `StateHasher` (Merkle, updated incrementally), `StateVersion {version, seq, state_hash, recorded_at, cause, process, memory}`.
- `StorageBackend` implementations: `FilesBackend`, `MemoryBackend`.
- **New** `Branch`: a copy-on-write view of a committed version, with its own throwaway ledger. One mechanism replaces today's two: the staging sandbox (a JSON copy plus attribute swaps on the engine) and the thesis overlay (`GraphOverlay` on the live working memory).
- **New** PROV fields on `ChangeSet`: `entity` (what changed), `activity` (process + proposal), `agent` (who vetted it, or which slot), `used` (evidence and market event ids).
- **New** `RecordStore[T]`: proposals, theses, forecasts, and decisions, rebuilt from the ledger on restart. Today they live only in the controller's memory.

## Interface

```python
class GraphMutator:
    def begin(self, cause: str, at: datetime, process: str, *, message: str = "",
              proposal_id: str | None = None, vetted_by: str | None = None) -> MutationTxn   # context manager

class MutationTxn:
    def add(self, collection: str, key: str, value) -> None        # collections are dotted: "wm.graph.interactions"
    def update(self, collection: str, key: str, **fields) -> None
    def remove(self, collection: str, key: str) -> None
    def put / append / truncate / clear / set(...)
    # on exit: ChangeSet → Engine.on_commit → ledger CHANGESET, version bump (unless forecast-only), hash, StateVersion

class SnapshotStore:
    def save(self, version: int) -> None
    def restore(self, version: int) -> tuple[WorkingMemory, LongTermMemory]   # snapshot ≤ version + change sets; hash-checked
    def as_of(self, recorded_at: datetime) -> int                              # the last day.close version at that time

class Branch:                                                                  # new
    @classmethod
    def of(cls, version: int, store: SnapshotStore) -> "Branch"
    wm: WorkingMemory; ltm: LongTermMemory; mutator: GraphMutator              # writes go to a MemoryBackend
    def changesets(self) -> list[ChangeSet]

def log(limit) / show(version) / diff(a, b)                                    # history.py
def export_prov(since_seq=0) -> rdflib.Graph | dict                            # new, slot provenance_exporter
```

## Slots

| Slot | Default | Alternatives |
|---|---|---|
| `storage` | files | memory. Planned: an append-only table store (Parquet or DuckDB), per implementation.html |
| `provenance_exporter` (new) | prov_json | prov_o_turtle |

## Depends on / used by

- Depends on: [M01](M01-core.md), [M03](M03-model.md), [M04](M04-memory.md). Not `intake/` (today `Proposal` imports `intake.refiner.RefinementStep`; that type moves to `model/` or `ports/`).
- Used by: [M13](M13-runtime.md), [M14](M14-services.md), and [M15](M15-views.md) for log, show, and diff.

## Flow

[architecture.md §11](../architecture.md#11-the-ledger-lifecycle) is the lifecycle: record → stage → govern → commit → audit and restore.

## Invariants

- **One writer.** Every change to WM or LTM goes through a `MutationTxn`. Each transaction becomes exactly one `ChangeSet`. Each change set names its process and bumps the version, except forecast-only ones.
- **Two learning commits per event.** `learn.working`, then `learn.long_term`. `day.close` is always a day's last commit.
- **Staging never touches the live state, ledger, or trace.** A branch writes to its own `MemoryBackend`.
- **Restore.** The init snapshot plus the ledger's change sets reproduce the live state hash.
- **Append-only.** No entry is edited or removed. A correction is a new change set that supersedes the old fact.

## Known issues and planned

- Snapshots are gzip JSON of the whole state. They are fine for the demo, but the oil demo's init ledger is 671 MB. Planned: a columnar store, and change sets compacted into periodic snapshots.
- `as_of` restores by recording time only. With bitemporal fields ([M03](M03-model.md#additions-this-design-makes)), add `as_of(valid=..., recorded=...)`.

## Done when

- The existing restore and determinism scenario tests pass.
- A branch test: stage an event on a branch, then check that the live hash, ledger length, and trace sequence are unchanged.
- A PROV export of the small demo after example 24 validates against the PROV-O shapes.
- After a restart, the proposals, theses, forecasts, and decisions are back (today they are lost).
