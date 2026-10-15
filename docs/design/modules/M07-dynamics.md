# M07 · Dynamics

**Layer** 3 · **Package** `dynamics/` · **Status** exists. It receives `PosteriorUpdater`, and stops importing `memory.working` at module scope.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Interface](#interface)
- [Slots](#slots)
- [Depends on](#depends-on)
- [Invariants](#invariants)
- [Planned (ml-stack §3, §6)](#planned-ml-stack-3-6)
- [Done when](#done-when)
<!-- /toc -->

**Code today:** `dynamics/kernels.py`, `propagation.py`, `daily.py`, `regressors.py`; `model/distributions.py:PosteriorUpdater`.

## Purpose

How a move in one value reaches others over time:
- **Kernels** give each interaction its timing.
- The **propagator** simulates shocks through the graph by Monte Carlo.
- The **daily propagator** is the state-space filter that predicts each day and records it.

## Owns

- `KernelRecursion`. It updates in O(1) per day: zero before the delay, a linear ramp over the lag, then a fade with λ = e^(−3/D) over the duration. A null duration means the effect is permanent.
- `PropagationSystem`, `Channel`, `ShockInput`, `PropagationResult`.
- The link-space Kalman update.

## Interface

```python
Propagator.propagate(system, shocks, n_samples, rng, *, record_contributions=False, exogenous=None) -> PropagationResult
DailyPropagator.predict(day, wm, ctx, txn) -> None              # day.predict
DailyPropagator.record(day, wm, ctx, txn) -> dict[str, float]   # day.record
PosteriorUpdater.update(current, obs, scale, process_noise_sd=0) -> Distribution
build_system(graph, interaction_ids, *, soft_bounds=True) -> PropagationSystem
```

## Slots

| Slot | Default | Alternatives | Production choice |
|---|---|---|---|
| `propagator` | mc_impulse (NumPy, 400 samples, CRN, soft bounds) | deterministic_mean | JAX jit/vmap |
| `daily_propagator` | kalman_predict | | Sparse state space with vintages |
| `posterior_updater` | link_kalman | | |

## Depends on

[M01](M01-foundation.md)–[M03](M03-memory.md).

## Invariants

- **Common random numbers.** Shocked and baseline runs use the same substream.
- **Soft bounds bend, never clip,** and the readout notes where one bent a value.
- **Deterministic** given the seed and the version.

## Planned (ml-stack §3, §6)

- **R9, R14:** joint parameter draws, factors (BBᵀ + D), GARCH, Student-t errors, and regimes.
- **R13:** no drift for prices; expectation nodes with lag-0 impact for traded values.
- **R1:** existence inside the filter (Gaussian-sum or IMM).
- **R17:** hyperparameters by marginal likelihood or EM.

## Done when

- The kernel recursion matches its closed form.
- With no shock, shocked minus baseline is zero.
- Soft bounds hold.
- Predict and record work on a two-node graph.
