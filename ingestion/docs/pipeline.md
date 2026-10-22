# The ingestion pipeline

How an uploaded file becomes proposed graph updates: the steps, the two times every document carries, rules-first
extraction, and why every step is deterministic. Where everything it produces is kept is [lake.md](lake.md); how it
is measured is [bench.md](bench.md); the format it produces is [contract.md](contract.md). For the routes that drive
it, see [the API reference](../../world_model/docs/api/README.md).

<!-- toc -->
**Contents**

- [The pipeline](#the-pipeline)
- [Two times: event and ingestion](#two-times-event-and-ingestion)
- [Extraction: rules first, an LLM only where the rules are silent](#extraction-rules-first-an-llm-only-where-the-rules-are-silent)
- [Determinism](#determinism)
- [Limits and next steps](#limits-and-next-steps)
<!-- /toc -->

## The pipeline

```
file ─▶ store ─▶ parse ─▶ chunk ─▶ index ─▶ recognize ─▶ extract ─▶ bundle ─▶ import ─▶ review ─▶ commit
        lake     text     ≤700ch   FTS5 +   model's      rules,     axelrod.   one graph  a person   a new
        (hash)   +pages   chunks   vectors  names        LLM opt.   import/v1  update per  (or auto)  version
                                                                                item
```

Paths in the Code column are under `ingestion/src/axelrod_ingest/`. Ingestion stops at the bundle; the import and review that follow are the
world model's.

| Step | Code | What it does |
|---|---|---|
| Store | `lake/sqlite.py` | Keeps the bytes once per content hash, per organization. The same file uploaded twice is one document |
| Parse | `parse.py` | PDF (PDFium, page by page), DOCX, PPTX, XLSX (values, not formulas), HTML, CSV, Markdown, text, JSON. A JSON file that is already an import bundle passes through unchanged |
| Chunk | `chunk.py` | Splits text into sentences (aware of abbreviations, bullets, and decimals), then packs them into chunks of up to 700 characters. A chunk never crosses a paragraph or a page, so every quote can be traced to its page |
| Index | `lake/sqlite.py`, `lake/embed.py` | Adds each chunk to a stemmed keyword index, an unstemmed prefix index, and an embedding |
| Recognize | `gazetteer.py` | Finds the model's own names in each chunk (read from the [world view](contract.md#the-world-view), not from the model): entities by name and alias (possessives and plurals included), and values by their own phrase ("Bund 10Y yield"), or by a head word ("rates", "yield") when the nearest entity has exactly one such value |
| Extract | `extract.py`, `llm.py` | Turns sentences into signals (below) |
| Bundle | `pipeline.py` | One item per chunk with signals: headline, the chunk as summary, tickers, the signals with exact quotes. Validated as `axelrod.import/v1` and stored |
| Import | `world_model/src/axelrod_wm/sim/imports.py` (the world model) | Folds items into the model one graph update each, in event-time order. Each update is reviewed before it commits |

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
| The cause after the effect | "margins were **hurt by** the stronger yen", "NII **benefits from** higher rates", "USD/JPY fell **after** the BoJ's hike" | support, with the connector's sign |
| An entity or a sector as an end | "a weaker yen lifts **Toyota**", "higher **yields** lift **Japanese insurers**" | support for the one value whose link has the stated sign, for each company of the sector |
| A channel reported as what happened | "a weaker yen **lifted** Toyota's profit" | support, and a move for each end (a mechanism, "lifts", gives none) |

A causal word used as a noun ("a 25bp increase") or a predicate ("yields are 5bp lower"), the object of another verb
("measures to support the yen"), and a view the author doubts ("we push back on the notion that ...") join nothing.

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
(`ingestion/tests/ingest/test_determinism.py`).

- **Ids are content hashes.** Document id = sha256 of the bytes. Bundle id = a digest of its canonical JSON.
- **Every list is sorted.** That covers chunks, mentions, signals, items, search hits (ties broken by id), and
  every SQL query.
- **The extractor and parser are versioned** (`ingest-1.0`, `parse-1.0`), and each bundle records both.
- **Embeddings.** Tests use a hashing embedder, which is exact and needs no model. The deploy uses bge-small through
  ONNX on one thread, with vectors rounded to 6 decimals.
- **The LLM** runs at temperature 0 and is replayed from its cache.

## Limits and next steps

- **Scanned PDFs** have no text layer: they parse to nothing, and the result warns that no claims were found. An OCR
  step would sit inside `parse`.
- **Tables.** XLSX and CSV rows are read cell by cell: header rows give periods, labels give units, and a current
  column wins. Tables are not yet mapped to whole series.
- **Causal claims** in prose (one value moving another) are the weakest part, at 0 of 7 on the blind half. What is
  left is mostly recognition: an end named by a word the model has no alias for, an anaphor ("this rise"),
  a longer phrase that shadows a shorter one ("domestic P&C profit" is only one insurer's), and an entity whose
  links leave more than one value with the stated sign.
- **Names the model does not know** are not proposed as new entities. Recognition is against the model's own names,
  which keeps extraction exact. New entities are added to the taxonomy deliberately.
- **Scale.** Semantic search compares vectors in Python, which is fine for thousands of chunks. Beyond that, the
  `LakeStore` interface is where an ANN index (sqlite-vec, pgvector) would go.
