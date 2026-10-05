# Architecture

A short map from the code to [PLAN.md](../PLAN.md). Section numbers (§) refer to the plan.

## The flow in one paragraph

A **market event** (news, data, a filing) arrives. A **translator** turns it into a `GraphUpdateEvent` made of ops. The **refiner** narrows each fuzzy end, from a taxonomy node to an entity to a concrete subentity. A **review policy** decides whether a person must approve it. On approval, the **engine** runs the shared process: parse, classify, recall, prefill, and analyze. Then the **learning task** folds observations into posteriors, updates the frontier, and counts superentity support. Every write goes through the **`GraphMutator`** as a `ChangeSet` in the ledger. A **thesis** (a hypothetical event) runs the same shared process. Then the **performance task** isolates networks, predicts within them, couples them, and unifies rival structures into weighted scenarios. Every step emits **trace events**, and the browser animates them.

## Packages

| Package / module | What it holds | Plan |
|---|---|---|
| `core/ids.py` | id prefixes and `IdFactory` | §6.1 |
| `core/categories.py` | category tags (SD, MF, …) | §6.2 |
| `core/distributions.py` | the distribution families, link moments, `DistSummary` | §6.3 |
| `core/temporal.py` | `KernelSpec` (delay, lag, duration), step responses, `TimeState` | §6.4 |
| `core/evidence.py` | provenance and `Evidence` | §6.5 |
| `core/entity.py` | `Entity`, `Subentity`, entity memory and decision profiles | §6.6 |
| `core/interaction.py` | `Interaction`, `EdgeDynamics`, parameters, significance | §6.7 |
| `core/superentity.py` | patterns, instances, and super-interactions | §6.8 |
| `core/taxonomy.py` | object and interaction taxonomies, signatures | §6.9 |
| `core/hypothesis.py` | hypotheses and their decaying value | §6.10 |
| `core/graph.py` | `CausalGraph`: lookups, entity links, hop distances | §6.11 |
| `core/serialization.py` | canonical JSON and hashing | §9 |
| `memory/working.py` | `WorkingMemory`, `DeviationHistory`, the forecast layer | §6.12 |
| `memory/long_term.py`, `episodes.py`, `patterns.py`, `explanations.py` | long-term memory stores; `patterns.py` also has `SuperInteractionBuilder` | §6.13, §6.8 |
| `memory/frontier.py` | the correlation frontier (`CoMovement`) | §8.7 |
| `memory/snapshots.py` | storage backends, snapshots, versions, the state hash | §9 |
| `events/market.py`, `graph_update.py`, `thesis.py` | market events, graph update events and ops, theses | §7.1–7.3 |
| `events/ledger.py` | the append-only event ledger | §9 |
| `ingest/translators.py` | `hand_drawn`, `data_feed`, `template`, and the `llm` stub | §7.4 |
| `ingest/resolver.py`, `refiner.py` | entity resolution and fuzzy-to-real refinement | §7.5 |
| `ingest/pipeline.py`, `sources.py` | the ingestion pipeline and event sources | §7.8 |
| `control/review.py` | proposals and review policies | §7.6 |
| `control/mutator.py` | `GraphMutator`, transactions, and change sets (the one writer) | §7.7 |
| `control/controller.py` | `WorldModelController`: the control plane the API and CLI call | §7.6, §8.15 |
| `control/decisions.py` | decision records, traces, and outcomes | §8.15 |
| `engine/registry.py`, `config.py`, `context.py`, `interfaces.py`, `engine.py` | the slot registry, configuration, `ProcessContext`, the ABCs, and `build_engine` | §8.1–8.3, §8.16 |
| `engine/shared.py`, `parse.py`, `classify.py`, `recall.py`, `prefill.py`, `analyze.py` | the shared process | §8.4 |
| `engine/propagation.py`, `regressors.py` | Monte Carlo impulse propagation and kernel regressors | §8.5 |
| `engine/learning.py`, `kernel_update.py`, `frontier_test.py`, `abduction.py` | the learning task: fold, kernels, frontier, superentity abduction | §8.6–8.8 |
| `engine/performance/` | `isolate.py`, `predict.py`, `couple.py`, `unify.py`, `task.py`, `records.py` | §8.9 |
| `engine/explain.py`, `explain_records.py` | path attribution and explanations | §8.10 |
| `engine/voi.py` | hypothesis scoring and value of information | §8.11 |
| `engine/consolidate.py` | daily consolidation: episodes, supports, level noise | §8.12 |
| `engine/initialize.py`, `defaults.py` | construction, seeds, and history replay | §8.13, §14 |
| `evaluation/` | backtests, metrics (omission, commission, coverage, CRPS), reliability | §8.14 |
| `sim/world.py` | the synthetic world: true parameters, AR noise, decision rules, releases | §11.1, §14.9 |
| `sim/scenario.py`, `runner.py` | scenario scripts and the step runner (with the init snapshot cache) | §11.2–11.3 |
| `sim/checklist.py` | the scenario checklist recorder | §15.3 |
| `trace.py` | trace events, recording and broadcast tracers | §10 |
| `api/app.py`, `routes.py`, `ws.py`, `views.py` | the FastAPI app, REST endpoints, the `/ws` stream, view models | §12 |
| `cli.py` | `axelrod init / run-scenario / demo / thesis / evaluate / export-trace` | §11.3 |

## Front end (`web/`)

| File | What it does | Plan |
|---|---|---|
| `index.html`, `css/tokens.css`, `css/app.css` | the layout and the palette | §13.1, §13.2 |
| `js/main.js` | boot, toolbar, keyboard shortcuts, modal and toast | §13.1, §13.8 |
| `js/api.js` | the REST client and the `/ws` stream with `hello`/replay | §12 |
| `js/store.js` | the client model: the `GraphView` plus incremental trace application | §13.7 |
| `js/graph/renderer.js` | `GraphRenderer` and its SVG implementation: layers, semantic zoom, overlays | §13.3 |
| `js/graph/zoom.js`, `forces.js`, `layouts.js`, `hulls.js` | zoom levels, gravity forces, the Figure 1 and gravity layouts, hull shapes | §13.3 |
| `js/graph/fuzzy.js`, `draw-tool.js`, `legend.js` | fuzzy ribbons, the draw tool, the legend | §13.4, §13.5, §13.2 |
| `js/panels/*.js` | inbox, review, inspector, thesis, forecast, hypotheses, decisions, memory, pipeline, timeline, caption | §13.6 |
| `js/animator/player.js`, `effects.js` | the trace player (live and replay) and the per-kind animations | §13.7 |
| `js/charts/fan.js`, `density.js`, `sparkline.js` | fan charts, distribution glyphs, sparklines | §13.6 |

The front end never computes model results. It renders the server's views and applies trace payloads.

## Invariants worth knowing

- **One writer.** Every change to working or long-term memory goes through `GraphMutator` transactions. A transaction becomes a `ChangeSet` in the ledger and bumps the state version. Forecast-layer-only change sets don't bump the version (§7.7, §9).
- **Explicit randomness.** Every random draw comes from the `ProcessContext` rng, split into named substreams, so a run is reproducible from its seed (§9).
- **Restore.** The init snapshot plus the ledger's change sets reproduce the live state hash (§15.3 item 15).
- **Slots.** Each component is an ABC registered by name, and `configs/default.yaml` picks one per slot. `tests/integration/test_api.py` (with `--runslow`) runs the scenario to the end with each shipped alternative (§8.16, §15.2).
- **Decisions.** Where the plan was silent, the simplest option was chosen and marked with a `# DECISION:` comment. `grep -rn DECISION src configs data` lists them.

## Tests

| Directory | Covers | Plan |
|---|---|---|
| `tests/unit/` | distributions, kernels, propagation, fold, kernel updater, taxonomy, ops, refiner and review, frontier, abduction, isolation, unify, couple, explanation, VOI, ledger and snapshots | §15.1 |
| `tests/integration/` | the API and `/ws` through `TestClient`; checklist items 4 and 5; every slot alternative (slow) | §15.2 |
| `tests/scenario/` | initialization, same-seed determinism, posing twice, restore; the full checklist (slow) | §15.1, §15.3 |
| `tests/ui/` | an optional Playwright smoke test (slow; skipped without Playwright) | §15.4 |
