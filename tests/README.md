# Tests

Every suite in `tests/`: what it covers, how many tests it holds, how to run it, and what it needs. The last section
is the design of the service's integration tests and how far it has got.

<!-- toc -->
**Contents**

- [Running them](#running-them)
- [The suites](#the-suites)
- [Markers, skips, and extras](#markers-skips-and-extras)
- [Coverage policy](#coverage-policy)
- [The outward API's tests](#the-outward-apis-tests)
- [Integration tests: design and status](#integration-tests-design-and-status)
<!-- /toc -->

## Running them

```bash
uv run pytest                                   # everything but the slow runs (they are collected and skipped)
uv run pytest --runslow                         # also the full scenario runs and the browser smoke tests
uv run pytest tests/service tests/integration tests/unit tests/lake tests/ingest -q -p no:warnings -m "not slow"
uv run pytest -m integration                    # the service's end-to-end flows only (about a minute)
uv run pytest -m "not integration"              # everything else
uv run --with playwright==1.58.0 pytest tests/ui --runslow   # the browser tests (run `playwright install chromium` once)
uv run ruff check src tests
```

Every test gets its own lakehouse directory and the exact `hashing` embedder, with no LLM step and no API keys from
the environment (`tests/conftest.py`), so nothing reads or writes the repository's `var/lake` and no model is
downloaded. All test data is synthetic: the notes and bundles in the tests are made up, and no test reports a real
event.

## The suites

Counts are from `uv run pytest --collect-only -q <folder>` on Oct 18 and include parametrized cases; `tests/service/`,
`tests/lake/`, `tests/unit/api/`, and `tests/integration/service/` were recounted after API v1.

| Suite | Tests | What it covers |
|---|---:|---|
| `tests/unit/` | 1,040 | Each package's units, without the HTTP app (below) |
| `tests/ingest/` | 583 | The ingestion pipeline: parsing (PDF, DOCX, PPTX, XLSX, HTML, CSV, Markdown, text, JSON), chunking, the gazetteer, rule and LLM extraction, the benchmark and its precision bar, and determinism (byte-identical across lakes, orders, processes, hash seeds, and read times) |
| `tests/lake/` | 150 | The lakehouse: the store's contract, SQLite (documents, chunks, FTS5, mentions, embeddings, bundles, imports, tenants, the world model registry, the audit log, idempotency keys and jobs), embedders, and search in every mode |
| `tests/service/` | 559 | The outward API, v1 (`/v1/world-models/{id}`, [docs/api/openapi.yaml](../docs/api/openapi.yaml)), its credentials, and its MCP server: see [below](#the-outward-apis-tests) |
| `tests/integration/` | 131 | The demo's own API (`/api/...`) and `/ws` through FastAPI's TestClient: update runs, staged review and selective approval, examples, the library, the log, structure edits, imports, the brief, the v4 export's determinism across processes; and `tests/integration/service/` (8), the service's end-to-end flows |
| `tests/scenario/` | 106 | Whole scenarios: initialization, determinism, restore; the small demo example by example, with rewind; the Sally demo's expected paths; the Toyota, Tokio Marine, and JPMorgan constructions; the full oil-demo checklist and the production demo (slow) |
| `tests/ui/` | 3 | Playwright smoke tests of the page and of importing a document (slow; skipped without Playwright or Chromium) |

`tests/unit/` by package:

| Folder | Tests | Covers |
|---|---:|---|
| `model/` | 166 | Distributions, the graph and its parts, taxonomies, kind defaults, business construction, calibration, corporate actions |
| `inference/` | 118 | Forecast tasks, transmission and paths, scenario tables, coupling and explanation, value of information, groups, calculation coverage, performance |
| `sim/` | 88 | Scenario scripts, the runner, the world, examples, imports, the checklist |
| `engine/` | 75 | Config, context, cursors, defaults, initialization, the registry and every slot's contract, RNG |
| `learning/` | 73 | Working and long-term memory, consolidation, abduction, kernel learning, the frontier, retirement |
| `shared/` | 69 | Classification, recognition, recall, parsing, explanation |
| `dynamics/` | 66 | Kernels, propagation, regressors, the daily model |
| `control/` | 56 | The controller, staged review, update runs and their loop |
| `intake/` | 52 | Intake, the refiner and its review, overlapping views |
| `repo/` | 49 | Snapshots, the ledger, the mutator, review records, history, persistence |
| `api/` | 57 | The demo app's state, auth and websocket, play; v1's failure-to-problem mapping and projection edge cases |
| `context/` | 42 | The construction view, sources and citations, the construction scripts and export, the v4.1.4 export |
| `flows/` | 28 | The flowchart is well formed and current in `docs/flowchart.svg` |
| `cli/` | 21 | The `axelrod` command |
| `evaluation/`, `memory/`, `events/`, `trace/` | 58 | Backtests and metrics; Entity memories, the frontier, working and long-term memory; graph-update events; the trace |
| top level | 37 | Basic auth, the build info, the import bundle format, the Railway drift verifier |

## Markers, skips, and extras

| Marker or condition | Where | Effect |
|---|---|---|
| `slow` | the full oil-demo checklist, the production demo, every slot alternative (`tests/integration/test_api.py`), the browser tests | Collected and skipped unless `--runslow` (`tests/conftest.py`) |
| `integration` | `tests/integration/service/` | Selects the service's end-to-end flows: `-m integration`, or `-m "not integration"` to leave them out. Registered in `pyproject.toml` |
| Playwright | `tests/ui/` | Skipped without it (`pytest.importorskip`) or without Chromium; run with `uv run --with playwright==1.58.0 pytest tests/ui --runslow` |
| `data/sally_data/` (local client data, gitignored) | the Tokio Marine and Toyota construction checks that read the client's own files, and `tests/unit/context/test_construction_scripts.py` | Skipped where it is absent, as on CI. `SALLY_CONSTRUCTION` points the Tokio Marine checks at another folder. Never commit that data |

## Coverage policy

- **Strict modules are fully covered**: every line and every branch, with no pragmas and no omissions (an unreachable
  line is deleted). They are the ingestion pipeline (`src/axelrod_wm/ingest/*`), the lakehouse
  (`src/axelrod_wm/lake/*`), and the outward service (`api/v1/*`, `api/tokens.py`, `api/mcp.py`, `api/keys.py`):
  `STRICT` in `scripts/coverage_gate.py`.
- **Everything else ratchets.** `coverage-floor.json` holds the repository's line, branch, and combined coverage (100%
  each today). A run below the floor fails; `--update` raises the floor when a run beats it, never lowers it.
- **CI** (`.github/workflows/tests.yml`) runs `tests/unit` on every pull request, and the whole suite (not the slow
  runs) with coverage, then the gate:

```bash
uv run pytest --cov=axelrod_wm --cov-branch --cov-report=json:coverage.json --junitxml=junit.xml
uv run python scripts/coverage_gate.py coverage.json --junit junit.xml [--update] [--readme README.md]
```

`--readme` rewrites the test widget in the repository's README from the JUnit XML.

## The outward API's tests

`tests/service/` holds the API to its contract ([docs/api/openapi.yaml](../docs/api/openapi.yaml)), route by route
and across all routes at once, so a route added later cannot skip a rule. `helpers.py` holds what they share: a static
key, and `Signer`, core's side of a service token for tests (an ephemeral ES256 key whose JWKS an
`httpx.MockTransport` serves, so nothing calls core).

| File | Tests | What it proves |
|---|---:|---|
| `test_v1_reads.py` | 37 | Each read: world models, versions, entities and their nested attributes, observations and states, compositions and paths, construction (JSON and markdown), traces (`through_totals`, `max_depth`), relationships and evidence, concepts, groups, the graph, the export; pinning by `version` and `as_of`, cursors, ETags and 304s |
| `test_v1_work.py` | 28 | Each write and workflow read: uploads as jobs (202, `Location`), documents, chunks and content, bundles, search in every mode, changes and their human review (`If-Match`, 428, 412, 409), evidence from an approved support, events and impact analysis, theses and simulations, failed jobs, `Idempotency-Key` kept forever and creation keyed on content |
| `test_v1_erid.py` | 7 | The unified world model, `/v1/erid`: the main engine's whole graph for internal staff (`403 internal_only` otherwise); a compartment equals the focused scenario (same entities and relationships); mirrored reads narrow, pin and page; a compartment for its assigned organization only; scopes; what the unified model learns reaches the compartment |
| `test_v1_auth.py` | 10 | Every operation's `x-required-scope` (a 403 sweep from the spec), two organizations (another's world model is 404), `WORLD_MODEL_OWNERS`, decisions by a person only (a key, an `act` token, or `azp: core-mcp` gets 403), the audit log's actor, org, `azp`, `act`, and `jti` |
| `test_tokens.py` | 26 | Service tokens: ES256 `at+jwt` with a `kid` only, `iss`/`aud`/`exp` (60 s leeway), required claims, `act`, deny lists, scope filtering, `core-mcp` and `act` tokens capped at `world_model:read`, the JWKS cache (refetch at most once a minute, a stale set for a day, 503 when the issuer is down) |
| `test_openapi_contract.py` | 129 | The spec lints as OpenAPI 3.1; served routes equal specified operations both ways; every answer (success and problem, every company's construction) validates against its declared response schema; the problem codes are the spec's; the generated reference and terms tables are current |
| `test_conventions.py` | 257 | Every route has a summary, refuses a caller without a credential (401 problem, `WWW-Authenticate`), echoes `X-Request-Id` and `traceparent`, carries `X-Axelrod-API-Version`, fails as a problem with a contract code, and refuses unknown body fields |
| `test_mcp.py` | 27 | Every MCP tool (32) through the SDK's own client: reads, pins, the golden-test reads (retrieval profiles, `occurred_at`, traces through totals), states, compositions, paths, ingestion, proposals, simulations, erid and compartments, the default world model, the access boundary (a read-only key, `core-mcp` and `act` tokens refused writes), no tool that decides, errors as tool errors |
| `test_keys.py` | 36 | Static scoped keys (parsing, scopes, read-only by default, rotation, never `changes:approve`), `WORLD_MODEL_OWNERS`, and the front door: keys, tokens, sessions, an open local run, 401 and 503 problems |
| `test_core_integration.py` | 2 | The patch for core's MCP catalog calls only routes the contract specifies and this service serves, only with GET: 17 read tools, none that writes or decides |

## Integration tests: design and status

`tests/integration/service/` runs the service end to end: REST and MCP over one app, with the lakehouse, the engine,
the review queue, and the snapshot store all real, on directories of the test's own. Each test is one user-visible
flow on v1, starts from a fresh service (`tests/service/helpers.py`: `service()`, with `root=` for files that a
restarted service reuses), and uses synthetic, dated notes only. Callers propose with a static key; a person decides
with a service token (`conftest.py`: `review_all`). They are marked `integration`.

**Budget.** About 50 seconds for the suite on a laptop (each flow 3–15 s; booting the Sally demo takes about 1 s). A
new flow should stay under 20 s; one that needs longer is marked `slow` as well.

| # | Flow | What it proves | Status |
|---|---|---|---|
| I1 | Upload → bundle → propose → a person approves → pinned read (`test_review_flow.py`) | The note's claim is not in the model before review; approval commits a new version naming the person (`decided_by`) and the proposer; the version before, and the state by date, stay readable; the document is searchable; a second proposal of the bundle is a no-op. Rejected changes leave the level where it was | Implemented |
| I2 | The ingestion pipeline proposes over MCP; a person decides (`test_mcp_flow.py`) | The tools compose into the flow with the pipeline's key; a `core-mcp` token is refused a proposal; no tool and no key can decide (403); after a person's approval the tools read the new version and the pinned old one, equal to the REST answers | Implemented |
| I3 | A simulation whose coverage names its unquantified relationships (`test_forecast_coverage.py`) | Every uncalibrated relationship the shock reaches is excluded in the coverage with its sign and mechanism, reads as size-unknown (null) where the API serves the relationship, holds back some target's `share_quantified`, and the same coverage reaches the brief and the v4.1.4 export | Implemented |
| I4 | Restart persistence (`test_restart.py`) | The lakehouse survives a restart whole (documents, text, chunks, raw bytes, bundles, items, search, counts, the audit log, the registry, idempotency keys and jobs: a key and the same content get the first answer after the restart). The model does not: it reloads from its initial snapshot and the earlier versions are 404. Re-proposing the stored bundle with the same decisions rebuilds the same version and state hash | Implemented (documents today's behavior; see the note below) |
| I5 | Export → re-import (`test_export_reimport.py`) | A bundle read out of one service (summary and items) and posted into a fresh one, with the same changes approved, gives the same version, state hash, attribute levels, and v4.1.4 export | Implemented |
| I6 | Multi-organization isolation through the whole flow (`test_tenancy_flow.py`) | Two organizations each upload, propose, review, and simulate; the other's world model is 404 by every route (documents, bundles, changes, simulations, jobs, audit, decisions); each model moved by its own note only; the same file is the same ids in both, proposed independently | Implemented |
| I7 | Concurrent updates (`test_concurrency.py`) | Two proposals at the same moment: one runs and waits for review, the other is `409 update_in_progress` (the check and the claim are one step under the engine's lock); reads still answer; the refused one goes through after review | Implemented |
| I8 | Late items | A bundle item dated before the model's last closed day is listed under `late_item_ids` and folds into the next day | Planned |
| I9 | Re-extraction after the model changes | `POST .../documents/{id}/bundles` after a change gives a new bundle against the new model, and the old bundle stays as history | Planned |
| I10 | Core's catalog against a live service | The patched core MCP tools (integrations/core) against this app over HTTP, not a stand-in | Planned |
| I11 | Large uploads | Twenty files of mixed formats in one request, near the size limit, within the time budget | Planned |
| I12 | Deletion | Deleting a document removes its text, chunks, indexes, and mentions from search, and keeps its bundles and imports as history | Planned |

**Note on I4.** A service loads its scenario from the initial snapshot and resets the snapshot store
(`sim/runner.py`, `_session_storage`), so committed versions do not survive a restart, while the lakehouse does. The
test asserts that, and that re-proposing the stored bundles with the same decisions rebuilds the model exactly. If versions should survive a
restart, the restart half of I4 changes; the replay check stays.

**Note on determinism.** A bundle's id is the hash of its content without `collected_at` (when it was read), so the
same file, under the same name, gives the same bundle id in any service or login. A different file name is a different
bundle, because the bundle's description names the file.
