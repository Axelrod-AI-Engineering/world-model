# Vocabulary

Every term this repository uses, in one place. The core model's terms follow the naming guide ("Axelrod World Model
Vision", October 4, 2026) and the World Model artifact, and are canonical: a tooltip may clarify a term, but nothing
replaces it. The **Not** column lists older words for the same thing, so a search finds both.

**Naming rule.** The model's term is canonical. Where the API or a client format uses another word, the row says so.
The main case: the model's *subentity* is an *attribute* in the outward API.

<!-- toc -->
**Contents**

- [Core model](#core-model)
- [Business construction](#business-construction)
- [Evidence, inputs and sources](#evidence-inputs-and-sources)
- [Ingestion](#ingestion)
- [Lakehouse and search](#lakehouse-and-search)
- [Review and graph updates](#review-and-graph-updates)
- [State and time](#state-and-time)
- [Forecasts and coverage](#forecasts-and-coverage)
- [Outward API and MCP](#outward-api-and-mcp)
- [Core integration](#core-integration)
- [Ingestion benchmark](#ingestion-benchmark)
- [Client export (v4.1.4)](#client-export-v414)
- [Specificity rules](#specificity-rules)
- [Demo and interface](#demo-and-interface)
- [Testing and quality](#testing-and-quality)
<!-- /toc -->

## Core model

The order follows importance: the data model first, then memory, then the two processes that use them.

### Data model

The full field lists are in [design/data-model.md](design/data-model.md).

| Term | Meaning | Not |
|---|---|---|
| **Entity** | An actor or an idea: a company, an agency, a market, a person, a macro factor. It is itself a small graph of subentities. | node |
| **Subentity** | One of an entity's values, with a prior and a posterior; always shown with its entity ("Tokio Marine · share price"). The outward API calls it an *attribute*, nested under its entity | value (in the UI) |
| **Attribute** | The outward API's name for a subentity, nested under its entity: `GET /entities/{id}/attributes/{key}` | |
| **Interaction** | A directed causal relation between two subentities: its existence (a probability), its effect (sd of target per sd of source), and its kernel (delay, lag, duration) | link, edge (in the UI) |
| **Kernel** | An interaction's timing: zero before the delay, a ramp over the lag, a fade over the duration | |
| **Moderator** | A third value that scales, gates, or adds to an interaction | parameter |
| **Channel** | One direction of an interaction, as the dynamics simulate it | |
| **Superentity** | A recurring configuration of entities and interactions, with roles: a sector, a rivalry, a shock. A *pattern* lives in long-term memory; an *instance* is bound in working memory. Superentities nest. | schema, configuration, cluster |
| **Super-interaction** | The interactions between two superentity instances, abstracted | |
| **Concept** | A node of a taxonomy (an object or interaction generalization). Every item is sorted into one and inherits its priors. | kind, category |
| **Soft economic constraint** | A bound that bends a value as it nears a limit, rather than clipping it | hard rule |
| **Standard units (z)** | (link(x) − anchor) / scale: how every value is compared | |
| **Category tag** | One of eight display labels; no causal meaning | |
| **Market event** | Something that happened and was published: news, a data release, a filing, an imported item. Its publication time decides its day. | article (generic) |
| **Imported item** | One dated piece of research in an import bundle (`axelrod.import/v1`) | |
| **Graph update event** | The operations one market event stands for, with their evidence; real or hypothetical | |
| **Operation** | One change: add or retire an item, change or observe a value, reweight or annotate an interaction, propose a hypothesis, group or dissolve a superentity | op |
| **Fuzzy end** | An operation's end that names a concept ("an airline") rather than a value | abstract target |
| **Refinement levels** | generalization → entity → subentity | "a kind of thing", "one value" |
| **Hedge** | A fuzzy end held across candidates, with a probability each plus an open share | pending refinement |
| **Thesis** | A what-if question, posed as a hypothetical graph update event. It is never learned from; with no shocks, it gives a baseline forecast. | |
| **Evidence** | What a belief rests on: its source, the excerpt, when it was observed, how strong | |

### Memory

| Term | Meaning | Not |
|---|---|---|
| **Working memory** | The world now: the graph, daily deviations, channel states, the hypothesis frontier, hedges, ripple judgments, the forecast layer | |
| **Long-term memory** | What generalizes, in five parts: | |
| · **Object generalizations** | Concepts of objects, and superentity patterns | |
| · **Interaction generalizations** | Concepts of interactions | |
| · **Entity memories** | Each actor's decisions, by context | |
| · **Correlation frontier** | Co-movements with no interaction; counted, never propagated, promoted only by review | |
| · **Prior states** | Episodes (distilled days) and explanations | |
| **Hypothesis frontier** | Open hypotheses about interactions and about actors' decisions, ranked by informational value | hypotheses board |
| **Episode · analog** | A distilled day · a recalled episode | |
| **Open node** | What the graph does not explain yet, drawn on every node | |

### Learning (five stages)

| Term | Meaning | Not |
|---|---|---|
| **Learning** | Folding a vetted event into memory: intake → learning · working memory → learning · long-term memory → human review → commit | |
| **Shared read** | The read learning and inference share: parse, classify, recall, bind, prefill, analyze | shared process |
| **Ripple · order · transmission path** | The moves a change sets off downstream · the fewest interactions from the shock to a value · the most significant path of that length | hop |
| **Fold** | Correct a value from a report, and update each interaction into it by how much it explains | |
| **Distill** | The day's consolidation of working memory into long-term memory | consolidation |
| **Staged change · proposal** | An event's whole learning, run on a copy, waiting for review | |
| **Ripple judgment** | A reviewer's probability that a value's ripple arrives | |
| **Commit · version** | One change set in the ledger; any version can be reopened or compared | |

### Inference (seven stages)

The stages are mutually exclusive and collectively exhaustive. Each answers one question.

| Term | Question it answers | Not |
|---|---|---|
| **Pose a thesis** | What is asked? | ask a question (as a label) |
| **Isolate** | What can the shock reach? (the **networks**: superentities, a residual network, a **context network** for watched values) | isolate the networks |
| **Isolated prediction** | How does each network respond alone? | simulate |
| **Distributed prediction** | How do the networks move together? (**scenarios**: rival choices × open hypotheses, weighed once, each coupled) | couple; simulate and couple |
| **Unify** | One answer from rival stories: the scenarios mixed by weight | weigh and unify; average |
| **Read out** | What moves, when, by which path, and why (orders, paths, groups, constraints, the brief) | read out and explain |
| **Evaluate** | Did it come true? (score at the horizon; track records) | score against outcomes |
| **Branch** | A copy of a committed version a thesis runs on; never merged | forecast layer |

### Architecture

| Term | Meaning |
|---|---|
| **Slot** | A swappable algorithm: an ABC, its records, a contract, and implementations chosen by config |
| **Contract** | A slot's process, cadence, inputs, outputs, reads, writes, and when it runs |
| **Port** | The ABC side of a slot |
| **Service** | A command workflow: review, update, thesis, structure |
| **View** | A pure read model: state → DTO |
| **Context layer** | The agent-facing verbs: recall, ask, trace, propose, feedback, status |
| **Session** | What the API serves: services, views, a tracer, a lock, capabilities |
| **Learn · Predict** | The two views: Learn for analysts who teach the model, Predict for clients who ask it |

## Business construction

The objects that carry a company from a macro driver to its accounts. Model: `world_model/src/axelrod_wm/model/construction.py`.
Method: [construction/README.md](construction/README.md).

| Term | Meaning |
|---|---|
| **Business construction** | A company's composition, operating states, named paths, transitions, and financial mappings, built as model objects. |
| **Composition (view)** | One view of a business (segments, regions, customer location, production location, products, investment assets, …) on one accounting basis and unit. Its parts add to the total through accounting links, with an explicit residual and eliminations. |
| **Additive / non-additive view** | Whether the parts sum to the total. A non-additive view (a capital roll-forward, overlapping product lines) is shown but not summed. |
| **Residual** | The explicit part a view's listed parts leave out (other businesses, corporate, an unexplained difference). |
| **Eliminations** | Intersegment amounts removed so the parts add to the consolidated total. |
| **Driving / reconciling view** | When several views share one total, one *drives* it (its parts propagate into the total); the others *reconcile* (they are checked against the total, never added). |
| **Matrix (cross-classified) view** | A total split two ways at once (segments × lines), with cells and row and column totals. |
| **Operating state** | A value the paths need that is not an account: landed cost, dealer inventory, claims severity, deposit beta. |
| **Named path** | A connected chain of interactions from a trigger to a named financial endpoint. Parallel responses are *branches* that share a source. |
| **Branch** | A parallel step in a path: one of several responses to the same state. |
| **Counter-path** | A path whose effect offsets another (retention against repricing, a hedge against an exposure). |
| **Transition** | A link as a business step: mechanism and actor; condition and its observable; timing (onset, build, persistence, recognition); evidence by claim; breaker; next state; unresolved inputs. |
| **Mechanism** | What happens in the step, and its direction, in words. |
| **Condition / observable** | What must hold for the step to act / the measurable thing that proves it. |
| **Breaker** | What stops, caps, delays, or reverses a step. |
| **Next state** | The operating state or financial output the step leads to. |
| **Calibration** | Whether a link's size is known: *calibrated* (estimated, propagates) or *uncalibrated* (sign and mechanism known, size unknown; no number, not zero). |
| **Accounting link** | `edge_type: accounting`: a part adds to its total with a fixed weight (the part's scale over the total's). Learning never refits it. |
| **Identity link** | An exact relation that is not a sum: a product (NII = balance × rate), a ratio (NIM = NII / assets), or a weighted average. Its weight is derived, not estimated. Being added. |
| **Stock-flow** | A stock that accumulates flows (capital += profit − distributions; AUM += flows + market). Being added. |
| **Reduced form** | A single link that summarizes a path (yen → operating profit), kept beside the structural steps and never added to them. |
| **Reconciliation** | The check that an additive view's parts, residual and eliminations equal its total, at the model's levels (medians) and at reported actuals, within 0.5%. |
| **Baseline** | A dated actual for a value, from the company's own material, kept locally as an `axelrod.import/v1` bundle. |
| **Gap register** | Per company: each missing or wrong piece of structure, what exists, what to add, the evidence needed, the conclusions it affects, the test, and its category (missing construction, missing calibration, incorrect mapping, export omission, retrieval omission). |
| **Generalization trace** | A trace of a development no path was written for, through every link, to show the structure reaches a financial endpoint or where it stops. |
| **Trace** | Every route from a change in one value to a company's financial endpoints, with uncalibrated steps and stops named (`context/construction.trace`). |
| **Completion report** | Per company: each gap's outcome (built and verified, built but uncalibrated, blocked by a named input, not built), and what is still unsupported. |
| **Corporate action** | A declared split (ratio, effective date) on an entity; per-share observations after it convert to the pre-split basis at import. |
| **Overlap guard** | At import, when one item or day observes parts of two views of one total, only one view's parts fold, so nothing counts twice. |

## Evidence, inputs and sources

| Term | Meaning |
|---|---|
| **Evidence basis** | What supports each claim of a link, kept apart: existence, direction, magnitude, timing. |
| **Support grade** | Where a claim comes from: *documented* (the company's disclosure), *guidance* (management's forward statement), *broker* (attributed research), *model* (an inspected workbook formula), *assumption* (the builder's, stated), *inferred* (follows from represented facts), *unknown*. |
| **Input (InputNeed)** | Something a transition needs to be sized or checked, with a status. |
| **Input status** | *found and connected* (in the material and bound to the model) · *found but not connected* · *not yet reviewed* · *not disclosed in reviewed sources* (lists what was searched). |
| **Source id** | A neutral tracked label (`ty.wb`, `tm.r1`) that resolves only locally to a document. Never a firm or file name. |
| **Source catalogue** | Local `sources.json`: source id → document, kind, publication date, period, basis, read state, proof limits. Exported as its own file. |
| **Citation** | Local `citations.json`: for a link or value, the source id, the location (sheet and cell, table and row, page and paragraph), and the passage. |
| **evidence_refs** | In the export, a relationship's resolved citations: source id, document, location, passage. |
| **Citation gaps** | Unresolved source ids and material claims without a citation, listed by the check and the export. |
| **Material claim** | A claim whose existence, direction, magnitude or timing rests on documented, guidance, broker or model support, and so must be cited. |
| **Input search** | `world_model/scripts/construction/inputs.py`: searches the supplied material for each missing input before it may be declared missing. |

## Ingestion

Pipeline: [ingestion/docs/pipeline.md](../../ingestion/docs/pipeline.md).

| Term | Meaning |
|---|---|
| **Document** | A stored file (PDF, DOCX, PPTX, XLSX, HTML, CSV, Markdown, text, JSON). Its id is a content hash. |
| **Parse** | Turning a file into text with pages, sheets and rows (PDFium for PDFs). |
| **Chunk** | A passage of a document (a sentence group, or one table row as a sentence), the unit of indexing and citation. |
| **Mention** | A recognized name of an entity or value in a chunk. |
| **Gazetteer** | The index of every name and alias the model knows, used to recognize mentions. A value name's head word can become a keyword, so names are chosen with care. |
| **Signal** | A claim read from a chunk: *observe* (a level), *move* (a change), *support* / *contradict* (an existing link), *link* (a proposed new link). Each carries its quote and location. |
| **Precision rules** | An observation is a reported current level of the right basis; a forecast is not a move; a revision is; history is not the present. |
| **Bundle** | `axelrod.import/v1`: dated items, each with its source, summary, entities, and signals. What ingestion produces and import consumes ([the contract](../../ingestion/docs/contract.md#the-import-bundle)). |
| **Item** | One dated piece of research in a bundle. |
| **LLM step** | An optional reader that proposes only what the deterministic extractor misses. Off unless a provider key is set; cached. |
| **Determinism** | The same file gives the same document, chunks, signals and bundle; the same bundle imported into the same state gives the same version. |

## Lakehouse and search

| Term | Meaning |
|---|---|
| **Lakehouse** | A SQLite catalog plus raw files, partitioned per tenant, on the deployment's volume. |
| **Event time / ingested at** | When a document's content happened or was published / when it was stored. Documents are indexed by both. |
| **Search modes** | *keyword* (BM25), *prefix* (names, then chunks), *semantic* (embeddings), *graph* (named nodes and neighbours), *hybrid* (reciprocal-rank fusion; default). |
| **Hit** | A search result: kind (chunk, entity, attribute), document, ref, score, text, and why. |

## Review and graph updates

| Term | Meaning |
|---|---|
| **Import** | Folding a bundle's items into the model, one graph update per item, in event-time order. |
| **Review** | Each proposed change waits for a person, who approves or rejects it. Nothing approves automatically over the API (`review: "auto"` was removed on Oct 18); the demos' `--auto-approve` is for local runs. |
| **Proposal** | A proposed graph update awaiting a decision: approve, or reject with a note. |
| **Late item** | An item dated before the model's last closed day. |
| **Rewind** | Returning the model to a past version, to review or replay from there. |

## State and time

How the API applies these: [design/api.md §2](design/api.md#2-the-domain-model).

| Term | Meaning |
|---|---|
| **Version** | A committed state of the world model. Every write that changes it makes a new version. |
| **State hash** | A content hash of a version, checked on restore. |
| **State identity** | What every read names: scenario, version, state hash, as-of, latest version, and the model's clock. |
| **Pinned read** | A read at `version=N` or `as_of=<time>`: what the model knew then. |
| **Clock** | The model's own date: the last day it has closed. |
| **Publication time / effective time / recorded time** | When a document was published / the period a claim is about / when the model recorded it. |
| **Lookahead** | Using information before it was published. Pinned reads and point-in-time evaluation exclude it. |

## Forecasts and coverage

| Term | Meaning |
|---|---|
| **Forecast** | A thesis run forward: targets with ranges, transmission by order, a scenario table. |
| **Transmission path** | The chain a shock travels, by order, from cause to outputs. Outputs sit at the end, and an *echo* repeats an output a chain carries past. |
| **Expected paths** | `expected_paths.yaml`: the channels, signs and output directions Sally's research says each forecast must show. |
| **Unquantified** | The uncalibrated links a forecast reaches, listed with sign and mechanism: represented, size unknown. |
| **Calculation coverage** | A forecast's account of itself: *contributed* (links that added a size), *excluded* (with why), *blocking inputs* (by status), and per target the share of routes fully quantified. |
| **Brief** | A forecast's summary: timing, exposures, indicators, evidence, coverage. |

## Outward API and MCP

Reference: [api/README.md](api/README.md).

| Term | Meaning |
|---|---|
| **Outward API** | REST under `/v1/world-models/{id}/*` on the Railway service, for other agents and core. Its contract is `world_model/docs/api/openapi.yaml`. Its nouns differ from the code's: an *attribute* is a subentity, a *relationship* an interaction, an *event* a market event, a *change* a proposal, a *simulation* a forecast. |
| **Caller** | Who is acting within an organization: the principal's `sub` (an org user, a key's caller name such as `core`, or a login), recorded with its kind, `azp`, `act` and `jti` on every write in the audit log, and as a change's `proposed_by` and `decided_by`. |
| **Organization** (was *tenant*) | Owns world models, documents and credentials (Axelrod, a client firm), never a user; it comes from the credential (a token's `org`, a key's org, a login). The `world_models` registry names each model's organization; another organization's model answers 404. A login's organization is its username unless `WORLD_MODEL_OWNERS` maps it (`default` with no logins). |
| **API key** | A static scoped credential: a `caller:key:org[:scope+scope]` entry in `WORLD_MODEL_API_KEYS`, sent as `Authorization: Bearer <key>`. With no scopes listed it reads only (`world_model:read`); it never carries `changes:approve`. |
| **Service token** | A short-lived ES256 JWT core mints per call ([design/core-mcp-auth.md](design/core-mcp-auth.md)), verified against a trusted issuer's JWKS (`WORLD_MODEL_TRUSTED_ISSUERS`). |
| **Principal** | Who a v1 request acts as, from a verified credential: a core-minted service token (a person, maybe through an agent host named by `act`), a static scoped key (a service), or a session (a person signed in here). The old `X-Axelrod-On-Behalf-Of` header is gone. |
| **Scope** | What a credential may do, named `resource:action` with three verbs (read, create, approve) plus admin: `world_model:read`; `documents:create`, `changes:create`, `simulations:create`; `changes:approve` (people only); `admin`. |
| **Envelope** | `{"data", "meta"}` for every answer (`meta`: `request_id`, the `version` read, and a list's `limit` and `next_cursor`); every error an RFC 9457 problem (`application/problem+json`) with a stable `code`. |
| **Version header** | `X-Axelrod-API-Version: 1` on every response. |
| **Erid kind** | The node kind core's contracts use: company, kpi, factor. |
| **erid (the API resource)** | The unified world model, `/v1/erid`: the whole graph, for internal staff, beside the per-client world models (core calls the world model state Erid). |
| **Compartment** | A client's view of the unified world model, defined as a focused world is: its companies, the players upstream of them, and one link downstream (`sally_focus`). Reads under `/v1/erid` take `compartment`. |
| **Idempotency key** | A client's `Idempotency-Key`, or a document's or bundle's content: the first answer to a create, kept forever in the lakehouse catalog. |
| **MCP server** | `/mcp`, `axelrod-world-model`: the same operations as tools over stateless Streamable HTTP, with the same key. |
| **Tool annotations** | read-only, additive, destructive, idempotent, open-world hints on each tool. |

## Core integration

| Term | Meaning |
|---|---|
| **Core** | `Axelrod-AI-Engineering/core`, the product's main service. Never written to from this repo. |
| **Core patch** | `world_model/integrations/core/`: a patch that adds the `world_model_*` tools to core's MCP catalog under core's sign-in. |
| **Canonical identity** | A node in core's own store (`world_model_state_nodes`) that the scenario canvas binds and pins. |
| **Expert writeback** | Core's design for human-reviewed world model changes; no agent approves its own change. |
| **Service keys (core side)** | `AXELROD_WORLD_MODEL_SERVICE_KEYS`: `org_id=key` entries, one per organization. |

## Ingestion benchmark

[ingestion/docs/bench.md](../../ingestion/docs/bench.md).

| Term | Meaning |
|---|---|
| **Gold set** | Hand-annotated claims on a selection of documents. |
| **Recall** | Share of gold claims the extractor finds. |
| **Located** | Found at the right sentence or table row, however read. |
| **Precision** | Share of predictions that are correct, from gold matches plus a labels file. |
| **Labels file** | An independent labeler's verdict (correct or incorrect) on predictions that match no gold claim. |
| **Dev / test split** | Documents split by content hash: tune on dev, check on test. |
| **Blind set** | Claims annotated independently on documents the gold never used. The final number. |
| **Negative control** | A document with no claims; anything read from it is a false positive. |

## Client export (v4.1.4)

The client's own schema; its field names are not ours to rename.

| Term | Meaning |
|---|---|
| **Domain pack (036)** | The model in the client's format: companies, relationships, transmission paths, the financial bridge. |
| **Registry entry (020)** | The pack's row in the client's registry. |
| **Evidence pack** | The current state, and one per forecast, with values and calculation coverage. |
| **Manifest / load order** | The files of an upload set, in the order the client's agents load them. |
| **Financial bridge** | The compositions, with each one's reconciliation. |
| **dependency_type** | `causal` or `accounting_identity`. |
| **represented_uncalibrated** | A relationship's status when its size is unknown; its numeric fields are empty. |
| **schema_gaps** | What the client's schema cannot yet hold, listed in the export. |

## Specificity rules

[design/specificity.md](design/specificity.md). The standard distilled from the client reviewer's feedback.

| Rule | In short |
|---|---|
| **R1 No jumps** | A change reaches the accounts through the business, the actor and the operating outcome; a direct link is only a labelled reduced form. |
| **R2 Defined values** | View, basis, unit, period, currency and geography. |
| **R3 Transitions** | Every link says what it means. |
| **R4 Sizes from evidence** | Or uncalibrated: never guessed, never zero. |
| **R5 Reconciliation** | Views add up; views of one total are never added together. |
| **R6 Sources resolve** | Every material claim cites a document, location and passage. |
| **R7 Searched inputs** | "Missing" only after a search. |
| **R8 Kinds of statement** | Actual, guidance, estimate, model, assumption, inference, history: kept apart. |
| **R9 Coverage** | A forecast says what it could not calculate. |
| **R10 Generalization** | Tested on a development it was not written for. |
| **R11 Most specific value** | A claim about a part is recorded on the part. |

## Demo and interface

[guides/gui.md](guides/gui.md), [guides/demos.md](guides/demos.md).

| Term | Meaning |
|---|---|
| **Scenario** | A world plus its script, seeds, theses and settings (`small_demo`, `prod_demo`, `sally_demo`, …). |
| **Learn / Predict** | The two modes: watch the model learn from events, or pose forecasts on a blank canvas that brings in their entities. |
| **Example** | A scripted step of a demo that isolates one feature. |
| **Import dialog** | Where a bundle or a raw document is read, its graph update drawn, and its items imported for review. |
| **Graph update view** | The canvas drawing of what an item would change: observed and moved values, proposed links dashed, supported links ticked. |
| **Admin** | The demo's controls for resets and logins. |

## Testing and quality

[../tests/README.md](../tests/README.md), [docs/development.md](../../docs/development.md).

| Term | Meaning |
|---|---|
| **Coverage gate** | `scripts/coverage_gate.py --member <name>`: every source file of a workspace member at 100% lines and branches, from that member's own tests ([development](../../docs/development.md#coverage)). |
| **World view** | What ingestion reads of a world model: entities, values, and links as frozen records with a canonical JSON form (`axelrod_ingest.contract.world_view`; [the contract](../../ingestion/docs/contract.md#the-world-view)). |
| **Slow / browser tests** | Scenario runs and Playwright checks, selected with `--runslow`. |
| **Conventions sweep** | `world_model/tests/service/test_conventions.py`: every route documented, keyed, versioned, enveloped, strict, and in the schema. |
| **Client data** | `data/` (client content, sources, working data, exports): gitignored, never committed or uploaded. |
