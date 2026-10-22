# The ingestion pipeline

How an uploaded file becomes proposed graph updates: the steps, the two times every document carries, rules-first
extraction, documents in Chinese and Korean, scans, duplicates across languages, and why every step is deterministic. Where everything it produces is kept is [lake.md](lake.md); how it
is measured is [bench.md](bench.md); the format it produces is [contract.md](contract.md). For the routes that drive
it, see [the API reference](../../world_model/docs/api/README.md).

<!-- toc -->
**Contents**

- [The pipeline](#the-pipeline)
- [Two times: event and ingestion](#two-times-event-and-ingestion)
- [What a document is: type, manifest, exclusion](#what-a-document-is-type-manifest-exclusion)
- [Scans and OCR](#scans-and-ocr)
- [Chinese and Korean](#chinese-and-korean)
- [Currencies and the yen sign](#currencies-and-the-yen-sign)
- [Duplicates across language and basis](#duplicates-across-language-and-basis)
- [Packs](#packs)
- [Extraction: rules first, an LLM only where the rules are silent](#extraction-rules-first-an-llm-only-where-the-rules-are-silent)
- [Determinism](#determinism)
- [Limits and next steps](#limits-and-next-steps)
<!-- /toc -->

## The pipeline

```
file ─▶ store ─▶ parse ─▶ type ─▶ chunk ─▶ index ─▶ recognize ─▶ extract ─▶ bundle ─▶ import ─▶ review ─▶ commit
        lake     text     filing,  ≤700      FTS5 +   model's      rules,     axelrod.   one graph  a person   a new
        (hash)   +pages   report,  units     vectors  names        LLM opt.   import/v1  update per  (or auto)  version
                 (OCR)    ...      chunks                                                item
                          excluded
                          here
```

Paths in the Code column are under `ingestion/src/axelrod_ingest/`. Ingestion stops at the bundle; the import and review that follow are the
world model's.

| Step | Code | What it does |
|---|---|---|
| Store | `lake/sqlite.py` | Keeps the bytes once per content hash, per organization. The same file uploaded twice is one document |
| Parse | `parse.py`, `encoding.py`, `ocr.py` | PDF (PDFium, page by page; a page that is a picture is read by OCR), DOCX, PPTX, XLSX (values, not formulas), HTML (its declared charset; a table is read row by row), CSV, Markdown, text, JSON. A JSON file that is already an import bundle passes through unchanged |
| Type | `sources.py`, `dates.py`, `units.py` | What the document is (filing, report, transcript, presentation, news, data aggregate, index page, other), whether it holds any content, when it was published and what period it covers, its language, and what a bare ¥ means in it. Stored in the document's metadata |
| Chunk | `chunk.py`, `cjk.py` | Splits text into sentences (aware of abbreviations, bullets, decimals, and the Chinese and Korean sentence ends), then packs them into chunks of up to 700 units (an ideograph or a Hangul syllable counts two). A chunk never crosses a paragraph or a page, so every quote can be traced to its page |
| Index | `lake/sqlite.py`, `lake/embed.py` | Adds each chunk to a stemmed keyword index, an unstemmed prefix index, and an embedding |
| Recognize | `gazetteer.py` | Finds the model's own names in each chunk (read from the [world view](contract.md#the-world-view), not from the model): entities by name and alias (possessives and plurals included), and values by their own phrase ("Bund 10Y yield"), or by a head word ("rates", "yield") when the nearest entity has exactly one such value |
| Extract | `extract.py`, `llm.py` | Turns sentences into signals (below) |
| Bundle | `pipeline.py` | One item per chunk with signals: headline, the chunk as summary, tickers, the signals with exact quotes. Validated as `axelrod.import/v1` and stored |
| Import | `world_model/src/axelrod_wm/sim/imports.py` (the world model) | Folds items into the model one graph update each, in event-time order. Each update is reviewed before it commits |

Nothing changes the world model before the import step, and nothing commits before review. A bundle can be read,
compared, and discarded without trace.

## Two times: event and ingestion

Every document carries two times:

- **Event time** is when the content became available, from `dates.py`: the date given with the upload (`published_at`);
  else, for a file a pack's manifest lists, the date in its file name (the packs name files `27-Mar-2026_...` after their
  publication); else the first full date in the opening text; else a date in the file name; else the ingestion time. With
  `ignore_future_dates` (the pack runner sets it) a date later than when the file arrived cannot be its publication and is passed over;
  by default it is kept, since invented notes and demos are dated ahead of the clock. A name that holds no date (`undated`,
  `current`, `period-2025`, `monthly-10th`, `Feb-2024`, where a month is no day) gives nothing: it is not guessed from.
  Where nothing dates a document it is dated when it arrived, and `meta.dates.published_source` says `ingested_at`.
- **Ingestion time** is when the file arrived.

A third date is kept apart from both: the **period** a document reports on, read from its opening text, else its file name
(`for the month of August 2025`, `for the six months ended 30 June 2026`, `Q2 2026`, `H1 2026`, `FY2025`, `2026年半年度报告`,
`截至2026年6月30日止六个月`). It is stored with its end date and kind, and each bundle item carries it as `occurred_at`:
a monthly production announcement published on 1 September 2025 has `published_at` 2025-09-01 and `occurred_at`
2025-08-31. A period that ends after the publication (a guidance for the coming year) is marked `period_forward` and gives
no `occurred_at`. `meta.dates.published_lag_days` says how long after the period the document appeared, so a date read from
a page's menu (a page that lists other dates) can be spotted.

Bundles fold in by event time, so the model learns in the order things happened, not the order files arrived. A
document can arrive after the model has closed its day: a note dated September 1, uploaded after October 1 has been
processed. Its items are **late**. They fold into the next day the model processes, with their own event time kept,
and the import lists them under `late`. Both times can be listed and filtered (`GET /documents?order=ingested_at`).

## What a document is: type, manifest, exclusion

`sources.classify` gives each file one type, with its reason, in this order of evidence:

| Evidence | Result |
|---|---|
| A pack names it an index only (`INDEX_ONLY`), or it is named "index of ...", "transcript index" | `index_page`, excluded |
| It says it is a notice only (`NOTICE_ONLY`) | `other`, still read |
| A web page whose prose (lines of eight words or twelve ideographs, and table rows) is under 500 characters: a menu, a script shell, a list of links, a page that says it is gated (enable JavaScript, subscribe to read, access denied, no content to display) | `other` (or `index_page` for a list of links), excluded, with the reason |
| A PDF with fewer than 200 letters and digits in the whole document | `other`, excluded |
| A report named in the file name (annual, interim, quarterly, business, ESG report; financial statements) | `report` |
| The source address (an exchange or regulator; a transcript path; a statistics body; a press room) | `filing`, `transcript`, `data_aggregate`, `news` |
| The file name's other words (transcript, IR record, presentation, investor day, voluntary announcement, ...) | `transcript`, `presentation`, `data_aggregate`, `filing` |
| The manifest's section (a risk folder holds news) | `news` |
| Nothing | `other`, still read |

The type is stored in `meta.doc_type` and maps to the contract's `source_type` when the caller gave none (`filing`,
`report`, and `presentation` are `filing`; `transcript` is `expert_call`; `news`; `data_aggregate` is `data`; index and other are `other`).
Items carry `doc_type:`, `lang:`, and `period:` tags. An **excluded** document is stored and its text kept, so the decision
can be audited, but it has no chunks, no embeddings, and no bundle; its status is `excluded` and `error` holds the reason.
Screening is a choice of the caller (`Ingestor(screen=True)`; the pack runner sets it) and applies only to web pages and PDFs
nobody gave a type: a short uploaded note is a document, a pack's index page is not.

**The manifest.** A pack arrives with a `MANIFEST.md`. `read_manifest` reads its structure only: the title, the `Updated`
line, each table whose first column is "file" (an entry per row: the saved file, its section, its place in the table, the
source URL, and the SHA-256 it states), and the bullets under every other heading. Its text is data: nothing in it is run or
obeyed, and it only labels files. Each document keeps `meta.manifest` with the URL, section, rank, and whether the bytes
match the stated hash (`sha256_matches`: a mismatch is reported, never hidden).

## Scans and OCR

A PDF page whose text layer holds fewer than twenty letters and digits, and that carries a large image, is a picture. With an OCR
engine (`ocr_from_env`: tesseract on the path or at `AXELROD_TESSERACT`; `AXELROD_OCR=off` disables it) the page is drawn in
grayscale at 200 dpi and read with a fixed configuration (`--psm 3 --oem 1`, one thread, language `AXELROD_OCR_LANG` or `eng`);
the engine's name, version, and configuration go in `meta.ocr`, with the pages it read. A page's text is cached by the hash of
(engine, version, configuration, the file's SHA-256, the page) in `AXELROD_OCR_CACHE` (default `<lake>/ocr`), so reading a file
again never runs the engine and gives the same text. Without an engine, or where it fails, the pages are listed in
`meta.needs_ocr`; a document with no text at all is stored with status `needs_ocr` and no bundle, and a partly scanned one
is read and its warnings name the missing pages. Nothing is left empty without a word. OCR is optional: the ingestor takes an `Ocr`, and
without one it reports.

## Chinese and Korean

- **Text.** HTML is decoded by its byte-order mark, then its declared charset (`<meta charset>`, `http-equiv`, or an XML
  declaration; gb2312 and gbk are read as gb18030, euc-kr and ks_c_5601-1987 as cp949), then UTF-8, and Latin-1 only as a fallback
  reported in `meta.encoding`. Full-width digits, letters, and punctuation become ASCII (NFKC within the full-width block only, so
  `m²` and `…` are kept; the full-width `！` and `？` stay because they end sentences). A name a PDF draws one character at a time
  ("艾 克 米 股 份") is rejoined.
- **Sentences and chunks.** A sentence ends at `。！？` (and `!?` before an ideograph) with no space, at a period before a space and
  a Hangul syllable, and at a Korean ending (다, 요, 죠, 까) at a line's end. A chunk's size counts an ideograph or a syllable
  as two, so a chunk holds about 350 Chinese characters. A piece cut from a sentence too long for a chunk ends at a line break, a
  space, or a clause mark, and never inside a Latin word, a number, a combining mark, or a Hangul word.
- **Figures.** Scale words multiply: 十 10, 百 100, 千 1,000, 万 10,000, 亿 100 million; 百万 a million, 十亿 a billion,
  万亿 a trillion; 천, 만, 억, 조 (a trillion), and Korean amounts that add smaller scales ("3조 5,000억" is 3.5 trillion).
  兆 is left out (a trillion in Taiwan, a million in 兆瓦). A number before 年, 月, 日, 년, 월, 일, 위 is a date or a rank, not a figure; 제3조
  is an article of a law, not three trillion.
- **Names.** Recognition matches Chinese, Japanese, and Korean names by their characters, longest first; a one- or two-character
  alias matches only at the start of a run or after a particle such as 的 (so 收入, revenue, is not found inside 利息收入, interest income).

Chinese and Korean prose is read for levels ("营业收入为人民币1,200亿元", "매출액은 258조원") and for the figures in tables.
The direction words that give a move ("增长", "감소") are not read.

## Currencies and the yen sign

Figures take their currency from the code or sign before them (`RMB`, `CNY`, `KRW`, `HKD`, `US$`, `HK$`, `₩`, `CN¥`, `JP¥`, `$`, `€`,
`£`) or the word after their scale (`元`, `人民币`, `美元`, `港元`, `日元`, `円`, `원`, `엔`, `달러`). A bare `¥` is ambiguous: the
yen in a Japanese document, the yuan in a Chinese one. `units.resolve_yen` reads the document, never the number, in this order:
its own currency words when only one side appears (RMB, 元, 人民币 against JPY, 円, 日元) or one side has three times the other's;
then whether the issuer is a PRC company (its opening text says so, or the caller does); then the language of the text; and by
default the yen. The answer and its evidence (`signs`, `cny_words`, `jpy_words`, `language`, `issuer_country`, `basis`) are stored in
`meta.currency.yen`, and a figure written `JP¥` or `CN¥` keeps what it says.

## Duplicates across language and basis

The same results reach the lake as an English filing, a Chinese filing, a bilingual report, and a summary: different bytes, the
same reported figures. The content hash cannot see that, and reading each would count one disclosure several times.
`dedupe.link_duplicates` links them.

1. **Fingerprint.** A document's reported figures, each reduced to its significant digits (so `777,102`, `777102.00` and the same
   figure in thousands agree), with at least five of them (`MIN_DIGITS`), as a sorted multiset; with the period end it has a digest.
2. **One disclosure.** Two documents are one disclosure when they report the same period (the period's end date) and the smaller
   one's figures are found in the larger at a rate of 0.8 or more, with at least 40 in common. A document with no period is never
   matched. Copies connected through such pairs form a group with an id (`so-...`).
3. **Primary.** The rule is an ordered list (`DedupeConfig.primary`), by default `english_ifrs` (English text that states IFRS), then
   `completeness` (the most distinct figures); the other rules are `english`, `ifrs`, `length`, `latest`, `earliest`. Ties go to
   the smaller document id, so the choice never depends on arrival order.

Every copy is kept with its text, chunks, and bundle. Each records `meta.shared_origin` (`group`, `role` primary or duplicate, `primary`, `members`,
`rule`, `containment`), and a reader that wants a disclosure once takes the primary. Linking is a pure function of the lake: run it
again and nothing changes.

## Packs

`pack.ingest_pack` ingests a folder with a manifest: the files in path order, each with what the manifest says of it, then the
linking. It returns a `PackReport`: a row per file (status, type and its reason, language, pages, chunks, signals, how it was
dated, how ¥ was read, hash match, pages that need OCR, warnings), the duplicate groups, and the counts. `lake_digest` hashes
everything a lake holds for a tenant (documents with their metadata, texts, chunks, mentions, embeddings, bundles), so two runs
over one pack are the same exactly when their digests are:

```bash
uv run python ingestion/scripts/ingest_pack.py data/sources/<client>/<pack> --world-view data/work/<client>/world_view.json \
    --lake-dir data/work/<client>/lake_<date>/<pack> --report data/work/<client>/lake_<date>/<pack>.json \
    --twice data/work/<client>/lake_<date>_rerun/<pack>
```

The lake's clock is fixed (`--clock`), so a rerun is identical; `--twice` runs the pack again into a second lake and exits
nonzero if the two differ. The LLM step runs only if `WORLD_MODEL_LLM_PROVIDER` is already set.

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

**What counts as history.** A sentence only about earlier years is history and claims nothing, judged against the period the
document reports on when it has one (an annual report of FY2025 published in March 2026 is about 2025, so 2025 figures are
its own and 2024 ones are history), else against its publication date. A year's flow is read in the column of that fiscal year, never
from a half-year, a quarter, or a table dated inside the year ("30 June 2026"): in English, Chinese (上半年, 第三季度, 前三季度), and
Korean (상반기, 3분기). In a document that reports a month, a quarter, or a half, a year's flow is read only where the text names the
year ("for the year", "FY2025", "annual", 年度, 연간), since its headline figure is the part's; a file named for guidance, an
outlook, or a forecast states plans, not results, and its figures are not read; a figure only targeted or expected ("targeting",
"goal", 预计, 예상) is no level; and a company named in the last three sentences that is not the subject (a subsidiary,
a peer) leaves a value phrase unresolved rather than claimed for the subject.

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
- **The extractor and parser are versioned** (`ingest-1.1`, `parse-1.1`), and each bundle records both.
- **Embeddings.** Tests use a hashing embedder, which is exact and needs no model. The deploy uses bge-small through
  ONNX on one thread, with vectors rounded to 6 decimals.
- **OCR** runs one fixed configuration on one thread and is cached by content, so a page is read once.
- **Dates and clocks.** A date is read from the file or its name, never from the clock, unless nothing dates the document; the pack
  runner fixes the clock, so nothing in a lake depends on when it was built.
- **Duplicates.** Groups, primaries, and ids are functions of the lake's contents and the rule.
- **The LLM** runs at temperature 0 and is replayed from its cache.

## Limits and next steps

- **Scanned PDFs** are read by OCR where an engine is installed (a picture page with no text layer, 200 dpi, English by default:
  install the Chinese and Korean language data and set `AXELROD_OCR_LANG` for scans in those). Where it is not, they are marked `needs_ocr`.
- **Chinese and Korean prose** is read for levels and table figures, not for moves; a name must be in the model (as an alias in
  the language) to be found, and Chinese has no word breaks, so recognition is dictionary matching, longest first.
- **HTML tables.** An HTML table is read row by row (rowspans carried down, colspans kept as empty cells), but a flow stated for a quarter is
  not read as a year's: a model value with a `/yr` unit takes the fiscal-year column.
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
