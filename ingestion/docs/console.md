# The ingestion console

An internal page, served by the ingestion service, for understanding and debugging stages 1 to 5 of
[implementation.md](implementation.md): store, parse, type and date, chunk, index and embed. It is for engineers, not
clients. Recognition, extraction and bundles are out of scope except as read-only counts.

<!-- toc -->
**Contents**

- [Reaching it](#reaching-it)
- [The tabs](#the-tabs)
- [Routes](#routes)
- [Safety](#safety)
- [In the code](#in-the-code)
<!-- /toc -->

## Reaching it

In dev, run the service on a local lake (no network needed) and open it:

```bash
INGEST_TOKEN=dev WORLD_MODEL_LAKE_DIR=/tmp/lake WORLD_MODEL_EMBEDDER=hashing uv run axelrod-ingest   # port 8000
# open http://localhost:8000/ and enter the token
```

Deployed, the console is at `https://world-model-ingestion-dev.up.railway.app/`, and `INGEST_TOKEN` protects every JSON call
([deployment.md](../../docs/deployment.md#three-services)). The page itself is open and holds no data: it asks for the token on
first load and keeps it in `sessionStorage` for the tab (never `localStorage`, a URL, or a log). A 401 clears it and asks
again; Sign out clears it. Keys: `1` to `4` switch tabs, `/` focuses search (neither while typing in a field).

## The tabs

| Tab | Shows |
|---|---|
| **1 Lake** | The tenant (a picker over the lake's tenants), the counts from `stats`, and documents by status, type and language. A table of documents (file name or title, status, type, language, published date and its source, period, pages, chunks, size, ingested time) with filters, sort by ingested or event time, and paging. A row opens the document: its metadata (type and reason, how it was dated, decoded, OCR, yen evidence, manifest and hash match, `shared_origin`), status and error, the text with chunk boundaries drawn faintly and each chunk's ordinal and page, the chunks list (each has "similar"), mention and signal counts, and a download of the raw file |
| **2 Add files** | Drop or pick files, set tenant, source, source type, published date and an optional world view file (the world model's export or a bare view). Each file goes to `POST /v1/ingest`; the result shows new or already stored, status, warnings, per-stage timings and a link to the document. Without a world view file an empty one is used: the document is stored, parsed, typed, chunked and embedded, but nothing is recognized |
| **3 Search** | A query in keyword, prefix, semantic or hybrid mode (graph, and model-name prefix hits, need a world view file). Each hit shows score, mode, the `why` list, title, ordinal, page, event time, and the chunk with the query's words highlighted. "Compare modes" runs the query in every available mode in columns. "similar" finds passages like a chunk |
| **4 Stage debugger** | A dry run of stages 1 to 5 on an uploaded file or a stored document, written nowhere. One collapsible card per stage with its decision and timing: **Store** (content id, SHA-256, size, MIME, whether the lake has it); **Parse** (format, parser version, segments and spans, decoding, OCR, the normalized text by page; a `ParseError` is a failed card); **Type, date, language, currency** (type and reason, substance, published date and the rule, period, language, yen and its evidence; an excluded or `needs_ocr` document stops here, plainly); **Chunk** (every chunk with page, span, weight and sentence boundaries, a weight histogram against `CHUNK_CHARS`, and a flag on chunks cut from a long sentence); **Index and embed** (index terms as tokenized, the note that FTS5 applies Porter stemming itself, the embedder, each vector's norm and first eight components, the top three nearest stored passages per chunk); **Duplicates** (the fingerprint, containment against the tenant's stored documents with the same period end, and whether it would join a `shared_origin` group and who would be primary) |

## Routes

All under the service's bearer token; failures are RFC 9457 problems, and the page shows each one's `title` and `detail`.

| Route | Returns |
|---|---|
| `GET /v1/tenants` | the lake's tenants |
| `GET /v1/lake/{tenant}/summary` | stats, and documents by status, type and language |
| `GET /v1/lake/{tenant}/documents` | the table; `status`, `type`, `language`, `q`, `order` (`event_time` or `ingested_at`), `dir`, `limit`, `offset` |
| `GET /v1/lake/{tenant}/documents/{id}` | metadata, text, chunks, counts |
| `GET /v1/lake/{tenant}/documents/{id}/raw` | the raw file (the page fetches it as a blob, with the token) |
| `POST /v1/search` | `tenant`, `q`, `mode`, `limit`, optional `world_view` (the view's JSON) |
| `POST /v1/similar` | `tenant`, `doc_id`, `ord`, `limit` |
| `POST /v1/debug/stages` | a multipart `file` and `meta`, or JSON `{tenant, doc_id}`: the dry run |

A file added here (or through `/v1/ingest`) is stored and read with no world view, so nothing in it is recognized yet. When the world model runs the lake sync (`WORLD_MODEL_LAKE_SYNC`, on by default in the hosted three-service mode), added files reach the model within about 30 seconds: it reads them against the model, imports what has signals, and keeps what needs a person pending with its reasons. See `GET /v1/world-models/{id}/sync` for its status.

Unfiltered tables are paged by the store; a filter reads the tenant's documents (500 at a time) and filters them here.

## Safety

- **The dry run writes nothing.** A test holds the lake's digest (`pack.lake_digest`) unchanged after a dry run of a stored
  document and of a new file.
- **It cannot drift from the pipeline.** `debug.dry_run` calls `parse`, `pipeline.analyze` (dates, language, yen, type: the same function
  `Ingestor.process` calls), `chunk` and the embedder, in that order; a test holds its answers equal to what `process` stores.
- **Uploads are untrusted.** They are parsed only through `parse` and never executed. Files over `INGEST_MAX_BYTES`
  (default 100 MB; the same limit as `/v1/ingest`) are refused with a 413.
- **Document text is attacker-controlled.** The page builds every string with text nodes; there is no `innerHTML`, no inline
  script or style, and the page's Content-Security-Policy allows only its own files. No CDN: it works with no outbound access.

## In the code

| File | Holds |
|---|---|
| `console.py` | the routes and the static page, mounted by `service.create_ingest_app` |
| `console/index.html`, `app.js`, `app.css` | the page (package data, in the wheel and the Docker image) |
| `debug.py` | `dry_run`, the six stage cards |
| `pipeline.py` | `analyze`, `derived_meta`, `typed_source`, `upload_date`: the stage 3 steps shared with `process` |
| `lake/` | `LakeStore.tenants()` and its route, SQLite and `RemoteLake` versions |
| `tests/test_console.py`, `tests/test_debug.py` | routes, auth, filters, the dry run's equality and no-write checks, a smoke test that every route `app.js` calls exists |
