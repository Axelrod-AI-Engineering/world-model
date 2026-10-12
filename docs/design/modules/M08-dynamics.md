# M08 · Dynamics

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; receive `PosteriorUpdater`; stop importing `memory/working` |
| Code today | `dynamics/kernels.py`, `propagation.py`, `daily.py`, `regressors.py`; `model/distributions.py` (`PosteriorUpdater`, `LinkKalmanUpdater`) |
| Target | `axelrod_wm/dynamics/`: `kernels.py`, `propagation.py`, `daily.py`, `posterior.py`, `regressors.py` |

## Purpose

The quantitative heart of the model: how a move in one value reaches others over time. **Kernels** give each interaction's timing. The **propagator** simulates shocks through the graph by Monte Carlo. The **daily propagator** is the state-space filter that predicts each day and records it.

## Owns

- `KernelRecursion`: an O(1) per-day update of a ramp-decay kernel (zero before the delay, a linear ramp over the lag, then a fade with λ = e^(−3/D) over the duration; a null duration means the effect is permanent).
- `PropagationSystem`, `Channel`, `ShockInput`, `PropagationResult` (`minus`, `median_z`, `summary`). These are port types ([M02](M02-ports.md)).
- `DailyPropagator`: `predict` opens a day by carrying yesterday's deviations through each channel; `record` writes every value's point and the posteriors of unobserved values.
- `PosteriorUpdater`: the link-space Kalman update.

## Interface

```python
class Propagator(ABC):
    def propagate(self, system: PropagationSystem, shocks: list[ShockInput], n_samples: int,
                  rng: np.random.Generator, *, record_contributions=False, exogenous=None) -> PropagationResult

class DailyPropagator(ABC):
    def predict(self, day: int, wm, ctx, txn) -> None
    def record(self, day: int, wm, ctx, txn) -> dict[str, float]

def build_system(graph: CausalGraph, interaction_ids, *, soft_bounds=True) -> PropagationSystem
```

## Slots

| Slot | Default | Alternatives | Production choice (implementation.html) |
|---|---|---|---|
| `propagator` | mc_impulse (NumPy, 400 samples, CRN, soft bounds) | deterministic_mean | JAX jit/vmap |
| `daily_propagator` | kalman_predict | — | A sparse state space with vintages |
| `posterior_updater` | link_kalman | — | |

## Depends on / used by

- Depends on: [M01](M01-core.md)–[M04](M04-memory.md). `ChannelState` (the pydantic state of a kernel recursion) moves to `memory/`, so that `memory/` stops importing `dynamics/`.
- Used by: [M07](M07-shared-read.md) (analyze), [M09](M09-learning-working.md) (the day), [M11](M11-inference.md) (predict, couple).

## Invariants

- **Common random numbers.** Shocked and baseline runs use the same substream (`core.substream(seed, scope, "propagate")`).
- **Soft bounds bend, never clip.** A value near its economic constraint slows down smoothly, and the readout notes where a bound bent a value.
- **Deterministic given the seed and version.**

## Known issues and planned

From ml-stack §3, §6 and the roadmap:

- Parameters are drawn independently, with no initial-state uncertainty and no common factor. R9 plans joint draws, factors, GARCH, Student-t errors, and regimes; R14 a factor covariance BBᵀ + D.
- There is a damped 28-day drift on everything, prices included. R13 removes drift for prices and adds expectation nodes with lag-0 impact for traded values (pricing in).
- Existence is not in the filter (§3). R1 filters with the mixture (Gaussian-sum or IMM) and tracks inclusion by sequential log-odds.
- Hyperparameters are fixed by kind. R17 plans marginal likelihood or EM.

## Done when

- `tests/unit/dynamics/` covers the kernel recursion against its closed form, propagation determinism and CRN (shock minus baseline is zero with no shock), soft bounds, and predict/record on a two-node graph.
