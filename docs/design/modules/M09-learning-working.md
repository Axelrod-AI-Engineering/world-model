# M09 · Learning · working memory

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; receive the hypothesis scorer from `inference/` |
| Code today | `learning/working_memory.py`, `learning/fold.py`, `learning/kernel_learning.py`, `inference/voi.py` (the `hypothesis_scorer` slot, whose contract process is learning.working), and `refiner.weigh_hedges` (called from here) |
| Target | `axelrod_wm/learning/working/`: `task.py` (`WorkingMemoryLearning`), `fold.py`, `ripple.py` (ripple judgments), `kernels.py`, `voi.py` |

## Purpose

What the world is like now. One vetted event is read and **folded** into the current state: reported values correct the model where it was wrong, and each interaction into a value is updated in proportion to how much of the surprise it explains. The module also opens, records, and closes each day.

## Owns

- `WorkingMemoryLearning` with `learn`, `open_day`, `record_day`, `close_day`.
- `Folder` and `FoldResult` (posteriors, unexplained moves (innovations), observed decisions).
- `RippleJudgment` handling: a reviewer's weight that a value's ripple arrives, applied to the daily prediction until the ripple has run its course.
- `KernelUpdater`; `HypothesisScorer` (the hypothesis frontier's VOI).

## Interface

```python
class WorkingMemoryLearning:
    def learn(self, event: GraphUpdateEvent, ctx, txn) -> WMResult
        # shared.run(incorporate=False) → folder.fold → refiner.weigh_hedges → judge_ripple
        # → WMResult(shared, fold, proposal_events)
    def open_day(self, day: int, ctx, txn) -> None                 # daily_propagator.predict           [day.predict]
    def record_day(self, day: int, ctx, txn) -> None               # daily_propagator.record            [day.record]
    def close_day(self, day: int, ctx, txn) -> list[ProposalEvent] # kernels, rescore hypotheses, expiries, prune, clock [day.close]

class Folder(ABC):
    def fold(self, parsed, analysis, wm, ctx, txn) -> FoldResult
```

## Slots

| Slot | Default | Alternatives | Planned |
|---|---|---|---|
| `daily_propagator` | kalman_predict | — | R1: filter with the mixture |
| `folder` | kalman_edge (a joint Kalman fold over level and β) | — | R1 |
| `posterior_updater` | link_kalman | — | |
| `kernel_updater` | grid_rescale (a joint 3-point rescale, weekly, with a likelihood gate) | none | R4: an 8×8 (delay, lag) grid posterior plus a duration grid, scored by the Kalman marginal likelihood |
| `hypothesis_scorer` | forecast_sensitivity_voi (sensitivity × 4p(1−p)) | — | R8: EVPI under the proper score; EVSI |

## Depends on / used by

- Depends on: [M01](M01-core.md)–[M04](M04-memory.md), [M06](M06-intake.md) (`weigh_hedges`), [M07](M07-shared-read.md), [M08](M08-dynamics.md).
- Used by: [M13](M13-runtime.md) (`LearningTask`).

## Flow

[architecture.md §5](../architecture.md#5-learning--working-memory).

## Invariants

- **One commit per event:** `learn.working`.
- **The day's order:** `day.predict` → events → `day.record` → `day.distill` (M10) → `day.close`. `day.close` is last.
- **Proposals are returned, not created.** A resolved hedge comes back as a `ProposalEvent`, and the service proposes it.
- **Reviewer confidence tempers the writes.** It scales an interaction's existence and evidence, a report's weight, and a move's expected size (ml-stack §5).

## Known issues and planned

- Effects follow a random walk with sd 0.0075 per day; existence is outside the filter (ml-stack §3, S-M1) → R1.
- Kernel learning shrinks CV by 10% per run regardless of evidence (§4.3) → R4.
- A ripple judgment is a mean shift in the filter only; the Monte Carlo ignores it (§7) → R6, a two-component mixture with a learned weight.
- Observation noise is fixed by kind (§4.4) → R17.

## Done when

- `tests/unit/learning/` covers the fold on a two-node graph (the innovation splits by explained share), hedge weighing and resolution, ripple-judgment expiry, and the order of the day's commits.
