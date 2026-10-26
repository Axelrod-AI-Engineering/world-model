# One unified model, served in compartments

Oct 25. This builds [D-20](decisions.md): one world model, with each account served a subset of it.

<!-- toc -->
**Contents**

- [Problem](#problem)
- [Scope](#scope)
- [Priorities](#priorities)
- [Requirements](#requirements)
- [Diagram](#diagram)
- [Dependencies](#dependencies)
- [Architecture](#architecture)
- [Infrastructure](#infrastructure)
- [Data model](#data-model)
<!-- /toc -->

## Problem

Each login opens its own world, in memory, so knowledge is learned once per client. A model imported from documents
is lost at every restart, because the import runner wipes its storage on load. And every imported item waits for a
person, so a pack of hundreds of documents cannot populate a model at all.

## Scope

**In scope:**
- One unified base built from every client world.
- Each login served a compartment of it.
- Imports that persist across restarts and redeploys.
- An auto-approve gate that applies an imported item only when it meets the construction standards.

**Out of scope:**
- Roles inside an organization.
- A compartment per user rather than per login.
- Merging conflicting construction files by hand. Conflicts stop the load and name the files.
- Staging and production.

## Priorities

| | What | Done when |
|---|---|---|
| **P0** | Imports persist | A restart or redeploy reopens the model at its last version, with its imported items and review policy; importing the same bundle again changes nothing |
| **P0** | The standards gate | An item applies without a person only when every check below passes; any other item becomes a pending proposal, with the failed check as its reason, and the import goes on |
| **P0** | One unified base | One engine loads every client world's construction files together; a clash of ids between worlds stops the load |
| **P0** | A compartment per login | A login whose scenario is a focus over the unified base reads, forecasts, and asks theses on its compartment of the one engine, not on an engine of its own |
| **P1** | Per-account learning | An account's own reviews, edits and theses are kept in an overlay for that account, persisted, and promoted to the base only through review |
| **P2** | Compartments by tag | A compartment can be given as superentities or tags, not only as covered companies |
| **P3** | Staging and production | The unified model, its data, and its compartments in the other environments |

## Requirements

1. **One writer.** Learning writes only to the unified engine, through the review path (D-13). A compartment never holds
   a second copy of the graph. It is a view, as `narrow` computes one.
2. **Isolated asking.** A forecast, a thesis, or a search from a login sees only its compartment. Names, values, links
   and passages outside it are not in the answer, not in its explanation, and not in its errors (D-04).
3. **Learning on the whole.** Evidence from any account's documents updates the base, so every compartment that holds
   the same entity sees the same estimate. The Kalman fold runs on the base graph, not on a compartment.
4. **Persistence.** The engine's ledger, versions and snapshots live on the volume, and the engine resumes from them.
   Resume rebuilds the imported-item map, the review policy and pending proposals from the ledger, so a resumed engine
   is the same as the one that stopped: same hash, same version, same queue.
5. **The standards gate** is a review policy. It approves an item only when all of the following hold:
   - **Not structural:** the item adds no entity and deletes nothing (D-12).
   - **No uncertain cross-company link:** a link between two companies needs a citation on the item (R20).
   - **Attributed:** the item names its source document and date. Third-party material names its publisher and is
     marked direct, proxy, or context only (R21).
   - **One basis:** the item does not count a total through two overlapping views (`intake/overlap.py`, R19).
   - **Plausible and confident:** it passes the extractor's plausibility band, and its confidence is at least 0.6.
   - **Labelled coverage:** when the source covers only part of a total, the item carries a `partial` label (R18).

   An item that fails becomes a pending proposal with the failed checks as its reasons (`review_reasons`). The gate
   never widens what a deletion, a structural change or a text translation may do without a person.

   **A run pauses for review only under `review_all`.** Under any other policy (`standards`, `default`,
   `auto_approve_all`) an import run goes to the end: items the policy approves apply as `policy:standards`, items that
   need a person stay pending (`Proposal.queued`), and the run completes. A completed run never blocks the next import,
   so one item waiting for a person cannot stop a bulk import. Under `review_all` the run still pauses at each item,
   in date order, as the review screen expects. In code the rule is `ReviewPolicy.pauses_run`, read by
   `ImportRunner.import_items`, which sets `UpdateRequest.on_review`.

   **Deciding a pending proposal later** applies it to the model as it stands then, as a new version: approving stores
   the proposal's side effects and folds its operations in on the first unprocessed day (the late fold). Before it
   applies, each operation is checked against the current graph (`stale_reason`). If something it names is gone (a
   retired value, link or entity), the approval fails with `409 conflict` naming it, nothing changes and the proposal
   stays pending, so a person can reject it. Rejecting closes it. Every decision is a ledger entry.
6. **Determinism.** The same bundles in the same order give the same versions and hashes, before and after a restart.
7. **No client content in the repository.** Worlds, scenarios and compartments stay in the client root on the volume
   ([deployment.md](../../../docs/deployment.md#client-content)).

## Diagram

```text
         documents ──▶ ingestion ──▶ lake (bundles)
                                        │
                                        ▼  imports, through the standards gate
  ┌──────────────────────── unified engine (one writer) ────────────────────────┐
  │  base graph: every client world's construction files, merged                │
  │  ledger · versions · snapshots on the volume (resume at start)              │
  └───────────────┬───────────────────────────┬─────────────────────────────────┘
                  │ narrow                    │ narrow
          compartment A (login a)     compartment B (login b)     internal logins: the whole
          reads · forecasts · theses  reads · forecasts · theses
```

## Dependencies

- `engine/focus.py` (`FocusSpec`, `focus_result`, `narrow_bundle`): the subset.
- `api/v1/compartments.py` (`discover`, `narrow`) and `api/v1/context.py` (`unified`): reads and access.
- `repo/snapshots.py` (`FilesBackend`, `SnapshotStore.restore`) and `repo/ledger.py`: persistence.
- `repo/review.py` (`ReviewPolicy`, the `review_policy` registry): the gate.
- `intake/overlap.py` (`overlap_guard`): the one-basis check.

## Architecture

**The unified scenario.** A scenario may name several construction folders. `read_construction` merges them in order,
records each id's origin, and fails when two folders define one id differently. The unified scenario is client content.
It names every client world and their seeds, and runs `canvas: seeded` under the import runner. It is the main
engine's scenario, so `erid` serves it whole to internal organizations.

**Compartments.** A login's scenario is a focus whose `base` is the unified scenario. `create_app` gives such a login a
view onto the main engine, holding the focus and the organization, in place of an engine of its own. Every read
handler, every forecast and every thesis for that login runs on `narrow(wm, focus)`. A forecast runs on a
`GraphOverlay` over the narrowed memory with `learn=False`, as theses do today. A login whose scenario is not a focus
over the unified base still gets its own engine, as today.

**Writes from a compartment.** An upload or import from a login goes to the unified engine, through the gate. The lake
tenant is the login's organization, so passages stay with the account that sent them. Items about companies outside
the login's compartment are dropped (`narrow_bundle`), so one client's documents never reshape another client's
companies.

**Persistence.** `ImportRunner.load` resets storage only when it holds no versions. Otherwise it resumes, as
`ScenarioRunner.resume` does: it restores the latest version, verifies its hash, and rebuilds the imported-item map
from the `MARKET_EVENT` ledger entries (`IM-<item id>`). It also rebuilds the review policy (a ledger entry when it
changes) and pending proposals (`PROPOSAL` entries without a decision, and a `queued` entry that says which day and
run left one pending, so it can be approved after a restart). A compartment's view sees and decides only the pending
proposals its own imports raised. A snapshot is taken after each import, so a
resume replays few change sets. Storage is `var/axelrod/unified` on the volume, and does not depend on the login.

**The gate.** `StandardsPolicy` is registered as `standards` in the `review_policy` registry. It is the default for
the unified scenario, and can be chosen through `PATCH /api/config/review`.

## Infrastructure

There is no new service. The world-model volume (`/app/var`) holds the unified engine's storage. The lake stays in
the data service. A redeploy restarts the engine, which resumes from the volume.

## Data model

- **`scenario.yaml`:** `initialization.construction_dirs`, a list, beside the single `construction_dir`.
- **Ledger:** `REVIEW_POLICY` entries, with the policy name and who set it. Imported items keep `MARKET_EVENT` with the
  `IM-` prefix.
- **Proposal:** `review_reasons` carries the gate's failed checks, and `by="policy:standards"` marks an automatic
  approval. `queued` marks one a run left pending. `/v1` changes carry `review_reasons` too.
- **Ledger:** a `queued` decision entry (`day`, `update_id`) when a run leaves a proposal pending.
- **Login:** `WORLD_MODEL_LOGINS` is unchanged (`user:password:scenario`). A login is a compartment when its scenario's
  `focus.base` is the main scenario.
