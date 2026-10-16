# The demos

There are five demos. All five serve the same interface ([interface.md](interface.md)) over the same engine.

<!-- toc -->
**Contents**

- [Emily's demo](#emilys-demo)
- [The tutorial (small and production demos)](#the-tutorial-small-and-production-demos)
- [The full demo](#the-full-demo)
- [The review](#the-review)
<!-- /toc -->

| Demo | Command | What it is |
|---|---|---|
| **Small demo** | `uv run axelrod small_demo` | A blank canvas. The 24 examples build a world model from nothing, one feature at a time. Start here. |
| **Production demo** | `uv run axelrod prod_demo` | The same 24 examples in the oil-shock world, after three years of synthetic history, with a deeper hierarchy: superentities of superentities, three levels deep (Global tightening › Stagflation squeeze › Energy price shock; Tech decoupling › Semiconductor complex › AI chip supply chain; Oil to airlines) |
| **Full demo** | `uv run axelrod demo` | The oil-shock scenario: 53 real actors and ideas and 18 scripted steps. The [hosted demo](deployment.md) runs this one. |
| **Emily's demo** | `uv run axelrod demo --scenario emily_demo` | The ordinary use case: a PM's world model brought up to date by importing research, then forecasts of her book. See [below](#emilys-demo). |
| **Sally's demo** | `uv run axelrod demo --scenario sally_demo` | Eleven names across banks, insurers, and Japan's exporters, brought up to date one day of research at a time; each forecast reads as a scenario table, and the model exports as context for a client's agents. See [below](#sallys-demo). |

The small and production demos serve http://127.0.0.1:8765. The full demo serves http://127.0.0.1:8000 unless you pass `--port`.

## Switching demos

You don't need to restart the server to change demos. The **demo menu** beside the name in the top bar lists all five. Choosing one switches the running server to it, and the page reloads into the new demo.

- **A demo opened before comes back as you left it**, with its reviews, examples, and versions. Each demo keeps its own storage (next to the first one's, for example `var/axelrod/demo-prod_demo`) and its own trace stream. To start a demo over, use **Reset**, or Admin › Scenario; **Reset to the original demo** (☰) starts every demo under the login over at once.
- **A demo opened for the first time is built in the background.** The demo you're on keeps working, and a card under the menu shows the progress. The production and full demos replay three years of synthetic history the first time they open on a machine, which takes about two and a half minutes. The card counts the days as they're replayed, and the menu marks those demos *First open replays its history: a few minutes*. After that the history is cached in `var/oil_shock_demo/` (the two demos share it), and opening either one takes seconds.
- **On the hosted demo, each login switches only its own engine.** Switching under Emily's login never changes what the main login sees, and the other way round. `WORLD_MODEL_SCENARIO` and `WORLD_MODEL_LOGINS` still choose the demo each login opens on ([deployment.md](deployment.md)).
- **In Emily's demo, Tutorial** switches to the small demo and opens its examples. **Back to your model** switches back, and her model is as she left it.

The API behind the menu: `GET /api/demos` returns the demos, the current one, and the switch under way (its phase and, during the history replay, the days done). `POST /api/demos/{id}` switches. Every page on the same engine receives a `switched` message on `/ws` and reloads. `POST /api/sim/load` still reloads a demo from its start.

## Emily's demo

What an ordinary week with the product looks like for a cross-asset PM. The model starts with her view of the chain (oil → inflation and growth → the Fed and the BoJ → the US–Japan rate gap → USD/JPY → her names: Tokio Marine, Zurich, Toyota, Komatsu, SoftBank Corp, JPMorgan, Citi, Morgan Stanley, UniCredit), in six superentities. It has no synthetic history.

1. **Import** (`I`, Learn) opens a bundle: research a collection agent has read and categorized, as dated items. Choose a JSON file, or one from the server's imports folder when it has one. The dialog shows the items as a timeline by day, with each item's source, category, relevance, and what it would change (a level, a move, a new link, or evidence for or against one), and what does not map onto the model.
2. **Importing** folds the chosen items in on their own dates through one update, which stops at each item for review, oldest first. The review highlights the phrases each change comes from. When the last one is decided, the caption says the model is up to date.
3. **Predict** opens on a blank canvas. Ask a question, or pick one of her four ready-made scenarios (from her Fed-versus-BoJ table and her yen simulator). The forecast brings forward only what it reaches, with the forecast's effect on each value; **Show the whole model** shows everything, as of the version the forecast used. Its transmission path opens first, as the grid; the brief is one click away, and takes notes, an **Edit**, and a **Re-run** ([interface.md](interface.md#panels)).
4. **Tutorial** opens the small demo in place of the model, and **Back to your model** returns.

The bundle format (`axelrod.import/v1`) is in `src/axelrod_wm/intake/bundle.py`; a synthetic sample is `tests/fixtures/import_bundle_sample.json`. Emily's own bundle is built from client research and lives in `data/emily_data/`, which is never committed or uploaded: on the hosted demo, import it with the file picker.

## Sally's demo

The world model as the **context layer** for a client's agents. The client's agents (a decision engine, a disruption-propagation agent, an execution and monetization agent) already load a "world model" of their own before they reason, in their v4.1.4 format: a core contract, a relationship schema, and a registry (000, 010, 020), then one domain pack of companies, clusters, and qualitative edges, then the run's evidence. Theirs has no effect sizes, lags, or forecasts. Sally's demo shows ours filling that slot: it learns from the same research, and exports what it holds in their format.

**The book.** Eleven names, each seeded with its drivers and links, in three groups that nest the smaller superentities:

| Group (superentity) | Names | Inside it |
|---|---|---|
| Banks and capital markets | JPMorgan Chase, Morgan Stanley, Citigroup, China Construction Bank, UniCredit, AIB Group | US capital-markets banks; Euro and Irish banks; China banks and property |
| Insurers on Japanese and global yields | Tokio Marine, MS&AD | Japanese insurers' reinvestment |
| Japan rates, growth, the yen, and overseas earnings | Toyota, Komatsu, SoftBank Corp | Rate gap and the yen; yen exporters; Japan rates and domestic growth |

Policy divergence and oil and inflation sit above all three. Other names in the research (Zurich, Munich Re, NN, Duke Energy, National Grid) are sector context only: they inform the drivers, and have no entities. AIB and MS&AD have no research yet, so they move only through their drivers.

1. **Import** (`I`). The research is sorted into **one bundle per day** (`data/sally_data/days/YYYY-MM-DD.json`). The dialog offers **Next day** (the first day after the model's date) and **Any day…**; on the hosted demo, choose one or several days' files with the file picker, and they are merged. Each item is reviewed on its date, as in Emily's demo.
2. **Predict.** Five ready-made theses: the BoJ to 1.5%, the Fed cutting 100 bp, a carry unwind (USD/JPY −8%), the PBoC cutting the LPR with property recovering, and the ECB cutting 50 bp. Or ask your own ("What if deal activity fell by 20% next quarter?").
3. **Scenarios for the book.** Each forecast's panel opens with its scenario table, the form of the client's Decision Engine card "Scenarios & conviction". The forecast's joint draws are sorted by how the book moves (the average effect on the eleven names' share prices, or their earnings line where a name has no price). **Bear** is the worst quarter of the draws, **Base** the middle half, **Bull** the best quarter. For each band: the names it favors and hurts (median moves, in percent), the drivers that differ most between bear and bull (the mechanism), and what would change the read (the open hypothesis on the book worth most to learn). The chances of the book ending up or down at all are the model's own, and sit above the table. Nothing in it is learned or written by a language model (`inference/scenario_table.py`).
4. **Agent context.** **Agent context** on a forecast opens the context beside the card it fills. It follows the client's numbered load order: their **000** (core contract), **010** (relationship schema), and **020** (registry), unchanged, then our **036 domain pack**, then **evidence**. The export has five parts: the **load order** (and which of their agents' cards reads which part), the **domain pack**, the **registry entry** to append to their 020 (so the harness activates the pack by `domain_pack_id` or file index), the **evidence pack** (every value at the committed version, what has been observed, and the open questions), and the forecast's **evidence pack** (targets, transmission, key interactions, the scenario table). Live state is evidence, never part of a pack, as their contract asks. **Download** saves everything as one file; **As files** saves each part under the file name the load order gives it. It grounds the agent's judgment and never concludes it: no ratings, no sizing, no funding sources.

How it maps onto the client's format (their packs' sections and the contract's ID rules, checked by `tests/integration/test_sally_context_api.py`):

| Their v4.1.4 section | Ours |
|---|---|
| pack header | `schema_version` `v4.1.4_modular_domain_pack`, `file_role` `DOMAIN_PACK__LOAD_AFTER_CORE_WHEN_ACTIVATED`, a `PACK_…` id and file index from the scenario (`context_pack` in `scenario.yaml`; Sally's is `PACK_GLOBAL_RATES_BANKS_INSURERS_JAPAN_EXPORTERS`, 036) |
| `companies` | Each company: `N_<TICKER_OR_COMPANY>`, `COMPANY_…` descriptive id, role tags from its concepts, `taxonomy` (sector, subsectors from its concept path, geography), `node_group` (watchlist or context) |
| `clusters`, `cluster_memberships`, `sector_packs` | Superentity patterns (`CL_…`, with their members' node ids and subclusters), their roles (`CLMEM_…__…`), and the top-level groups (`PACK_…`) with activation terms, metric families, required baselines, and do-not-infer rules |
| `company_edge_relationships` | Each interaction into (or out of) a company, owned by that company: `REL_<COMPANY>__E##_<EDGE>` on the pack's own edge vocabulary (E60 on, clear of theirs), direction (positive, negative, or mixed when the effect's 90% range includes zero), `confidence_prior` (high, medium_high, medium, context_only, from the existence probability), the contract's relationship properties (time horizon, status, validator, invalidator, evidence, provenance), and an `axelrod` block with the numbers their schema has no room for |
| `required_search_scopes` | One per configuration: what to search, the mechanisms to inspect, and the evidence that would confirm or break its links |
| `cross_validation_assertions` | Companies moved by the same driver, which should move together (or apart) |
| `industry_caveat_definitions`, `caveat_impact_assertions` | Seeded links not yet validated, links with an uncertain sign, soft economic bounds, and open hypotheses, each mapped to the companies and edges it touches |
| `transmission_paths` | Each configuration's chain, causes first, in edge-vocabulary steps |
| `financial_model_semantic_fields` | The company values the model moves (`FMSPEC_…`) |
| `domain_specific_support_objects` | The edge vocabulary, macro factors (central banks, curves, economies) and the links among them, and the model's version and state hash |
| 020 registry entry | The row to append: `domain_pack_id`, name, file name, activation terms, `never_merge_into_base`, file index |
| evidence | The current state, and each forecast, as evidence packs loaded after the domain pack |

The research is client material and stays local, like Emily's: `data/sally_data/` is gitignored and never in the Docker image. Research agents write dated items into `data/sally_data/_bundle_parts/`, and `scripts/imports/bundles.py` gives them the model's ids, checks each part against the model, and writes the daily bundles:

```bash
uv run python scripts/imports/bundles.py ids sally_demo > data/sally_data/_bundle_parts/model_ids.txt
uv run python scripts/imports/bundles.py check sally_demo data/sally_data/_bundle_parts/<group>.json
uv run python scripts/imports/bundles.py days sally_demo data/sally_data/_bundle_parts data/sally_data/days --title "Sally's research"
```

5. **Export the world model** (☰, Learn) exports the model as it stands after the research approved so far, without a forecast: the 036 domain pack, its 020 registry entry, and the current state as an evidence pack, as one file or as the separate files the agents' load order names. Export again after each day's research, and the agents read the updated model.

To write the whole upload set to a folder (after folding in a folder of daily bundles, with an evidence pack per ready thesis, and the client's 000, 010, and 020 beside it, 020 with our row appended): `uv run python scripts/imports/export_context.py sally_demo data/sally_data/exports/<name> --days data/sally_data/days --theses --client-core <their folder>`. Point it at a gitignored folder: the set holds client files.

The API: `GET /api/context/v4` returns the export (load order, domain pack, registry entry, evidence); `?forecast=<id>` adds that forecast's evidence pack. The exporter is `src/axelrod_wm/context/v4.py`.

## The tutorial (small and production demos)

```bash
uv run axelrod small_demo              # a blank canvas
uv run axelrod small_demo 9            # open at example 9: examples 1–8 are played first, and 9 waits for review
uv run axelrod prod_demo ripple        # an example's id works as well as its number
uv run axelrod small_demo --list       # the examples, and how many "more like this" events each has
uv run axelrod small_demo --headless   # every example's review, printed in the terminal
```

**Tutorial** (`E`) in the top bar lists 24 steps, called examples below. Most show one feature of the framework through one or more sample articles. Two show a backend user adding what they know with no article at all. Each title names the idea it tests, for example "Analogy: a new shock recalls an old one".

| Memory | Examples |
|---|---|
| Working memory | 1 create an entity · 2 links inside an entity · 4 a shock and its ripple, by order · 7 an observation teaches an effect · 14 evidence weakens a link · 23 delete a link |
| Your own knowledge (no article) | 5 add an entity, its value, and an interaction from experience · 9 connect your idea to the rest, at half confidence (example 10's ripple then runs through it) |
| Intake | 3 a fuzzy mention, refined to one value · 12 an ambiguous mention stays fuzzy |
| Long-term memory | 8 a new member inherits its concept's priors · 10 an actor's decision goes into its entity memory · 11 a later shock recalls an earlier one · 13 later evidence settles a fuzzy end · 15 a recurring group is proposed as a superentity · 16 a correlation gains strength · 17 a co-movement is proposed as a link · 18 a crowded kind splits · 19 collapse · 20 nest two superentities in one · 21 expand · 22 delete a superentity the model provided |
| Review | 6 many new items: keep only some |
| Inference | 24 a what-if question |

How the examples run:

- **They form one chain.** Running example *n* plays examples 1 to *n* − 1 first. Running an earlier example rewinds to it and replays the decisions you made on the earlier ones.
- **More like this.** Under an example, **More like this** adds further articles of the same kind to the current state.
- **Every example stops at Review.** Nothing in either memory changes until you approve. [The review](#the-review) explains what it shows.

The examples, their articles, and the "more like this" events are in `src/axelrod_wm/sim/examples/`.

## The full demo

```bash
uv run axelrod demo --port 8765
```

In the full demo, **Update** (`U`) reads news and data up to a date, and **Step ▸** (`→`) and **Play** (`Space`) follow the scripted story. A run pauses whenever something needs review. The first start replays three years of synthetic history (about two and a half minutes) and caches it in `var/oil_shock_demo/`. Later starts take a few seconds. The cache rebuilds itself when the data, config, or engine code changes.

## The review

Every change that needs a person is staged first: the event's whole learning runs on a copy of the model, and **Review** shows everything the copy would commit. It is grouped by stage, each in its stage's color:

- **Intake:** the article, with the phrases that asked for each change marked.
- **Working memory:** every change, with one checkbox each; what recall brought back; the ripple, by order and path; what the fold learns. Each value's ripple can be deselected or given the probability that it arrives.
- **Long-term memory:** what it learns, and any proposals it raises.
- **Your review:** approve all, some, or none. Deselecting a change stages the event again without it.

While a review is open, the canvas shows the staged graph. Staged items have a dashed outline, retired ones a red outline, and moved values are tinted by order. A banner at the bottom of the canvas holds the key.

Three more inputs feed the review:

- **Your confidence.** A slider sets your confidence in the article (100% takes it as stated), and any change can have its own. It goes into the data the approval writes: an interaction's existence and evidence, a report's weight, a move's expected size, and a record on each new entity and value.
- **Your own knowledge.** ☰ → **Add from your own knowledge** opens a form for an entity, its values (a typical level and spread set the prior), interactions (sign, size, timing), why you believe it, and your confidence. It is staged and reviewed like an article. Your reason is kept as the evidence on what it adds. Examples 5 and 9 open it prefilled.
- **Fuzzy ends stay fuzzy.** A mention binds only when the article names its target. Otherwise it is hedged across its candidates, with a share for one not in the graph yet, and drawn as soft interactions as strong as they are probable. Later articles move the odds, and a resolution comes back for review once one candidate passes the bound.
