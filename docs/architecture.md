# Architecture

A short map from the code to [PLAN.md](../PLAN.md) (revision 2). Section numbers (§) refer to the plan.

## The flow in one paragraph

The model keeps a **daily state**. An **update run** (§7.8) collects market events (news, data, filings, and items the user types in) from its sources up to a date, drops duplicates, and walks the days in order. Each day it **predicts** (daily propagation carries yesterday's moves through the graph's channels, so unobserved subentities move too), then takes that day's events in publication order. A **translator** turns each event into a `GraphUpdateEvent` made of ops; the **refiner** narrows each fuzzy end from a taxonomy node to an entity to a concrete subentity; a **review policy** decides whether a person must approve it, and the run pauses on that day until they do. Approved events go through the **shared process** (parse, classify, recall, prefill, analyze) and the **learning task** folds them into posteriors. At the end of each day the model **records** its state and **consolidates**: episodes, superentity support (including composites, superentities made of superentities), the correlation frontier, kernels, and entity memories. Every write goes through the **`GraphMutator`** as a `ChangeSet` in the ledger. A **thesis** (a hypothetical event) runs the same shared process; then the **performance task** isolates networks, predicts within them, couples them, and unifies rival structures into weighted scenarios. Every step emits **trace events**, and the browser animates them.

## Packages

| Package / module | What it holds | Plan |
|---|---|---|
| `core/ids.py`, `categories.py` | id prefixes and `IdFactory`; the eight category tags (SD, MF, SC, DI, DF, EN, EX, SH) | §6.1, §6.2 |
| `core/distributions.py` | the distribution families, link moments, `DistSummary` | §6.3 |
| `core/temporal.py` | `KernelSpec` (delay, lag, duration), step responses, `TimeState` | §6.4 |
| `core/evidence.py` | provenance and `Evidence` | §6.5 |
| `core/entity.py` | `Entity` (with its plain description) and `Subentity` | §6.6 |
| `core/interaction.py` | `Interaction`, `EdgeDynamics`, parameters, significance | §6.7 |
| `core/superentity.py` | patterns (with `sub_pattern_ids` for composites), instances (with `child_instance_ids`), super-interactions | §6.8 |
| `core/taxonomy.py`, `hypothesis.py`, `graph.py` | taxonomies and signatures; hypotheses and their decaying value; `CausalGraph` | §6.9–6.11 |
| `core/serialization.py` | canonical JSON and hashing | §9 |
| `memory/working.py` | `WorkingMemory`: the graph, `DeviationHistory` (one point per subentity per day), channel states, the forecast layer | §6.12 |
| `memory/long_term.py` | `LongTermMemory`: object and interaction generalizations, prior states (episodes, explanations), `SuperInteractionBuilder` | §6.13, §6.8 |
| `memory/entity_memory.py`, `frontier.py` | entity memories (weekly entries, level noise, decision profiles); the correlation frontier (`CoMovement`) | §6.13, §8.7 |
| `memory/snapshots.py` | storage backends, snapshots, versions, the sharded state hash | §9 |
| `events/market.py`, `graph_update.py`, `thesis.py`, `ledger.py` | market events and channels, graph update events and ops, theses, the append-only ledger | §7.1–7.3, §9 |
| `ingest/sources.py`, `scrapers.py` | event sources (history replay, JSONL replay) and the mock web scraper with dedup keys | §7.8 |
| `ingest/translators.py`, `resolver.py`, `refiner.py`, `pipeline.py` | translators (data feed, template, fixtures, hand-drawn); entity resolution; fuzzy-to-real refinement; ingestion | §7.4, §7.5 |
| `control/updates.py` | `UpdateCycle`: collect, model edits, the day loop (predict, late queue, walk, record, consolidate), pause and resume, reports | §7.8 |
| `control/review.py`, `mutator.py` | proposals and review policies; `GraphMutator`, transactions, change sets (the one writer) | §7.6, §7.7 |
| `control/controller.py`, `decisions.py` | `WorldModelController`, the control plane the API and CLI call; decision records and outcomes | §7.6, §8.15 |
| `engine/registry.py`, `config.py`, `context.py`, `interfaces.py`, `engine.py`, `rng.py` | the slot registry, configuration, `ProcessContext`, the ABCs, `build_engine`, named random substreams | §8.1–8.3, §8.16 |
| `engine/shared.py`, `parse.py`, `classify.py`, `recall.py`, `prefill.py`, `analyze.py` | the shared process | §8.4 |
| `engine/kernels.py`, `propagation.py`, `regressors.py` | the daily kernel recursion; Monte Carlo impulse propagation; kernel regressors | §6.4, §8.5 |
| `engine/daily.py` | the daily model: predict, channel states, record, activity | §8.6.1 |
| `engine/learning.py`, `kernel_update.py`, `frontier_test.py`, `abduction.py` | the fold, kernel learning, the frontier test, superentity abduction and composition | §8.6–8.8 |
| `engine/performance/` | `isolate.py`, `predict.py`, `couple.py`, `unify.py`, `task.py`, `records.py`; `groups.py` forecasts coarser targets (an entity, superentity, sector, or category) as the average effect of its members, sample by sample from the same scenario mixture | §8.9 |
| `engine/explain.py`, `explain_records.py`, `voi.py` | path attribution and explanations; hypothesis scoring and value of information | §8.10, §8.11 |
| `engine/consolidate.py` | daily consolidation: episodes, supports, kernels, entity memories, pruning | §8.12 |
| `engine/initialize.py`, `defaults.py` | construction, seeds, and the history replay as one long update run | §8.13, §14 |
| `evaluation/` | backtests and metrics (omission, commission, coverage, CRPS) | §8.14 |
| `sim/world.py` | the synthetic world: true parameters, daily dynamics, decision rules, releases | §11.1, §14.9 |
| `sim/scenario.py`, `runner.py`, `checklist.py` | scenario scripts, the step runner (with the init snapshot cache and sessions), the checklist recorder | §11.2–11.3, §15.3 |
| `trace.py` | trace events, recording and broadcast tracers; each event carries a scope (a market event id, a thesis id, or `day:<date>`) so one piece of news or one question can be replayed alone | §10 |
| `api/app.py`, `routes.py`, `ws.py`, `views.py` | the FastAPI app (update runs driven one day per lock acquisition), REST endpoints, `/ws`, view models | §12 |
| `cli.py` | `axelrod init / update / run-scenario / demo / thesis / evaluate / export-trace` | §11.3 |

## Front end (`web/`)

The first screen is the graph, a caption, and one row of controls; panels open on demand. Detail is chosen per node, never by zoom.

| File | What it does | Plan |
|---|---|---|
| `index.html`, `css/tokens.css`, `css/app.css` | the layout, the architecture page's palette, the faint canvas grid | §13.1, §13.2 |
| `js/main.js` | boot, side panels, tooltips, right-click menus, the settings menu, keyboard shortcuts (with undo and redo, and the `?` sheet) | §13.1, §13.8 |
| `js/api.js`, `js/store.js` | the REST client and `/ws`; the client model (GraphView plus incremental trace application, update runs) | §12, §13.7 |
| `js/graph/model.js` | what is on screen: open and closed superentities, open entities, where each edge attaches, edge aggregation | §13.3 |
| `js/graph/renderer.js` | `GraphRenderer` and its SVG implementation: pills that open into subentity rows (each with a small distribution), outlines and cards, edges, overlays; shared ownership (a stripe per owner, lenses where outlines overlap, member chips on closed cards and tethers to where shared members are drawn); labels placed clear of all other text; animations (glows, ripples, comets, flows); the undo history; the walkthrough's and the guide's overlays | §13.3 |
| `js/graph/hulls.js` | grouping (rivals share an outline, composites nest) and outlines traced as one level of a field (d3.contours) | §13.3 |
| `js/graph/layouts.js`, `forces.js`, `zoom.js` | the Figure 1 grid (reflowed as entities open) and the gravity layout; geometric zoom and the grid pattern | §13.3 |
| `js/graph/menu.js`, `legend.js` | the right-click menu; the key (the eight categories and the symbols) | §13.2 |
| `js/graph/fuzzy.js`, `draw-tool.js` | fuzzy ribbons; the draw tool (it can attach a drawn edge to an update) | §13.4, §13.5 |
| `js/panels/update.js` | the Update dialog, the update strip, the update report | §13.6 |
| `js/panels/*.js` | inbox (by update and day), review, inspector, thesis, forecast, hypotheses, decisions, memory, pipeline, timeline, caption | §13.6 |
| `js/animator/guide.js` | the guide: a raccoon that hops to what the model is working on and narrates a forecast (or a piece of news) the first time, paced by the trace; it can be switched off | addition |
| `js/panels/briefs.js`, `chat.js` | forecast briefs in the left sidebar (`GET /api/forecasts/{id}/brief`, built in `api/brief.py`), and the chat mock-up opened from selected brief text | addition |
| `js/panels/admin.js` | the Admin window: story, map (categories, superentities by kind, actors, symbols), view, settings; minimizable, draggable, and able to pop out into its own window | addition |
| `js/panels/methods.js`, `web/methods.html` | the technical briefing on the proposed implementation and ML stack | addition |
| `js/panels/walkthrough.js` | turns one scope's trace events into steps (learning: news → translate → fuzzy to real → review → parse → classify → recall → prefill → expect → fold → generalize; prediction: question → recall → isolate → predict per network → couple → unify → forecast → explain); each step frames and highlights what it touched | addition |
| `js/animator/player.js`, `effects.js` | the trace player (live and replay, faster when behind) and the per-kind animations | §13.7 |
| `js/charts/fan.js`, `density.js`, `sparkline.js` | fan charts, distribution glyphs, sparklines | §13.6 |

The front end never computes model results. It renders the server's views and applies trace payloads.

## Invariants worth knowing

- **One writer.** Every change to working or long-term memory goes through `GraphMutator` transactions. A transaction becomes a `ChangeSet` in the ledger and bumps the state version. Forecast-layer-only change sets don't bump the version (§7.7, §9).
- **World events and model edits.** News and data enter only through update runs and are folded on their own day; edits drawn or typed by hand change structure, never values (§7.8).
- **Explicit randomness.** Every random draw comes from the `ProcessContext` rng, split into named substreams, so a run is reproducible from its seed (§9). The synthetic world keys its draws too (one stream per interaction's true effect and per series' noise), so adding an actor never re-deals the others.
- **Restore.** The init snapshot plus the ledger's change sets reproduce the live state hash (§15.3 item 15).
- **Slots.** Each component is an ABC registered by name, and `configs/default.yaml` picks one per slot. `tests/integration/test_api.py` (with `--runslow`) runs the scenario to the end with each shipped alternative (§8.16, §15.2).
- **Decisions.** Where the plan was silent, the simplest option was chosen and marked with a `# DECISION:` comment. `grep -rn DECISION src configs data web` lists them.
- **Low friction without clutter.** Panels never nest a scrolling box: rows of chips wrap, long lists show a few items and fold the rest behind "+ n more", less-used sections fold behind a one-line summary, and every shortcut is listed on one sheet (`?`) instead of a button.

## Tests

| Directory | Covers | Plan |
|---|---|---|
| `tests/unit/` | distributions, kernels, propagation, the daily model, kernel learning, taxonomy, ops, refiner and review, frontier, abduction (including composites), recall, isolation, unify, couple, explanation, VOI, consolidation, update runs, ledger and snapshots; trace scopes, distribution pictures, group forecasts, the two-children split, and the world's keyed noise | §15.1 |
| `tests/integration/` | the API and `/ws` through `TestClient`, including update runs; checklist items 4 and 5; every slot alternative (slow) | §15.2 |
| `tests/scenario/` | initialization, same-seed determinism, posing twice, restore; the full checklist (slow) | §15.1, §15.3 |
| `tests/ui/` | a Playwright smoke test of the canvas, menus, presets, a step, and memory (slow; skipped without Playwright) | §15.4 |
