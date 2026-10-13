# M05 · Intake

**Layer** 3 · **Package** `intake/` · **Status** exists. Changes:
- `ImportRunner` comes in from `sim/`;
- the imports of `sim/` go;
- conflict detection is added.

**Code today:** `intake/sources.py`, `scrapers.py`, `translators.py`, `bundle.py`, `resolver.py`, `refiner.py`, `pipeline.py`; `sim/imports.py`.

## Purpose

From the outside world to a graph update event, in three steps:
1. a **source** yields market events;
2. a **translator** turns each one into operations;
3. the **refiner** narrows each fuzzy end from kind to entity to subentity.

An end binds only when the article names it; otherwise it is hedged. Intake returns results. It never proposes and never commits.

## Owns

- Sources, scrapers, `dedup_keys`.
- Translators, with `TranslationContext` and `TranslationResult` (events, plus the phrase span behind each operation).
- The import bundle `axelrod.import/v1`. Each item has dated fields, entities, tickers, stance, relevance, confidence, and **signals**. A signal is one of observe, move, link, support, or contradict, and carries a quote. This bundle is the seam to any upstream research agent ([frameworks.md](../frameworks.md#recommendation)).
- `EntityResolver`, `Refiner` (`refine`, `weigh_hedges`), `IngestionPipeline`.
- **New** `ConflictDetector`, which yields `Conflict {op_index, kind: value|sign|timing|existence|type, severity, against}`.

## Interface

```python
IngestionPipeline.ingest(event: MarketEvent, now) -> IngestResult     # translate → refine → detect conflicts
MarketEventSource.poll(since, until) -> list[MarketEvent]
MarketEventTranslator.translate(event, TranslationContext) -> TranslationResult
EntityResolver.resolve(mention, constraints, candidate_ids, graph) -> list[(id, score)]
Refiner.refine(event, wm, ltm, ctx) -> RefinementResult
Refiner.weigh_hedges(parsed, fold, wm, ctx, txn) -> list[ProposalEvent]  # called from M08
ConflictDetector.detect(event, wm, ltm, ctx) -> list[Conflict]           # new
read_bundle(src) -> ImportBundle; market_event_of(item) -> MarketEvent
```

## Slots

| Slot | Default | Alternatives / planned |
|---|---|---|
| `source` | config `update.sources` | jsonl_replay, history_replay, mock_web_scraper; `synthetic_data_feed` registers from [M17](M17-demo.md) |
| `translator` | news → hand_drawn, template; data → data_feed | structured (bundles); llm (a stub, held to the operation schema); example (demo) |
| `entity_resolver` | alias_fuzzy | |
| `refiner` | taxonomy | R18: likelihood-based responsibilities |
| `conflict_detector` (new) | rules: opposite sign on an existing interaction, a value outside a soft bound, a retired item reused | llm_pairwise. It **only flags**; the reviewer decides (Semantica's conflict types). |

## Depends on

[M01](M01-foundation.md)–[M03](M03-memory.md); `node_signature` from [M02](M02-model.md). Not `sim/`.

## Diagrams

From an article to a graph update event:

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  A["Article, data release, filing, or imported item"]:::start ==> D{"Seen before?<br/>same address, or same site and title"}:::check
  D ==>|no| T{"A reviewed translation exists?"}:::check
  T ==>|no| TR["Translate<br/>template · data_feed · structured · llm"]:::step
  TR ==> OPS{"Any operations?"}:::check
  OPS ==>|yes| K{"Does an end name a kind<br/>(an airline) rather than a value?"}:::check
  K ==>|no| OUT["Graph update event<br/>ends are values, plus any hedged ends"]:::done
  D -->|yes| DROP["Drop the duplicate (logged)"]:::done
  T -->|yes| F["Use the reviewed fixture"]:::opt
  F --> OPS
  OPS -->|no| UN["Nothing to learn (logged)"]:::done
  K -->|yes| N["Narrow one level: kind → entity → subentity<br/>refiner · entity_resolver"]:::opt
  N --> NAMED{"Does the article name<br/>one candidate outright?"}:::check
  NAMED -->|yes| BIND["Bind the end"]:::opt
  NAMED -->|no| HEDGE["Hedge: a probability per candidate + an open share,<br/>drawn as soft interactions"]:::opt
  BIND --> OUT
  HEDGE --> OUT
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  linkStyle 0,1,2,3,4,5 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

A fuzzy end's lifecycle ([cognition.md F11](../cognition.md#f11--an-open-world)):

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "transitionColor": "#857C70", "transitionLabelColor": "#665E54", "compositeBackground": "#F7F2EA"}}}%%
%% style: end
stateDiagram-v2
  [*] --> abstract: an end names a kind
  abstract --> entity: narrowed one level
  entity --> bound: the article names one candidate
  abstract --> hedged: no candidate named
  entity --> hedged: no candidate named
  hedged --> hedged: later events reweigh candidates × confidence
  hedged --> resolution_proposed: one candidate passes the bound with enough checks
  resolution_proposed --> bound: approved (rivals' soft interactions retired)
  resolution_proposed --> hedged: rejected
  hedged --> expired: too old
  bound --> [*]
  expired --> [*]
```

## Invariants

- **Intake never writes memory.**
- **Deduplication.** The same address, or the same site and title, is dropped and logged.
- **Bind only a named mention.** Otherwise hedge it across the candidates, plus an open share.
- **Every operation keeps its phrase span.**
- **A signal whose ends aren't in the graph is reported, never invented.**

## Done when

- Unit tests cover dedup, each translator, binding versus hedging, and bundle parsing.
- Conflict detection flags the three rule cases and never fails ingestion.
- `intake/` doesn't import `sim/`.
