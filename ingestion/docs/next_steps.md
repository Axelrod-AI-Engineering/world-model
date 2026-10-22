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

Ingestion takes a file (PDF, DOCX, XLSX, HTML, CSV, Markdown, text, or a scan) and does the following:

1. Stores the file in the lakehouse, under its organization.
2. Parses and types it.
3. Splits it into passages.
4. Finds the model's own names in the passages.
5. Proposes graph updates as an import bundle, `axelrod.import/v1`.

Every step is deterministic. The same file and model give the same bundle, and a hashseed regression test guards this.

| Area | State |
|---|---|
| Formats | PDF, DOCX, XLSX, HTML, CSV, Markdown and text are all read. Scans are read by OCR (tesseract) where it is installed, English by default. |
| Languages | English in full. Chinese and Korean are read for levels and table figures, not for moves. Japanese yen and Chinese yuan are told apart by evidence. |
| Document metadata | Type and exclusion reason, the manifest entry and hash check, published date and reporting period, and duplicate groups across language and accounting basis (`shared_origin`). |
| Extraction | Rules first. An optional, cached LLM step runs only where the rules find nothing. Recognition is against the model's own names and aliases, and new entities are never proposed. |
| Packs | A folder with a manifest becomes a lake, a report on each file, and a determinism digest (`ingestion/scripts/ingest_pack.py`). |
| Boundary | Ingestion never imports the world model; `tests/test_boundary.py` enforces it. CI requires 100% line and branch coverage of the member. |

## What is built downstream

### Retrieval: built and in use

Search over the lake has five modes:

| Mode | How it ranks |
|---|---|
| `keyword` | BM25 |
| `prefix` | prefix matching |
| `semantic` | bge-small embeddings, run on the CPU inside the service, so no text leaves the deploy |
| `graph` | the nodes the query names and their neighbours, then the passages that mention them |
| `hybrid` | the default: reciprocal-rank fusion of keyword, semantic and graph |

Where it is served:
- **HTTP:** `GET /v1/world-models/{id}/search?q=…&mode=…&limit=…`
- **MCP:** the `world_model_search` tool.

What a result carries and who sees it:
- Each hit gives its document, passage, text and event time, and says why it matched.
- Results are deterministic.
- Organizations are tenants: a credential sees only its own documents.

Construction agents already use search to find the passages a construction cites.

### Extraction into the model: built, with low recall

Bundles are imported as graph updates through `/v1`. The rules are precise, but their recall is low. In particular, they
read causal claims in prose (one value moving another) at 0 of 7 on the blind half of the gold set. Signals are pointers
for a person or an agent to follow, not a finished model.

### Not built

- **Grounded answering.** No route takes a question, retrieves passages and model state together, and returns an
  answer that cites both. Search is the "R" of RAG; the generation step does not exist yet.
- **A context or memory layer for agents.** The architecture keeps it separate from the causal model, but it is still a
  design only. See [the architecture](../../docs/architecture.md).
- **A link from the lake to the evaluation suite.** The inner-loop tests answer from frozen excerpts, not from the lake,
  so they barely measure the model. In the last round, only 5 of 100 answers cited a model object.

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

**Why:** semantic search compares vectors in Python, which is fine for thousands of passages but not for many packs.

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
