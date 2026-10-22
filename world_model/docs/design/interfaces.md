# Interfaces

Every boundary in the system, in one place, from the inside out:

- the **slots** algorithms plug into;
- the **service commands** the product runs;
- the **internal API** the web app calls (`/api/*` and `/ws`);
- the **outward API** other services and agents call (`/v1` and `/mcp`);
- the **context layer** agents will call;
- the **formats** that cross the system's edges: import bundles, the ledger, traces, and config.

The data these exchange is in [data-model.md](data-model.md).

<!-- toc -->
**Contents**

- [Slots: where algorithms plug in](#slots-where-algorithms-plug-in)
- [Service commands](#service-commands)
- [REST and the stream](#rest-and-the-stream)
- [Context layer (planned)](#context-layer-planned)
- [Import bundle](#import-bundle)
- [Ledger and storage](#ledger-and-storage)
- [Trace events](#trace-events)
- [Configuration](#configuration)
<!-- /toc -->

## Slots: where algorithms plug in

A slot is an ABC with a contract, registered by name; `configs/*.yaml` picks one implementation per slot (`components:`). Signatures use `ctx` for a `ProcessContext` and `txn` for a `MutationTxn`; `txn=None` is a read. `uv run axelrod contracts` prints every contract (process, cadence, inputs, outputs, reads, writes, when it runs).

| Stage | Slot | Signature | Default (alternatives) |
|---|---|---|---|
| Intake | `source` | `poll(since, until) -> list[MarketEvent]` | per config (jsonl_replay, history_replay, mock_web_scraper, synthetic_data_feed) |
| | `translator` | `translate(event, TranslationContext) -> TranslationResult` | a chain per kind (hand_drawn, template, data_feed, structured, llm, example) |
| | `entity_resolver` | `resolve(mention, constraints, candidate_ids, graph) -> list[(id, score)]` | alias_fuzzy |
| | `refiner` | `refine(event, wm, ltm, ctx) -> RefinementResult` | taxonomy |
| | `conflict_detector` *(planned)* | `detect(event, wm, ltm, ctx) -> list[Conflict]` | rules |
| Shared read | `parser` | `parse(event, wm, ltm, ctx, txn) -> ParsedEvent` | default |
| | `classifier` | `classify(taxonomy, item_id, is_new, ctx, txn, *, incorporate) -> Classification` | taxonomy_descent |
| | `attention` | `select(scores, top_k) -> dict[str, float]` | softmax_top_k |
| | `recaller` | `recall(parsed, wm, ltm, ctx) -> RecallResult` | overlap_attention (recency) |
| | `binder` | `bind(pattern, seed_entity_ids, graph, ltm) -> Binding \| None` | bfs_role_filling |
| | `inducer` | `bind(parsed, recall, wm, ltm, ctx, txn)`; `count(day, wm, ltm, ctx, txn) -> InductionResult` | co_activation |
| | `prefiller` | `prefill(parsed, recall, induction, wm, ltm, ctx) -> PrefilledModel` | analog_empirical_bayes (none) |
| | `analyzer` | `analyze(parsed, model, wm, ctx) -> Analysis` | propagation |
| | `explainer` | `explain_learning(...)`; `explain_forecast(forecast, networks, scenarios, shared, ctx) -> Explanation` | path_attribution |
| Dynamics | `propagator` | `propagate(system, shocks, n_samples, rng, *, record_contributions, exogenous) -> PropagationResult` | mc_impulse (deterministic_mean) |
| | `daily_propagator` | `predict(day, wm, ctx, txn)`; `record(day, wm, ctx, txn)` | kalman_predict |
| | `posterior_updater` | `update(current, obs, scale, process_noise_sd) -> Distribution` | link_kalman |
| Learning · WM | `folder` | `fold(parsed, analysis, wm, ctx, txn) -> FoldResult` | kalman_edge |
| | `kernel_updater` | `update(wm, ltm, ctx, txn) -> list[str]` | grid_rescale (none) |
| | `hypothesis_scorer` | `score(h, wm, ltm, ctx)`; `rescore_touched(entity_ids, wm, ltm, ctx, txn)` | forecast_sensitivity_voi |
| Learning · LTM | `generalization_updater` | `update(classifications, ltm, ctx, txn)` | path_stats |
| | `taxonomy_grower` | `maybe_split(taxonomy, gen_id, ctx, txn) -> list[str]` | shared_feature_split (none) |
| | `frontier` · `promotion_test` | `test(fold, wm, ltm, ctx, txn) -> FrontierResult` · `passes(co, recognition, cfg)` | residual_comovement · threshold |
| | `consolidator` | `run(day, ctx) -> ConsolidationReport` | daily |
| Inference · isolate | `isolator` | `isolate(shared, wm, ltm, ctx) -> list[Network]` | bound_superentity (k_hop) |
| · isolated prediction | `network_predictor` | `predict(network, inputs, model, ctx) -> NetworkPrediction` | mc_network |
| · distributed prediction | `rival_detector` · `scenario_weighter` · `coupler` | `groups(networks, ltm)` · `weights(scenarios, networks, wm, ltm, ctx)` · `couple(networks, forced_existence, shocks, model, ctx, n_samples)` | pattern_and_sign · support_fit_track (uniform) · union_graph (iterative_block) |
| · unify | `unifier` | `plan(networks, wm, ltm, ctx)`; `combine(thesis, scenarios, coupled, baseline, local, networks, ctx) -> Forecast` | channels_and_rivals (weighted_mixture) |
| · evaluate | `scorer` | `score(forecast, realized, cfg) -> dict` | omission_commission_calibration |
| Review | `review_policy` | `assess(proposal, wm) -> ReviewRequirement` | default (auto_approve_all, review_all) |
| Repo | `storage` | `append_ledger · read_ledger · save_snapshot · load_snapshot · versions · append_version · snapshot_versions · reset` | files (memory) |
| Context *(planned)* | `context_retriever` | `retrieve(query, as_of, scope, k) -> list[Fact]` | find_plus_neighborhood |

**Rules:**
- A slot writes only the collections its contract's `writes` lists.
- A slot never receives the engine.
- A slot returns proposals; it never creates them.

## Service commands

The product's commands ([M13](modules/M13-services.md)). Each one runs under the engine's lock, returns a typed result, and emits trace events.

| Service | Commands |
|---|---|
| Review | `propose`, `stage(pid, keep, confidences, ripple) -> StagedChange`, `approve(pid, by, note, keep, confidence, op_confidence, ripple)`, `reject`, `defer`, `edit`, `set_review_policy` |
| Update | `request_update(until, sources)`, `continue`, `cancel`, `import_items(bundle, ids)` |
| Thesis | `pose(question or thesis, version, watch) -> Forecast`, `pin`, `record_decision`, `resolve_decision`, `add_hypothesis`, `mark_hypothesis` |
| Structure | `propose_group`, `propose_dissolve`, `propose_retire`, `submit_graph_update`, `add_from_knowledge` |

## REST and the stream

The FastAPI app ([M14](modules/M14-interfaces.md)) serves `/api/*`, `/ws`, `/login`, and the static front end: the
demo's internal API, behind the sign-in. Other services and agents use the outward API instead, REST under
`/v1/world-models/{id}` and MCP at `/mcp`. Its design is [api.md](api.md), its contract
[../api/openapi.yaml](../api/openapi.yaml), and its reference [../api/README.md](../api/README.md).

| Group | Routes (abridged) |
|---|---|
| State | `GET /api/state`, `/api/versions`, `/api/entities/{id}`, `/api/interactions/{id}`, `/api/superentities/{id}`, `/api/taxonomies/{kind}` |
| Learn | `POST /api/updates`, `/api/import`, `/api/manual`, `/api/graph-update-events`; `GET /api/proposals`, `/api/proposals/{id}/stage`; `POST /api/proposals/{id}/approve · reject · defer · edit` |
| Predict | `POST /api/theses`, `/api/theses/{id}/pose`; `GET /api/forecasts/{id}`, `/api/forecasts/{id}/brief`, `/api/paths/forecast/{id}`; `POST /api/decisions`, `/api/decisions/{id}/resolve` |
| Memory and checks | `GET /api/memory`, `/api/checks`, `/api/find`, `/api/hypotheses`, `/api/frontier` |
| History | `GET /api/repo/log`, `/api/repo/commits/{v}`, `/api/repo/diff` |
| Demos | `GET /api/scenarios`, `/api/examples`; `POST /api/examples/{id}`, `/api/library/{event_id}`, `/api/sim/load` |
| Docs | `GET /api/flows`, `/api/flows/{id}/svg`, `/api/contracts` |
| Health | `GET /api/health` (open, for the readiness probe) |

**`/ws`:**
1. The client sends `{"type": "hello", "since_seq": n}`.
2. The server replays the trace since `n`, then streams `{"type": "trace", "event": …}` and `{"type": "status", …}`. Ping and pong keep it alive.

The front end renders views and applies trace payloads; it never computes model results.

## Context layer (planned)

Six verbs over MCP and REST ([M15](modules/M15-context-layer.md)). Reads are free; writes are only ever proposals.
Today agents reach the model through the outward API's v1 routes and MCP tools ([../api/README.md](../api/README.md)),
which already keep this rule; the verbs below are the planned layer on top.

| Verb | Returns |
|---|---|
| `recall(query, as_of?, scope?, k?)` | Facts with version, valid time, evidence, trust tier |
| `ask(question or thesis, watch?, version?)` | A forecast by order and path, and its brief |
| `trace(item_id, version?)` | Its lineage: change sets → proposal → review → evidence → source |
| `propose(text or bundle item, quotes, confidence)` | A proposal id, pending review |
| `feedback(forecast_id, outcome or rating)` | Nothing; the outcome is scored at the horizon |
| `status(proposal_id)` | Pending, approved, or rejected |

## Import bundle

`axelrod.import/v1` is the seam to any upstream research agent. Its fields, the example, and the rules are in
[the contract](../../../ingestion/docs/contract.md#the-import-bundle), because ingestion owns the format. The world model's side of it is
`intake/structured.py`: every item becomes a market event on its own date, its signals become a proposed graph
update, and a person reviews it like any article. A signal whose ends are not in the graph is dropped and reported.

## Ledger and storage

| File (under `var/<session>/`) | Holds |
|---|---|
| `ledger.jsonl` | Append-only `LedgerEntry` lines: `seq`, `kind`, `recorded_at`, `occurred_at`, `state_version`, `payload` |
| `versions.jsonl` | `StateVersion` lines: `version`, `seq`, `state_hash`, `cause`, `process`, `memory` |
| `snapshots/vNNNNNN.json.gz` | The whole state at a version, canonical JSON |
| `traces/<run_id>.jsonl` | The trace of one run |

To restore a version: load the newest snapshot at or before it, replay the change sets, and check the hash.

## Trace events

`TraceEvent(seq, run_id, phase, kind, sim_time, state_version, refs, payload, scope)`.

- **`scope`** ties an event to a market event, a thesis, or a day.
- **`refs`** name the objects to highlight.
- **The kinds by stage** are listed on each flowchart node (`flows/`). Examples: `thesis.posed`, `isolate.networks`, `predict.network`, `unify.scenarios`, `couple.done`, `forecast.ready`, `review.queued`, `state.version`.

## Configuration

| File | Sets |
|---|---|
| `world_model/configs/default.yaml` | Every section: seed, time, thresholds, propagation, learning, frontier, abduction, refinement, hypotheses, evaluation, review, update, translators, `components:` (one implementation per slot), storage |
| `world_model/configs/<demo>.yaml` | A demo's overrides |
| `world_model/examples/worlds/<world>/` | Construction: entities, interactions, templates, the series map |
| `world_model/examples/scenarios/<scenario>/` | A script, seeds, theses, a watchlist, decisions, market events |
