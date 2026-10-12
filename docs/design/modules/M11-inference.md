# M11 · Inference

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; hand VOI to M09, decisions to M12, transmission to M07 |
| Code today | `inference/task.py` (the task plus four ABCs), `isolate.py`, `predict.py`, `couple.py`, `unify.py` (plus the rival and weighter ABCs), `groups.py`, `records.py`; `voi.py`, `decisions.py`, `transmission.py`, `paths.py` (moving out) |
| Target | `axelrod_wm/inference/`: `isolate.py`, `predict.py`, `couple.py`, `scenarios.py` (plan + rivals + weights), `unify.py`, `groups.py`, `readout.py` (constraints, orders, paths) |

## Purpose

How the model answers a what-if question. Posing a thesis runs the shared read on a **branch** of a committed version that is never merged. Inference then:

1. **isolates** the networks the shock reaches;
2. predicts each network alone (**isolated prediction**), then couples them (**distributed prediction**);
3. **unifies** the rival scenarios into one forecast;
4. reads every value out by order and transmission path, at any granularity.

## Owns

- `NetworkIsolator`, `NetworkPredictor`, `NetworkCoupler`, `ForecastUnifier`, `RivalDetector`, `ScenarioWeighter` (implementations).
- `Network` (a bound superentity instance, a residual, or a context/watch network), `NetworkPrediction`, `ForecastScenario`.
- Group forecasts (`EffectMixture`, `group_forecasts`): entity, sector, superentity, and category targets, averaged draw by draw.

## Interface

```python
def forecast(thesis: Thesis, branch: Branch, shared: SharedResult, slots: InferenceSlots,
             ctx, *, watch: list[str]) -> Forecast
    # isolate → predict each network (± shock) → plan scenarios → couple (± shock, same draws)
    # → weigh → combine → groups → binding constraints → transmission (M07)
    # A pure read: the caller (ThesisService, M14) writes the forecast layer and the ledger.
```

## Slots

| Slot | Default | Alternatives | Planned |
|---|---|---|---|
| `isolator` | bound_superentity (relevance = 0.5·attention + 0.5·reach) | k_hop | |
| `network_predictor` | mc_network | — | |
| `rival_detector` | pattern_and_sign | — | |
| `coupler` | union_graph | iterative_block (Gauss–Seidel) | |
| `scenario_weighter` | support_fit_track (support × 56-day fit × track record × p) | uniform | R7: leave-future-out scores; stacking or pseudo-BMA+; a beta-transformed linear pool |
| `unifier` | channels_and_rivals (keeps the top 8; largest-remainder sample mixture) | weighted_mixture | |

## Depends on / used by

- Depends on: [M01](M01-core.md)–[M05](M05-repo.md) (`Branch`), [M07](M07-shared-read.md), [M08](M08-dynamics.md).
- Used by: [M13](M13-runtime.md) (`InferenceTask`).

## Flow

[architecture.md §9](../architecture.md#9-inference-the-six-stages), and the thesis sequence in [§10](../architecture.md#pose-a-thesis).

## Invariants

- **Inference never learns.** It reads a branch; nothing it computes is committed. Only outcomes feed back, through track records ([M12](M12-evaluation.md)).
- **Rival scenarios are mixed, not averaged.** Where they disagree, the forecast is wide or has two humps.
- **The context network.** Every watched name is reached by a path or reported as unreached. No tracked name is dropped silently.
- **Reproducible.** A forecast records `based_on_version`, `config_hash`, and `seed`.
- **A held decision is do().** A decision variable pinned for a window ignores its incoming interactions; a changed value is a soft intervention.

## Known issues and planned

- Scenario weights use in-sample fit (S-M5) → R7.
- Explanation by ablation is not a path-specific effect → R12.
- Config mismatch: `max_networks` and `top_k_superentities` are 8 in the yaml but 6 in code (ml-stack §12).

## Done when

- `tests/unit/inference/` covers isolation with a residual and a watch network, rival detection, CRN coupling (no shock gives a zero effect), and mixture weights summing to one.
- Example 24 of the tutorial and the oil demo's theses pass. The live state hash is unchanged after any number of theses.
