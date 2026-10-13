# M11 · Evaluation

**Layer** 3 · **Package** `evaluation/` · **Status** exists; it receives decisions from `inference/`.
**Code today:** `evaluation/backtest.py`, `metrics.py`, `inference/decisions.py`.

## Purpose

How inference earns trust:
- A forecast that someone acts on is recorded with the version it read.
- When its horizon passes, what happened scores it.
- The superentities whose networks called the move gain track record.
- Backtests freeze the model at a past date and pose what happened next.

## Interface

```python
Scorer.score(forecast, realized, cfg) -> dict                  # CRPS, pinball, coverage 50/80/90, omission, commission
backtest(req, store, runtime) -> EvaluationReport              # as_of(t) → pose what followed → forecast → score → track records
record_decision(forecast_ids, version, review_at, by) -> DecisionRecord   # must cite a baseline at the same version
resolve_decision(decision_id, realized) -> Outcome             # evaluation commit
```

## Slots

| Slot | Default | Planned |
|---|---|---|
| `scorer` | omission_commission_calibration | R10: rolling origin, log score, PIT, BVAR/LP baselines, DM/CW/GW/MCS tests, desk metrics |

## Depends on

[M01](M01-foundation.md)–[M04](M04-repo.md).

## Invariants

- **Track records are the only feedback from inference into memory.**
- **Score against raw observations, never against filtered values.** R0 makes this change; today's scores are circular (S-C1). It is the roadmap's first fix.
- **No leakage.** A backtest uses only what was recorded by the freeze date, and, with bitemporal fields, only what was also valid by then.

## Done when

- The metrics are correct on known distributions.
- A decision with a mismatched hash is refused.
- An oil-demo backtest reproduces from its seed.
- R16's null worlds give scores at chance level.
