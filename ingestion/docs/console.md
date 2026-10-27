# The ingestion console

An internal page, served by the ingestion service, for understanding and debugging stages 1 to 5 of
[implementation.md](implementation.md): store, parse, type and date, chunk, index and embed. It is for engineers, not
clients. Recognition, extraction and bundles are out of scope except as read-only counts.

<!-- toc -->
**Contents**

- [Reaching it](#reaching-it)
- [The tabs](#the-tabs)
- [Staying current](#staying-current)
- [Updating the lake](#updating-the-lake)
- [Reaching the model](#reaching-the-model)
- [Routes](#routes)
- [Safety](#safety)
- [In the code](#in-the-code)
- [Ingest jobs](#ingest-jobs)
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
again; Sign out clears it. The last tenant is remembered per browser in `localStorage` (the only thing kept there). Keys: press
`?` for the list: `1` to `4` switch tabs, `/` focuses search, `j` `k` `Enter` walk the Lake table, `r` refreshes, `p` pauses the
live refresh, `n` marks new rows as seen (none of them while typing in a field).

## The tabs

| Tab | Shows |
|---|---|
| **1 Lake** | The tenant (a picker over the lake's tenants), the counts from `stats`, and documents by status, type and language. A table of documents (file name or title, status, where it stands with the world model, type, language, published date and its source, period, pages, chunks, size, ingested time) with filters, sort by ingested or event time, and paging. A row opens the document, with **Reprocess**, **Delete** and **Download raw file**: its metadata (type and reason, where it stands with the world model, how it was dated, decoded, OCR, yen evidence, manifest and hash match, `shared_origin`), status and error, the text with chunk boundaries drawn faintly and each chunk's ordinal and page, the chunks list (each has "similar"), mention and signal counts, and a download of the raw file |
| **2 Add files** | Drop or pick files or a folder, set tenant, source, source type, published date and an optional world view file (the world model's export or a bare view). Files wait in a queue and go, a few at a time ("jobs submitted at once"), to `POST /v1/ingest?mode=async`: the service answers `202` with a job at once and the row polls `GET /v1/jobs/{id}` (every 1 s, then 2 s, then 5 s), so a ten-minute OCR file shows `running… 6m`, not a timeout. Each row shows its own state (queued, sending, waiting, running, then new or already stored, or failed), the document's status, warnings, per-stage timings and a link to the document. Without a world view file an empty one is used: the document is stored, parsed, typed, chunked and embedded, but nothing is recognized. See [Updating the lake](#updating-the-lake) |
| **3 Search** | A query in keyword, prefix, semantic or hybrid mode (graph, and model-name prefix hits, need a world view file). Each hit shows score, mode, the `why` list, title, ordinal, page, event time, and the chunk with the query's words highlighted. "Compare modes" runs the query in every available mode in columns. "similar" finds passages like a chunk |
| **4 Stage debugger** | A dry run of stages 1 to 5 on an uploaded file or a stored document, written nowhere. One collapsible card per stage with its decision and timing: **Store** (content id, SHA-256, size, MIME, whether the lake has it); **Parse** (format, parser version, segments and spans, decoding, OCR, the normalized text by page; a `ParseError` is a failed card); **Type, date, language, currency** (type and reason, substance, published date and the rule, period, language, yen and its evidence; an excluded or `needs_ocr` document stops here, plainly); **Chunk** (every chunk with page, span, weight and sentence boundaries, a weight histogram against `CHUNK_CHARS`, and a flag on chunks cut from a long sentence); **Index and embed** (index terms as tokenized, the note that FTS5 applies Porter stemming itself, the embedder, each vector's norm and first eight components, the top three nearest stored passages per chunk); **Duplicates** (the fingerprint, containment against the tenant's stored documents with the same period end, and whether it would join a `shared_origin` group and who would be primary) |

## Staying current

The Lake tab keeps itself up to date; nothing needs a reload.

- **Polling.** Every 5 seconds the page asks `GET /v1/lake/{tenant}/changes?since=<baseline>`, which costs a handful of indexed
  counts (`LakeStore.overview`, `stats`) and returns a `version` (a digest of the counts, the statuses and the newest ingest time),
  the document count and `new` (documents ingested after the baseline). Only when the `version` has moved does it read the summary,
  the activity feed and the table again. After a failure it waits 10, 20, 40, then 60 seconds; while the browser tab is hidden it
  does not poll, and it polls at once when the tab is shown again. The line above the counts shows "last updated hh:mm:ss"
  (or "paused", or the error and that it is retrying) with **Pause** and **Refresh now**.
- **Nothing is lost.** A refresh replaces the table's rows in place: filters, sort, page, the open document, the highlighted row
  and the window's scroll position stay (the row at the top of the window is found again by id and put back where it was, so new
  rows arriving above it do not move what you are reading). Counts and the feed have fixed heights, so the page does not jump.
- **New rows.** The baseline is the newest ingest time when the tab was first loaded (or last marked seen). Rows newer than it carry
  a dot and a line in the accent colour, and a chip "N new" appears by the status line; clicking it (or `n`) marks them seen.
- **Recent activity.** The latest 8 ingests (`GET /v1/lake/{tenant}/activity`): time, file, status, chunks and the error, which is
  highlighted when the file failed. Per-stage timings are not stored with a document, so they show only for files ingested from
  this browser (the Add files queue keeps them).
- **Cost.** Chunk counts for a page of rows are one `GROUP BY` (`LakeStore.count_chunks`) and the model column two reads
  (`LakeStore.model_progress`), not a read per row; the table is paged
  (50, 100 or 200 rows), so 700 or 70,000 documents draw the same number of rows.

## Updating the lake

- **Add files.** Drop files or a folder (`webkitGetAsEntry` walks it) or choose a folder. Files the parsers cannot read are left
  out before upload: the page gets the extensions and MIME types from `GET /v1/supported` (`parse.PARSERS` and `parse.MIMES`), so
  it cannot disagree with the service. A `MANIFEST.md` in the folder is sent as text to `POST /v1/manifest`, which returns its
  entries by file name (`sources.read_manifest`); each file beside it then goes with `meta.manifest` (file, url, section, rank,
  sha256, publisher) and its URL's host as the source, exactly as `pack.py` does. The manifest itself and dotfiles are not
  ingested. The queue shows per file queued, sending, new, already stored, failed or cancelled; a progress bar and counts;
  **Cancel** aborts what is in flight; **Retry failed** requeues failed and cancelled files; **Clear finished** empties the done
  ones. A network error or a 502 or later is tried once more. A long queue shows the failures, what is in flight, the latest
  finished and the next to go.
- **Reprocess** runs `POST /v1/process` on the stored document: parse, type and date, chunk, embed and extract again, against the
  world view file chosen on the Add files tab or, without one, an empty view (so mentions are cleared and nothing is recognized;
  the confirm dialog says which).
- **Delete** (`DELETE /v1/lake/{tenant}/documents/{id}`, behind the token, after a confirm dialog): removes the document, its
  file, text, chunks, mentions and embeddings (`delete_document`), then its bundles through `LakeStore.delete_bundles_of`: bundles
  made from that document alone and used by no import are deleted; a bundle built from several documents, or one the world model
  imported, is kept, because something else depends on it. The answer says how many were removed and how many kept.
- **Tenants.** The picker lists the lake's tenants, each with its document count (`GET /v1/tenants`); typing a new name starts an
  empty tenant, which exists once a document is added to it.

## Reaching the model

Adding a file stores it; the world model reads it on its own (below), and the **model** column says how far it got, from
what the lake holds (`LakeStore.model_progress`: the imports of bundles made from the document, and the lake sync's ledger):

| Shows | Means |
|---|---|
| **imported · N items** | N items reached the world model. Its review policy decides what applies; the rest waits in the model's review queue |
| **waiting** | Readable, not read against the model yet. The sync runs about every 30 s and waits while an update is in review |
| **nothing new** | Read against the model; nothing in it changes the model |
| **read on upload** | Uploaded through the world model's API, which read it and proposes its changes from there |
| a status (`failed`, …) | The sync found the document in that status and left it |
| (blank) | Excluded, failed or needing OCR before any sync: the model will not read it |

The column moves on its own: an import changes the lake's counts, so the next poll redraws the table. The document view
lists each world model's ledger entry under **World model**.

## Routes

All under the service's bearer token; failures are RFC 9457 problems, and the page shows each one's `title` and `detail`.

| Route | Returns |
|---|---|
| `GET /v1/tenants` | the lake's tenants, and `documents`: each one's document count |
| `GET /v1/supported` | `extensions` and `mimes` the parsers take, and the `source_types` |
| `POST /v1/manifest` | `{text}`: the MANIFEST.md's `title`, `updated` and `entries` keyed by file name |
| `GET /v1/lake/{tenant}/changes` | `version`, `documents`, `stats`, `statuses`, `last_ingested_at`, and `new` (after `since`): the poll |
| `GET /v1/lake/{tenant}/summary` | stats, and documents by status, type and language, with the `version` and `last_ingested_at` |
| `GET /v1/lake/{tenant}/activity` | the latest ingests (`limit`, default 12), newest first |
| `GET /v1/lake/{tenant}/documents` | the table; `status`, `type`, `language`, `q`, `order` (`event_time` or `ingested_at`), `dir`, `limit`, `offset` |
| `GET /v1/lake/{tenant}/documents/{id}` | metadata, text, chunks, counts |
| `GET /v1/lake/{tenant}/documents/{id}/raw` | the raw file (the page fetches it as a blob, with the token) |
| `DELETE /v1/lake/{tenant}/documents/{id}` | `deleted`, `bundles_removed`, `bundles_kept` |
| `POST /v1/ingest?mode=async`, `GET /v1/jobs/{id}`, `POST /v1/process` | the service's own routes, used for adding files (as jobs) and for reprocessing |
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
- **The delete is the console's only write of its own,** needs the token, asks first, and never touches a bundle another document
  or an import depends on.
- **Uploads are untrusted.** They are parsed only through `parse` and never executed. Files over `INGEST_MAX_BYTES`
  (default 100 MB; the same limit as `/v1/ingest`) are refused with a 413.
- **Document text is attacker-controlled.** The page builds every string with text nodes; there is no `innerHTML`, no inline
  script or style, and the page's Content-Security-Policy allows only its own files. The token is only in `sessionStorage`; the
  one `localStorage` key is the last tenant name. No CDN: it works with no outbound access.

## In the code

| File | Holds |
|---|---|
| `console.py` | the routes and the static page, mounted by `service.create_ingest_app` |
| `console/index.html`, `app.js`, `app.css` | the page (package data, in the wheel and the Docker image) |
| `debug.py` | `dry_run`, the six stage cards |
| `pipeline.py` | `analyze`, `derived_meta`, `typed_source`, `upload_date`: the stage 3 steps shared with `process` |
| `lake/` | `LakeStore.tenants()`, `overview()`, `count_chunks()`, `model_progress()` and `delete_bundles_of()`, each with its data service route (`/v1/lake/overview`, `/chunk-counts`, `/model-progress`, `DELETE /documents/{id}/bundles`) and SQLite and `RemoteLake` versions |
| `tests/test_console.py`, `tests/test_debug.py` | routes, auth, filters, the dry run's equality and no-write checks, a smoke test that every route `app.js` calls exists |

## Ingest jobs

The hosted service sits behind a proxy that cuts a request at 300 s, and a large scanned PDF takes longer than that to OCR, so the console (and any script) sends files as jobs.

- `POST /v1/ingest?mode=async` (or the header `Prefer: respond-async`, RFC 7240) takes the same multipart body, bearer token, size limit and meta checks as the synchronous call, and refuses a bad request at once (422, 413, 401). Otherwise it answers `202 Accepted` with `Location: /v1/jobs/{id}` and `{id, status: "queued", files: [{name, size, content_id}]}`. `content_id` is the document's id in the lake: the first 24 hex digits of the file's SHA-256. Without the parameter or header the call is synchronous and unchanged (the world model's `RemoteIngestor` uses it). `mode=sync` wins over the header.
- `GET /v1/jobs/{id}` answers `{id, status, files, created_at, started_at, finished_at, progress: {done, total, current}, results, error}`. `status` is `queued`, `running`, `succeeded` or `failed`; `results` has the synchronous response's shape. A file the pipeline could not parse is a succeeded job whose document has status `failed`; a job fails only when the work itself raised (`error` says what).
- One worker thread per process runs jobs first in, first out, one at a time, so memory stays bounded and OCR does not compete with itself. At most 100 jobs wait; past that the call is a `503` with `Retry-After`.
- A job is a progress handle, not a record: the lake holds the result, and the document is there as soon as it is stored. Jobs live in memory, the last 500 (a finished one past that is forgotten; a queued or running one never is). **A restart loses queued and running jobs**; `GET` of an unknown id is a 404 that says so. The console then checks the lake for the document by its content id (computed in the browser with SubtleCrypto) and shows it as stored, or as failed with "send it again".
- Cancel in the console stops sending files. A job the service already has cannot be cancelled: it runs to the end.
