# M02 · Ports

| | |
|---|---|
| Layer | 0 · Foundation |
| Status | **Merge**: the ABCs exist but live in eight places |
| Code today | `engine/interfaces.py` (seven slots), `engine/contracts.py`, and ABCs inside `inference/task.py`, `inference/unify.py`, `inference/voi.py`, `memory/frontier.py`, `model/distributions.py`, `repo/review.py`, `repo/snapshots.py`, `intake/*.py`, `learning/*.py`, `dynamics/*.py`, `shared/recognize.py`, `shared/explain.py` |
| Target | `axelrod_wm/ports/`, one file per engine module: `intake.py`, `shared.py`, `dynamics.py`, `learning.py`, `inference.py`, `evaluation.py`, `repo.py`, plus `contracts.py` |

## Purpose

The one place that says what each swappable component must do. A **slot** is an ABC, its input and output record types, and a **contract** (process, cadence, inputs, outputs, reads, writes, when it runs). Engines (layer 3) implement ports; the runtime (layer 4) wires them; nothing else needs the implementations.

## Owns

- Every slot ABC (list below), bound to its slot with `registry("slot", ABC)`.
- The record types that cross a slot boundary: `ParsedEvent`, `Classification`, `RecallResult`, `InductionResult`, `PrefilledModel`, `Analysis`, `SharedResult`, `FoldResult`, `FrontierResult`, `ConsolidationReport`, `Network`, `NetworkInputs`, `NetworkPrediction`, `ForecastScenario`, `TranslationContext`, `TranslationResult`, `RefinementResult`, `ReviewRequirement`, `PropagationSystem`, `ShockInput`, `PropagationResult`.
- `Contract` and `CONTRACTS[slot]`.

## Interface: the slots

The default implementation of each slot is in `configs/default.yaml` (`components:`); "Alternatives" are the other registered names.

| Slot | ABC and signature | Process · cadence | Default | Alternatives |
|---|---|---|---|---|
| `source` | `MarketEventSource.poll(since, until) -> list[MarketEvent]` | intake · per run | config `update.sources` | jsonl_replay, history_replay, mock_web_scraper, synthetic_data_feed |
| `translator` | `MarketEventTranslator.translate(event, TranslationContext) -> TranslationResult` | intake · per market event | chain per kind (`translators:`) | hand_drawn, template, data_feed, structured, llm, example |
| `entity_resolver` | `EntityResolver.resolve(mention, constraints, candidate_ids, graph) -> list[(id, score)]` | intake · per fuzzy end | alias_fuzzy | — |
| `refiner` | `Refiner.refine(event, wm, ltm, ctx) -> RefinementResult` | intake · per event | taxonomy | — |
| `review_policy` | `ReviewPolicy.assess(proposal, wm) -> ReviewRequirement` | review · per proposal | default | auto_approve_all, review_all |
| `parser` | `EventParser.parse(event, wm, ltm, ctx, txn) -> ParsedEvent` | shared · per event or thesis | default | — |
| `classifier` | `Classifier.classify(taxonomy, item_id, is_new, ctx, txn, *, incorporate) -> Classification` | shared · per new item | taxonomy_descent | — |
| `taxonomy_grower` | `TaxonomyGrower.maybe_split(taxonomy, gen_id, ctx, txn) -> list[str]` | LTM · per kind touched | shared_feature_split | none |
| `attention` | `AttentionPolicy.select(scores, top_k) -> dict[str, float]` | shared · per recall | softmax_top_k | — |
| `recaller` | `Recaller.recall(parsed, wm, ltm, ctx) -> RecallResult` | shared · per event or thesis | overlap_attention | recency |
| `binder` | `PatternBinder.bind(pattern, seed_entity_ids, graph, ltm) -> Binding \| None` | shared · per recalled pattern | bfs_role_filling | — |
| `inducer` | `SuperentityInducer.bind(parsed, recall, wm, ltm, ctx, txn) -> InductionResult`; `.count(day, wm, ltm, ctx, txn) -> InductionResult` | shared (bind) · LTM daily (count) | co_activation | — |
| `prefiller` | `Prefiller.prefill(parsed, recall, induction, wm, ltm, ctx) -> PrefilledModel` | shared | analog_empirical_bayes | none |
| `analyzer` | `Analyzer.analyze(parsed, model, wm, ctx) -> Analysis` | shared | propagation | — |
| `propagator` | `Propagator.propagate(system, shocks, n_samples, rng, *, record_contributions, exogenous) -> PropagationResult` | dynamics · per analysis | mc_impulse | deterministic_mean |
| `daily_propagator` | `DailyPropagator.predict(day, wm, ctx, txn)`; `.record(day, wm, ctx, txn) -> dict` | WM · twice a day | kalman_predict | — |
| `posterior_updater` | `PosteriorUpdater.update(current, obs, scale, process_noise_sd) -> Distribution`; `.shift(...)` | WM · per observation | link_kalman | — |
| `folder` | `Folder.fold(parsed, analysis, wm, ctx, txn) -> FoldResult` | WM · per vetted event | kalman_edge | — |
| `kernel_updater` | `KernelUpdater.update(wm, ltm, ctx, txn) -> list[str]` | WM · every few days | grid_rescale | none |
| `hypothesis_scorer` | `HypothesisScorer.score(h, wm, ltm, ctx) -> float`; `.rescore_touched(entity_ids, wm, ltm, ctx, txn) -> list[str]` | WM · at day close | forecast_sensitivity_voi | — |
| `generalization_updater` | `GeneralizationUpdater.update(classifications, ltm, ctx, txn)` | LTM · per vetted event | path_stats | — |
| `frontier` | `FrontierTester.test(fold, wm, ltm, ctx, txn) -> FrontierResult` | LTM · per live event | residual_comovement | — |
| `promotion_test` | `PromotionTest.passes(co, recognition, cfg) -> bool` | LTM · per frontier check | threshold | — |
| `consolidator` | `Consolidator.run(day, ctx) -> ConsolidationReport` | LTM · once a day | daily | — |
| `explainer` | `Explainer.explain_learning(shared, fold, frontier, ctx)`; `.explain_forecast(forecast, networks, scenarios, shared, ctx) -> Explanation` | shared · per event and forecast | path_attribution | — |
| `isolator` | `NetworkIsolator.isolate(shared, wm, ltm, ctx) -> list[Network]` | inference · per thesis | bound_superentity | k_hop |
| `network_predictor` | `NetworkPredictor.predict(network, inputs, model, ctx) -> NetworkPrediction` | inference · per network | mc_network | — |
| `rival_detector` | `RivalDetector.groups(networks, ltm) -> list[list[str]]` | inference | pattern_and_sign | — |
| `coupler` | `NetworkCoupler.couple(networks, forced_existence, shocks, model, ctx, n_samples) -> PropagationResult` | inference · per scenario | union_graph | iterative_block |
| `scenario_weighter` | `ScenarioWeighter.weights(scenarios, networks, wm, ltm, ctx) -> list[float]` | inference | support_fit_track | uniform |
| `unifier` | `ForecastUnifier.plan(networks, wm, ltm, ctx) -> list[ForecastScenario]`; `.combine(thesis, scenarios, coupled, baseline, local, networks, ctx) -> Forecast` | inference | channels_and_rivals | weighted_mixture |
| `scorer` | `Scorer.score(forecast, realized, cfg) -> dict` | evaluation | omission_commission_calibration | — |
| `storage` | `StorageBackend.append_ledger · read_ledger · save_snapshot · load_snapshot · versions · append_version · snapshot_versions · reset` | repo · per commit | files | memory |

**New slots** proposed by this design (see each module):

| Slot | Module | Why |
|---|---|---|
| `conflict_detector` | [M06](M06-intake.md) | Flag an operation that contradicts a committed fact (value, sign, timing, existence), with a severity, for the review. Borrowed from Semantica's conflict types. |
| `provenance_exporter` | [M05](M05-repo.md) | Export the ledger as PROV-O (entity, activity, agent) for audit |
| `context_retriever` | [M16](M16-context-layer.md) | The context layer's recall: semantic plus graph neighborhood, at a version |

## Contracts

`CONTRACTS[slot]` gives `process`, `cadence`, `inputs`, `outputs`, `reads`, `writes`, `mandatory`, `condition`, `flow_nodes`, and `used_by`. `uv run axelrod contracts` prints them all as a table. The `writes` column is the authority on which state collections a slot may touch through its `txn`.

## Depends on / used by

- Depends on: [M01](M01-core.md), [M03](M03-model.md), [M04](M04-memory.md) (types only).
- Used by: every engine (they implement ports) and [M13](M13-runtime.md) (which wires them).

## Invariants

- **One home per ABC.** Every slot ABC is defined in `ports/`, nowhere else.
- **Registry, contracts, and flowcharts agree.** Every registered slot has a contract, and every flowchart node's `component` names a slot. This test exists today (`tests/unit/engine`).
- **Writes are declared.** A slot that writes outside its contract's `writes` fails a test, which records the collections each `txn` touches.

## Known issues and planned

- Contracts are documentation strings, not typed. Planned: generate the signature column from the ABCs so the two cannot drift.
- `posterior_updater` is registered but never called (ml-stack §12). Either wire it into the folder or remove the slot.
- Translators and sources are chosen outside `components:` (by kind, and by `update.sources`). Keep that, and document it in the contract.

## Done when

- `tests/unit/ports/test_layers.py` builds the import graph with `ast` and fails on any upward import, or on any cycle at module scope.
- The existing registry/contract/flowchart consistency test passes.
- Each slot has a conformance test (the same inputs to every registered implementation give outputs of the right type and shape, and write only what the contract allows). `tests/integration` "every slot alternative" grows into this.
