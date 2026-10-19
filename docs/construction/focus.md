# A focused world and its export

<!-- toc -->
**Contents**

- [Declare a focus](#declare-a-focus)
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

## What a focus keeps

- **Companies.** The focus companies with their whole construction. Every other covered company goes with its whole
  construction file: its values, links (including those between shared values, and those into a focus company's
  values, such as one insurer's links from another's claim-severity states), paths, compositions, identities,
  stock-flows, and matrices.
- **Players.** Every entity upstream of a focus value (a chain of links into it, through sources, moderators, and
  state values), or one link downstream of it: macro and policy, markets, sectors, competitors, suppliers, regulators.
  A value that a removed company's file added to a shared entity stays only if it is itself upstream or one link
  downstream of a focus value.
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
uv run python scripts/construction/check.py sally_focus --entities toyota tokio_marine --reconcile --statistic median \
    --sources data/sally_data/construction --trace dollar_yen.usd_jpy:toyota boj.policy_rate:tokio_marine
uv run pytest tests/scenario/test_sally_focus.py
uv run pytest tests/scenario/test_construction_toyota.py tests/scenario/test_construction_tokio_marine.py
```

The two company test files run against both `sally_demo` and `sally_focus`. `test_sally_focus.py` checks that no
removed company or value remains, that each focus company's compositions, paths, identities, stock-flows, values, and
links match sally_demo's, that traces run as they do there, and that the remaining theses run.

## Export it

```
D=data/sally_data
uv run python scripts/imports/export_context.py sally_focus $D/exports/world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date> \
    --days $D/days --theses \
    --client-core $D/unpacked/world_model_v4/world_model_v4_1_4_numbered_modular_domain_packs_plus_035 \
    --construction-sources $D/construction
(cd $D/exports && zip -qr world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date>.zip \
    world_model_v4_1_4_axelrod_037_focus_toyota_tokio_marine_<date>)
```

The script prints, per day bundle, the items kept and those dropped as about a removed company; bundles left empty
are skipped. The source catalogue keeps only the exported companies' folders, so a removed company's documents never
appear (a broker that is also a covered company can still appear as the author of a focus company's research). The
export is the same file whichever process writes it, apart from the manifest's `generated_at`. Exports are client
data: they stay in `data/sally_data` and are never committed.

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
them. Tests: `tests/unit/context/test_reading.py`, and `tests/integration/test_export_determinism.py` for the
process-independence of the files.

## Regenerate after a new pack

1. Merge the company's construction round (its `data/worlds/sally_demo/construction/<company>.yaml`) and put its local
   sources, citations, and baselines under `data/sally_data/construction/<company>/`.
2. Run the checks above. A new link into another company's values goes automatically; a new group or thesis whose text
   names a removed company needs an override in `data/scenarios/sally_focus/scenario.yaml`, and the report's
   `groups_dropped`, `theses_dropped`, and `mentions` say which.
3. Run the export with a new date in the folder name, and zip it.

### Repair data (Oct 19)

A company folder under `--construction-sources` may hold `repair.json` (client material: dated observations with sources, management
explanations, a financing bridge, input classes). The export binds it (`context/earnings.py`): reported against estimated on each of the
company's values, the baseline reconciliations, the bridges, the assumption records and the controlled model checks. The decision date
and the as-of date come from the instruction and the model state, not from the run; the manifest's `generated_at` is the only moving
field, and `file_versions` gives a sha256 for every file. The reading set adds `41_` to `44_` files for these objects.
