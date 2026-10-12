# M06 · Intake

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; cut its imports of `sim/`, add conflict detection |
| Code today | `intake/sources.py`, `scrapers.py`, `translators.py`, `bundle.py`, `resolver.py`, `refiner.py`, `pipeline.py`; `sim/imports.py` (`ImportRunner`, the client's real import path) |
| Target | `axelrod_wm/intake/`: `sources/`, `translators/`, `bundle.py`, `resolver.py`, `refiner.py` (refine + `weigh_hedges`), `conflicts.py` (new), `pipeline.py`. `ImportRunner` moves here from `sim/`. |

## Purpose

From the outside world to a graph update event. A **source** yields market events; a **translator** turns one into operations; the **refiner** narrows each fuzzy end from kind to entity to subentity. It binds an end only when the article names it, and otherwise hedges it across candidates. Intake proposes and never commits.

## Owns

- `MarketEventSource`, `WebScraper`, `MockWebScraper`, `dedup_keys`.
- `MarketEventTranslator` and `TranslationContext` (the world's templates, its series map, and reviewed fixtures); `TranslationResult` (events, plus the phrase spans that asked for each operation).
- `ImportBundle`, `ImportItem`, `Signal`: the `axelrod.import/v1` format.
  - Item fields: id, published_at, occurred_at, source, source_type, kind, headline, summary, url, entities, tickers, category, stance, relevance, confidence, tags, signals.
  - Signal types: observe, move, link, support, contradict. Each carries a quote and a note.
- `EntityResolver`, `Refiner`, `RefinementResult` (refined event, steps, pending hedges, soft support), `RefinementStep`.
- `IngestionPipeline`.
- **New** `ConflictDetector` and `Conflict {op_index, kind: value|sign|timing|existence|type, severity, against: committed fact id, evidence}`.

## Interface

```python
class IngestionPipeline:
    def ingest(self, event: MarketEvent, now: datetime) -> IngestResult
        # translate (chain by kind) → refine → detect conflicts
        # → IngestResult(graph_update_events, spans, refinement, conflicts)
        # The service (M14) turns it into a Proposal. Intake never calls propose() itself.

class Refiner(ABC):
    def refine(self, event, wm, ltm, ctx) -> RefinementResult
    def weigh_hedges(self, parsed, fold, wm, ctx, txn) -> list[ProposalEvent]     # called from learning (M09)

class ConflictDetector(ABC):                                                       # new slot: conflict_detector
    def detect(self, event: GraphUpdateEvent, wm, ltm, ctx) -> list[Conflict]

def read_bundle(path_or_bytes) -> ImportBundle
def market_event_of(item: ImportItem) -> MarketEvent
```

## Slots

| Slot | Default | Alternatives | Notes |
|---|---|---|---|
| `source` | per config `update.sources` | jsonl_replay, history_replay, mock_web_scraper, synthetic_data_feed | `synthetic_data_feed` is a demo fixture and registers from [M19](M19-demo.md) |
| `translator` | chain per kind: news → hand_drawn, template; data → data_feed | structured (bundles), llm (a stub today), example (demo) | An LLM translator must be held to the operation schema (literature §6) |
| `entity_resolver` | alias_fuzzy | — | |
| `refiner` | taxonomy | — | |
| `conflict_detector` (new) | rules | llm_pairwise | Rules: an opposite sign on an existing interaction, a value outside a soft bound, a retired item reused. Borrowed from Semantica's conflict types and Cognee's contradiction check, but it **only flags**: a person decides in review. |

## Depends on / used by

- Depends on: [M01](M01-core.md), [M02](M02-ports.md), [M03](M03-model.md), [M04](M04-memory.md), and [M07](M07-shared-read.md) for `node_signature` only. Not `sim/`: the op builders `bundle.py` borrows from `sim/examples/catalog.py` move here.
- Used by: [M14](M14-services.md) (UpdateService, ReviewService), and [M09](M09-learning-working.md) (`weigh_hedges`).

## Flow

[architecture.md §4](../architecture.md#4-intake), and the hedge lifecycle in [§12](../architecture.md#a-fuzzy-end-hedge).

## The research agent seam

The import bundle is the boundary between the world model and any upstream research agent. An agent built on Cognee (or anything else) reads and categorizes research and emits `axelrod.import/v1`. Intake treats every item as a market event that a person reviews. Nothing upstream writes to the model directly. See [frameworks.md](../frameworks.md#recommendation).

## Invariants

- **Intake never writes memory.** It returns results; services propose; learning writes after review.
- **Deduplication.** The same address, or the same site and title, is dropped and logged.
- **An end binds only when the article names it.** Otherwise it is hedged: a probability per candidate plus an open share, drawn as soft interactions as strong as they are probable.
- **Spans.** Every operation keeps the phrase that asked for it, so the review can mark it.
- **A signal whose ends are not in the graph is dropped and reported**, never invented.

## Known issues and planned

- The LLM translator is a stub (ml-stack §5). Its contract is the operation schema plus spans; it is evaluated against the reviewed fixtures.
- Hedge weights are counts, not posteriors (S-M8); R18 plans likelihood-based responsibilities.
- Point-in-time data: R15 adds vintage, reference period, and release time to observations.

## Done when

- `tests/unit/intake/` covers dedup, each translator on fixtures, binding versus hedging, and bundle parsing (`tests/fixtures/import_bundle_sample.json`).
- Conflict detection flags the three rule cases and never blocks ingestion.
- `intake/` has no import of `sim/`.
