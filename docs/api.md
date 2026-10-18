# World model API

The world model as a service: reads of the causal graph at a stated version, upload of files into the lakehouse and
from there into import bundles, review of the graph updates those bundles propose, search over everything ingested,
and forecasts. The same service is exposed twice, as REST under `/api/world-model` and as MCP tools at `/mcp`, on
the Railway deploy that serves the demo.

**Contents**

- [Who it is for](#who-it-is-for)
- [Authentication](#authentication)
- [Conventions](#conventions)
- [Routes](#routes)
- [A walk-through](#a-walk-through)
- [MCP](#mcp)
- [Mounting it from core](#mounting-it-from-core)
- [Configuration](#configuration)
- [Code and tests](#code-and-tests)

## Who it is for

- **The LLM harness** reads entities, values, and links as context, searches documents, and poses forecasts.
- **The MCP layer in core** mounts `/mcp` next to its other servers.
- **Ingestion jobs and people** upload research, read what it would change, and import it through review.

The service owns the world model. It does not own the agents that use it.

## Authentication

Each caller gets an API key: `Authorization: Bearer <key>`. A key acts as one login, so it reads and writes that
login's world model (Sally's key sees `sally_demo`) and that login's documents.

- **Keys** are set on Railway in `WORLD_MODEL_API_KEYS`, as comma-separated `caller:key:login` entries.
  - `caller` names who is calling. It is recorded on every approval and import.
  - `key` is at least 24 characters. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
  - `login` is the main Basic Auth username or a login from `WORLD_MODEL_LOGINS`.
  - A malformed entry, a short key, or a caller named twice stops the server from starting.
- **A key opens only** `/api/world-model/*` and `/mcp`. It does not open the demo UI or its `/api/...` routes.
- **A signed-in browser** may call the service with its session cookie, as `session:<login>`. That is how the
  interactive docs at `/docs` work.
- **A local run** with no logins and no keys leaves the service open as caller `local`. Once keys are set locally,
  every call needs one.
- **No key, a wrong key, or a key for an unknown login** gets `401` and `WWW-Authenticate: Bearer`.

To rotate a key, add the new entry, deploy, move the caller over, and then remove the old entry.

## Conventions

These follow core's API conventions (`Axelrod-AI-Engineering/core`), so a client that speaks to core speaks to this.

- **Version header.** Every response carries `X-Axelrod-API-Version: 1`.
- **Errors** are one envelope, whatever failed:

  ```json
  {"error": {"code": "version_not_found", "message": "version 900 is not in this world model (latest 255)",
             "details": null}}
  ```

  | Status | Codes |
  |---|---|
  | 400 | `invalid_request` (a value the model cannot use), `invalid_json` |
  | 401 | `authentication_required` |
  | 404 | `not_found`, `node_not_found`, `document_not_found`, `bundle_not_found`, `proposal_not_found`, `forecast_not_found`, `thesis_not_found`, `version_not_found`, `file_missing` |
  | 409 | `conflict`, `update_in_progress`, `already_decided`, `not_parsed` |
  | 413 | `payload_too_large`, `too_many_files` |
  | 422 | `invalid_request` (the body or query failed validation; `details` lists each field), `note_required`, `question_not_understood` |

- **Bodies** are JSON with unknown fields refused, except uploads, which are `multipart/form-data`.
- **Every read names its state.** Each answer has a `state` object with `scenario`, `version`, `state_hash`, `as_of`
  (when that version was committed), `latest_version`, and `clock` (the model's date). A read can be pinned to a past state:
  - `version=N` gives that committed version, restored from snapshots and checked against its hash.
  - `as_of=<ISO date-time>` gives the state at the last day closed at or before that time.
  - A version outside the model, or a date before it begins, is `404 version_not_found`.
- **Determinism.** The same file gives the same document id, chunks, signals, and bundle id. The same bundle
  imported into the same state gives the same version and hash. Ids are content hashes.
- **Idempotency.** Uploading the same bytes again returns the stored document with `"new": false`. Importing a
  bundle again imports nothing new.

## Routes

All paths are under `/api/world-model`. The live schema, with every field, is at `/docs` and `/openapi.json`.

### Reads

| Route | What it answers |
|---|---|
| `GET /state` | The state (above), counts of entities, values, links, and documents, plus `caller` and `tenant` |
| `GET /query` | `node_ids` (comma-separated) or `q` (names), with `depth` (0–4), `limit`, and `version` or `as_of`. Returns entities, values, and causal edges (Erid-compatible: `id`, `caption`, `erid_kind`; edges `from_id` / `relation` / `to_id` with `effect_sd_per_sd`, `existence_p`, `lag_days`), plus `missing_data` and `truncated` |
| `GET /nodes?q=` | Entities and values whose names start with or contain `q` |
| `GET /entities/{id}` | One entity: its values, concepts, and links |
| `GET /values/{id}` | One value: mean, unit, spread (sd and the 5–95% range), whether it was observed, its drivers and effects |
| `GET /taxonomy` | The static taxonomy's concepts, parents, and entities |
| `GET /context/v4?forecast=` | The model, and a forecast if one is given, in the client's v4.1.4 world-model format |

### Documents

| Route | What it does |
|---|---|
| `POST /documents` | Upload up to 20 files (50 MB each) as `files`, with optional `source`, `source_type`, and `published_at`. Each file is stored, parsed, chunked, indexed, and read into a bundle. Returns `201` and one result per file: `document`, `new`, `chunks`, `mentions`, `signals`, `llm_signals`, `warnings`, `bundle` |
| `GET /documents` | Stored documents, by `event_time` (default) or `ingested_at`, with `since`, `until`, `limit`, `offset` |
| `GET /documents/{id}` | One document and its bundles |
| `GET /documents/{id}/text` | The extracted text |
| `GET /documents/{id}/chunks` | Chunks and the names recognized in each |
| `GET /documents/{id}/raw` | The file as uploaded |
| `POST /documents/{id}/extract` | Read the document again against the model as it is now. This gives a new bundle if the model has changed |
| `DELETE /documents/{id}` | Remove the document, its text, chunks, indexes, and mentions. Its bundles and imports stay as history |

`source_type` is one of `broker_research`, `expert_call`, `news`, `central_bank`, `data`, `filing`, `client_model`, or
`other`. Supported formats are PDF, DOCX, PPTX, XLSX, HTML, CSV, Markdown, plain text, and JSON. A JSON file that is
already an `axelrod.import/v1` bundle is stored as that bundle unchanged. See [ingestion.md](ingestion.md) for how a
file becomes a bundle.

### Bundles and review

| Route | What it does |
|---|---|
| `POST /bundles` | Store an `axelrod.import/v1` bundle that another agent wrote. It is validated first |
| `GET /bundles`, `GET /bundles/{id}` | Stored bundles; one bundle in full, with its imports |
| `POST /bundles/{id}/import` | Fold the bundle into the model, one graph update per item, in event-time order. Body: `{"review": "queue" \| "auto", "item_ids": [...]}`. With `queue`, each proposed update waits for review. With `auto`, each is approved as the caller. Items dated before the model's last closed day are **late**: they fold into the next day and are listed under `late`. Returns `update_id`, `imported`, `late`, `approved`, `pending_proposals`, `version_before`, and the new `state` |
| `GET /proposals?status=` | `pending` (default), `approved`, `rejected`, or `all` |
| `POST /proposals/{id}/approve` | Approve as the caller, with an optional `{"note": ...}` |
| `POST /proposals/{id}/reject` | Reject as the caller. A note is required |

Only one update runs at a time per login. An import while another update waits for review is
`409 update_in_progress`.

### Search

`GET /search?q=&mode=&limit=` searches documents' chunks and the model's names. Each hit gives `kind` (`chunk`,
`entity`, or `value`), `doc_id`, `ref`, `score`, `text`, and `why`.

| Mode | How it ranks |
|---|---|
| `keyword` | BM25 over chunks (all words first, then any word) |
| `prefix` | Names, then chunks, by word prefix ("toy" finds Toyota) |
| `semantic` | Cosine similarity of embeddings (bge-small on the deploy) |
| `graph` | The nodes named in `q` and their neighbours, then the chunks that mention them |
| `hybrid` (default) | Reciprocal-rank fusion of keyword, semantic, and graph |

### Forecasts

| Route | What it does |
|---|---|
| `POST /forecasts` | `{"question": "What if the BoJ hiked by 25bp next quarter?"}` or `{"thesis_id": "S-T3"}`, with `horizon_days` (7–1095, default 182). Returns `201` with targets and ranges, transmission by order, and the scenario table. A question the model cannot map is `422 question_not_understood` |
| `GET /forecasts`, `GET /forecasts/{id}` | Forecasts posed so far; one forecast, with the state it was based on |
| `GET /forecasts/{id}/brief` | Summary, expected timing, exposures, indicators, and evidence |

## A walk-through

```bash
WM=https://world-model-dev.up.railway.app/api/world-model
AUTH="Authorization: Bearer $WORLD_MODEL_KEY"

curl -s -H "$AUTH" $WM/state

# upload a note: stored, parsed, and read into a bundle
curl -s -H "$AUTH" -F files=@2026-10-05_rates_note.pdf -F source="Desk" -F source_type=broker_research \
     $WM/documents | jq '.results[0] | {doc: .document.id, signals, bundle: .bundle.id}'

# what it would change, then import it for review
curl -s -H "$AUTH" $WM/bundles/<bundle-id> | jq '.bundle.items[] | {id, headline, signals}'
curl -s -H "$AUTH" -H 'Content-Type: application/json' -d '{"review": "queue"}' $WM/bundles/<bundle-id>/import
curl -s -H "$AUTH" $WM/proposals
curl -s -H "$AUTH" -X POST $WM/proposals/<proposal-id>/approve

# read the change, and the state before it
curl -s -H "$AUTH" "$WM/values/boj.policy_rate"
curl -s -H "$AUTH" "$WM/query?node_ids=boj.policy_rate&version=<version_before>"

curl -s -H "$AUTH" "$WM/search?q=yen%20carry&mode=hybrid"
curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d '{"question": "What if the BoJ hiked by 25bp next quarter?"}' $WM/forecasts
```

## MCP

`/mcp` is an MCP server (`axelrod-world-model`) over stateless Streamable HTTP, built with the official `mcp` 2.x SDK
the way core builds its own. It takes the same Bearer key. Each tool calls the REST route above in process, so
answers, auth, and errors are identical. A REST error comes back as a tool error, `"<code>: <message>"`.

| Tool | Route | Annotation |
|---|---|---|
| `world_model_state` | `GET /state` | read-only |
| `world_model_query` | `GET /query` | read-only |
| `world_model_search_nodes` | `GET /nodes` | read-only |
| `world_model_get_entity` | `GET /entities/{id}` | read-only |
| `world_model_get_value` | `GET /values/{id}` | read-only |
| `world_model_taxonomy` | `GET /taxonomy` | read-only |
| `world_model_search` | `GET /search` | read-only |
| `world_model_ingest_document` | `POST /documents` (`content_base64` or `text`) | write, idempotent |
| `world_model_list_documents` | `GET /documents` | read-only |
| `world_model_get_bundle` | `GET /bundles/{id}` | read-only |
| `world_model_import_bundle` | `POST /bundles/{id}/import` | write |
| `world_model_list_proposals` | `GET /proposals` | read-only |
| `world_model_decide_proposal` | `POST /proposals/{id}/approve` or `/reject` | write |
| `world_model_forecast` | `POST /forecasts` | write |
| `world_model_get_forecast` | `GET /forecasts/{id}` | read-only |
| `world_model_forecast_brief` | `GET /forecasts/{id}/brief` | read-only |
| `world_model_context_v4` | `GET /context/v4` | read-only |

Core reserves the name `world_model.query` for point-in-time reads. Here that is `world_model_query`, since MCP tool
names in core are snake_case.

To use it from Claude Code:

```bash
claude mcp add --transport http world-model https://world-model-dev.up.railway.app/mcp --header "Authorization: Bearer $WORLD_MODEL_KEY"
```

## Mounting it from core

Core consumes EODHD's MCP server with the Agents SDK's `MCPServerStreamableHttp`. The world model mounts the same way:

```python
from agents.mcp import MCPServerStreamableHttp

world_model = MCPServerStreamableHttp(
    name="world-model",
    params={"url": f"{settings.world_model_url}/mcp",
            "headers": {"Authorization": f"Bearer {settings.world_model_api_key}"},
            "timeout": 60},
    cache_tools_list=True,
)
```

A REST client can call `/api/world-model/...` with the same header. Core keeps the key in its own settings, like its
other provider keys. The world model never sees core's users. The key's caller name (e.g. `core`) is what reviews and
imports record.

## Configuration

| Variable | Default | What it sets |
|---|---|---|
| `WORLD_MODEL_API_KEYS` | none | `caller:key:login` entries (see [Authentication](#authentication)) |
| `WORLD_MODEL_LAKE_DIR` | `var/lake` | The lakehouse: a SQLite catalog and raw files per login. On Railway it sits on the volume at `/app/var/lake` |
| `WORLD_MODEL_EMBEDDER` | `auto` | `fastembed` (bge-small, ONNX, CPU), `hashing` (exact, no model; used in tests), or `auto` (fastembed when installed) |
| `WORLD_MODEL_EMBED_CACHE` | fastembed's default | Where the embedding model is cached; keep it on the volume |
| `WORLD_MODEL_LLM_PROVIDER` | off | `anthropic` or `openai`. Off unless set *and* that provider's key is present. Answers are cached, so a re-read never calls it again |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | none | The provider's key |
| `WORLD_MODEL_LLM_MODEL` | provider default | The model for the LLM extraction step |

Secrets live in Railway's variables only, never in the repository.

## Code and tests

| Part | Code | Tests |
|---|---|---|
| REST routes, envelope, pinning | `src/axelrod_wm/api/service.py` | `tests/service/test_service_api.py` |
| MCP server | `src/axelrod_wm/api/mcp.py` | `tests/service/test_mcp.py` (through the SDK's own client) |
| API keys, middleware | `src/axelrod_wm/api/keys.py`, `api/auth.py` | `tests/service/test_keys.py` |
| Lakehouse and search | `src/axelrod_wm/lake/` | `tests/lake/` |
| Ingestion pipeline | `src/axelrod_wm/ingest/` | `tests/ingest/` |

These modules are held at 100% line and branch coverage in CI (`scripts/coverage_gate.py`).
