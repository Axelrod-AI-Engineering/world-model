# The world model in core's MCP catalog

For Zsolt (core's MCP) and whoever applies it to `Axelrod-AI-Engineering/core`. This repo never writes to core: the
change is a patch, ready to apply on a core branch and review there.

- [What it adds](#what-it-adds)
- [How it works](#how-it-works)
- [Apply and test it](#apply-and-test-it)
- [Configure it](#configure-it)
- [Keeping the two catalogs in step](#keeping-the-two-catalogs-in-step)

## What it adds

[`0001-world-model-service-mcp-tools.patch`](0001-world-model-service-mcp-tools.patch), made against core `main` at
`01886b5` (after #67 and #72). It extends core's own seam, `register_mcp_world_model_tools` in
`src/axelrod_app/mcp_world_model.py`, which #67 left for "further World Model reads". `search_canonical` is unchanged.

| Tool | World model route | Effect |
|---|---|---|
| `world_model_state` | `GET /state` | read |
| `world_model_query` | `GET /query` (`version` / `as_of` pin the read) | read |
| `world_model_search_nodes` | `GET /nodes` | read |
| `world_model_get_entity`, `world_model_get_value` | `GET /entities/{id}`, `/values/{id}` | read |
| `world_model_taxonomy` | `GET /taxonomy` | read |
| `world_model_search` | `GET /search` | read |
| `world_model_construction`, `world_model_construction_markdown` | `GET /construction/{id}` (JSON, or markdown) | read |
| `world_model_trace` | `GET /construction/{id}/trace` | read |
| `world_model_get_forecast`, `world_model_forecast_brief` | `GET /forecasts/{id}`, `/brief` | read |
| `world_model_context_v4` | `GET /context/v4` | read |
| `world_model_list_documents`, `world_model_get_bundle`, `world_model_list_proposals` | `GET /documents`, `/bundles/{id}`, `/proposals` | read |
| `world_model_forecast` | `POST /forecasts` | adds a forecast |
| `world_model_ingest_source` | a core project source → `POST /documents` | stores and reads a document into a bundle |
| `world_model_import_bundle` | `POST /bundles/{id}/import` with `review: "queue"` | proposes graph updates |

Two of the world model's own tools are left out on purpose:

- `world_model_decide_proposal`: approving a world model change is a person's decision in the world model's review,
  as core's expert-writeback design requires. No agent approves its own change through core.
- `world_model_ingest_document` (base64 in the tool call): `world_model_ingest_source` replaces it. The host uploads
  with `sources_create_upload` (#67), and the bytes never pass through the conversation.

## How it works

- **Who is asking.** Each tool authenticates the org user from core's MCP token, as every core tool does. It then
  calls the world model service with the key for that user's organization, and sends
  `X-Axelrod-On-Behalf-Of: <org_id>/<org_user_id>`. The service records `core for <org_id>/<org_user_id>` on
  every import and proposal.
- **Errors** come back as core's tool errors, `"<code>: <message>"`, with the service's own codes (`node_not_found`,
  `version_not_found`, …).
  - A service that can't be reached gives `world_model_unavailable`.
  - A response that isn't the service's error format gives `world_model_error: HTTP <status>`.
- **Results** are structured: `WorldModelResult` carries the service's answer with its `state` (version, hash,
  clock). Each tool publishes an output schema, as #66 requires.
- **Annotations** follow core's sets in `mcp_catalog.py`:
  - every read is in `_READ_ONLY_TOOLS`;
  - the three writes are in `_ADDITIVE_TOOLS` (not destructive);
  - all are closed-world.

  Titles are in `_TOOL_TITLES`, and the group is `McpDocGroup.WORLD_MODEL`, so #74's generated reference lists them
  under "World model".

## Apply and test it

```bash
git switch -c world-model-service-tools origin/main
git am /path/to/0001-world-model-service-mcp-tools.patch
EODHD_API_KEY=placeholder AXELROD_WORLD_MODEL_EVENTS_ENABLED=0 .venv/bin/python -m pytest tests/backend/test_mcp_server.py -q
```

- **Core's tests:** 117 pass, core's 112 plus 5 new. `mcp_world_model.py` is at 100% line and branch coverage.
  `ruff check src tests scripts` is clean.
- **The new tests** run against a stand-in service (`httpx.MockTransport`). They check:
  - the key and the on-behalf-of header;
  - every route and its parameters;
  - output schemas;
  - that writes only propose, and that no tool approves;
  - ingesting a project source by id;
  - each error path;
  - the per-organization keys.
- **End to end:** the same tools, run against a live world model service with a real key, answered as
  `core for smoke/<org_user_id>`. They stored and parsed an uploaded project source, and returned
  `node_not_found` as a tool error. That run is not part of the patch.

If #74 lands first, `docs/mcp/SETUP.md` may conflict. The patch changes only the "world model" bullet and adds one
paragraph after the tool list.

## Configure it

| Core setting | Environment variable | Value |
|---|---|---|
| `world_model_service_url` | `AXELROD_WORLD_MODEL_SERVICE_URL` | the world model service's origin, e.g. `https://world-model-dev.up.railway.app` |
| `world_model_service_keys_raw` | `AXELROD_WORLD_MODEL_SERVICE_KEYS` | `org_id=key` entries, comma-separated; `*=key` serves every other organization. Keys are 24+ characters |

On the world model's side, each key is an entry in `WORLD_MODEL_API_KEYS` (`core:<key>:<login>`), and the login
decides which world model that organization sees. Both sides keep keys only in Railway's variables. Without the core
settings, every `world_model_*` tool returns `world_model_unavailable`, and the rest of the catalog is unaffected.

## Keeping the two catalogs in step

`tests/service/test_core_integration.py` in this repo reads the patch. It checks that every tool the patch publishes
calls a route this service serves, and that the two tools left out stay left out. When a route changes here, that test
fails until the patch is regenerated.
