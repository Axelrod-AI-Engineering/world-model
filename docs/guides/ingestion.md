# Ingestion and the lakehouse

How an uploaded file becomes proposed graph updates, and where everything it produces is kept. For the routes that
drive it, see [the API reference](../api/README.md).

<!-- toc -->
**Contents**

- [The pipeline](#the-pipeline)
- [Two times: event and ingestion](#two-times-event-and-ingestion)
- [Extraction: rules first, an LLM only where the rules are silent](#extraction-rules-first-an-llm-only-where-the-rules-are-silent)
- [Determinism](#determinism)
- [The lakehouse](#the-lakehouse)
- [Search](#search)
- [Benchmarks](#benchmarks)
- [Limits and next steps](#limits-and-next-steps)
<!-- /toc -->

## The pipeline

```
file ─▶ store ─▶ parse ─▶ chunk ─▶ index ─▶ recognize ─▶ extract ─▶ bundle ─▶ import ─▶ review ─▶ commit
        lake     text     ≤700ch   FTS5 +   model's      rules,     axelrod.   one graph  a person   a new
        (hash)   +pages   chunks   vectors  names        LLM opt.   import/v1  update per  (or auto)  version
                                                                                item
```

| Step | Code | What it does |
|---|---|---|
| Store | `lake/sqlite.py` | Keeps the bytes once per content hash, per organization. The same file uploaded twice is one document |
| Parse | `ingest/parse.py` | PDF (PDFium, page by page), DOCX, PPTX, XLSX (values, not formulas), HTML, CSV, Markdown, text, JSON. A JSON file that is already an import bundle passes through unchanged |
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
<org>/raw/<doc-id>.<ext>    the files as uploaded
```

| Table | Holds |
|---|---|
| `documents` | One row per file per organization: hash, name, type, source, the two times, status, and parse metadata |
| `texts` | The extracted text and the parser that produced it |
| `chunks`, `chunks_fts`, `chunks_prefix` | Chunks with their offsets and pages; the stemmed and unstemmed full-text indexes |
| `mentions` | Which entity and value each chunk names |
| `embeddings` | One float32 vector per chunk, with the embedder's name |
| `bundles` | Each bundle, whole, with its source documents and extractor version |
| `imports` | Each import of a bundle: when, by whom, the graph update it started, and which items |
| `llm_cache` | LLM answers by digest |

Organizations are tenants: a credential sees only its organization's documents. Storage sits behind an interface (`lake/store.py`,
`LakeStore`), so a warehouse such as Postgres, or Parquet on object storage, can replace SQLite without changing the
pipeline or the API.

## Search

Search runs over what has been ingested and over the model's own names. It has five modes: keyword (BM25), prefix,
semantic, graph (the nodes named and their neighbours, then the chunks that mention them), and hybrid
(reciprocal-rank fusion of keyword, semantic, and graph). This is the retrieval layer for the agents' RAG: each hit
gives its document, chunk, and text, and says why it matched. See [../api/](../api/README.md#search).

## Benchmarks

`ingest/bench.py` and `scripts/bench/ingest_bench.py` measure two things on a corpus, the way uploads arrive (each
file's bytes and name, nothing else).

**Speed, per stage.** Every result carries seconds per stage (`IngestResult.timings`: store, parse, chunk, index,
embed, extract, llm, bundle). The report gives each stage's total, share, mean, p50, and p95, and throughput in
documents, pages, and megabytes per second.

**Extraction, against a gold set.** A gold signal is a claim a careful reader took from one source file. It is
annotated with the file, the page, the verbatim evidence, a verdict (supported or partly), and where it lives:

- a sentence or a table row, which counts toward recall;
- an inference across sentences or a chart, which is reported but not counted.

A prediction agrees with a gold signal from the same file in these cases:

| Gold signal | Agrees when |
|---|---|
| Observe | Same value, level within 2% or 0.05 |
| Move | Same value, same direction |
| Support or link | Same two ends |

The report gives these measures:

- **Recall**, overall, by signal type, and by verdict.
- **Located**: the right value was found, however it was read.
- **Precision**: from gold matches plus a labels file, since the gold set is a selection, not every claim.
- **Misses**, each with what was read instead.

**Guarding against overfitting.** Documents are split by the hash of their path:

| Split | Share | Use |
|---|---|---|
| dev | two thirds | For tuning |
| test | one third | For checking (`--split`) |

A blind set, annotated independently from documents the gold never used, gives the final number. The first round of
tuning showed why: recall on the tuning split rose threefold while the held-out split did not move.

```bash
uv run python scripts/bench/ingest_bench.py --corpus data/<client>_data --dirs <folders> \
    --items <gold items folder> --gold <gold annotations> --labels <labels> --split dev --out data/<client>_data/bench/run
```

**Results on the first client corpus (Oct 17, aggregates only).**

| Set | Recall | What it measures |
|---|---|---|
| Gold, dev split | 49% | the tuning split |
| Gold, test split | 44% | held out from the first tuning round |
| Blind half A | 79% | tuned on in the third round, so no longer a held-out measure |
| Blind half B | 35% (6 of 17) | the final number; never tuned on |

On half B, observed levels read from tables are recalled two times in three. Causal claims (links, support, and moves)
were not recalled at all. Every prediction that matched a labelled claim was correct, and there were no false
positives on negative controls. Precision is measured separately, on the gold files (below).

**A round on causal claims (Oct 18).** The rules above for connectors, sectors, bare yields, entity ends, and reported
channels were written from sentence structure, with invented test sentences, and checked on the gold set: recall did
not move on either split (49% dev, 44% test), because the gold's causal claims mostly sit in sentences that name their
ends by words the model has no name for, or are the annotator's inference. The round added 10 predictions across both
splits (9 judged correct by hand; the error is a past episode's move read as current), and none on negative controls.
Its effect is for the next blind set to show.

**Precision, now measured (Oct 18).** An independent labeler judged every prediction on the 67 gold files (a
prediction is correct when the document states it, with the right value and basis, the right direction, and as a
current level, neither past nor forecast). Precision was 61% (dev 62%, test 58%). The incorrect ones were mostly
forecasts or guidance read as observations (about half), a value or entity taken wrongly (a quarter: a peer's figure
on the next line, one component for an aggregate, a check row or a share row of a workbook), and history read as
current. A round of rules, tuned on the dev split only, raised precision without losing a gold match on either split:

| Split | Recall | Predicted | Precision (shared labels) | Precision (with the new predictions labelled too) |
|---|---|---|---|---|
| dev, before | 49% (48 of 98) | 138 | 62% | 62% |
| dev, after | 50% (49 of 98) | 102 | 90% (6 unlabelled) | 87% |
| test, before | 44% (19 of 43) | 74 | 58% | 58% |
| test, after | 44% (19 of 43) | 62 | 77% (6 unlabelled) | 76% |

The rules:

- **An observation is a reported current level.** A level is read in the latest actual column, never an estimate
  column ("9/26E", "2027E"), never a year-end half a year before the document (a later quarter has been reported), and
  a market price only on a date or a "Current" column (not at a quarter's end or as a fiscal year's average).
- **A workbook's model is not a report.** A row's columns from its first computed figure on (decimals after whole
  numbers) are a projection; a year at least half reported is still read, with less confidence than a figure stated
  for the year. Check rows ("A = B"), rows of zeros, share rows ("mix, %"), a balance repeated in its year's column, a
  value named only in a label's parenthetical, and a level whose figures run past the dated columns are not read.
- **A forecast is not a move.** Previews ("is seen up", "incoming"), base cases, projections, the market's pricing of
  moves to come, assumptions ("based on"), another's expectation or guidance ("management expects", "guided to"),
  predictions ("will grow by 13%"), and changes over estimated years are no claim, read in the mention's own part of
  the sentence (up to a semicolon or a sub-bullet). A revision of a forecast or of guidance (from A to B, "raised our
  forecasts") is news and stays a move.
- **The right value.** A value named without its entity is not taken after an acronym the model does not know on the
  same line (another bank's ticker, another central bank), nor after "its" when the last sentence named a stranger
  in the possessive. A part in a list of labelled parts that moved both ways is not the whole; a figure stripped of
  something is on another basis; a value as the object of someone's aim ("buybacks to improve returns") does not move.
- **The right period and direction.** A quarter's sequential change does not move a year's flow, nor does a month's
  print or a sequential change move a year-on-year rate; a pause ("unchanged", "on hold") is no move; a flow's figure
  after its change ("rose 16% to ¥22bn") is a period's result unless the year is named; an uncalibrated link is
  supported or contradicted by the sign its mechanism states.
- **History and scenarios.** Bullets under a scenario's heading ("Upside Scenario") are supposed until prose resumes;
  an episode dated by day and month only, right after a sentence about an earlier year, is history; so are "past
  episodes".

What remains is mostly a disagreement between the gold and the labeler, not a reading error: the gold takes a
current fiscal year's estimate of an annual figure (a research table's "03/27E" column, a workbook's forward row, a
year the model completes) as the value's level, while the labeler calls the same reading a forecast. The rules keep
those readings, so as not to lose gold matches; reading them strictly would raise precision further and lower recall.

Half B was partly exposed before scoring: a bench run read three of its files and showed some predicted values to the
tuner, although no rule was tuned on them. Without those files, half B has only 6 claims, too few to report on their
own. The next blind set should be annotated from fresh documents, and runs should name their files explicitly
(`--files`), never whole folders.

A client's corpus, gold, and reports stay in that client's gitignored folder. The scoring is tested on invented
examples (`tests/ingest/test_bench.py`).

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
