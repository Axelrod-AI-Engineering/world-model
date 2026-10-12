# M14 · Services

| | |
|---|---|
| Layer | 4 · Runtime |
| Status | **Split** the god object |
| Code today | `control/controller.py` (`WorldModelController`, 940 lines, about 47 `self.engine` references), `control/updates.py` (`UpdateCycle`), `control/stage.py` (972 lines: sandbox mechanics plus about 600 lines of review view assembly); `repo/review.py` (`Proposal`, `ReviewPolicy`) |
| Target | `axelrod_wm/control/`: `review.py` (`ReviewService`), `updates.py` (`UpdateService`), `theses.py` (`ThesisService`), `structure.py` (`StructureService`), `sources.py` (`SourceRegistry`), `facade.py` (a thin `WorldModelController` for back compatibility) |

## Purpose

The commands of the product. Each service owns one workflow, persists its records through the ledger ([M05](M05-repo.md) `RecordStore`), and emits trace events. Services are the only callers of `propose()`, and the only place that decides when learning runs.

## Owns

| Service | Commands | Records |
|---|---|---|
| `ReviewService` | `propose(kind, event, world)`, `stage(pid, keep, confidences, ripple) -> StagedChange`, `approve(pid, by, note, keep, confidence, op_confidence, ripple)`, `reject(pid, by, note)`, `defer(pid)`, `edit(pid, event)`, `set_review_policy(name)` | `Proposal {id, kind, status, event, refinement, conflicts, requirement, decided_by, note}` |
| `UpdateService` | `request_update(UpdateRequest)`, `continue_(run_id)`, `cancel(run_id)`, `import_items(bundle, ids)` | `UpdateRun`, `UpdateReport` |
| `ThesisService` | `pose(question or Thesis, version, watch)`, `pin(tid)`, `record_decision(...)`, `resolve_decision(...)`, `add_hypothesis`, `mark_hypothesis(hid, status)` | `Thesis`, `Forecast`, `DecisionRecord` |
| `StructureService` | `propose_group(ids, name)`, `propose_dissolve(pattern_id)`, `propose_retire(item_id)`, `submit_graph_update(event)` (drawn edits; world ops are refused), `add_from_knowledge(form)` | proposals of the kinds above |
| `SourceRegistry` | `register_source(name)`, `source(name)`, `translator_chain(kind)` | — |

## Interface

The table above is the interface. Every command:

- runs under the engine lock;
- returns a typed result;
- emits trace events (`review.queued`, `review.auto`, `update.*`, `thesis.posed`, `forecast.ready`, `state.version`);
- never builds a view model. Views are [M15](M15-views.md)'s job; today `control/` imports `api.views`.

## Depends on / used by

- Depends on: [M13](M13-runtime.md), [M05](M05-repo.md), [M06](M06-intake.md) (pipeline, bundle), [M12](M12-evaluation.md).
- Used by: [M15](M15-views.md), [M16](M16-context-layer.md), [M17](M17-api-cli.md), [M19](M19-demo.md).

## Flow

- The update run: [architecture.md §8](../architecture.md#8-the-day-loop-an-update-run).
- Review: [§7](../architecture.md#7-human-review-and-commit) and the sequence in [§10](../architecture.md#staged-review-of-one-event).
- The proposal lifecycle: [§12](../architecture.md#proposal).

## Invariants

- **Vetted learning.** Nothing that needs review is learned before a person approves it, and what they approve is what they saw staged. Rejecting changes nothing. A deferred event folds in late once approved.
- **Review at the end.** Staging runs the event's whole learning: WM, LTM, and the day's distillation.
- **Deselect re-stages.** A partial approval edits out the deselected operations and the operations that depend on them (`closure`, `subset`).
- **Every decision is logged** (`REVIEW_DECISION`), with who decided and at what confidence.
- **Learn is internal; Predict is external.** Learning commands are for backend users; `ThesisService` is the only service external users reach.
- **Services persist.** A restart restores proposals, theses, forecasts, and decisions from the ledger.

## Known issues and planned

- Today `sim/imports.py` and `sim/examples/session.py` reach into `controller._translators`. `SourceRegistry` makes this public.
- Today `AppState` wraps a `ScenarioRunner`, and routes probe it with `hasattr`. With services, the API depends on services only ([M17](M17-api-cli.md)).

## Done when

- The existing integration tests (`test_review_api`, `test_ripple_review`, `test_import_api`, `test_api`) pass against the facade unchanged.
- New service tests cover the proposal lifecycle, a deferred approval folding in late, and records surviving a restart.
- `control/` has no import of `api/` or `sim/`.
