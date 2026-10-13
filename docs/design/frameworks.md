# Cognee and Semantica

We compared two open-source frameworks to decide what to build, what to borrow, and what we could run. Both repositories were read at their source on 2026-10-12, alongside their READMEs. Neither package was run.

## The two in one paragraph each

**[Semantica](https://github.com/semantica-agi/semantica)** (MIT, Python, v0.7.0, about 14k stars, pre-1.0) is a staged knowledge-graph pipeline for regulated domains. Its stages are ingest → parse → normalize → split → extract → conflict detection → deduplication → KG construction. Four modules then run in parallel over the graph: ontology, reasoning, provenance, and context and decisions. Storage is vector, property-graph, and RDF stores. Its strengths are W3C PROV-O lineage, bitemporal facts (`valid_from`, `valid_until`, `recorded_at`; `state_at(date)`), typed conflicts with severity and resolution strategies, trust tiers (quarantine, bronze, silver, gold), decision records, and a light core. Its "causal" links are qualitative edge types (CAUSED, INFLUENCED, PRECEDENT_FOR) between decisions.

**[Cognee](https://github.com/topoteretes/cognee)** (Apache-2.0, Python, v1.6.3, about 32k stars) is memory for AI agents. Its public verbs are `remember`, `recall`, `improve`, and `forget`, over the classic `add` → `cognify` → `memify` → `search`. Everything is a `DataPoint`: a pydantic node whose typed fields become edges, with `identity_fields` for deterministic ids and `index_fields` for what gets embedded. Pipelines are lists of `Task`s, so any function can become a step. It has an MCP server, a feedback weight per node updated from use, an opt-in provenance ledger, LLM-judged contradiction edges, and newest-wins supersession for declared single-valued relations. Extraction is LLM-first, and its dependency footprint is heavy.

## Side by side

| | Semantica | Cognee | Our world model |
|---|---|---|---|
| Core abstraction | A staged KG pipeline, plus a context graph of decisions | DataPoint nodes through a Task pipeline | A causal graph: entities, subentities, interactions with effects and kernels, superentities |
| Edges | Labeled, qualitative | Labeled, from typed fields | Quantitative: existence, effect size, timing (delay, lag, duration), moderators |
| Dynamics and forecasts | None | None | Monte Carlo propagation, daily state-space filter, scenario mixtures, transmission paths |
| Provenance | First-class W3C PROV-O | Opt-in relational ledger, plus `source_*` fields | Append-only ledger of change sets (process, proposal, who vetted) |
| Time | Bitemporal, `state_at`, Allen intervals | created, updated, version, `valid_to` supersession | Versions, `as_of`, time states; not yet bitemporal |
| Conflicts | Typed, with severity, resolution strategies, credibility, and truth maintenance | LLM `contradicts` edges; supersede, never delete | Only by a person in review |
| Human review of facts | Policy gates on decisions | Proposals for agent skills only | Everything is staged and reviewed, ripple included |
| Extensibility | Importable modules; a step DAG; store registries | Any function → Task; adapters; community plugins | Slots: ABC + contract + registry + config |
| Agent interface | MCP, REST, CLI | MCP (remember, recall, improve, forget), REST, SDKs | REST and WebSocket; no MCP yet |
| Determinism | Deterministic core; LLM only for extraction | Extraction is LLM or GLiNER | Deterministic from seed and version |
| Dependencies | Light core, heavy extras | Heavy core | Light (pydantic, numpy, FastAPI) |

## What neither provides

The things that make the world model worth having:

- **Quantitative interactions.** Effect sizes, timing kernels, moderators, existence probabilities.
- **Propagation across orders.** Second- and third-order effects, with paths and arrival times.
- **Forecasts with uncertainty.** Rival scenarios mixed into a distribution, soft economic constraints, and pricing in.
- **Calibration against outcomes.** Scoring, track records, backtests.
- **Review of numbers.** A person approving a change to an effect size or a ripple.

In both frameworks, "causal" means an edge label, and reasoning is by rules or an LLM. So the core stays ours.

## Borrow from Semantica

| Pattern | Where it lands |
|---|---|
| Bitemporal facts: valid time vs recorded time, `state_at(date)` | [M02](modules/M02-model.md#additions-this-design-makes) fields; [M04](modules/M04-repo.md) `as_of(valid, recorded)`; leak-free backtests in [M11](modules/M11-evaluation.md) |
| PROV-O lineage: entity, activity, agent | PROV fields on `ChangeSet` and the `provenance_exporter` slot ([M04](modules/M04-repo.md)); `trace` in the context layer ([M15](modules/M15-context-layer.md)) |
| A conflict taxonomy (value, type, relationship, temporal, logical) with severity | The `conflict_detector` slot ([M05](modules/M05-intake.md)), which flags into the review |
| Trust tiers from corroboration, and source credibility | `Evidence.trust_tier`, `source_credibility` ([M02](modules/M02-model.md)) |
| Decision records linked to their causes, with "trace ancestry" and "impact" queries | Decision records citing forecasts at a version ([M11](modules/M11-evaluation.md)); `provenance_view` ([M14](modules/M14-interfaces.md)) |
| A README architecture as one arrow chain, a bullet per stage, a module reference, and Mermaid diagrams in a separate page | [README.md](README.md) and [architecture.md](architecture.md) follow it |
| A light core with heavy backends behind extras | Keep: optional extras for an LLM translator, a columnar store, and MCP |

## Borrow from Cognee

| Pattern | Where it lands |
|---|---|
| `identity_fields` → deterministic uuid5 ids, so one real actor merges across ingestions | `core.identity_key` ([M01](modules/M01-foundation.md)); `Entity.identity` ([M02](modules/M02-model.md)) |
| `index_fields`: types declare what gets embedded | Structured embeddings for the `context_retriever` and the Cobweb trees ([cognition.md F2–F5](cognition.md)) |
| Task pipelines; opt-in steps that never break ingestion | Our slots already do this. Keep the rule that optional steps (conflict detection, provenance export) only annotate and never fail a run. |
| Supersede, never delete (`superseded_by`, a reason) | `superseded_by` on interactions and time states ([M02](modules/M02-model.md)); the ledger is append-only |
| Agent verbs over MCP: remember, recall, improve | `propose`, `recall`, `ask`, `trace`, `feedback`, `status` ([M15](modules/M15-context-layer.md)) |
| A feedback weight updated from use | `feedback` → outcomes → track records ([M11](modules/M11-evaluation.md)). We score against outcomes, not ratings, wherever an outcome exists. |
| Session (short-term) memory distilled into the permanent graph | Already our working memory → long-term memory, through `day.distill` |
| The proposals pattern: before and after, rationale, confidence, status | Our staged review is a stronger version, so keep ours |

## What we don't take

- **LLM-first extraction straight into the graph.** Every change is staged and reviewed.
- **A generic graph or vector database as the system of record.** The ledger plus snapshots is the system of record. A store can be a read index later. Recall works over concept trees and analogs instead ([cognition.md](cognition.md)).
- **`forget`.** We retire items by review, and history stays.
- **Newest-wins conflict resolution.** In finance, a newer claim is not automatically a truer one. A person decides, with the conflict flagged.

## Recommendation

1. **Build the core ourselves.** That covers model, memory, repo, intake, the shared read, dynamics, learning, inference, and evaluation (M01–M13). This is mostly done; [migration.md](migration.md) cleans its boundaries.
2. **Build a thin context layer ourselves** ([M15](modules/M15-context-layer.md)). It uses Cognee's verb shape and Semantica's provenance and time model, on our ledger. It is small (it wraps services and views), and it keeps the review gate that neither framework has for facts.
3. **Optionally run Cognee upstream, as research memory, behind the import bundle.** A research agent keeps articles, filings, and analyst notes in Cognee, which is strong at unstructured documents and sessions, and emits `axelrod.import/v1` items with quotes. The world model reviews them like any import. This is the only place a framework would run as a component, and the bundle keeps it swappable.
4. **Don't depend on Semantica.** Borrow its patterns. It is pre-1.0 and fast-moving, and its value (lineage, time, conflicts) maps onto fields and a ledger we already own.

```mermaid
flowchart LR
  subgraph UP["Upstream (optional)"]
    DOCS[/"Articles · filings · notes"/] --> COG["Research memory<br/>(Cognee)"]
    COG --> RA["Research agent"]
  end
  RA -- "axelrod.import/v1<br/>items with quotes" --> WM
  subgraph WM["World model (ours) · M01–M13"]
    IN["Intake"] --> REV["Staged review"] --> LED["Ledger<br/>PROV + bitemporal<br/>(Semantica patterns)"]
  end
  subgraph CL["Context layer (ours) · M15"]
    V["recall · ask · trace<br/>propose · feedback · status<br/>(Cognee verb shape)"]
  end
  LED --> CL
  CL -- "propose → review" --> IN
  AG["Agents · analysts"] <--> CL
```

## Open questions for the review call

- Do we want MCP in the first version of the context layer, or REST only?
- Is a Cognee research memory worth its dependency weight now, or should the research agent stay a script that writes bundles?
- Should PROV export be Turtle (RDF, which Semantica can read) or JSON first?
