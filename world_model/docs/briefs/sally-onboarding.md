# Sally onboarding: what we built, and what core needs from it

Status as of 2026-10-17, with the API and auth facts brought up to v1 (Oct 18). Owner: Karthik (world model). For
Zsolt (MCP), Kedar (LLM harness), and whoever owns core's `contracts/v1/world_model.py`. This is a dated brief: the
living docs are the [API reference](../api/README.md), [ingestion/docs/pipeline.md](../../../ingestion/docs/pipeline.md),
[construction/](../construction/README.md), and [design/core-mcp-auth.md](../design/core-mcp-auth.md).

<!-- toc -->
**Contents**

- [1. Summary](#1-summary)
- [2. Who owns what](#2-who-owns-what)
- [Briefs](#briefs)
- [3. What the onboarding built](#3-what-the-onboarding-built)
- [4. Where it stands](#4-where-it-stands)
- [5. What to expose to core](#5-what-to-expose-to-core)
- [6. Asks, by person](#6-asks-by-person)
- [7. Decisions still open](#7-decisions-still-open)
- [8. What never leaves this repo](#8-what-never-leaves-this-repo)
- [9. Next steps](#9-next-steps)
<!-- /toc -->

## 1. Summary

Sally is our first design partner: a PM running roughly fifty Japan, US, and EU names on the elevated-rates and
yen-carry themes. Over October 15–17 we turned her research into a working world model. It covers her companies and
the macro drivers she watches, and each forecast carries a transmission path she can check against her own research.
Her files reach the model through an ingestion pipeline with a measured benchmark, and the model is served to other
agents through a documented REST API and an MCP server. It exports in her team's v4.1.4 world-model format. After her
team reviewed the export, we added business construction: compositions, operating paths with explicit transitions,
and uncalibrated links that are represented but carry no size.

The world model stays a separate service from core. Core and its agents reach it over HTTP with a per-caller key,
and a ready patch puts its tools into core's own MCP catalog (`integrations/core/`). The briefs below say, for each
person, what was built, how it reaches core, and how to use it. Section 5 is the full list of what core consumes, and
section 7 the decisions still open.

## 2. Who owns what

| Person | Owns | Touches the world model through |
|---|---|---|
| Karthik | The world model and everything in this repo: model, ingestion, lakehouse, API, MCP server, exports | — |
| Zsolt | MCP in core: the catalog, OAuth, and which servers core mounts | `/mcp` on this service, mounted from core |
| Kedar | The LLM harness: how agents get context, call tools, and cite | v1 reads (`/graph`, entities, relationships), `/exports/v4.1.4`, simulations, construction and traces |
| Manav | The user surface in core | The scenario canvas's canonical bindings (section 5.3) |
| Emily | Domain content and the client relationship | The taxonomy, client feedback, and the client's v4.1.4 schema |

## Briefs

### Zsolt: MCP

**What we built.**
- The world model is an MCP server of its own: `/mcp` on the service, built on the official `mcp` 2.x SDK the way
  core's is, with 27 `world_model_*` tools over the v1 API (Oct 18: [../api/](../api/README.md), contract
  [api/openapi.yaml](../api/openapi.yaml)). None decides a change.
- A patch for core, [`integrations/core/0001-world-model-service-mcp-tools.patch`](../../../integrations/core/README.md),
  made against core `main` after #67 and #72. It extends #67's seam, `register_mcp_world_model_tools`, with 20
  `world_model_*` tools on `/v1/world-models/{id}` (`search_canonical` is unchanged):
  - reads: world models, a world model, graph, entities, entity, attribute, concepts, search, construction (JSON or a
    markdown page), trace, simulation, brief, v4 export, documents, bundle, changes;
  - three writes that only propose: `world_model_simulate`, `world_model_ingest_source`, and
    `world_model_propose_changes`, whose changes wait for a person's review.

**How it reaches core.**
- Each core tool authenticates the org user from core's MCP token, as every core tool does. It then calls the
  service with that organization's key. The on-behalf-of header is gone (Oct 18): identity will come from a
  core-minted service token ([../design/core-mcp-auth.md](../design/core-mcp-auth.md)), which the service already
  verifies; the patch does not mint one yet.
- Errors are core's `"code: detail"` tool errors, from the service's RFC 9457 problems.
- The tools are in `McpDocGroup.WORLD_MODEL`, with titles, read-only and additive annotations, and output schemas,
  so #74's generated tool reference lists them under "World model".
- `world_model_ingest_source` takes a project source that the host uploaded with `sources_create_upload`, so the
  file never passes through the conversation.
- No tool approves a world-model change. A person approves each one in review, as core's expert-writeback design
  requires.

**How to use it.**
- Apply the patch with `git am` on a core branch.
- Set `AXELROD_WORLD_MODEL_SERVICE_URL` and `AXELROD_WORLD_MODEL_SERVICE_KEYS` (`org_id=key`, or `*=key`).
- On our side, add `core:<key>:<org>` to `WORLD_MODEL_API_KEYS`.
- Results so far:
  - core's MCP tests pass (117, including 5 new), and the module is at 100% line and branch coverage;
  - the tools ran end to end against a live world model service.
- `world_model/tests/service/test_core_integration.py` in our repo keeps the patch in step with our routes.

### Kedar: the LLM harness

**What we built.**
- Point-in-time reads: every answer names its `state` (version, hash, clock), and `version=` or `as_of=` pins a read.
- Search with chunk-level citations.
- Simulations with transmission by order, and `unquantified_relationships` for those a shock reaches whose size is unknown.
- A company's business construction, and a trace from any change to the company's financial endpoints.
- The model in the client's v4.1.4 format, which is what the client's own agents read.

**How it reaches core.**
- Through core's MCP catalog (Zsolt's brief) when the harness runs inside core.
- Otherwise directly: REST under `/v1/world-models/{id}/*`, or our `/mcp`, with a scoped key.

**How to use it.**
- For context: `world_model_graph` (depth 1–2) on the names in the question, then `world_model_construction` or
  `world_model_trace` for a company, and `world_model_export_v4` for the full pack.
- Pass the `version` from the first read to every later read, so a cited answer can be reproduced.
- Report `unquantified_relationships` and null effects as "represented, size unknown", never as zero.
- To learn from a file: `world_model_ingest_source`, then `world_model_propose_changes`; a person approves each change.
- [../api/](../api/README.md) has every route, parameter and error code.

### Core's contract owner and Manav: the canvas

**What we built.**
- Normalized reads (Oct 18, v1): `/graph` returns entities with their attributes nested and relationships
  (`source_attribute_id`, `target_attribute_id`, `type`, `effect`, `confidence`, `kernel`), and each relationship has
  its own evidence records.
- Every read of the model can be pinned by `version` or `as_of`, and names the `state_hash` it read.

**How it reaches core.**
- Not yet. The scenario canvas reads canonical nodes from core's own `world_model_state_nodes` table and pins them by
  content hash (section 5.3).

**How to use it.**
- Decide how nodes reach `CanonicalRead`: core calls `/graph`, or approved changes are published into core's store
  (decision 7.1).
- Extend `Edge.relation` for causal links, and agree how a value maps to a `KpiNode`.
- Until then, the canvas can call `world_model_graph` through MCP for display, and record our `state_hash` with its
  snapshot.

### Emily: the client

**What we built.**
- Sally's world on the V1.0 taxonomy.
- Her expected transmission paths, checked by a test.
- The v4.1.4 export.
- Business construction for Toyota and Tokio Marine, answering the reviewer's feedback: compositions, operating paths
  with transitions, and calibration status.
- An ingestion pipeline with a measured benchmark.
- In the demo, **Import → Read a document…** takes a file through ingestion and draws the graph update it would
  make on the canvas: values observed or moved, proposed links dashed, and supported links ticked. Each change shows
  the sentence or table row it came from, and nothing changes until it is imported and approved.

**How it reaches core.** Through the same API and MCP as above. The client's agents read the v4.1.4 export.

**How to use it.**
- `world_model/scripts/imports/export_context.py` writes a fresh export.
- `docs/construction/<company>.md` (client root) holds each company's gap register and its completion report.

## 3. What the onboarding built

Pull requests are stacked. Merging to `main` deploys, so nothing below merges without Karthik.

| When | PR / branch | What it added |
|---|---|---|
| Oct 15 | #12–#15 (merged) | Sally's demo: daily research, a scenario table, the world model as agent context, and the transmission path on the canvas |
| Oct 16 | #16 `feature/export-world-model` | Export in the client's v4.1.4 layout: a domain pack, a registry entry, and evidence packs |
| Oct 17 | #17 `feature/sally-taxonomy` | Sally's world on the V1.0 taxonomy (+7 entities), plus fixes from a full walk-through |
| Oct 17 | #18 `feature/ingestion-api` | Ingestion from files, a lakehouse, and the outward API (REST + MCP) with per-caller keys |
| Oct 17 | #19 `feature/ui-notes` | UI notes: values shown in their units, fuller transmission paths, no bars or superentities on the canvas |
| Oct 17 | `feature/bench-ready` (stacked on #18, includes #19) | The ingestion benchmark, extraction tuning, coverage, Sally's expected transmission paths, business construction, the graph-update view of an ingested document, and the core MCP integration patch |

### 3.1 Ingestion, lakehouse, API ([pipeline.md](../../../ingestion/docs/pipeline.md), [../api/](../api/README.md))

- **Upload → bundle → review → graph update.** A file (PDF, DOCX, PPTX, XLSX, HTML, CSV, Markdown, text, JSON) is
  stored, parsed, chunked, indexed, and read into an `axelrod.import/v1` bundle. Importing the bundle proposes one
  graph update per item, and a person approves or rejects each one. (Automatic approval, `review: "auto"`, was
  removed with v1 on Oct 18.)
- **Lakehouse.** A SQLite catalog plus raw files, siloed per organization, on the Railway volume. Documents are indexed by
  ingestion time and event time, so late-arriving data folds into the next day and is flagged `late`.
- **Search.** Keyword (BM25), prefix, semantic (bge-small, CPU), graph, and hybrid (reciprocal-rank fusion).
- **Determinism.** Ids are content hashes. The same file always gives the same document, chunks, signals and bundle,
  and the same bundle imported into the same state always gives the same version and hash.
- **The LLM step is optional.** It proposes only what the deterministic extractor misses, and it is off until a
  provider key is set. Its answers are cached, so reading a file again never calls it again.

### 3.2 Ingestion benchmark ([bench.md](../../../ingestion/docs/bench.md))

- `ingest/bench.py` and `ingestion/scripts/ingest_bench.py` score extraction against a hand-built gold set: recall
  overall, by signal type and by verdict; whether each match is located (the right sentence or table row); precision
  from a labels file; and the time spent in each stage.
- Files are split into dev and test by content hash. Negative controls are files with no claims, so anything
  extracted from them counts as a false positive.
- The final number comes from a blind set, annotated independently on documents the gold set never used. Tuning
  rounds work on one half; the other half stays sealed until the end.
- The pipeline was rebuilt so it runs to completion on the whole corpus:
  - PDFium replaces pypdf;
  - table rows become sentences, and long chunks are capped;
  - the quadratic pass over pairs of causal claims is bounded;
  - negation and boilerplate filters are added;
  - each document keeps one claim per value.

  Sally's corpus now ingests in about 25 seconds.

### 3.3 Transmission paths that match Sally's research

- `<client root>/scenarios/sally_demo/expected_paths.yaml` writes down, from her research, which channels each forecast must
  draw and with which sign, and which way each output must move. `world_model/tests/scenario/test_sally_expected_paths.py` holds
  the forecasts to it.
- Outputs sit at the end of the path. An output that a chain carries past is echoed in the output column, so the
  path reads left to right.

### 3.4 Business construction (reviewer feedback on the export)

The client's reviewer found that our company packs jumped from a macro driver straight to sales or profit. The
model now carries the business in between ([model/construction.py](../../src/axelrod_wm/model/construction.py)):

| Object | What it is |
|---|---|
| `Composition` | One view of a business (reporting segments, regions, customer vs production location, products, investment assets, …) on one accounting basis. Its parts add to the total through accounting links, with a residual and eliminations. Overlapping views are never added together |
| `NamedPath` | A connected chain of interactions from a trigger to a named financial endpoint. Parallel responses are branches |
| `Transition` (on an interaction) | The link as a business step: mechanism and actor, condition and its observable, timing (onset, build, persistence, recognition), evidence kept apart for existence, direction, magnitude and timing, the breaker, the next state, and the inputs still missing |
| `calibration: uncalibrated` | The mechanism and its sign are represented, but its size is unknown. It carries no numbers and adds nothing to a simulation, and a forecast that reaches it lists it under `unquantified` |
| `edge_type: accounting` | A part adds to its total. The weight is fixed and never refit, so learning cannot flip an identity |

Three methods let the missing inputs slot in as they arrive ([../construction/](../construction/README.md)):

- `world_model/scripts/construction/calibrate.py` turns a disclosed sensitivity into a link's size, in log space for lognormal
  values, and edits that one link in place;
- a declared stock split converts per-share observations to the model's pre-split basis at import;
- when an item or a day observes parts of two overlapping views of one total, imports fold only one view, so a
  change is never counted twice.

`validate_construction` checks the structure. `context/construction.py` makes each company's readable view and
traces any change through every link to the company's financial endpoints, which is how a reviewer tests the
construction on a development it was not written for. The v4 export now carries a financial bridge, the
business-construction transmission paths, the transitions in the canonical relationship properties, and a list of
the schema's gaps. Toyota and Tokio Marine are built first. Each has a gap register, its construction file, and a
validation test.

## 4. Where it stands

| Area | State |
|---|---|
| Tests | Unit, integration, service and scenario suites pass. The slow and browser tests are rerun before the PR opens |
| Coverage | The whole repository is at 100% lines and branches (1,885 tests), and `coverage-floor.json` now holds it there. The slow scenario and browser tests pass (17) |
| Ingestion recall | The blind half is the final number: 35% (6 of 17), up from 29%. Observed levels from tables are recalled two times in three, and causal claims not at all. The tuned splits read higher (49% dev, 44% test, 79% on the tuned blind half), and that gap is overfitting. Precision, measured by an independent labeler, rose from 62% to 90% on dev and from 58% to 77% on test, without losing a gold match. The rules: an observation is a reported current level, and a forecast is not a move. What remains is mostly whether a current-year estimate counts as a level: the gold says yes, the labeler says no. The blind half was partly exposed, so the next blind set needs fresh documents. [pipeline.md](../../../ingestion/docs/bench.md) has the details |
| Transmission paths | Every channel Sally's research requires is drawn with the right sign, and every output moves the expected way |
| API | Every route and MCP tool is tested for success, auth, and each error code. Service and MCP code are at 100% |
| Deploy | The image builds with `uv sync --frozen --no-dev --extra semantic`. Railway deploys need Karthik added as a project Admin |

Benchmark figures are aggregates over the client's corpus. The per-file results stay with the client's data.

## 5. What to expose to core

In priority order. P0 is needed for core to use the world model at all.

### 5.1 P0: the service and its keys

- **Base URL** of the Railway service, plus a credential for each caller: a core-minted service token, or a scoped
  key (`WORLD_MODEL_API_KEYS`: `caller:key:org[:scopes]`, never `changes:approve`). Every write is recorded with its
  actor in the audit log, and the organization decides which world models the credential sees.
- **REST, v1** (Oct 18) under `/v1/world-models/{id}/*`: 61 operations, written first as an OpenAPI 3.1 contract
  ([api/openapi.yaml](../api/openapi.yaml)) and tested against it. The old `/api/world-model` routes are retired.
- **Conventions:** RFC 9457 problems, `{"data", "meta"}` envelopes, cursors, `Idempotency-Key`, `202` and a job for
  long work, `ETag` and `If-Match` on decisions, bitemporal fields, `X-Request-Id` and `X-Axelrod-API-Version: 1`.

### 5.2 P0: MCP for Zsolt

- `/mcp` serves `axelrod-world-model` over stateless Streamable HTTP. It is built on the official `mcp` 2.x SDK, as
  core's own server is, and takes the same credentials. Each of its 27 tools calls the matching v1 route in
  process, so answers, auth and errors are the same.
- Read-only tools carry `readOnlyHint`, and writes (ingest, propose changes, simulate) do not. No tool decides a
  change.
- **In core's own catalog:** the patch in [integrations/core](../../../integrations/core/README.md) re-publishes the tools
  from core's `/mcp`, under core's sign-in, for each org user (Zsolt's brief). This is the recommended route.
- Alternatively, core can mount our `/mcp` the way it mounts EODHD (`MCPServerStreamableHttp` with the key in
  core's settings). The snippet is in [../api/](../api/README.md#mounting-it-from-core).
- `world_model_graph` answers what core reserved as `world_model.query` (point-in-time reads).

### 5.3 P1: canonical identities for the scenario canvas

Core's canvas reads canonical nodes from its own store (`world_model_state_nodes`, through `CanonicalRead`) and pins
them into an immutable snapshot whose id is a content hash. To bind the canvas to this world model:

- **Identity mapping.** `/graph` returns entities (with a `type`) and their attributes, and relationships
  (`source_attribute_id`, `type`, `target_attribute_id`). Two things don't fit core's contract yet:
  - Core's `Edge.relation` allows only `issues`, `has_kpi`, `classified_by` and `part_of`. Our causal edges are
    `type: "causal"`, with `effect`, `confidence` and a `kernel`, and accounting relationships are a natural
    `part_of`. Core's contract needs a causal relation, or causal edges need to live outside `Edge`.
  - `KpiNode` needs `metric_type` and `period`. Our attributes carry a unit, an attribute kind and, after construction, a
    view and an accounting basis. We need an agreed mapping.
- **Pinning.** Every read names its version (`number`, `state_hash`, `committed_at`), and any read can be pinned
  with `version=` or `as_of=`. Core's snapshot can record our `state_hash` next to its own content hash, so a pinned
  experiment can always re-read the exact world model it was built on.
- **How core gets the nodes.** Either core's `CanonicalRead` calls our `/graph`, or an adapter publishes our approved
  updates into core's store as `ApprovedWorldModelEvent` deltas (`NodeUpsert` / `EdgeUpsert`). The second keeps the
  canvas working when this service is down, but it makes two copies of the state. This is decision 7.1.

### 5.4 P1: context for Kedar's harness

- **`/exports/v4.1.4?simulation=`** gives the model, and a simulation if one is named, in the client's v4.1.4 format. That
  format is what the client's own agents read.
- **`/entities/{id}/construction?format=markdown`** gives a company's readable construction, and **`/traces`**
  gives the routes from a change to the company's endpoints. Agents should cite these objects, not paraphrase them.
- **`unquantified_relationships`** lists the uncalibrated relationships a simulation reaches: their sign, mechanism, and the attributes
  downstream of them. The harness should show these as "represented, size unknown", never as zero and never as a
  number.
- **Search** (`/search`, hybrid by default) gives passage-level citations: `document_id`, `ordinal`, `text`, and
  `why`; a name hit is an `entity` or an `attribute`, with its `entity_id`.
- **Attributes nest in their entity** (Oct 18, a breaking change before anyone adopted the API): what the API called a
  value is an *attribute* of an entity, with a full id (`toyota.operating_profit`) and a key (`operating_profit`).
  `/graph`, `/entities`, and `/entities/{id}` return entities with their attributes nested; relationships keep full
  attribute ids and name their entities.
- **Writes go through review.** An agent that reads a file posts it to `/documents` (or posts a bundle to
  `/bundles`) and proposes its changes (`POST /changes`). A person approves or rejects each change, with `If-Match`;
  the service refuses a decision from a key or an agent-driven token. This matches core's
  expert-writeback design, in which no agent approves its own change.

### 5.5 P2: later

- Per-model grants, once core has roles ([design/core-mcp-auth.md §9](../design/core-mcp-auth.md#9-open-questions)).
- A push channel (webhook or event) when a version is committed, so core can refresh pinned views.
- Construction for the rest of Sally's names, after Toyota and Tokio Marine are reviewed.

## 6. Asks, by person

**Zsolt (MCP)**
1. Review and apply the patch in `integrations/core/`: re-export through core's catalog, under core's sign-in.
2. Add the world-model tools to the MCP Server Phase 2 catalog in Notion.
3. Confirm the auth design in [../design/core-mcp-auth.md](../design/core-mcp-auth.md): core mints a short-lived service token per call (decision 7.3).

**Kedar (harness)**
1. Choose which reads the harness uses for context (`/graph` at depth 1–2, `/exports/v4.1.4`, construction), and the
   budget for each.
2. Handle `unquantified_relationships` and null effects in answers, and pin each read by `version` so a cited
   answer can be reproduced.
3. Agree that agents only propose: a person decides every change (no `review: "auto"`).

**Core's contract owner**
1. Add a causal relation to `Edge` (or a separate causal-edge record), and agree on the value → `KpiNode` mapping.
2. Decide how canonical nodes reach `CanonicalRead`: by calling our API, or by publishing approved events into
   core's store (decision 7.1).

## 7. Decisions still open

1. **Which state is authoritative.** Today this service is authoritative for the causal model, and core's
   `world_model_state_nodes` is authoritative for company, security and KPI identity. We need one owner per kind of
   record, and one direction of sync.
2. **The service boundary.** We recommend keeping the world model a separate service, reached through REST and MCP,
   because it owns heavy state (snapshots, a lakehouse, embeddings) and deploys on its own. The alternative is to
   vendor it into core's process.
3. **Tenancy and auth.** Settled on our side (Oct 18, [design/core-mcp-auth.md](../design/core-mcp-auth.md)): the
   organization comes from the credential, each world model belongs to one organization, and core will mint a
   short-lived service token per call that names the org user. Until core mints them, the patch sends one key per
   organization (`org_id=key`, with `*` as the default). Still open: how core mints the
   token and who holds its key.
4. **Key rotation.** A caller may hold two keys at once, so a key rotates by overlap: add the new entry, move the
   caller, remove the old one. Who holds core's key, and how often it rotates, is still open.
5. **The Notion MCP catalog** is the single draft of core's next tools, so the world-model tools belong there and
   not in a second list. The patch's tool table is the draft to copy in.

## 8. What never leaves this repo

- The client's research, workbooks, exports, and the reviewer's feedback stay local and gitignored. That covers
  `data/` (client content, sources, working data, exports), and the meeting and feedback PDFs. Tracked files hold
  structure, generic business mechanisms, and synthetic, round priors, but never the client's figures, quotes or file
  names.
- Expert calls never record individuals' names.
- Credentials live only in Railway's environment variables.
- Nothing in this repo writes to core. Core was read from a read-only clone.

## 9. Next steps

1. Finish the Toyota and Tokio Marine construction, regenerate Sally's export, and send it for a second review.
2. Causal claims: a pass of general rules (more causal verbs, clause shapes, sectors as ends) added 10 predictions, 9 of them correct, but recalled no further gold claims. The remaining misses are recognition (aliases), references back to earlier sentences, and alias shadowing. Annotate a fresh blind set. Precision is now measured, and it is 77% on test after the precision round.
3. Rerun the full suite with coverage, raise the floor, run the slow and browser tests, and open the
   `feature/bench-ready` PR.
4. Walk Zsolt and Kedar through the briefs, and settle decisions 7.1–7.3. Zsolt applies the core patch.
5. Get Karthik Admin on the Railway project so the dev deploy can carry the new routes.
