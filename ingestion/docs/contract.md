# The contract

What passes between ingestion and the world model, and nothing else: the **import bundle** that ingestion produces, and
the **world view** that it reads. Both live in `ingestion/src/axelrod_ingest/contract/`, import only the standard
library and pydantic, and are checked by `ingestion/tests/test_boundary.py`, so either side can depend on them without
the other.

<!-- toc -->
**Contents**

- [The boundary](#the-boundary)
- [The import bundle](#the-import-bundle)
- [Attribution fields](#attribution-fields)
- [The world view](#the-world-view)
<!-- /toc -->

## The boundary

```
                 world view (the model's names, units, levels, links)
  world model ──────────────────────────────────────────────────────▶  ingestion
  axelrod_wm                                                           axelrod_ingest
       ◀──────────────────────────────────────────────────────────────
                 import bundle (dated items, each with signals and quotes)
```

- Ingestion never imports the world model. `ingestion/tests/test_boundary.py` reads the source of the package and of
  its tests and fails on an `axelrod_wm` import anywhere, including a lazy import inside a function. It also fails if
  anything in `contract/` imports more than the standard library, pydantic, and the contract itself.
- The world model depends on ingestion, and calls it in process: the service builds a world view from the graph
  (`axelrod_wm.intake.world_view.world_view_of`), passes it to the ingestor, and folds the bundle that comes back
  through review like any other.
- Because the view has a deterministic JSON form, ingestion can later run as its own service: it is sent the view
  over HTTP instead of in process, and nothing in the code that reads it changes.

## The import bundle

`axelrod.import/v1` is the seam to any upstream research agent, ingestion included. The world model trusts none of it:

- Every item becomes a market event on its own date and is reviewed like an article.
- A signal whose ends are not in the graph is dropped and reported.

| Level | Fields |
|---|---|
| Bundle | `format`, `title`, `collected_by`, `collected_at`, `description`, `synthetic`, `items` |
| Item | `id`, `published_at`, `occurred_at`, `source`, `source_type` (broker_research, expert_call, news, …), `kind` (news, data, analyst, filing), `headline`, `summary`, `url`, `entities`, `tickers`, `category`, `stance`, `relevance` (0–1), `confidence` (0–1), `tags`, `document`, `publisher`, `basis` (direct, proxy, context_only), `citation`, `coverage` (full, partial), `plausible`, `signals` |
| Signal | `observe` (`value_of`, `value`) · `move` (`value_of`, `delta`, `mode`) · `link` (`source`, `target`, `label`, `effect`, `delay_days`, `lag_days`, `duration_days`) · `support` / `contradict` (`source`, `target`, `strength`); each with the `quote` that makes it and a `note` |

The last six item fields name what the world model's `standards` review gate checks (R18-R21): an item that leaves one out is still valid, but waits for a person.

```json
{"format": "axelrod.import/v1", "title": "...", "collected_by": "...", "items": [
  {"id": "EM-001", "published_at": "2026-09-11T06:00:00Z", "source": "...", "source_type": "broker_research",
   "kind": "analyst", "headline": "...", "entities": ["boj"], "category": "rates", "relevance": 0.9,
   "signals": [{"type": "observe", "value_of": "boj.policy_rate", "value": 1.25, "quote": "..."}]}]}
```

Ingestion fills an item's times and tags from the document: `published_at` is when it became available, `occurred_at` the end of
the period it reports on (a monthly announcement published on 1 September has `occurred_at` 31 August; a forward-looking period
gives none), and `tags` carry `extracted`, `doc_type:<type>`, `lang:<code>`, and `period:<label>` ([pipeline.md](pipeline.md#two-times-event-and-ingestion)).
A bundle does not say whether its document is a copy of another: that is in the document's `meta.shared_origin`
([duplicates](pipeline.md#duplicates-across-language-and-basis)).

The schema is `contract/bundle.py` (pydantic models that forbid unknown fields); a synthetic sample is
`ingestion/tests/fixtures/import_bundle_sample.json`, and its tests are `ingestion/tests/contract/test_bundle.py`. The
other half, turning a bundle's signals into proposed graph updates, belongs to the world model
(`world_model/src/axelrod_wm/intake/structured.py`).

Two import rules keep a reported number from being misread, and both are the world model's: a per-share level dated
after a split is converted to the model's basis, and parts of two additive views of one total are not both folded
([the intake module](../../world_model/docs/design/modules/M05-intake.md)).

## Attribution fields

Ingestion fills the six attribution fields on every item it extracts (`extract.provenance_of`); an item the world model's
`standards` gate cannot read all of waits for a person. A field is left empty (`""` or `null`) when the rules cannot say,
never guessed. A bundle uploaded as a file is passed through as written, with no fields added.

| Field | Rule |
|---|---|
| `document` | The lake document id (the content hash of the bytes), which finds the stored text and chunks. `url` is the manifest's address when there is one. |
| `publisher` | The manifest's publisher (a "Publisher", "Issuer", "Outlet" or "Author" column), else `hints.publisher` given with the upload, else the document's own metadata (an HTML `<meta>` publisher, `og:site_name` or author; a PDF's author), else the host of the manifest URL. Empty when none says: for third-party types the gate then waits. |
| `basis` (R21) | `direct` for an item from a `filing` whose every signal is a value of the document's subject company (an issuer stating its own figures). `proxy` for a third-party item (`broker_research`, `expert_call`, `news`, `other`) whose every signal is the quantity itself (a level, or a sized change). `context_only` for a third-party item whose signals are all links, supports, or bare directions. A mix, a filing about someone else, and the other source types (`central_bank`, `data`, `client_model`) are left empty. |
| `citation` (R20) | For an item with a `link`, `support` or `contradict` signal: `<document id> p.<page> chars <start>-<end>`, the span in the document's text of the sentence of the first such signal (no page for formats without pages); `<document id> chunk <n>` if the sentence is not found in its chunk. Empty for an item with no link. |
| `coverage` (R18) | `partial` when a signal's value is a part of a total the model also holds (it feeds an accounting or identity link: a segment, a region), or is a year's flow (`/yr`) read from a document that reports a month, a quarter or a half. `full` otherwise; empty when no signal is about a value. |
| `plausible` | `true` only when every signal was checked and passed: a level inside the value's band (6 sd + 4 scale, or six standard units on a log scale), a sized move within the sizes the extractor accepts (relative up to 90%, absolute up to 2 points). `false` when one is outside. Empty when a signal has no number to check (a link, a support, a bare direction). |

## The world view

Extraction recognizes the model's own names in a document, and reads each value's unit, scale, and current level. It
needs those, not the model. A `WorldView` (`contract/world_view.py`) is that, as frozen records sorted by id:

| Record | Fields |
|---|---|
| `EntityView` | `id`, `name`, `kind`, `aliases`, `region`, `sector`, `subentity_ids` |
| `ValueView` | `id`, `entity_id`, `name`, `attribute_kind`, `unit`, `scale`, `family`, `mean`, `sd`, `aliases` |
| `LinkView` | `id`, `source_id`, `target_id`, `label`, `fixed`, `effect_mean`, `polarity` |

`WorldView(entities, values, links)` holds them. Only active links are in it. A link is `fixed` when it is an
accounting, identity, or stock-flow weight that learning never refits; `polarity` is the sign of its effect, or for a
link not yet calibrated the sign its mechanism states.

**JSON.** `to_json()` gives canonical JSON (records sorted by id, keys sorted, no whitespace), so equal views give
equal strings, and `from_json()` reads it back to an equal view. The tests check the round trip, the sorting, and that
building the same view in another order gives the same bytes.

**The world model's side.** `world_view_of(graph)` is a pure adapter: it reads the graph and nothing else, and sorts
everything by id. Extraction through a view is byte-identical to extraction through the graph it replaced; that was
checked before the swap, on the synthetic Acme corpus (the unit tests' sentences and the determinism suite's
documents, through every step to the stored bundles).

**Fixtures instead of a model.** Ingestion's tests run against `ingestion/tests/fixtures/world_view_acme.json`: the
synthetic Acme world as a view, with the subject patterns its world marks as inverted ("the euro" names the dollar
index's reciprocal). `world_model/scripts/export_world_view.py` writes it, and a world model test
(`world_model/tests/unit/intake/test_world_view.py`) fails when the file differs from what `world_view_of` makes of
the Acme graph. To regenerate it:

```bash
uv run python world_model/scripts/export_world_view.py acme_demo ingestion/tests/fixtures/world_view_acme.json \
    --client-dir world_model/tests/fixtures/clients
```

The same script exports a client's model for the benchmark (`ingestion/scripts/ingest_bench.py --world-view`); that file
belongs in the client's gitignored folder under `data/`.
