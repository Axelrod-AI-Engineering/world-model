# M08 · Learning · working memory

**Layer** 3 · **Package** `learning/working/` · **Status** exists; regrouped, and it receives VOI from `inference/`.
**Code today:** `learning/working_memory.py`, `fold.py`, `kernel_learning.py`, `inference/voi.py`.

## Purpose

What the world is like now. One vetted event is **folded** into the current state:
- a reported value corrects the model;
- each interaction into that value is updated in proportion to how much of the surprise it explains.

This module also opens, records, and closes each day, and keeps the hypothesis frontier scored.

## Owns

- `WorkingMemoryLearning`.
- `Folder`, returning `FoldResult` (posteriors, unexplained moves, observed decisions).
- Ripple judgments.
- `KernelUpdater`.
- `HypothesisScorer`.

## Interface

```python
WorkingMemoryLearning.learn(event, ctx, txn) -> WMResult        # learn.working: shared read → fold → weigh hedges → ripple judgments
WorkingMemoryLearning.open_day(day, ctx, txn)                   # day.predict
WorkingMemoryLearning.record_day(day, ctx, txn)                 # day.record
WorkingMemoryLearning.close_day(day, ctx, txn) -> list[ProposalEvent]   # day.close: kernels, rescore, expiries, prune, clock
Folder.fold(parsed, analysis, wm, ctx, txn) -> FoldResult
KernelUpdater.update(wm, ltm, ctx, txn) -> list[str]
HypothesisScorer.score(h, wm, ltm, ctx) -> float; .rescore_touched(entity_ids, wm, ltm, ctx, txn) -> list[str]
```

## Slots

| Slot | Default | Planned |
|---|---|---|
| `folder` | kalman_edge (joint over level and β) | R1: filter with the mixture; inclusion log-odds |
| `kernel_updater` | grid_rescale (3-point, weekly) | R4: (delay, lag) grid posterior by marginal likelihood |
| `hypothesis_scorer` | forecast_sensitivity_voi: sensitivity × 4p(1−p) | R8: EVPI under the forecast's score ([cognition.md F10](../cognition.md#f10--structure-apart-from-strength-and-what-is-worth-knowing)) |

## Depends on

[M01](M01-foundation.md)–[M03](M03-memory.md), [M05](M05-intake.md) (`weigh_hedges`), [M06](M06-shared-read.md), [M07](M07-dynamics.md).

## Diagrams

Step by step:

```mermaid
flowchart TD
  IN[/"Graph update event, on its day"/] --> OPEN["The day opens: yesterday's moves ripple forward<br/>(slot: daily_propagator, once per day)"]
  OPEN --> P["Apply each operation<br/>add or retire structure; a change becomes a shock;<br/>a report becomes an observation (slot: parser)"]
  P --> NEW{"New items?"}
  NEW -- yes --> CL["Sort each down its taxonomy; inherit the kind's priors<br/>(slot: classifier)"]
  NEW -- no --> RC
  CL --> RC["Recall superentities and past days with a matching signature<br/>(slot: recaller, attention)"]
  RC --> FIT{"Does a recalled superentity fit?"}
  FIT -- yes --> BD["Bind it as an instance;<br/>a relation it predicts but the graph lacks → proposal (slot: binder)"]
  FIT -- no --> PF
  BD --> PF["Build the working set: interactions near the event,<br/>adjusted by similar past days (slot: prefiller)"]
  PF --> MV{"Does the event move a value?"}
  MV -- yes --> AN["Simulate with and without the move on the same draws;<br/>each reached value gets an order, a path, a peak (slot: analyzer → propagator)"]
  MV -- no --> RP
  AN --> RP{"Does the event report a value?"}
  RP -- yes --> FO["Surprise = report − prediction;<br/>update the level and each incoming interaction by its share (slot: folder)"]
  RP -- no --> HG
  FO --> HG{"Hedged ends waiting?"}
  HG -- yes --> WH["Weigh each candidate by this event × your confidence<br/>(refiner.weigh_hedges)"]
  WH --> PASS{"One candidate past the bound?"}
  PASS -- yes --> RES["Propose the resolution (waits for review)"]
  PASS -- no --> OUT
  HG -- no --> OUT
  RES --> OUT[/"Staged working memory: structure, moves, ripple by order,<br/>updated values and effects, hedges' new odds"/]
```

A hypothesis's lifecycle:

```mermaid
stateDiagram-v2
  [*] --> open: proposed by intake, the frontier, or a person
  open --> open: rescored when its entities are touched (VOI, 14-day half-life)
  open --> branched: valuable and undecided in a thesis → scenarios with and without it
  branched --> open
  open --> supported: marked, or evidence passes the bound
  open --> refuted
  open --> expired
  supported --> [*]
  refuted --> [*]
  expired --> [*]
```

## Invariants

- **The day's commits come in this order:** `day.predict`, the events' `learn.working`, `day.record`, `day.distill` ([M09](M09-learning-long-term.md)), `day.close`.
- **Proposals are returned, not created.**
- **Reviewer confidence tempers the writes:** existence, a report's weight, and a move's expected size.

## Planned

- R6: a ripple judgment becomes a two-component mixture. Today the Monte Carlo ignores it.
- R17: learn the observation noise.

## Done when

- A fold on a two-node graph splits the innovation by explained share.
- Hedges resolve.
- Ripple judgments expire.
- The commits come in order.
