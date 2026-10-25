# A focused world and its export

<!-- toc -->
**Contents**

- [Declare a focus](#declare-a-focus)
- [One base from several worlds](#one-base-from-several-worlds)
- [A compartment per login](#a-compartment-per-login)
- [What a focus keeps](#what-a-focus-keeps)
- [Check it](#check-it)
- [Export it](#export-it)
- [Regenerate after a new pack](#regenerate-after-a-new-pack)
<!-- /toc -->

A focused world is a scenario's world narrowed to some of its covered companies (the entities with a
`construction/<entity>.yaml`) and the players they connect to. It is computed from the base on every load
(`engine/focus.py`) and never copied, so a new document pack for a focus company reaches it as soon as the base's
construction file changes.

## Declare a focus

A scenario folder with a `scenario.yaml` that names its base and companies. Every field it leaves out is the base's.

```yaml
id: sally_focus
title: "..."
focus:
  base: sally_demo
  companies: [toyota, tokio_marine]
  overrides:                       # text that named a removed company, rewritten for the focused world
    S8: {name: Yen exporter, description: "..."}       # a group
    S-T4: {question: "..."}                             # a thesis
    china_economy: {description: "..."}                 # an entity, value, or link
    watchlist: {name: "..."}
context_pack: {domain_pack_id: ..., name: ..., slug: ..., file_index: "037", edge_id_start: 60}
```

Only seeded import scenarios (`imports: true`) take a focus.

## One base from several worlds

A client's world is a folder (`entities.yaml`, `interactions.yaml`, `construction/<company>.yaml`, `taxonomy/`). The
unified model is one base built from every client's world, so its scenario names the folders, in the order they merge:

```yaml
id: unified
canvas: seeded
imports: true
start: 2026-08-03
initialization:
  construction_dirs: [worlds/client_a, worlds/client_b]    # or construction_dir: worlds/client_a, for one; not both
  taxonomy_dir: worlds/client_a/taxonomy                   # one taxonomy for the merged model
  seeds: [scenarios/client_a/superentity_seeds.yaml, scenarios/unified/client_b_seeds.yaml]   # one file, or a list
```

Every path resolves against the root that holds the scenario, like any other (`axelrod_wm/clients.py`).
`read_construction` reads each folder alone and merges them in order. An id two folders both define (a shared market
such as an oil price, a rate, a currency) is kept once when the definitions are identical. When they differ, the load
stops with an error that names both files and the id (`entity 'crude_oil' is defined differently in
client_a/entities.yaml and client_b/entities.yaml`): nothing is merged by hand. The same holds for interactions, paths,
compositions, identities, stock-flows, and matrices, and for the entries of the seed files (patterns, superentity labels,
frontier seeds, palettes). Each id a construction file adds keeps its origin, the file's stem and the world folder, so a
focus still drops a whole company with its construction file. The first folder also supplies the world's question
templates (`templates.yaml`) and the data feed's series map.

Templates, `theses.yaml`, `expected_paths.yaml`, and `watchlist.yaml` are read from the scenario's own folder, so the
unified scenario carries the ready-made questions of the whole model; a compartment keeps the ones it holds.

## A compartment per login

A login (`WORLD_MODEL_LOGINS`, `username:password:scenario`) whose scenario is a focus whose `base` is the main engine's
scenario is a **compartment**: it opens no engine of its own, but a view onto the main one (`api/viewstate.py`), and
the organization of the login owns the compartment. Every read, forecast, and thesis of that login runs on the main
engine's memory narrowed by this focus (`narrow` and `narrow_ltm`, `api/v1/compartments.py`), so the same rules apply
to the browser's routes, to `/v1`, to search, and to `/mcp`:

- **Nothing outside it shows**: an entity, value, link, group, or passage outside the compartment is a 404 by id and
  no hit in search. Hypotheses, pending refinements, forecasts, prior episodes, stored explanations, the ledger, and the
  trace are cut or kept apart, so no answer, explanation, graph payload, or error carries them.
- **Forecasts and theses** run on a graph overlay over the narrowed memory with `learn=False`. They, their
  explanations, annotations, and trace are the login's own, in memory. The main engine's state, version, and forecast
  layer do not change.
- **Writes** go to the main engine, through its review: a document or bundle is narrowed to the compartment first
  (`narrow_bundle`: an item about another company, or with a signal on another company's value, is dropped whole), then
  imported by the main runner. The login reviews the proposals its own imports raised, and only those that name nothing
  outside. The lake partition stays the login's organization. Other changes (an edit, a structure change, a rewind, an
  update run, the review policy, a demo switch, the commit log, a backtest) are refused with a 409: they belong to the
  unified model.
- **The demo menu** offers a compartment login only itself, and `/api/scenarios` lists only it.
- **Internal organizations** (`WORLD_MODEL_INTERNAL_ORGS`) and the main login read the whole model and every
  compartment (`/v1/erid`). A compartment is also served at `/v1/erid/compartments/{id}` to its owner.

A login whose scenario is a focus over some other base, or any other scenario, keeps an engine of its own.

## What a focus keeps

- **Companies.** The focus companies with their whole construction. Every other covered company goes with its whole
  construction file: its values, links (including those between shared values, and those into a focus company's
  values, such as one insurer's links from another's claim-severity states), paths, compositions, identities,
  stock-flows, and matrices.
- **Players.** Every entity upstream of a focus value (a chain of links into it, through sources, moderators, and
  state values), or one link downstream of it: macro and policy, markets, sectors, competitors, suppliers, regulators.
  A value that a removed company's file added to a shared entity stays only if it is itself upstream or one link
  downstream of a focus value.
- **Identity terms.** The terms of an identity or stock-flow reach its target like links do, so a value that only an
  identity ties to a focus company is kept, and a path may step along a generated link (`<identity id>:<term>`).
- **Links and objects** whose every value is kept; a link that is an identity's or a stock-flow's term goes with it.
- **Groups** keep their kept members and links. A group that held companies and keeps none, or that keeps fewer than
  two members, is dropped. **Theses** keep their kept targets and groups; one whose shock is on a removed value, or
  with no focus target left, is dropped. **Expected paths** keep the chains, channels, and missing links whose every
  value is kept. The **taxonomy** lists only what remains; a kind's default link that now applies to nothing is allowed.
- **Text.** A group or thesis whose text names a removed company (its name, short name, or an alias of three or more
  characters) is dropped unless an override rewrites it. Other kept text that names one is listed under `mentions`.
- **Imports.** Every import into a focused scenario leaves out the items about a removed company (named in its
  entities, tickers, signals, headline, or summary) and the signals on removed values.

The kept and dropped counts by category:

```
uv run python -c "import json; from axelrod_wm.sim.scenario import ScenarioScript; from axelrod_wm.engine.focus import focus_result; print(json.dumps(focus_result(ScenarioScript.load('sally_focus').focus).report(), indent=1))"
```

## Check it

```
uv run python world_model/scripts/construction/check.py sally_focus --entities toyota tokio_marine --reconcile --statistic median \
    --sources data/work/sally/construction --trace dollar_yen.usd_jpy:toyota boj.policy_rate:tokio_marine
uv run pytest world_model/tests/scenario/test_sally_focus.py
uv run pytest world_model/tests/scenario/test_construction_toyota.py world_model/tests/scenario/test_construction_tokio_marine.py
```

The two company test files run against both `sally_demo` and `sally_focus`. `test_sally_focus.py` checks that no
removed company or value remains, that each focus company's compositions, paths, identities, stock-flows, values, and
links match sally_demo's, that traces run as they do there, and that the remaining theses run.

## Export it

```
D=data/work/sally; X=data/exports/sally; S=data/sources/sally
uv run python world_model/scripts/imports/export_context.py sally_focus $X/world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date> \
    --days $D/days --theses \
    --client-core $S/unpacked/world_model_v4/world_model_v4_1_4_numbered_modular_domain_packs_plus_035 \
    --construction-sources $D/construction
(cd $X && zip -qr world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date>.zip \
    world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date>)
```

The script prints, per day bundle, the items kept and those dropped as about a removed company; bundles left empty
are skipped. The source catalogue keeps only the exported companies' folders, so a removed company's documents never
appear (a broker that is also a covered company can still appear as the author of a focus company's research). The
export is the same file whichever process writes it, apart from the manifest's `generated_at`. Exports are client
data: they stay in `data/work/sally` and are never committed.

### The reading set (`reading/`)

The full domain pack is the client's contract, but it runs to megabytes (the focused world's is 2.2 MB, about 480k
tokens), and an answering system's file reader refuses a file that large ("file too large to extract") and answers
without it. So the export also writes `reading/` (`context/reading.py`; `--max-file-kb`, default 100, 0 for none):

- `00_START_HERE.md`: what the model is, the companies, version and as-of date, every file with its size and when
  to open it, how to follow an id to its file, and the rule that a file which fails to load is reported, never
  answered as if read.
- `01_overview_<company>.md`: business composition, segments and regions, the paths (one line each, with their file),
  the relationship files by edge, and calculation coverage.
- JSON shards of at most 100 KB holding the pack's objects unchanged, never cut mid-object: `10_pack_core`,
  `20_relationships_<company>` (grouped by edge, then by the metric the link points at), `30_paths_<company>`,
  `40_semantic_fields`, `50_financial_<company>` (the bridge and identities), `60_support`; and
  `90_index_ids_NN.json`, every relationship, path, composition, identity, node, link, and field id to its file.

Every object is in exactly one shard. The build reads the written files back and refuses to finish unless their union
equals the pack's objects (nothing lost, nothing duplicated; the script prints the count). The manifest marks the
domain pack's load-order entry `role: machine_import`, names `read_first`, and lists each reading file with its
size and sha256. If the pack itself repeats an id (the check lists any), the index gives every file that holds it.
The source catalogue, evidence packs, and forecast packs are small enough to read as they are; START_HERE links
them. Tests: `world_model/tests/unit/context/test_reading.py`, and `world_model/tests/integration/test_export_determinism.py` for the
process-independence of the files.

## Regenerate after a new pack

1. Merge the company's construction round (its `<client root>/worlds/sally_demo/construction/<company>.yaml`) and put its local
   sources, citations, and baselines under `data/work/sally/construction/<company>/`.
2. Run the checks above. A new link into another company's values goes automatically; a new group or thesis whose text
   names a removed company needs an override in `<client root>/scenarios/sally_focus/scenario.yaml`, and the report's
   `groups_dropped`, `theses_dropped`, and `mentions` say which.
3. Give the export a new number. Set `context_pack.file_index` in the focus scenario first, so the folder number and
   the file names inside it match.
4. Run the export with a new date in the folder name, and zip it.

### Repair data (Oct 19)

A company folder under `--construction-sources` may hold `repair.json` (client material: dated observations with sources, management
explanations, a financing bridge, input classes). The export binds it (`context/earnings.py`): reported against estimated on each of the
company's values, the baseline reconciliations, the bridges, the assumption records and the controlled model checks. The decision date
and the as-of date come from the instruction and the model state, not from the run; the manifest's `generated_at` is the only moving
field, and `file_versions` gives a sha256 for every file. The reading set adds `41_` to `44_` files for these objects.

A repair file needs only `repair_version`, `entity` and `company_id`; a section that is empty is left out. Several companies in one export
(the four automakers and battery makers) each bind their own repair data: every section lists all of them, `manifest.repairs` lists
each company's repair, `manifest.repair` is the last one's, and `evidence.baseline_selections` lists each selected baseline.

**A second, later baseline.** `selected_baseline` (`baseline_id`, `period`, `available_at`) stays the primary baseline: the observation
pairs, the model checks and `evidence.baseline_selection` read it alone. Repair data may add a `latest_period_baseline` of the same shape
(or a list, `additional_baselines`) for a later period or another accounting basis. Each baseline reconciles on its own levels:

- The selected baseline owns the observations flagged `selected_baseline`. Another baseline owns the observations that name it
  (`baseline_id`) or, when one names none and is unflagged, those with the baseline's `available_at` and period end (a comparative
  column or an earlier period never qualifies).
- A composition reconciles against the first baseline, the selected one first, that has every level it reads, and otherwise against the
  selected one, where it is `blocked` by the missing levels. Observations of two baselines never enter one reconciliation.
- Each reconciliation reports its `baseline_id`, period and `baseline_available_at` (also on the composition's `reconciliation`).
  `manifest.repair.additional_baselines` lists the ids of the other baselines; baseline ids must be unique and each needs `baseline_id`,
  `period` and `available_at`.
