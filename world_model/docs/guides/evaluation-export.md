# The evaluation export (`axelrod.wm-export/v1`)

The world model written for an evaluator rather than an answering agent (Oct 31): core's Mission Control has a World
Model quality tab that scores an uploaded export against frozen source documents and a reviewed gold set, with no agent
in the loop. Core defines the schema; this repository fills it (`world_model/src/axelrod_wm/context/wm_export.py`).

<!-- toc -->
**Contents**

- [What it holds](#what-it-holds)
- [Writing one](#writing-one)
- [The update series](#the-update-series)
<!-- /toc -->

## What it holds

| Part | What it is | Where it comes from |
|---|---|---|
| `manifest` | World model id, version, state hash, as-of, generated-at, generator, attachments, scenario step | the engine; `generated_at` is the only wall-clock field |
| `capabilities` | What the model can do: as-of reads, restore, retire, idempotent import; not supersession or undo | declared by the exporter |
| `entities`, `variables` | Entities and their values; each value's estimate (the posterior, `kind: model`), its input class (reported, derived, externally estimated, assumed), its role in the mechanism (driver, operating state, financial endpoint, or null) | the graph; input classes as `context/earnings.attach_repair` takes them |
| `records` | Dated, scoped figures: reported observations from the company's repair data (`origin: attachment`, outside the state hash) and observations the model folded from imports (`origin: model_state`) | `repair.json`; subentity history |
| `bindings` | Evidence: source, document name and **sha256**, page, printed page, location, passage, the claims it supports | sources, citations, repair observations |
| `sources` | The source catalogue, with each document's hash and the publication date when it is a date | `sources.json` |
| `relations` | Links with type, sign, timing, calibration, effect (null when uncalibrated, never 0), evidence by claim, condition, breaker, unresolved inputs, and whether the link drives its target | interactions and their transitions |
| `views`, `paths` | Compositions (total, members, signed eliminations, residual, the views of the same total) and named paths, every step kept as declared | the construction |
| `assumptions` | Values that rest on an assumed input, with the prior and what would replace it | input classes |
| `history` | Versions, commits (who made them: a person or the system) and proposals | storage, the ledger, the controller |
| `schema_gaps` | What the export cannot say yet | declared by the exporter |

A binding names its document by content hash, so an evaluator joins it to a frozen corpus by (sha256, page) without
sharing ids with this repository.

## Writing one

```bash
D=data/work/sally
uv run python world_model/scripts/imports/export_wm.py snapshot sally_focus data/exports/sally/wm-export.json \
    --days $D/days --construction-sources $D/construction \
    --remap data/sally_data/=data/sources/sally/ \
    --remap "Toyota 7203/=data/sources/sally/toyota_pack_2026-10-18/Toyota 7203/" \
    --world-model-id sally-focus-toyota --label "Toyota and Tokio Marine" --subject Toyota
```

`--remap OLD=NEW` rewrites a path prefix before hashing: `sources.json` still names the old `data/sally_data/` layout,
and repair observations name documents relative to the Toyota pack. Client material stays local; write the export to a
gitignored folder.

## The update series

An export is a static file, so the operations a world model must support are exercised here and exported step by step
(`context/wm_export_series.py`): build, ingest a bundle, export the same state again, re-import the bundle, ingest a
second bundle, the two bundles in the other order on a fresh model, an as-of read and a restore. Each export's
`manifest.scenario` names its step, operation and the step it is compared with. On the synthetic client:

```bash
WORLD_MODEL_CLIENT_DIR=world_model/tests/fixtures/clients uv run python world_model/scripts/imports/export_wm.py \
    series acme_demo first.json second.json data/exports/acme-series --world-model-id acme --label Acme
```

The series records what happened and does not judge it. Today a re-import and a restore leave the state hash unchanged,
and the two import orders end in different states (an earlier-dated item imported later folds on the next processed
day), which the evaluator reports.
