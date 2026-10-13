# M04 · Repo (version control)

**Layer** 2 · **Package** `repo/` · **Status** exists.
- **Adds:** `Branch`, PROV fields, and record stores.
- **Loses:** `Proposal` and `ReviewPolicy`, to M13 and M01.

**Code today:** `repo/mutator.py`, `ledger.py`, `snapshots.py`, `history.py`, `review.py`.

## Purpose

The **one writer**. Every change to either memory goes through a transaction. Each transaction becomes one `ChangeSet` in an append-only ledger, and snapshots plus change sets reproduce any version, verified by hash.

## Owns

- `GraphMutator`, `MutationTxn`, `ChangeSet {process, memory, message, proposal_id, vetted_by, changes}`, `PROCESSES`.
- `EventLedger`, `LedgerEntry {seq, kind, recorded_at, occurred_at, state_version, payload}`.
- `SnapshotStore`, `StateHasher` (Merkle), `StateVersion`; `FilesBackend`, `MemoryBackend`.
- **New** `Branch`: copy-on-write over a committed version, with its own throwaway ledger. It replaces two mechanisms: staging's JSON copy with attribute swaps, and the thesis overlay on live working memory.
- **New** PROV fields on `ChangeSet`: entity, activity, agent, and used (evidence, market event).
- **New** `RecordStore[T]` for proposals, theses, forecasts, and decisions, rebuilt from the ledger on restart.

## Interface

```python
GraphMutator.begin(cause, at, process, *, message="", proposal_id=None, vetted_by=None) -> MutationTxn  # context manager
MutationTxn.add / update / remove / put / append / truncate / clear / set(collection: str, key, ...)     # "wm.graph.interactions"
SnapshotStore.save(version); .restore(version) -> (wm, ltm); .as_of(recorded_at) -> version
Branch.of(version, store) -> Branch          # .wm, .ltm, .mutator (MemoryBackend), .changesets()
log(limit) · show(version) · diff(a, b) · export_prov(since_seq) -> PROV graph      # new
```

## Depends on

[M01](M01-foundation.md), [M02](M02-model.md), [M03](M03-memory.md).

## Diagram

The ledger lifecycle (record → stage → govern → commit → audit) is in [architecture.md §6](../architecture.md#6-the-ledger-lifecycle).

## Invariants

- **One writer.** Each transaction becomes one change set, which names its process and bumps the version. The exception is forecast-only change sets, which don't bump it.
- **Two learning commits per event** (`learn.working`, then `learn.long_term`). `day.close` is a day's last commit.
- **A branch never touches the live state, ledger, or trace.**
- **Restore.** The init snapshot plus the change sets reproduce the live hash.
- **Append-only.** A correction is a new change set that supersedes the old one.

## Planned

- The init ledger is 671 MB on the oil demo. Planned: a columnar store and compaction.
- `as_of(valid, recorded)` once the bitemporal fields exist.

## Done when

- The restore and determinism tests pass.
- Staging on a branch leaves the live hash, ledger length, and trace unchanged.
- A PROV export validates.
- Records survive a restart.
