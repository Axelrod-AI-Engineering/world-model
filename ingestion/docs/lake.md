# The lakehouse and search

Where everything ingestion reads and produces is kept, and how it is searched. The steps that fill it are in
[pipeline.md](pipeline.md); the service routes over it are in [the API reference](../../world_model/docs/api/README.md).

<!-- toc -->
**Contents**

- [The lakehouse](#the-lakehouse)
- [Search](#search)
<!-- /toc -->

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

A document's `status` is `stored`, `parsed`, `extracted`, `imported`, or one of three that end its path: `failed` (it could not be read;
`error` says why), `excluded` (it holds no content, or is an index; `error` holds the reason; its text is kept, with no chunks or
bundle), and `needs_ocr` (a scan with no text layer and no OCR engine). Its `meta` holds what ingestion learned of it:

| Key | Holds |
|---|---|
| `format`, `pages`, `encoding` | The format, its pages or slides, how its bytes were decoded (`name`, and `how`: bom, declared, utf-8, or fallback) |
| `language`, `currency.yen` | `en`, `zh`, `ko`, or `ja`; how a bare ¥ was read, with the evidence |
| `dates` | `published_at` and where it came from, the period (`period_end`, `period`, `period_kind`, `period_source`), `period_forward`, `published_lag_days` |
| `doc_type` | The type, its reason, whether it was excluded, and the basis |
| `ocr`, `needs_ocr` | The engine, its version and configuration, and the pages it read; the pages nobody read |
| `manifest` | What the pack's manifest says of the file: URL, section, rank, stated SHA-256, and whether the bytes match |
| `shared_origin` | The disclosure group a copy belongs to: group id, role (primary or duplicate), the primary, the members |

Organizations are tenants: a credential sees only its organization's documents. Storage sits behind an interface (`ingestion/src/axelrod_ingest/lake/store.py`,
`LakeStore`), so a warehouse such as Postgres, or Parquet on object storage, can replace SQLite without changing the
pipeline or the API.

## Search

Search runs over what has been ingested and over the model's own names. It has five modes: keyword (BM25), prefix,
semantic, graph (the nodes named and their neighbours, then the chunks that mention them), and hybrid
(reciprocal-rank fusion of keyword, semantic, and graph). This is the retrieval layer for the agents' RAG: each hit
gives its document, chunk, and text, and says why it matched. See [the API reference](../../world_model/docs/api/README.md#search).

