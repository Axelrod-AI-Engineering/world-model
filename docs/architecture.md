# Architecture

A map from the code to its processes. The concepts, the flowcharts, and the literature review live in the demo itself (How it works, in the top bar; the review is `web/literature.md`); [flowchart.svg](flowchart.svg) is the overview as a picture. Section numbers (§) in the code refer to [plan.md](plan.md) (revision 2).

## The flow in one paragraph

There is one world model, and it works like version control:

1. An **update run** collects market events up to a date and turns each into a **proposal** (in the two demos, each example's article is one update run).
2. A **review policy** decides whether a backend user must vet it. If so, the run pauses on that event's day until they do.
3. The person reviews at the **end** of learning: `control/stage.py` runs the event's whole learning (working memory, long-term memory, and the day's distillation) on a copy of the state with a throwaway ledger, and the review shows everything the copy would commit: each operation (selectable), the event's moves, the ripple by order with its paths, what the fold learns, and what long-term memory learns. Approving with a selection edits the rest out first. The ripple is not an operation of the event, but it moves working memory day by day, so each value's ripple can be deselected or given the probability that it arrives (`GraphUpdateEvent.ripple`); approved, the weight is stored as a `RippleJudgment` and the daily prediction scales that value's expected ripple by it until the ripple has run its course.
4. For each day, **working memory** first predicts the day (`predict:`).
5. Each approved event then commits twice, once per learning process:
   - **learning of working memory** reads and folds the event into the current state (`<event>`);
   - **learning of long-term memory** registers what it teaches across time and entities (`ltm:<event>`).
6. The day is recorded (`record:`), **distilled** into long-term memory (`distill:`), and **closed** (`close:`).
7. Structural changes (collapse, expand, add, retire) are proposals too, staged the same way, and commit once when approved.
8. **Inference** is a separate process with its own flowcharts (`flows/inference.py`). A **thesis** runs the same read on a **branch** that is never merged; inference then isolates networks, predicts within them, couples them, unifies rival structures into weighted scenarios, and reads out every value by order and path. Once a decision's horizon passes, its outcome is scored and the superentities used gain track record.

Every step is a component with a contract (`engine/contracts.py`; `axelrod contracts`), and every step sits on the flowchart (`flows/`; `axelrod flows`): five stages of learning and six of inference, each with its own flowchart from input to output. Every step also emits **trace events** scoped to its market event.

## Packages (`src/axelrod_wm/`)

| Package | What it holds |
|---|---|
| `model/` | The data model: ids and the eight categories; distributions; kernels and time states (`temporal.py`); evidence; `Entity` and `Subentity` (with soft economic constraints); `Interaction`; superentity patterns and instances; taxonomies and signatures (an interaction's features include its sign and whether it stays inside one entity); hypotheses; `CausalGraph`; explanation records; canonical serialization |
| `memory/` | Working memory (the graph, a daily deviation history, channel states, the forecast layer, pending refinements, the hypothesis frontier, the reviewers' ripple judgments); every node's open node (`open_world.py`: a value's movement its interactions do not explain, a kind's reserve for one not seen yet); long-term memory (object and interaction generalizations, prior states, `SuperInteractionBuilder`); entity memories; the correlation frontier |
| `events/` | Market events, graph update events and their operations (including `retire_entity` and `retire_interaction`), and theses |
| `repo/` | Version control. `mutator.py` is the one writer: transactions, `ChangeSet`s with process, memory, message, proposal, and who vetted them. `ledger.py` is the append-only log. `snapshots.py` holds storage, versions, and restore. `review.py` holds proposals and review policies. `history.py` provides log, show, and diff. |
| `intake/` | Sources and the mock scraper (with dedup keys); translators (fixtures, templates, the data feed); entity resolution; refinement from fuzzy to real, which binds an end only when the article names it and otherwise hedges it (a posterior over its candidates plus an open share, drawn as soft interactions; `weigh_hedges` updates it inside each event's staged learning and raises a refinement proposal once one candidate passes the bound); the ingestion pipeline |
| `shared/` | The read that learning and inference share (`process.py`): parse, classify (sorting, plus the `incorporate` half that long-term learning runs), recall, recognition (binding patterns), prefill, analyze, explain |
| `dynamics/` | Kernel recursions, regressors, Monte Carlo propagation with common random numbers and soft bounds, and the daily model (predict and record) |
| `learning/` | `working_memory.py` (the event commit, and the day's open, record, and close); `long_term.py` (the event's lessons); `consolidate.py` (the daily distillation); `fold.py`; `generalize.py`; `kernel_learning.py`; `frontier_test.py`; `abduction.py` (schema induction); `structural.py` (approved structural changes); `task.py` (`LearningTask`, which runs the two processes) |
| `inference/` | `task.py` (the inference task), isolate, predict, couple, unify, groups (forecasts for an entity, sector, superentity, or category), transmission (orders and paths), value of information, forecast records, decisions |
| `engine/` | The slot registry, config, `ProcessContext`, the interfaces, `contracts.py` (every slot's contract), `build_engine`, named random substreams, initialization (construction with each kind's defaults, seeds, the history replay) |
| `control/` | `WorldModelController`, the façade the API, CLI, and runner call. It covers proposals, review, structure edits (`propose_group`, `propose_dissolve`, `propose_retire`), theses, and decisions. `updates.py` is the update run. `stage.py` is the staged review: an event's learning on a sandboxed copy of the state, reported change by change. |
| `flows/` | Learning's overview as data, five stages with their input and output (`__init__.py`); each stage's own flowchart, with every condition, branch, and loop (`stages.py`); inference's overview and its six stage flowcharts (`inference.py`); the renderer to SVG and text (`render.py`) |
| `evaluation/` | Backtests and metrics (omission, commission, coverage, CRPS); track records |
| `sim/` | The synthetic world; scenario scripts (steps can update, pose, evaluate, decide, or edit structure); the runner with its init cache; the oil demo's checklist; the two demos (`examples/`: the example and article model, the small and production catalogs, and the session that runs the chain with rewind and the library) |
| `api/` | The FastAPI app, REST routes, `/ws`, view models, forecast briefs; `checks.py` (each kind of check: when, how, what it updates exactly, its bound; and what is being checked now); `find.py` (semantic search and filters over entities, values, interactions, and superentities) |
| `trace.py`, `cli.py` | Trace events (each scoped to a market event, a thesis, or a day); the CLI |

## Data (`data/`)

| Path | What it holds |
|---|---|
| `worlds/economy/` | The demo's world: entities, interactions, translation templates, the series map |
| `worlds/small_demo/` | The small demo's world: a blank canvas (no entities) with its own kinds and templates |
| `taxonomy/` | The shared taxonomies: objects (with each kind's default values and links), interactions, attributes |
| `scenarios/oil_shock_demo/` | The demo script, seeds, layout, market events and reviewed translations, theses, decisions, watchlist, and the synthetic truth |
| `scenarios/small_demo/`, `scenarios/prod_demo/` | The two demos: a blank canvas, and the oil world (`base: oil_shock_demo`); their examples are in `sim/examples/` |

## Front end (`web/`)

The first screen is the graph, a caption, and one row of controls; panels open on demand. Detail is chosen per node, or, with **Auto** on, follows zoom: zoomed far out, superentities close into cards; zoomed in, the entities in view open into their values. Every node carries an **open node**, an empty dashed circle sized by what the graph does not explain yet. **Color** colors pills by one question at a time (change, blind spots, category) and keeps the key. **Find** is a semantic filter over nodes and edges that widens to neighborhoods one and two hops out. A **levels** path names each level of superentities within superentities. The hover card is a **lens**: a small picture of what the cursor is on. The timeline has three lanes: news, checks, and commits. The **Learn** and **Predict** views differ only in their controls: Predict hides everything that learns. In the two demos, **Examples** replaces Update and Step. The top bar shows only the moment's primary action, Review when something waits, and one ☰ menu for the rest.

| File | What it does |
|---|---|
| `index.html`, `css/` | The layout, the palette, the faint canvas grid, and the two views |
| `js/main.js` | Boot, the views, side panels, tooltips, right-click menus (including structure edits in Learn), and keyboard shortcuts |
| `js/api.js`, `js/store.js` | The REST client and `/ws`; the client model |
| `js/graph/` | The renderer (pills, subentity rows, outlines and cards, shared ownership, edges, animations), layouts, zoom, menus, fuzzy ribbons, and the draw tool |
| `js/panels/review.js` | The staged review, grouped by stage in the stages' colors: the article with its phrases marked, every change with a checkbox (deselecting re-stages), pending ends, the ripple by order (each value's ripple deselectable, or weighed by the probability it arrives), what recall brought back, what is learned; the canvas shows the staged graph |
| `js/panels/examples.js` | The demos' menu: the chain of examples (run, rewind), their articles, and "more like this" |
| `js/panels/console.js` | The commit log: commits, show, diff, and open a version |
| `js/panels/methods.js`, `flowchart.js`, `js/md.js`, `literature.md`, `implementation.html` | How it works: Learning (the five stages, each stage's flowchart, how a model fills up, the words) and Inference (its six stages and their flowcharts); Literature (the literature review, rendered from Markdown); Implementation (the ML stack and every component's contract) |
| `js/panels/checks.js`, `find.js`, `levels.js`, `colorkey.js`; `js/graph/open-node.js`, `lens.js` | Checks (C); find and filter with neighborhoods (/); the levels path ([ and ]); color and its key (K); the open node; the hover lens |
| `js/panels/*.js` | Inbox, inspector, thesis, forecast, briefs, hypotheses, decisions, memory, pipeline, timeline, caption, walkthrough, admin, chat |
| `js/animator/` | The trace player and the guide |
| `js/charts/` | Fan charts, distribution glyphs, sparklines |

The front end never computes model results: it renders the server's views and applies trace payloads.

## Invariants

- **One writer.** Every change to working or long-term memory goes through `GraphMutator` transactions. Each transaction becomes one `ChangeSet` in the ledger. Each change set names its process (`repo/mutator.PROCESSES`) and bumps the state version; forecast-layer change sets do not bump it.
- **Two learning processes.** A vetted event commits to working memory, then to long-term memory, and the day's distillation commits on its own. `close:` is always the day's last commit.
- **Vetted learning.** Nothing that needs review is learned before a person approves it, and what they approve is what they saw staged. Staging never touches the live state, ledger, or trace. Rejecting changes nothing. A deferred event folds in late, once approved.
- **Inference never learns.** A thesis reads a branch, and only outcomes feed back, through track records.
- **Contracts.** Each component is an ABC registered by name, with a contract. `configs/default.yaml` picks one implementation per slot. A test keeps the registry, the contracts, and the flowcharts in step.
- **Explicit randomness.** Every draw comes from a named substream, so a run is reproducible from its seed. Analyses run with and without a shock on the same draws.
- **Restore.** The init snapshot plus the ledger's change sets reproduce the live state hash.
- **Decisions.** Where the plan was silent, the simplest option was chosen and marked `# DECISION:`. `grep -rn DECISION src configs data web` lists them.

## Tests

| Directory | Covers |
|---|---|
| `tests/unit/model`, `repo`, `intake`, `shared`, `dynamics`, `learning`, `inference`, `control` | Each package's units. This includes the two-process commit order, retirement, and review. |
| `tests/unit/flows`, `tests/unit/engine` | The flowchart is well formed and current in `docs/flowchart.svg`; its trace kinds exist; every registry slot has a contract |
| `tests/integration/` | The API and `/ws`, including update runs, staged review and selective approval, the examples and the library, the log, and structure edits; every slot alternative (slow) |
| `tests/scenario/` | Initialization, determinism, restore; the full oil-demo checklist (slow); the small demo, example by example, with rewind; the production demo (slow) |
| `tests/ui/` | A Playwright smoke test (slow; skipped without Playwright) |
