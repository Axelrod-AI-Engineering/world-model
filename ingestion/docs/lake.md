# The lakehouse and search

Where everything ingestion reads and produces is kept, and how it is searched. The steps that fill it are in
[pipeline.md](pipeline.md); the service routes over it are in [the API reference](../../world_model/docs/api/README.md).

<!-- toc -->
**Contents**

- [The lakehouse](#the-lakehouse)
- [As a service](#as-a-service)
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

## As a service

The lake can run as its own process, so one service owns the SQLite file and every other service reaches it over HTTP
(the three-service deployment is in [deployment.md](../../docs/deployment.md#three-services)).

- **Server** (`lake/server.py`, `axelrod-lake`): `create_lake_app(store, token)` is a FastAPI app with one route per `LakeStore`
  method under `/v1/lake`. Records are JSON, the pydantic records of `store.py`; a document goes up as a multipart file part and
  comes back as an octet-stream (never base64); embeddings go up as float32 bytes, and `nearest` runs in the service against its
  cached matrix, so only the query vector travels. Every route but `GET /health` needs `Authorization: Bearer <LAKE_TOKEN>`
  (constant-time compare); failures are RFC 9457 problems: a `KeyError` is a 404, a `ValueError` a 422, a lookup that finds
  nothing a 404 with code `absent`. `LAKE_DIR` (default `/data/lake`), `LAKE_TOKEN` (required), and `PORT` configure it.
- **Client** (`lake/remote.py`): `RemoteLake(url, token, client=None)` is a `LakeStore`. It returns the same records in the same
  order and raises the store's own exceptions, so the lake's tests run unchanged against it (the `lake` fixture is parametrized
  over the local store and the remote one). Reads are retried three times on connection errors, timeouts, and 5xx answers;
  writes are sent once (a repeated write cannot duplicate anything, because ids are content hashes and puts replace, but retrying
  is the caller's choice). A service that is down is a `RemoteLakeError`.
- **Choosing**: `lake_from_env` returns the remote lake when `WORLD_MODEL_LAKE_URL` (and `WORLD_MODEL_LAKE_TOKEN`) are set, else the
  SQLite lake in `WORLD_MODEL_LAKE_DIR` (default `var/lake`). With neither set, nothing is remote.

A remote client holds no files, no vectors, and no matrix: each lives only in the service.

## Search

Search runs over what has been ingested and over the model's own names. It has five modes: keyword (BM25), prefix,
semantic, graph (the nodes named and their neighbours, then the chunks that mention them), and hybrid
(reciprocal-rank fusion of keyword, semantic, and graph). This is the retrieval layer for the agents' RAG: each hit
gives its document, chunk, and text, and says why it matched. See [the API reference](../../world_model/docs/api/README.md#search).

**Retrieval** (`LakeStore.retrieve`, Oct 26) is the public form, behind `GET /v1/world-models/{id}/chunks`
([retrieval.md](../../world_model/docs/api/retrieval.md)). It returns passages only, and the whole ranking runs in the
store in one call. The document filter (ids, source types, sources, dates, entities named) is SQL inside each channel;
keyword, semantic, and graph ranks are fused by reciprocal rank; `per_document` caps each document; and the page comes
back with its documents, mentions, and neighbouring chunks read in three queries. The world model only embeds the query
and resolves the names in it. Against the data service, one retrieval is one lake call, where a hybrid `search` makes
two per hit.

