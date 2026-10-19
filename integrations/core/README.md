# The world model in core's MCP catalog

For Zsolt (core's MCP) and whoever applies it to `Axelrod-AI-Engineering/core`. This repo never writes to core: the
change is a patch, ready to apply on a core branch and review there.

- [What it adds](#what-it-adds)
- [How it works](#how-it-works)
- [Apply and test it](#apply-and-test-it)
- [Configure it](#configure-it)
- [What comes next: service tokens](#what-comes-next-service-tokens)
- [Keeping the two catalogs in step](#keeping-the-two-catalogs-in-step)

## What it adds

[`0001-world-model-service-mcp-tools.patch`](0001-world-model-service-mcp-tools.patch), made against core `main` at
`01886b5` (after #67 and #72). It extends core's own seam, `register_mcp_world_model_tools` in
`src/axelrod_app/mcp_world_model.py`, which #67 left for "further World Model reads". `search_canonical` is unchanged.

Every tool calls the service's v1 API ([../../docs/api/](../../docs/api/README.md)) under `/v1/world-models/{world_model_id}`
(`{wm}` below). Each tool takes a `world_model_id`, which defaults to the organization's only world model.

| Tool | World model route | Effect |
|---|---|---|
| `world_model_list_world_models`, `world_model_get_world_model` | `GET /v1/world-models`, `GET {wm}` | read |
| `world_model_graph` | `GET {wm}/graph` (`version` / `as_of` pin the read) | read |
| `world_model_list_entities` | `GET {wm}/entities` (an entity matched through its attributes nests just those) | read |
| `world_model_get_entity`, `world_model_get_attribute` | `GET {wm}/entities/{id}`, `…/attributes/{attribute}` (`version` pins either) | read |
| `world_model_list_concepts` | `GET {wm}/concepts` | read |
| `world_model_search` | `GET {wm}/search` | read |
| `world_model_construction`, `world_model_construction_markdown` | `GET {wm}/entities/{id}/construction` (JSON, or markdown) | read |
| `world_model_trace` | `GET {wm}/entities/{id}/traces?from=` (`through_totals`, `max_depth`) | read |
| `world_model_get_simulation`, `world_model_simulation_brief` | `GET {wm}/simulations/{id}`, `…/brief` | read |
| `world_model_export_v4` | `GET {wm}/exports/v4.1.4` | read |
| `world_model_list_documents`, `world_model_get_bundle`, `world_model_list_changes` | `GET {wm}/documents`, `{wm}/bundles/{id}` and `…/items`, `{wm}/changes` | read |

**Read only.** As agreed in the API review (Oct 19, [docs/design/architecture-plan.md](../../docs/design/architecture-plan.md)),
core's backend MCP reads the world model and does not write to it. The three write tools of the earlier patch
(`world_model_simulate`, `world_model_ingest_source`, `world_model_propose_changes`) are removed. Documents, proposed
changes and simulations reach the world model through its web interface (a signed-in person) and the data-ingestion
pipeline (a scoped key). The service enforces the same boundary on its side: a token on the `core-mcp` channel, or
with `act`, holds `world_model:read` only, whatever it asks for.

The world model's own MCP tools that core leaves out:

- **Deciding a change.** Approving a world model change is a person's decision in a review UI. Our own `/mcp` has
  no such tool either, and the service refuses a decision from a key or an agent-driven token
  (`403 human_approval_required`).
- **Every write:** `world_model_ingest_document`, `world_model_propose_changes`, `world_model_simulate` (read only,
  above). If core's MCP is later granted writes, the earlier `world_model_ingest_source` (a core project source sent by
  id, so the bytes never pass through the conversation) is the shape to bring back.
- **The unified world model** (`/v1/erid`): for internal staff; core reads per-organization world models.

## How it works

- **Who is asking.** Each tool authenticates the org user from core's MCP token, as every core tool does. It then
  calls the world model service with the key for that user's organization. The `X-Axelrod-On-Behalf-Of` header is
  gone: the service no longer takes a person's identity from a header it cannot check (see
  [What comes next](#what-comes-next-service-tokens)).
- **Errors** come back as core's tool errors, `"<code>: <detail>"`, from the service's RFC 9457 problems
  (`entity_not_found`, `version_not_found`, …).
  - A service that can't be reached gives `world_model_unavailable`.
  - A response that isn't a problem gives `world_model_error: HTTP <status>`.
- **Results** are structured: `WorldModelResult` carries the service's `data` and `meta` (the request id and the
  version read). Each tool publishes an output schema, as #66 requires.
- **Annotations** follow core's sets in `mcp_catalog.py`:
  - every tool is in `_READ_ONLY_TOOLS`;
  - all are closed-world.

  Titles are in `_TOOL_TITLES`, and the group is `McpDocGroup.WORLD_MODEL`, so #74's generated reference lists them
  under "World model".

## Apply and test it

```bash
git switch -c world-model-service-tools origin/main
git am /path/to/0001-world-model-service-mcp-tools.patch
EODHD_API_KEY=placeholder AXELROD_WORLD_MODEL_EVENTS_ENABLED=0 .venv/bin/python -m pytest tests/backend/test_mcp_server.py -q
```

- **Core's tests:** 117 pass, core's 112 plus 5 new (re-run Oct 19 on the clone at `01886b5`). `mcp_world_model.py`
  is at 100% line and branch coverage. `ruff check src tests scripts` is clean.
- **The new tests** run against a stand-in v1 service (`httpx.MockTransport`). They check:
  - the key, and that no on-behalf-of header is sent;
  - every route and its parameters, and the default world model (found by listing the organization's models);
  - output schemas;
  - that every tool reads (only GET requests), and that none writes or decides;
  - each error path, and an organization with several world models.

If #74 lands first, `docs/mcp/SETUP.md` may conflict. The patch changes only the "world model" bullet and adds one
paragraph after the tool list.

## Configure it

| Core setting | Environment variable | Value |
|---|---|---|
| `world_model_service_url` | `AXELROD_WORLD_MODEL_SERVICE_URL` | the world model service's origin, e.g. `https://world-model-dev.up.railway.app` |
| `world_model_service_keys_raw` | `AXELROD_WORLD_MODEL_SERVICE_KEYS` | `org_id=key` entries, comma-separated; `*=key` serves every other organization. Keys are 24+ characters |

On the world model's side, each key is an entry in `WORLD_MODEL_API_KEYS` (`core:<key>:<org>`, which holds
`world_model:read` only when no scopes are listed), and the organization decides which world models
the key sees. Both sides keep keys only in Railway's variables. Without the core settings, every `world_model_*` tool
returns `world_model_unavailable`, and the rest of the catalog is unaffected.

## What comes next: service tokens

[docs/design/core-mcp-auth.md](../../docs/design/core-mcp-auth.md) replaces the org keys with a short-lived ES256 token
that core mints per call (`sub` = the org user, `org`, `scope`, `azp: core-mcp`, and `act` naming the MCP host). The
world model service already verifies such tokens (`WORLD_MODEL_TRUSTED_ISSUERS`) and records each actor. The patch
does not mint them yet: that is core's step 3 of the rollout (a mint function, a JWKS route, signing-key settings, and
the MCP `client_id` on the access token), proposed in §6 of that document. Until then, the service records core's
calls as the key's caller, with no person.

## Keeping the two catalogs in step

`tests/service/test_core_integration.py` in this repo reads the patch. It checks that every request the patch's tools
make is a route of [docs/api/openapi.yaml](../../docs/api/openapi.yaml) that this service serves, with the same
method, and that no tool decides a change. When a route changes here, that test fails until the patch is regenerated.
