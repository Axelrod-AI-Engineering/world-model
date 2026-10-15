# M10 · Inference

**Layer** 3 · **Package** `inference/` · **Status** exists. It hands off three pieces:
- VOI to M08;
- decisions to M11;
- transmission to M06.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Interface](#interface)
- [Slots](#slots)
- [Depends on](#depends-on)
- [Diagram](#diagram)
- [Invariants](#invariants)
- [Planned](#planned)
- [Done when](#done-when)
<!-- /toc -->

**Code today:** `inference/task.py`, `isolate.py`, `predict.py`, `couple.py`, `unify.py`, `groups.py`.

## Purpose

How the model answers a what-if question. A thesis runs the shared read on a **branch** that is never merged. Inference then runs stages 2–5 of the seven, which are mutually exclusive and each answer one question:

1. Pose a thesis (M13): what is asked?
2. **Isolate:** what can the shock reach?
3. **Isolated prediction:** how does each network respond alone?
4. **Distributed prediction:** how do the networks move together? Scenarios (rival choices × open hypotheses) are formed and weighed once, and the heaviest are coupled.
5. **Unify:** one forecast, the scenarios mixed by weight.
6. Read out (M06): what moves, when, and by which path.
7. Evaluate (M11): did it come true?

## Owns

- `Network` (a bound superentity instance, a residual, or a context/watch network), `NetworkPrediction`, `ForecastScenario`.
- Group forecasts: an entity, a sector, a superentity, or a category, each averaged draw by draw.

## Interface

```python
forecast(thesis, branch, shared, slots, ctx, *, watch) -> Forecast    # pure; ThesisService (M13) writes the ledger
NetworkIsolator.isolate(shared, wm, ltm, ctx) -> list[Network]
NetworkPredictor.predict(network, inputs, model, ctx) -> NetworkPrediction
RivalDetector.groups(networks, ltm) -> list[list[str]]
NetworkCoupler.couple(networks, forced_existence, shocks, model, ctx, n_samples=None) -> PropagationResult
ScenarioWeighter.weights(scenarios, networks, wm, ltm, ctx) -> list[float]
ForecastUnifier.plan(networks, wm, ltm, ctx) -> list[ForecastScenario]
ForecastUnifier.combine(thesis, scenarios, coupled, baseline, local, networks, ctx) -> Forecast
```

## Slots

| Slot | Default | Alternatives / planned |
|---|---|---|
| `isolator` | bound_superentity (0.5·attention + 0.5·reach) | k_hop |
| `network_predictor` | mc_network | |
| `rival_detector` | pattern_and_sign | |
| `coupler` | union_graph | iterative_block (Gauss–Seidel) |
| `scenario_weighter` | support_fit_track: support × fit × track record × p | uniform; R7: leave-future-out stacking |
| `unifier` | channels_and_rivals (top 8) | weighted_mixture |

## Depends on

[M01](M01-foundation.md)–[M04](M04-repo.md) (`Branch`), [M06](M06-shared-read.md), [M07](M07-dynamics.md).

## Diagram

The seven stages are in [architecture.md](../architecture.md#inference-seven-stages). As a sequence:

![Pose a thesis, as a sequence](../diagrams/thesis-sequence.svg)

## Invariants

- **Inference never learns.** Only outcomes feed back, through track records.
- **Rivals are mixed, not averaged.** Where they disagree, the forecast is wide or has two humps.
- **The context network.** Every watched name is reached by a path or reported unreached.
- **Reproducible:** `based_on_version`, `config_hash`, `seed`.
- **A held decision is do().** A changed value is a soft intervention.

## Planned

- Scenario weights are fit in sample (S-M5) → R7.
- Config: `max_networks` is 8 in the yaml and 6 in the code.

## Done when

- Unit tests cover isolation with residual and watch networks, CRN coupling, and weights that sum to one.
- The live hash is unchanged after any number of theses.
