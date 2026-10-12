# M12 · Evaluation

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; receive decisions from `inference/` |
| Code today | `evaluation/backtest.py`, `evaluation/metrics.py`; `inference/decisions.py` |
| Target | `axelrod_wm/evaluation/`: `metrics.py`, `scorer.py`, `backtest.py`, `decisions.py`, `track_records.py` |

## Purpose

How inference earns trust. A forecast that someone acts on is recorded with the version it read. Once its horizon passes, what happened scores it, and the superentities whose networks called the move gain track record. Backtests freeze the model at a past date and pose what happened next.

## Owns

- Metrics: CRPS (sample and quantile), pinball loss, coverage at 50/80/90, omission, commission.
- `Scorer`; `EvaluationRequest`, `EvaluationReport`.
- `DecisionRecord`, `Outcome`, `DecisionTrace`. A decision must cite a baseline forecast at the same version, and `trace_decision` checks the hash.
- Track records on superentity patterns.

## Interface

```python
def backtest(req: EvaluationRequest, store: SnapshotStore, runtime) -> EvaluationReport
    # as_of(t) → pose the later reported changes as a thesis → forecast → compare with observed → score
    # → update track records → EVALUATION ledger entry
def record_decision(forecast_ids, version, review_at, by) -> DecisionRecord
def resolve_decision(decision_id, realized) -> Outcome          # scores at the horizon, updates track records

class Scorer(ABC):
    def score(self, forecast: Forecast, realized: dict[str, list[float]], cfg: dict) -> dict
```

## Slots

| Slot | Default | Planned |
|---|---|---|
| `scorer` | omission_commission_calibration | R10: rolling origin, sample CRPS plus log score, PIT; BVAR/LP baselines; Diebold–Mariano, Clark–West, Giacomini–White, MCS; desk metrics |

## Depends on / used by

- Depends on: [M01](M01-core.md)–[M05](M05-repo.md).
- Used by: [M13](M13-runtime.md), and [M14](M14-services.md) (ThesisService for decisions; the context layer's `feedback`).

## Invariants

- **The only feedback from inference into memory is track records**, written in an `evaluation` commit.
- **Score against raw observations or the true state, never against filtered values** (R0). Today the scores use filtered values, which is circular (S-C1). This is the first fix in the roadmap.
- **No leakage.** A backtest restores the version as it was recorded at the freeze date. With bitemporal fields ([M03](M03-model.md#additions-this-design-makes)), it also uses only data valid and recorded by then.

## Known issues and planned

- R0 (above), R10 (proper evaluation), R16 (misspecified and null synthetic worlds as controls).

## Done when

- `tests/unit/evaluation/` covers the metrics on known distributions and decision tracing (a hash mismatch is refused).
- A backtest on the oil demo reproduces its report from the seed.
