# World model API

The world model as a service, v1: entities and their attributes, relationships and their evidence, read at a stated
version; documents read into proposed changes that a person reviews; theses run as simulations. The same service is
exposed twice: as REST under `/v1`, and as MCP tools at `/mcp`.

The contract is [openapi.yaml](openapi.yaml) (OpenAPI 3.1). The [Reference](#reference) below is generated
from it. [design/api.md](../design/api.md) explains why the API looks the way it does, and
[design/core-mcp-auth.md](../design/core-mcp-auth.md) explains how core authenticates.

<!-- toc -->
**Contents**

- [Who it is for](#who-it-is-for)
- [Authentication and scopes](#authentication-and-scopes)
- [Conventions](#conventions)
- [Entities and attributes](#entities-and-attributes)
- [A walk-through](#a-walk-through)
- [MCP](#mcp)
- [Mounting it from core](#mounting-it-from-core)
- [Configuration](#configuration)
- [Code and tests](#code-and-tests)
- [Reference](#reference)
  - [World models](#world-models)
  - [Versions](#versions)
  - [Entities](#entities)
  - [Construction](#construction)
  - [Relationships](#relationships)
  - [Taxonomy](#taxonomy)
  - [Events](#events)
  - [Documents](#documents)
  - [Bundles](#bundles)
  - [Search](#search)
  - [Changes](#changes)
  - [Theses](#theses)
  - [Simulations](#simulations)
  - [Graph](#graph)
  - [Exports](#exports)
  - [Jobs](#jobs)
  - [Errors](#errors)
  - [Schemas](#schemas)
<!-- /toc -->

## Who it is for

- **Core's MCP server** reads the model and proposes changes for its signed-in users. It uses core-minted service
  tokens.
- **The LLM harness, scripts, and our own `/mcp`** read, upload, and propose. They use scoped static keys.
- **A person in a review UI** approves or rejects each proposed change. This takes a session or a core-web token.

The service owns the world model. It does not own the agents that use it.

## Authentication and scopes

The organization and the person always come from a credential the service can verify. A header or a path never
supplies them. There are three kinds of credential, plus an open local mode:

| Credential | Who it names | How |
|---|---|---|
| **Service token** (`serviceToken`) | a person in an organization, and the agent host when one drives the call | a short-lived ES256 JWT that core mints per call, verified against a trusted issuer's JWKS. Claims are `iss`, `aud`, `exp` (5 min), `iat`, `jti`, `sub` (org user), `org`, `scope`, `azp` (`core-mcp` or `core-web`), `name`, and `act` |
| **Static key** (`apiKey`) | a service of an organization (no person) | `Authorization: Bearer <key>`, from `WORLD_MODEL_API_KEYS` entries `caller:key:org[:scope+scope…]` |
| **Session** (`session`) | a person signed in to this service | the sign-in cookie (the review UI, `/docs`) |
| *Local* | `local` | with no keys, logins or issuers configured, `/v1` is open with every scope except `changes:review` |

**Scopes**, in four tiers. Each operation in the reference names the scope it needs (`x-required-scope`). A credential
without that scope gets `403 insufficient_scope`.

| Tier | Scopes | Routes |
|---|---|---|
| read | `read` | every `GET` |
| propose | `documents:write`, `changes:write`, `simulations:write` | `POST` documents, bundles, re-extraction; `POST /changes`; `POST` theses and simulations |
| approve | `changes:review` | `POST /changes/{id}/approvals` and `/rejections` |
| admin | `admin` | `DELETE /documents/{id}`, the audit log |

- **Approval is human-only.** A decision from a static key, or from a token that carries `act` or `azp: core-mcp`, is
  `403 human_approval_required`, whatever its scopes. A static key never carries `changes:review`: the service refuses
  to start with such an entry.
- **Tenancy.** Each world model belongs to one organization (the `world_models` registry). A world model of another
  organization answers `404 world_model_not_found`, the same as one that does not exist.
- **Audit.** Every write records its actor (`kind`, `org`, `sub`, `name`, `azp`, `act`, `jti`) in the world model's
  audit log (`GET …/audit-events`). Changes carry it as `proposed_by` and `decided_by`.
- **Failures.** A missing or invalid credential is `401` (`authentication_required`, `invalid_token`) with
  `WWW-Authenticate: Bearer`. A token that names an unknown signing key, when the issuer's JWKS cannot be reached, is
  `503 issuer_unavailable`.

## Conventions

- **Envelope.** A resource answers `{"data": {…}, "meta": {"request_id", "version"}}`. A collection answers
  `{"data": […], "meta": {"request_id", "version", "limit", "next_cursor"}}`.
- **Errors** are RFC 9457 problem details, `application/problem+json`, with a stable `code`. See [Errors](#errors).
- **Pinning.** Reads of the model take `version=N` or `as_of=<date-time>`, and `meta.version` names what was served:
  `number`, `state_hash`, `committed_at`, `latest`, `clock`. A version outside the model, or a date before it begins,
  is `404 version_not_found`.
- **Pagination** is by cursor: `limit` (1–200, default 50), then the previous page's `meta.next_cursor`. A cursor
  keeps the version it started on. A cursor the service did not issue is `400 invalid_cursor`.
- **Idempotency.** A `POST` that creates takes `Idempotency-Key`. The same key with the same body returns the first
  answer. The same key with another body is `422 idempotency_key_reused`. Content-hash ids make uploads and bundles
  idempotent as well.
- **Async work** (uploads, re-extraction, proposing changes, simulations) answers `202` with a job and
  `Location: …/jobs/{id}`. Poll the job until it succeeds or fails.
- **Concurrency.** Reads of the model carry `ETag: "<state_hash>"`, and `If-None-Match` gives `304`. A decision on a
  change needs `If-Match` with the ETag of the version it was reviewed against. Without one it is
  `428 precondition_required`; if the model has moved, it is `412 version_moved`.
- **Facts and inferences.** Every claim carries an `epistemic_type` (documented, observed, reported, broker,
  guidance, model, assumption, expert_judgment, inferred). Theses and simulations never write facts. A change becomes
  fact only when a person approves it.
- **Time.** Observations are bitemporal (`valid_at`, `observed_at`). Documents have `published_at` and `ingested_at`.
  Relationships have `valid_from` and `valid_to`.
- **Headers.** Every response carries `X-Request-Id` (yours, if you sent one) and `X-Axelrod-API-Version: 1`. A W3C
  `traceparent` is echoed.
- **Determinism.** The same file (name and bytes), read against the same model, gives the same document, chunks,
  signals, and bundle ids. The same bundle proposed and approved on the same version gives the same `state_hash`.
- **Restarts.** The lakehouse (documents, bundles, audit) survives a restart. The model reloads from its initial
  snapshot, so replay its approved changes to rebuild later versions.

## Entities and attributes

An **entity** is a company, an agency, a market, or a factor, with a stable internal id (`toyota`) that is never a
ticker. Tickers live in `identifiers`. Its **attributes** are its measured quantities. An attribute's id is
`<entity id>.<key>`: `toyota.operating_profit` is the attribute `operating_profit` of `toyota`. Attributes are nested
in their entity. `/entities/{entity_id}/attributes/{attribute_key}` takes the key or the full id.

A **relationship** runs between two attributes: `source_attribute_id` → `target_attribute_id`, with its `type`
(causal, accounting, identity, stock_flow), `confidence` (0–1), and `effect` (target sd per source sd). An
uncalibrated relationship has a sign but no size, so its `effect` is `null`, never 0. Its `evidence` records cite
their sources.

In the code, an attribute is a *subentity* and a relationship is an *interaction*. A simulation is the engine's
*forecast*, and a change is its *proposal* (see [vocab.md](../vocab.md)).

## A walk-through

```bash
API=https://world-model-dev.up.railway.app/v1
AUTH="Authorization: Bearer $WORLD_MODEL_KEY"
WM=$API/world-models/sally_demo

curl -s -H "$AUTH" $API/world-models | jq '.data[].id'
curl -s -H "$AUTH" "$WM/entities/toyota" | jq '.data.attributes[] | {key, level}'

# upload a note: 202 and a job; the job's result names the document and its bundle
curl -s -H "$AUTH" -H "Idempotency-Key: $(uuidgen)" -F files=@2026-09-01_data.txt -F source_type=data \
     $WM/documents | jq '.data'
curl -s -H "$AUTH" $WM/jobs/<job-id> | jq '.data.result'
curl -s -H "$AUTH" $WM/bundles/<bundle-id>/items | jq '.data[] | {id, headline, signals}'

# propose a change per item; a person approves each, against the version they reviewed
curl -s -H "$AUTH" -H 'Content-Type: application/json' -d '{"bundle_id": "<bundle-id>"}' $WM/changes
curl -s -H "$AUTH" "$WM/changes?status=pending" | jq '.data[].id'
curl -si -H "$REVIEWER" $WM/changes/<change-id> | grep -i etag
curl -s -H "$REVIEWER" -H 'If-Match: "<etag>"' -H 'Content-Type: application/json' -d '{"note": "checked"}' \
     $WM/changes/<change-id>/approvals

# the change, and the state before it
curl -s -H "$AUTH" "$WM/entities/oil/attributes/brent"
curl -s -H "$AUTH" "$WM/entities/oil/attributes/brent?version=<version-before>"

# a what-if, run as a simulation
curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d '{"question": "What if the BoJ hiked by 25bp next quarter?"}' $WM/theses
curl -s -H "$AUTH" -X POST $WM/theses/<thesis-id>/simulations
curl -s -H "$AUTH" $WM/simulations/<simulation-id>/coverage
```

`$REVIEWER` is a person's credential: a session or a core-web token. A key cannot approve.

## MCP

`/mcp` is an MCP server (`axelrod-world-model`) over stateless Streamable HTTP, built on the official `mcp` 2.x SDK.
It takes the same credentials. Each tool calls the REST route in process, so answers, auth, and errors are identical.
A REST error comes back as a tool error, `"<code>: <detail>"`. Every tool takes `world_model_id`, which defaults to the
organization's only world model. No tool decides a change: approval is a person's step in a review UI.

| Tool | Route | Annotation |
|---|---|---|
| `world_model_list_world_models` | `GET /world-models` | read-only |
| `world_model_get_world_model` | `GET {wm}` | read-only |
| `world_model_list_versions` | `GET {wm}/versions` | read-only |
| `world_model_graph` | `GET {wm}/graph` | read-only |
| `world_model_list_entities` | `GET {wm}/entities` | read-only |
| `world_model_get_entity` | `GET {wm}/entities/{entity_id}` | read-only |
| `world_model_get_attribute` | `GET {wm}/entities/{entity_id}/attributes/{attribute_key}` | read-only |
| `world_model_list_observations` | `GET …/attributes/{attribute_key}/observations` | read-only |
| `world_model_list_relationships` | `GET {wm}/relationships` | read-only |
| `world_model_get_relationship` | `GET {wm}/relationships/{id}` and its evidence | read-only |
| `world_model_list_concepts` | `GET {wm}/concepts` | read-only |
| `world_model_construction` | `GET {wm}/entities/{entity_id}/construction` (json or markdown) | read-only |
| `world_model_trace` | `GET {wm}/entities/{entity_id}/traces` | read-only |
| `world_model_list_events` | `GET {wm}/events` | read-only |
| `world_model_impact_analysis` | `GET {wm}/events/{event_id}/impact-analysis` | read-only |
| `world_model_search` | `GET {wm}/search` | read-only |
| `world_model_ingest_document` | `POST {wm}/documents` (`content_base64` or `text`) | write, idempotent |
| `world_model_list_documents` | `GET {wm}/documents` | read-only |
| `world_model_get_bundle` | `GET {wm}/bundles/{id}` and its items | read-only |
| `world_model_propose_changes` | `POST {wm}/changes` | write |
| `world_model_list_changes` | `GET {wm}/changes` | read-only |
| `world_model_get_change` | `GET {wm}/changes/{id}` and its diff | read-only |
| `world_model_simulate` | `POST {wm}/theses`, then `POST {wm}/theses/{id}/simulations` | write |
| `world_model_get_simulation` | `GET {wm}/simulations/{id}`, with its coverage | read-only |
| `world_model_simulation_brief` | `GET {wm}/simulations/{id}/brief` | read-only |
| `world_model_export_v4` | `GET {wm}/exports/v4.1.4` | read-only |
| `world_model_get_job` | `GET {wm}/jobs/{id}` | read-only |

The read tools take `version` and `as_of` where their routes do. To use it from Claude Code:

```bash
claude mcp add --transport http world-model https://world-model-dev.up.railway.app/mcp --header "Authorization: Bearer $WORLD_MODEL_KEY"
```

## Mounting it from core

Core re-publishes these tools in its own MCP catalog, under its own sign-in. The proposal is
[integrations/core](../../integrations/core/README.md). For each call, core mints a service token for the signed-in org
user, with the tool's scopes and `act` naming the MCP host, and calls `/v1/world-models/{id}/…`. The patch publishes no
tool that decides a change.

## Configuration

| Variable | Default | What it sets |
|---|---|---|
| `WORLD_MODEL_API_KEYS` | none | static keys, `caller:key:org[:scope+scope…]`. With no scopes, a key has `read documents:write changes:write simulations:write`. `changes:review` is refused. Each caller may hold two keys, so keys can rotate by overlap |
| `WORLD_MODEL_TRUSTED_ISSUERS` | none | `issuer;jwks_url;audience` entries, comma-separated, one per core stage. JWT verification is off unless this is set |
| `WORLD_MODEL_DENY` | none | `kid:…`, `org:…` or `sub:…` entries, refused at once |
| `WORLD_MODEL_LAKE_DIR` | `var/lake` | the lakehouse: the SQLite catalog (documents, bundles, the world model registry, the audit log) and raw files per organization |
| `WORLD_MODEL_EMBEDDER` | `auto` | `fastembed` (bge-small), `hashing` (exact; used in tests), or `auto` |
| `WORLD_MODEL_EMBED_CACHE` | fastembed's default | where the embedding model is cached |
| `WORLD_MODEL_LLM_PROVIDER` | off | `anthropic` or `openai` for the optional extraction step |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `WORLD_MODEL_LLM_MODEL` | none | the provider's key and model |

The organization of a login is its username. The main login's organization is `WORLD_MODEL_BASIC_AUTH_USERNAME`, or
`default` with no logins. Secrets live in Railway's variables only, never in the repository.

## Code and tests

| Part | Code | Tests |
|---|---|---|
| The contract | `docs/api/openapi.yaml` | `tests/service/test_openapi_contract.py` (lint, route parity, response schemas, this reference) |
| REST routes | `src/axelrod_wm/api/v1/` (API models in `schemas.py`, projections from the domain in `project.py`) | `tests/service/` |
| Credentials, tokens, scopes | `src/axelrod_wm/api/keys.py`, `api/tokens.py`, `api/auth.py` | `tests/service/test_keys.py`, `test_tokens.py` |
| MCP server | `src/axelrod_wm/api/mcp.py` | `tests/service/test_mcp.py` |
| End-to-end flows | the service, MCP, lakehouse, engine and snapshots together | `tests/integration/service/` |

[tests/README.md](../../tests/README.md) lists every suite.

## Reference

<!-- reference:start -->
All 61 operations, from the contract ([openapi.yaml](openapi.yaml)). Paths are under `/v1`; `{wm}` is `/world-models/{world_model_id}`.

### World models

The organization's world models and the credential's identity.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET /me` | Who the credential is: organization, caller, scopes, world models | `read` |  | 200, 401, 403, 404, 503 |
| `GET /world-models` | The organization's world models | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}` | One world model: its latest version, clock and counts | `read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/audit-events` | The world model's audit log, newest first | `admin` |  | 200, 400, 401, 403, 404, 422, 503 |

### Versions

Committed, immutable versions.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/versions` | Committed versions, newest first | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/versions/{version_ref}` | One committed version (`latest` for the newest) | `read` |  | 200, 401, 403, 404, 422, 503 |

### Entities

Entities, their attributes, observations and states.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/entities` | Entities, filtered by type, concept, group or name | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}` | One entity, with its attributes (and relationships) | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes` | An entity's attributes | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}` | One attribute: level, spread, unit, view, basis, and its latest observation | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}/observations` | An attribute's dated observations (valid_at, observed_at) | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}/states` | The model's state of an attribute over time, oldest first | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |

### Construction

How a company is built: compositions, paths, the whole construction, traces.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/entities/{entity_id}/compositions` | An entity's business views | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/compositions/{composition_id}` | One business view | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/paths` | An entity's named paths | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/paths/{path_id}` | One named path, each step a relationship | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/construction` | A company's whole construction in one read (JSON, or markdown) | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/traces` | Every route from a change in one attribute to a company's accounts | `read` | yes | 200, 401, 403, 404, 422, 503 |

### Relationships

Relationships between attributes, and their evidence.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/relationships` | Relationships, filtered | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/relationships/{relationship_id}` | One relationship | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/relationships/{relationship_id}/evidence` | A relationship's evidence | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/evidence/{evidence_id}` | One evidence record | `read` | yes | 200, 401, 403, 404, 422, 503 |

### Taxonomy

Concepts and groups.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/concepts` | The taxonomy's concepts | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/concepts/{concept_id}` | One concept and its entities | `read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/groups` | Recurring configurations of entities | `read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/groups/{group_id}` | One group | `read` | yes | 200, 401, 403, 404, 422, 503 |

### Events

Market events and what they did.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/events` | Market events, by publication time | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/events/{event_id}` | One market event | `read` |  | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/events/{event_id}/impact-analysis` | What an event did: the attributes it moves, directly and one relationship on | `read` | yes | 200, 401, 403, 404, 422, 503 |

### Documents

Uploaded files and their passages.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/documents` | Stored documents | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/documents` | Upload files: store, parse, chunk, index, and read each into a bundle | `documents:write` |  | 202, 400, 401, 403, 404, 413, 415, 422, 503 |
| `GET {wm}/documents/{document_id}` | One document | `read` |  | 200, 401, 403, 404, 503 |
| `DELETE {wm}/documents/{document_id}` | Delete a document, its text, chunks, indexes and mentions; its bundles and changes stay as history | `admin` |  | 204, 401, 403, 404, 503 |
| `GET {wm}/documents/{document_id}/chunks` | A document's passages and the names in each | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/documents/{document_id}/chunks/{ordinal}` | One passage | `read` |  | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/documents/{document_id}/content` | The extracted text, or the file as uploaded | `read` |  | 200, 401, 403, 404, 409, 422, 503 |
| `POST {wm}/documents/{document_id}/bundles` | Read a stored document again, against the model as it is now | `documents:write` |  | 202, 401, 403, 404, 422, 503 |

### Bundles

Research read into dated items with signals.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/bundles` | Stored bundles, oldest first | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/bundles` | Store a bundle an agent wrote (axelrod.import/v1) | `documents:write` |  | 201, 400, 401, 403, 404, 415, 422, 503 |
| `GET {wm}/bundles/{bundle_id}` | One bundle | `read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/bundles/{bundle_id}/items` | A bundle's dated items and their signals | `read` |  | 200, 400, 401, 403, 404, 422, 503 |

### Search

Search over passages and names.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/search` | Search passages and the model's names | `read` |  | 200, 401, 403, 404, 422, 503 |

### Changes

Proposed changes and their review.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/changes` | Proposed changes, pending by default | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/changes` | Propose one change per bundle item, in event-time order | `changes:write` |  | 202, 401, 403, 404, 409, 422, 503 |
| `GET {wm}/changes/{change_id}` | One change; its ETag is the model's current version | `read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/changes/{change_id}/diff` | What approving the change would do | `read` |  | 200, 401, 403, 404, 503 |
| `POST {wm}/changes/{change_id}/approvals` | Approve a change: commits a version | `changes:review` |  | 201, 401, 403, 404, 409, 412, 422, 428, 503 |
| `POST {wm}/changes/{change_id}/rejections` | Reject a change, with a reason | `changes:review` |  | 201, 401, 403, 404, 409, 412, 422, 428, 503 |

### Theses

What-if questions.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/thesis-templates` | Ready theses the world model ships with | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/theses` | Theses posed so far | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/theses` | Pose a what-if: a question, or a ready thesis | `simulations:write` |  | 201, 401, 403, 404, 422, 503 |
| `GET {wm}/theses/{thesis_id}` | One thesis | `read` |  | 200, 401, 403, 404, 503 |
| `POST {wm}/theses/{thesis_id}/simulations` | Run a thesis on the latest version | `simulations:write` |  | 202, 401, 403, 404, 422, 503 |

### Simulations

Theses run on a version.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/simulations` | Simulations run so far, oldest first | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/simulations/{simulation_id}` | One simulation: targets with ranges, scenario table | `read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/simulations/{simulation_id}/transmission` | The shock's path, by order | `read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/simulations/{simulation_id}/coverage` | What the simulation's numbers are made of | `read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/simulations/{simulation_id}/brief` | A reader's summary of a simulation | `read` |  | 200, 401, 403, 404, 503 |

### Graph

Subgraphs for agents.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/graph` | A subgraph for an agent's context window | `read` | yes | 200, 401, 403, 404, 422, 503 |

### Exports

The model in clients' formats.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/exports/v4.1.4` | The world model in the client's v4.1.4 format | `read` |  | 200, 401, 403, 404, 422, 503 |

### Jobs

Asynchronous work.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/jobs/{job_id}` | One job | `read` |  | 200, 401, 403, 404, 503 |

### Errors

Every failure is `application/problem+json` (RFC 9457): `type` (`https://docs.axelrod.ai/problems/{code}`), `title`, `status`, `detail`, `instance`, `code`, `request_id`, and `errors` (each invalid field).

| Status | When |
|---|---|
| 400 | The request cannot be used (invalid_request, invalid_json, invalid_cursor) |
| 401 | No credential, or not a valid one (authentication_required, invalid_token) |
| 403 | The credential lacks the scope (insufficient_scope), or a decision came from a static key or an agent-driven token (human_approval_required) |
| 404 | The world model, version or resource does not exist (…_not_found) |
| 409 | The state forbids it now (update_in_progress, already_decided, not_parsed, conflict) |
| 412 | If-Match names a version the model has moved past (version_moved) |
| 413 | Too many files or too large a file (too_many_files, payload_too_large) |
| 415 | The body's media type is not accepted (unsupported_media_type) |
| 422 | The body or query failed validation (invalid_request, with errors), or cannot be acted on (note_required, question_not_understood, thesis_unbound, idempotency_key_reused) |
| 428 | A decision needs If-Match (precondition_required) |
| 503 | A token names a signing key and the issuer's JWKS cannot be reached (issuer_unavailable) |

Codes: `invalid_request`, `invalid_json`, `invalid_cursor`, `authentication_required`, `insufficient_scope`, `not_found`, `world_model_not_found`, `version_not_found`, `entity_not_found`, `attribute_not_found`, `relationship_not_found`, `evidence_not_found`, `composition_not_found`, `path_not_found`, `event_not_found`, `document_not_found`, `chunk_not_found`, `file_missing`, `bundle_not_found`, `change_not_found`, `thesis_not_found`, `simulation_not_found`, `concept_not_found`, `group_not_found`, `job_not_found`, `invalid_token`, `issuer_unavailable`, `human_approval_required`, `conflict`, `update_in_progress`, `already_decided`, `not_parsed`, `version_moved`, `payload_too_large`, `too_many_files`, `unsupported_media_type`, `idempotency_key_reused`, `note_required`, `question_not_understood`, `thesis_unbound`, `precondition_required`.

### Schemas

| Schema | What it is |
|---|---|
| `EntityType` | What an entity is. A security or a sector is modelled as a market or a group, not as its own type. |
| `RelationshipType` | causal: a mechanism with a size; learned_causal: promoted from co-movement; accounting: a part adds to its total (fixed weight); identity: a term of a product, ratio or difference (weight derived); stock_flow: a flow accumulating into a stock. |
| `Calibration` | uncalibrated: the mechanism and its sign are known, its size is not (effect is null, never 0). |
| `Sign` | The direction a rise in the source moves the target. |
| `Direction` | Whether the relationship also acts from target to source. |
| `RelationshipStatus` | Retired relationships stay as history (valid_to is set). |
| `Origin` | How the object entered the model. |
| `EpistemicType` | What kind of claim it is: a fact from a filing or data release (documented, observed), a report, a broker or company view, a model output, an assumption, or an inference by the model. Facts are kept apart from inferences. |
| `EvidenceType` | The kind of source an evidence record cites. |
| `CompositionRole` | driving: its parts' accounting relationships carry changes into the total; reconciling: observed and reconciled against the total, never propagating into it; non_additive: its parts overlap (a view that is not a sum). |
| `EventType` | The kind of market event. |
| `EventChannel` | How the event reached the model. |
| `SourceType` | Where a document comes from. |
| `DocumentStatus` | How far a document has been read. |
| `SearchMode` | keyword: BM25 over passages; prefix: names, then passages, by word prefix; semantic: embedding similarity; graph: the nodes named and their neighbours, then passages mentioning them; hybrid: reciprocal-rank fusion of keyword, semantic and graph. |
| `HitKind` | What a search hit is. |
| `ChangeKind` | What a change proposes. |
| `ChangeStatus` | pending: waits for a person; approved: committed a version; rejected: never applied; deferred: set aside to fold in later; auto_applied: applied under a review policy. |
| `JobType` | The work a job does. |
| `JobStatus` | Where a job is. |
| `ThesisMode` | How the thesis was posed. |
| `SimulationStatus` | A simulation is stored once it has run; it is immutable. |
| `ImpactDirection` | Which way the event moves the attribute. |
| `ImpactStatus` | completed: the event's changes were approved; pending_review: proposed, waiting for a person; not_imported: no change was proposed from it. The impacts are what the event's operations reach in either case. |
| `ExclusionReason` | Why a reached relationship carries no size in a simulation. |
| `InputStatus` | Where an input a transition needs stands. |
| `ContentFormat` | text: the extracted text as JSON; raw: the file as uploaded. |
| `Scope` | What a credential may do, in four tiers: read (read); propose (documents:write, changes:write, simulations:write); approve (changes:review: human only, never on a static key or an agent-driven token); admin (admin). |
| `ActorKind` | token: a core-minted service token (a person, maybe through an agent); key: a static scoped credential (a service, no person); session: a person signed in to this service; local: an open local run; system: the engine itself (a review policy, a day's close). |
| `ProblemCode` | A stable, machine-readable error code; `type` is https://docs.axelrod.ai/problems/{code}. |
| `FieldError` | One invalid field. |
| `Problem` | An RFC 9457 problem details object, served as application/problem+json. |
| `VersionRef` | The state an answer was read from. |
| `Meta` | About the answer: its request id, and the version it was read from (reads of the model). |
| `ListMeta` | About a page of a collection. |
| `AgentRef` | The agent host acting for the person (the token's act claim). |
| `Actor` | Who acted, as structured fields: never a header the service cannot check. |
| `Me` | The credential's identity. |
| `Counts` | How many of each object the world model holds now. |
| `WorldModel` | One causal world model. An organization may hold several. |
| `Version` | A committed, immutable version of the world model. |
| `Level` | An attribute's current distribution. q05 and q95 are null for a family without quantiles. |
| `Observation` | A dated observation of an attribute (bitemporal; append-only). |
| `AttributeState` | The model's state of an attribute at a time (a trajectory point). |
| `Attribute` | One of an entity's measured quantities. |
| `ConceptRef` | A concept of the taxonomy. |
| `Entity` | A company, agency, market or factor: a stable identity with its attributes nested. |
| `Kernel` | When the effect starts, peaks and fades; null when uncalibrated. |
| `Relationship` | A directed causal or accounting relation between two attributes. |
| `Evidence` | One record supporting (or contradicting) a relationship. Append-only. |
| `Composition` | One view of a business split into parts that add to a total. |
| `PathStep` | One step of a named path: a relationship. |
| `Path` | A named chain of relationships from a starting change to a company's financial endpoint. |
| `LinkCounts` | Counts of the relationships touching a company's attributes. |
| `Construction` | A company's business construction in one read (workflow read). |
| `TraceStep` | One step of a traced route. |
| `TraceRoute` | One route of a trace. |
| `Trace` | Every route from a change in one attribute to a company's accounts (workflow read). |
| `Concept` | A concept of the taxonomy. |
| `Group` | A recurring configuration of entities (a bound superentity pattern). |
| `Event` | A market event. Append-only. |
| `Impact` | One attribute an event moves. |
| `ImpactAnalysis` | What an event did: the attributes it moves directly and one relationship on (workflow read). |
| `Document` | A stored file. |
| `Mention` | A name recognized in a passage; attribute_id is null for the entity alone. |
| `Chunk` | A passage of a document. |
| `DocumentText` | A document's extracted text. |
| `BundleSummary` | Research read into dated items with signals (axelrod.import/v1). |
| `BundleItem` | One dated item of a bundle. |
| `ImportBundle` | An axelrod.import/v1 bundle, as an agent writes it. |
| `Hit` | A search hit. |
| `JobResult` | What a job produced. |
| `Job` | Asynchronous work: poll it until it succeeds or fails. |
| `ChangeCreate` | Propose one change per bundle item, in event-time order. Each waits for a person's review: nothing approves itself. |
| `Change` | One proposed change to the model: an uncommitted diff. |
| `Operation` | One operation of a change. |
| `ChangeDiff` | What approving a change would do. |
| `AuditEvent` | One write, as the audit log records it (append-only). |
| `Decision` | A person's decision on a change. |
| `ApprovalCreate` | An approval, with an optional note. |
| `RejectionCreate` | A rejection; the reason is required. |
| `ThesisCreate` | A what-if: a question, or a ready thesis of the world model (a template). |
| `Thesis` | A what-if question as hypothetical operations. Never a fact. |
| `ThesisTemplate` | A ready thesis the world model ships with. |
| `SimulationCreate` | Run a thesis; the horizon defaults to the thesis's. |
| `Effect` | An effect's 5/50/95% range, in sd. |
| `SimulationTarget` | A target attribute and its effect at the horizon. |
| `Simulation` | A thesis run on a version: a hypothetical change, never committed. Immutable. |
| `TransmissionStep` | One attribute the shock reaches, by order. |
| `Coverage` | What a simulation's numbers are made of: contributed and excluded relationships, blocking inputs, and per target the share of routes fully quantified. |
| `Brief` | A reader's summary of a simulation: bottom line, timing, exposures, indicators, evidence, and its coverage (workflow read). |
| `Export` | The world model in the client's v4.1.4 format (that schema's own field names). |
| `Graph` | A subgraph for an agent's context window: entities with the attributes reached, and the relationships between them (workflow read). |
<!-- reference:end -->
