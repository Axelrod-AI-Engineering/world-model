# M01 · Foundation (core and ports)

**Layer** 0 · **Package** `core/`, `ports/` · **Status** split out: the pieces exist but are scattered.
**Code today:**
- core: `model/ids.py`, `model/serialization.py`, `engine/rng.py`, `engine/registry.py`, `trace.py`;
- ports: `engine/interfaces.py` (seven slots), `engine/contracts.py`, and ABCs in about fifteen implementation files.

## Purpose

What every module needs, and what needs nothing in return: ids, canonical bytes, reproducible randomness, the trace bus, the slot registry, and **every slot's ABC and contract in one place**. Making this layer a leaf removes most of today's import cycles.

## Owns

- **core:**
  - `IdFactory`, `entity_of`;
  - **new** `identity_key(kind, **fields)`, a uuid5 over declared identity fields such as a ticker or LEI (from Cognee);
  - `canonical_json`, `sha256_text`, `substream(seed, *names)`;
  - `Tracer` with `NullTracer`, `RecordingTracer`, `BroadcastTracer`;
  - `registry(slot, ABC)` and `register(slot, name)`.
- **ports:** each slot's ABC, the records that cross slot boundaries (`ParsedEvent`, `SharedResult`, `FoldResult`, `Network`, `ForecastScenario`, `TranslationResult`, `RefinementResult`, `PropagationResult`, …), and `CONTRACTS[slot]` (process, cadence, inputs, outputs, reads, writes, condition).

## Interface: the slots

The defaults are set in `configs/default.yaml` (`components:`). `uv run axelrod contracts` prints every contract.

| Module | Slot: default (alternatives) |
|---|---|
| [M05 intake](M05-intake.md) | `source` (jsonl_replay, history_replay, mock_web_scraper, synthetic_data_feed) · `translator`: chain per kind (hand_drawn, template, data_feed, structured, llm, example) · `entity_resolver`: alias_fuzzy · `refiner`: taxonomy · **new** `conflict_detector`: rules |
| [M06 shared read](M06-shared-read.md) | `parser`: default · `classifier`: taxonomy_descent · `attention`: softmax_top_k · `recaller`: overlap_attention (recency) · `binder`: bfs_role_filling · `inducer`: co_activation · `prefiller`: analog_empirical_bayes (none) · `analyzer`: propagation · `explainer`: path_attribution |
| [M07 dynamics](M07-dynamics.md) | `propagator`: mc_impulse (deterministic_mean) · `daily_propagator`: kalman_predict · `posterior_updater`: link_kalman |
| [M08 learning · WM](M08-learning-working.md) | `folder`: kalman_edge · `kernel_updater`: grid_rescale (none) · `hypothesis_scorer`: forecast_sensitivity_voi |
| [M09 learning · LTM](M09-learning-long-term.md) | `generalization_updater`: path_stats · `taxonomy_grower`: shared_feature_split (none) · `frontier`: residual_comovement · `promotion_test`: threshold · `consolidator`: daily |
| [M10 inference](M10-inference.md) | `isolator`: bound_superentity (k_hop) · `network_predictor`: mc_network · `rival_detector`: pattern_and_sign · `coupler`: union_graph (iterative_block) · `scenario_weighter`: support_fit_track (uniform) · `unifier`: channels_and_rivals (weighted_mixture) |
| [M11 evaluation](M11-evaluation.md) | `scorer`: omission_commission_calibration |
| [M04 repo](M04-repo.md) | `storage`: files (memory) · **new** `provenance_exporter`: prov_json |
| [M13 services](M13-services.md) | `review_policy`: default (auto_approve_all, review_all) |
| [M15 context layer](M15-context-layer.md) | **new** `context_retriever`: find_plus_neighborhood |

Each module's spec gives its ABCs' signatures.

## Depends on

Nothing inside `axelrod_wm`, except that `ports/` uses [M02](M02-model.md)'s and [M03](M03-memory.md)'s types.

## Invariants

- `core/` is a leaf.
- Every slot ABC is defined in `ports/` and nowhere else.
- **Registry, contracts, and flowcharts agree.** Every slot has a contract, and every flowchart node names a slot. A test for this exists today.
- **Writes are declared.** A slot writes only the collections in its contract's `writes`.
- **Explicit randomness.** Every draw comes from a named substream, so the same seed and names give the same draws.

## Planned

- Generate the contracts' signature column from the ABCs, so the two cannot drift.
- `posterior_updater` is registered but never called (ml-stack §12). Wire it into the folder, or drop it.

## Done when

- `tests/unit/ports/test_layers.py` builds the import graph with `ast` and fails on an upward import or a cycle.
- Each slot has a conformance test: every registered implementation takes the same inputs, returns outputs of the right type, and writes only what its contract allows.
