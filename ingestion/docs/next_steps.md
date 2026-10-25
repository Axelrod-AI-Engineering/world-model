# Ingestion: state and next steps

A handoff for whoever picks up ingestion next: what it does today, what is built downstream of it, what is not, and the
work in order of priority. How the pipeline works is in [pipeline.md](pipeline.md), where its output is kept and how it
is searched is in [lake.md](lake.md), and what it exchanges with the world model is in [contract.md](contract.md).

<!-- toc -->
**Contents**

- [Where it stands](#where-it-stands)
- [What is built downstream](#what-is-built-downstream)
- [Next steps, in priority order](#next-steps-in-priority-order)
- [Working rules](#working-rules)
<!-- /toc -->

## Where it stands

Ingestion turns a file into proposed changes to the world model. It never changes the model itself: a person or agent
reviews each proposed change before it is applied. The table below gives each step that exists, how it works and where
it lives. Ingestion paths are under `ingestion/src/axelrod_ingest/`, and world-model paths are under
`world_model/src/axelrod_wm/`.

| Step | How it works | Where |
|---|---|---|
| Store | Each file's bytes are kept once per content hash, under its organization (tenant), in `<lake>/<org>/raw/`. A catalog row records the hash, name, source, event time and ingestion time. | `pipeline.py` (`Ingestor.store_file`), `lake/sqlite.py` |
| Parse | PDF, DOCX, XLSX, HTML, CSV, Markdown and text become plain text plus table cells. The charset is detected from the BOM, the declared encoding, UTF-8, or a fallback. A scan with no text layer is read by tesseract where it is installed; results are cached by content. | `parse.py`, `tables.py`, `encoding.py`, `ocr.py` |
| Type and date | Classifies the document (filing, report, transcript, or an excluded index or shell page) and checks it against the pack's manifest. Its event time is resolved by a fixed order of evidence, and the period it reports on is kept beside it. | `sources.py`, `dates.py` |
| Languages and units | Chinese, Japanese and Korean text is split into tokens. Currencies and scales are normalized, and a bare ¥ is read as yen or yuan from evidence in the document. | `cjk.py`, `units.py`, `text.py` |
| Duplicates | Copies of one disclosure across language or accounting basis are grouped (`shared_origin`), with one primary, so a fact is counted once. | `dedupe.py` |
| Split and index | The text is split into passages with their offsets and pages. Each passage goes into two SQLite FTS5 indexes (one stemmed for keyword search, one unstemmed for prefix search) and gets one embedding. | `chunk.py`, `lake/sqlite.py`, `lake/embed.py` |
| Recognize | A gazetteer built from the model's own entity and value names and aliases is matched over tokens: longest match first, never overlapping, with case rules for acronyms. Generic phrases ("share price") are resolved to the entity that owns them. Mentions are stored per passage. | `gazetteer.py`, `contract/world_view.py` (the model's names, produced by `intake/world_view.py`) |
| Extract | Rules read levels, moves and table figures, with the exact quote and its offsets. Where a passage names the model's entities but the rules find nothing, an optional LLM step (Anthropic or OpenAI) proposes signals. These are validated against the text and the model's ids and cached by digest, so a rerun replays byte-for-byte. | `extract.py`, `llm.py` |
| Bundle | The signals become an `axelrod.import/v1` bundle: dated items, each with signals and quotes. It is validated and stored with its source documents and extractor version. | `pipeline.py`, `contract/bundle.py` |
| Packs | A folder with a manifest is ingested into a lake. This produces a report on each file and a determinism digest that must match on a rerun. | `pack.py`, `ingestion/scripts/ingest_pack.py` |
| Measure | Speed and extraction precision and recall are scored against a gold set, with a blind half. | `bench.py`, `ingestion/scripts/ingest_bench.py`, [bench.md](bench.md) |

How the world model uses it:
- **Contract and boundary.** The two sides share only the contract: the bundle schema and the read-only world view
  (`contract/`). Ingestion never imports the world model, and `ingestion/tests/test_boundary.py` enforces it.
- **Setup.** The service creates one lake (`SQLiteLake`, at `WORLD_MODEL_LAKE_DIR`, which is the volume on Railway) and
  one `Ingestor` at startup, in `api/app.py`.
- **Swappable storage.** All storage goes through the `LakeStore` interface in `lake/store.py`.

**Determinism.** Every query has an explicit `ORDER BY`, and every set is sorted before it is iterated. Embeddings are
run single-threaded and rounded to 6 decimals, and LLM answers are cached by digest. The hashseed regression test is
`world_model/tests/integration/test_hashseed_determinism.py`.

## What is built downstream

### Upload and review: built

The `/v1` routes are in `api/v1/routes_ingest.py`, and the MCP tools are in `api/mcp.py`.

| What | Route | How |
|---|---|---|
| Upload | `POST /v1/world-models/{id}/documents` | Returns 202 and runs `Ingestor.ingest_many` as a background job, with an idempotency key. Results come back in event-time order, the order they fold into the model. |
| Read documents | `GET …/documents`, `…/{doc}`, `…/{doc}/chunks`, `…/{doc}/content` | Returns the catalog, passages and text straight from the lake. |
| Read again | `POST …/documents/{doc}/bundles` | Extracts a stored document again against the model as it is now, because the model's names and links change as it learns. |
| Agent bundles | `POST …/bundles`, `GET …/bundles`, `…/{bundle}/items` | Stores and reads bundles that an agent wrote by hand, under the same schema. |
| Import | `POST …/changes` (one proposed change per bundle item), then `…/changes/{change}/approvals` or `/rejections` (`api/v1/routes_work.py`) | Each item of a bundle becomes a market event on its own date. The `structured` translator turns its signals into a proposed graph update. Signals whose ends are not in the graph are dropped and reported. Per-share values are converted across splits, and overlapping additive views are kept from double counting. A person approves each change. |
| Preview | the Import dialog | Draws the graph update a document would make, before anything changes. |

The import code is in `sim/imports.py` and `intake/structured.py` (the translator), with `intake/overlap.py` and
`model/corporate_actions.py`. The preview is `api/ingest_view.py`.

### Retrieval: built and in use

`lake/search.py` (`Searcher`) has five modes:

| Mode | How it ranks |
|---|---|
| `keyword` | FTS5 with Porter stemming, ranked by BM25: every word first, then any word if that finds nothing |
| `prefix` | the unstemmed FTS5 index, with the last word as a prefix, plus the model's entities and values whose names start that way |
| `semantic` | cosine similarity between the query's embedding and every passage's, computed exactly as one NumPy matrix product over the tenant's vectors, held in memory until they change |
| `graph` | the entities and values the query names, their neighbours through the model's relationships, then the passages that mention them |
| `hybrid` | the default: reciprocal-rank fusion (k = 60) of keyword, semantic and graph |

Embeddings (`lake/embed.py`), chosen by `WORLD_MODEL_EMBEDDER`:
- **`fastembed`:** IBM granite-embedding-small-english-r2 (open, from a US developer), 384 dimensions, ONNX on the CPU inside the service, so no text leaves the
  deploy.
- **`hashing`:** an exact 256-bucket hash of words and word pairs, with no model. The tests use it, and it is the
  fallback when fastembed is not installed.

Where it is served:
- **HTTP:** `GET /v1/world-models/{id}/search?q=…&mode=…&limit=…`
- **MCP:** the `world_model_search` tool, which calls that route.

What a result carries and who sees it:
- Each hit gives its document, passage ordinal, text, event time and any entity it names, and says why it matched.
- Lists are ordered by score, then by document and position, so the same query always returns the same results.
- Organizations are tenants: a credential sees only its own documents.

Construction agents already use search to find the passages a construction cites. They follow the construction skill in
`world_model/skills/world-model-construction/` and check their work with `world_model/scripts/construction/check.py`.

### Superentity labels: built

Superentities are the nested groups the UI draws. Each is named by its top keywords under class-based TF-IDF over its
members' names, kinds and sectors, with its sibling groups as the classes. An optional temperature-0 LLM relabel
(`ClusterLabels`, `POST /api/clusters/relabel`) is cached in the lake by a hash of the members' ids, so a label never
changes between runs. Building the view only reads that cache. The code is `api/hierarchy.py`.

### Extraction recall: low

The rules are precise, but their recall is low. In particular, they read causal claims in prose (one value moving
another) at 0 of 7 on the blind half of the gold set. Signals are pointers for a person or an agent to follow, not a
finished model.

### Not built

- **Grounded answering.** No route takes a question, retrieves passages and model state together, and returns an
  answer that cites both. Search is the "R" of RAG; the generation step does not exist yet.
- **A context or memory layer for agents.** The architecture keeps it separate from the causal model, but it is still a
  design only. See [the architecture](../../docs/architecture.md).
- **A link from the lake to the evaluation suite.** The inner-loop tests (`evaluation/inner_loop*.py`, with tools in
  `evaluation/inner_loop_tools.py`) answer from frozen excerpts, not from the lake, so they barely measure the model.
  In the last round, only 5 of 100 answers cited a model object.

## Next steps, in priority order

### 1. Grounded answering

**Why:** search already exists, and this step makes it an answer that can be checked. It is also what the evaluation
suite needs in order to measure the model rather than the excerpts.

**Scope:**
- Add a `/v1` route and an MCP tool. They take a question, run hybrid search, read the model objects the hits name,
  and return an answer.
- Every sentence of the answer cites a passage (document and ordinal) or a model object.
- Use a temperature-0 call with cached answers, the same pattern as `llm.py`, so a rerun is identical.
- Add a variant of the inner-loop suite that answers through this route instead of from frozen excerpts.

**Done when:** the variant runs end to end, and its scorecard reports how often answers cite model objects next to
the pass rate.

### 2. Extraction recall

**Why:** recall is the weakest number in [bench.md](bench.md), and constructions are written largely by hand because of it.

**Scope**, in order of expected gain:
1. Map tables to whole series, not single cells.
2. Resolve references back to an earlier noun ("this rise", "the increase").
3. Add aliases for the ends of causal claims.
4. Prefer the longer, entity-specific phrase when two overlap.

**Done when:** each change is measured on the blind half of the gold set, with no loss of precision.

### 3. Draft constructions from the lake

**Why:** building a company construction today means an agent reads search results and writes YAML. Most of that work
is sources, citations and baselines, which the lake already holds.

**Scope:**
- Build a tool that drafts those parts of a company construction from its pack: the source list with duplicate groups
  folded, citations to passages, and baseline values from table series.
- A drafted claim stays uncalibrated until it is cited, and nothing is added without evidence. In particular, the tool
  never adds a link between two companies that no source documents.

**Done when:** the draft passes `check.py --sources` for a new company with no hand edits to the source list.

### 4. Scale and storage

**Why:** semantic search is exact: it scores every passage. Since Oct 24 it does so as one NumPy matrix product over
a tenant's vectors, held in memory. That is under a millisecond per query at 15,000 passages (it was 0.4 s in pure
Python), with identical results. An exact scan still grows with the lake, and every service process holds its own copy
of the vectors, so millions of passages need an index.

**Scope:**
- Put an approximate nearest-neighbour index (sqlite-vec, or pgvector) behind `LakeStore`.
- If several services need the lake, move it to Postgres behind the same interface.

The pipeline and the API do not change.

**Done when:** search over 1M passages answers in under a second, with the same results as exact search on the test set.

### 5. Multilingual depth

**Why:** most non-English filings are only read for figures today.

**Scope:**
- Switch to a multilingual embedder, so semantic search works over Chinese, Korean and Japanese passages. This is the
  cheapest gain.
- Install OCR language data for scans in those languages.
- Read moves in Chinese and Korean prose. A move is a statement that a value rose or fell.

**Done when:** a query in English finds the matching passage in a non-English duplicate of the same disclosure.

### 6. Live ingestion

**Why:** client packs are loaded by hand today.

**Scope:**
- Add scheduled pulls of new filings and releases into the lake.
- Each document keeps its two times: when it was published (event time) and when we ingested it. The model can then be
  shown as it stood on any past date.
- Ingestion agents only monitor runs and fix failures. They never change the deterministic pipeline's output by hand.

### 7. A repository of its own

**Why:** the boundary is already enforced. Once the contract stops changing, ingestion can move out of the monorepo.

**Scope:**
- Move `ingestion/` to its own repository.
- Publish `axelrod_ingest.contract` as a versioned package that both sides pin.

## Working rules

- **Determinism.** Sort anything iterated from a set. An LLM step is temperature 0 and cached by digest. A pack run
  ends with a digest that must match on a rerun.
- **Untrusted input.** Treat every uploaded or downloaded file as untrusted data. Run any Python that reads it with
  `-I`, and keep it in its own directory.
- **No client content in the repository.** Packs, lakes, exports and answer keys live under `data/`, which is
  gitignored. Tests use invented documents only.
- **Coverage.** Keep 100% line and branch coverage of the member, with no pragmas.
- **Held-out answers.** Nothing reads the held-out answer keys except the grader.
