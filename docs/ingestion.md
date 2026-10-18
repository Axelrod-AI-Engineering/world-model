# Ingestion and the lakehouse

How an uploaded file becomes proposed graph updates, and where everything it produces is kept. For the routes that
drive it, see [api.md](api.md).

**Contents**

- [The pipeline](#the-pipeline)
- [Two times: event and ingestion](#two-times-event-and-ingestion)
- [Extraction: rules first, an LLM only where the rules are silent](#extraction-rules-first-an-llm-only-where-the-rules-are-silent)
- [Determinism](#determinism)
- [The lakehouse](#the-lakehouse)
- [Search](#search)
- [Limits and next steps](#limits-and-next-steps)

## The pipeline

```
file ─▶ store ─▶ parse ─▶ chunk ─▶ index ─▶ recognize ─▶ extract ─▶ bundle ─▶ import ─▶ review ─▶ commit
        lake     text     ≤700ch   FTS5 +   model's      rules,     axelrod.   one graph  a person   a new
        (hash)   +pages   chunks   vectors  names        LLM opt.   import/v1  update per  (or auto)  version
                                                                                item
```

| Step | Code | What it does |
|---|---|---|
| Store | `lake/sqlite.py` | Keeps the bytes once per content hash, per login. The same file uploaded twice is one document |
| Parse | `ingest/parse.py` | PDF (pypdf, page by page), DOCX, PPTX, XLSX (values, not formulas), HTML, CSV, Markdown, text, JSON. A JSON file that is already an import bundle passes through unchanged |
| Chunk | `ingest/chunk.py` | Splits text into sentences (aware of abbreviations, bullets, and decimals), then packs them into chunks of up to 700 characters. A chunk never crosses a paragraph or a page, so every quote can be traced to its page |
| Index | `lake/sqlite.py`, `lake/embed.py` | Adds each chunk to a stemmed keyword index, an unstemmed prefix index, and an embedding |
| Recognize | `ingest/gazetteer.py` | Finds the model's own names in each chunk: entities by name and alias (possessives and plurals included), and values by their own phrase ("Bund 10Y yield"), or by a head word ("rates", "yield") when the nearest entity has exactly one such value |
| Extract | `ingest/extract.py`, `ingest/llm.py` | Turns sentences into signals (below) |
| Bundle | `ingest/pipeline.py` | One item per chunk with signals: headline, the chunk as summary, tickers, the signals with exact quotes. Validated as `axelrod.import/v1` and stored |
| Import | `sim/imports.py` | Folds items into the model one graph update each, in event-time order. Each update is reviewed before it commits |

Nothing changes the world model before the import step, and nothing commits before review. A bundle can be read,
compared, and discarded without trace.

## Two times: event and ingestion

Every document carries two times:

- **Event time** is when the content is about. It is the date given with the upload (`published_at`), else the
  first date in the opening text, else a date in the file name (`2026-10-05_note.md`), else the ingestion time.
- **Ingestion time** is when the file arrived.

Bundles fold in by event time, so the model learns in the order things happened, not the order files arrived. A
document can arrive after the model has closed its day: a note dated September 1, uploaded after October 1 has been
processed. Its items are **late**. They fold into the next day the model processes, with their own event time kept,
and the import lists them under `late`. Both times can be listed and filtered (`GET /documents?order=ingested_at`).

## Extraction: rules first, an LLM only where the rules are silent

The rules read each sentence that names a value:

| Pattern | Example | Signal |
|---|---|---|
| A level | "raised its policy rate by 25bp **to 1.25%**" | observe `boj.policy_rate` = 1.25 |
| A move with a size | "net interest income **rose 4%**" | move up, sized |
| A direction alone | "Brent **climbed**" | move up, half a standard deviation |
| Inverted quotes | "the yen **strengthened**" while the value is USD/JPY | move down |
| A causal claim on a known link | "lower Bund yields **weigh on** UniCredit's net interest income" | support the link (or contradict it, if the sign disagrees) |
| A causal claim between two values with no link | the same, when no link exists | propose a new link |

Each signal keeps its exact quote and its span in the text. A sentence gives at most one signal per value: a level
wins over a move, and a move over a bare direction.

**The LLM step is off by default.** When a provider and key are set (`WORLD_MODEL_LLM_PROVIDER`), it reads only the
chunks that name model values but where the rules found nothing. It is asked for the same signal schema, and every
answer is checked: the ids must exist, the quote must appear verbatim in the chunk, and a support must name an
existing link. LLM signals carry lower confidence (0.5) and are tagged `llm:<model>` in the item's notes. Answers are
cached by (provider, model, prompt version, prompt, and the model's names), so reading a document again never calls
the LLM again and gives the same bundle.

## Determinism

The same file read against the same model gives the same bundle, byte for byte. This is tested
(`tests/ingest/test_determinism.py`).

- **Ids are content hashes.** Document id = sha256 of the bytes. Bundle id = a digest of its canonical JSON.
- **Every list is sorted.** That covers chunks, mentions, signals, items, search hits (ties broken by id), and
  every SQL query.
- **The extractor and parser are versioned** (`ingest-1.0`, `parse-1.0`), and each bundle records both.
- **Embeddings.** Tests use a hashing embedder, which is exact and needs no model. The deploy uses bge-small through
  ONNX on one thread, with vectors rounded to 6 decimals.
- **The LLM** runs at temperature 0 and is replayed from its cache.

## The lakehouse

`WORLD_MODEL_LAKE_DIR` (default `var/lake`; on Railway, the volume) holds:

```
lake.sqlite3                SQLite (WAL): the catalog and the indexes
<login>/raw/<doc-id>.<ext>  the files as uploaded
```

| Table | Holds |
|---|---|
| `documents` | One row per file per login: hash, name, type, source, the two times, status, and parse metadata |
| `texts` | The extracted text and the parser that produced it |
| `chunks`, `chunks_fts`, `chunks_prefix` | Chunks with their offsets and pages; the stemmed and unstemmed full-text indexes |
| `mentions` | Which entity and value each chunk names |
| `embeddings` | One float32 vector per chunk, with the embedder's name |
| `bundles` | Each bundle, whole, with its source documents and extractor version |
| `imports` | Each import of a bundle: when, by whom, the graph update it started, and which items |
| `llm_cache` | LLM answers by digest |

Logins are tenants: a key sees only its login's documents. Storage sits behind an interface (`lake/store.py`,
`LakeStore`), so a warehouse such as Postgres, or Parquet on object storage, can replace SQLite without changing the
pipeline or the API.

## Search

Search runs over what has been ingested and over the model's own names. It has five modes: keyword (BM25), prefix,
semantic, graph (the nodes named and their neighbours, then the chunks that mention them), and hybrid
(reciprocal-rank fusion of keyword, semantic, and graph). This is the retrieval layer for the agents' RAG: each hit
gives its document, chunk, and text, and says why it matched. See [api.md](api.md#search).

## Limits and next steps

- **Scanned PDFs** have no text layer: they parse to nothing, and the result warns that no claims were found. An OCR
  step would sit inside `parse`.
- **Tables.** XLSX and CSV are read as text rows. They are not yet mapped to series observations.
- **Names the model does not know** are not proposed as new entities. Recognition is against the model's own names,
  which keeps extraction exact. New entities are added to the taxonomy deliberately.
- **Scale.** Semantic search compares vectors in Python, which is fine for thousands of chunks. Beyond that, the
  `LakeStore` interface is where an ANN index (sqlite-vec, pgvector) would go.
