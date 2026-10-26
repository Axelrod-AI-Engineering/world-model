# World model API

The world model as a service, v1: entities and their attributes, relationships and their evidence, read at a stated
version; documents read into proposed changes that a person reviews; theses run as simulations. The same service is
exposed twice: as REST under `/v1`, and as MCP (Model Context Protocol) tools at `/mcp`.

The contract is [openapi.yaml](openapi.yaml) (OpenAPI 3.1). The [Reference](#reference) and the
[terms table](#terms-and-acronyms) below are generated from it. [design/api.md](../design/api.md) explains why the API
looks the way it does, and [design/core-mcp-auth.md](../design/core-mcp-auth.md) explains how core authenticates.

<!-- toc -->
**Contents**

- [Terms and acronyms](#terms-and-acronyms)
- [Who it is for](#who-it-is-for)
- [Authentication and scopes](#authentication-and-scopes)
- [Conventions](#conventions)
- [Entities and attributes](#entities-and-attributes)
- [The unified world model: erid](#the-unified-world-model-erid)
- [A walk-through](#a-walk-through)
- [MCP](#mcp)
- [Mounting it from core](#mounting-it-from-core)
- [Configuration](#configuration)
- [Code and tests](#code-and-tests)
- [Reference](#reference)
  - [World models](#world-models)
  - [Unified world model](#unified-world-model)
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

## Terms and acronyms

<!-- terms:start -->
| Term | Full name | Meaning | Example |
|---|---|---|---|
| API | Application Programming Interface | The routes other programs call to use the world model. | `GET /v1/world-models` |
| v1 | version 1 of this API | The major version, in every path. Additive changes stay in v1; a breaking change is v2. | `/v1/…` |
| World model |  | One causal model: entities, their attributes, the relationships between attributes, its history and documents. An organization may own several. | `sally_demo` |
| erid | the unified world model (core's name for the world model state) | The whole graph, served beside the per-client world models. Its reads take a compartment; the whole graph is for internal staff. | `GET /v1/erid` |
| Compartment |  | A client's view of the unified world model: its companies, every player upstream of their values, and one link downstream (as a focused world is defined). | `sally_focus` |
| Organization (`org`) |  | Owns world models, documents and credentials: Axelrod or a client firm. It comes from the credential, never from the request. | `default`, `acme` |
| Internal staff |  | People and services of an internal organization (`WORLD_MODEL_INTERNAL_ORGS`). Only they read the whole unified world model. | Axelrod engineers |
| Person |  | A human, signed in to the web interface (a session) or named by a core-minted token without an agent. Only a person approves a change. | an analyst reviewing changes |
| Service |  | A program with a static key: the data-ingestion pipeline, a script. Never approves a change. | `ingest-pipeline` |
| Agent |  | An AI client acting for a person through MCP. Recorded in `act`; reads only. | Claude in core's MCP |
| Principal |  | The verified identity a request acts as: its kind, organization, subject, scopes and, for a token, `azp`, `act` and `jti`. | `{kind: token, org: acme, sub: org_user_9}` |
| `kind` | actor kind | How the principal was verified: `token` (core-minted), `key` (static), `session` (signed in here), `local` (an open local run), `system` (the engine itself). | `token` |
| Scope |  | A permission, named `resource:action` with three actions (read, create, approve), plus `admin`. | `changes:approve` |
| RBAC | Role-Based Access Control | Granting permissions by role. Here scopes are granted per credential; finer roles (approvers, admins) come later. |  |
| JWT | JSON Web Token (RFC 7519) | A signed set of claims. Core mints one per call as a service token. | `eyJhbGciOiJFUzI1NiIs…` |
| JSON | JavaScript Object Notation | The text format of every request and response body. | `{"data": …}` |
| JWKS | JSON Web Key Set (RFC 7517) | The issuer's public signing keys, by key id, at a URL this service fetches and caches. | `https://core…/.well-known/jwks.json` |
| ES256 | ECDSA using P-256 and SHA-256 (RFC 7518) | The only signature algorithm accepted on a service token. | header `alg: ES256` |
| ECDSA | Elliptic Curve Digital Signature Algorithm | The signature family ES256 belongs to. |  |
| `at+jwt` | OAuth 2.0 access token in JWT form (RFC 9068) | The `typ` header a service token must carry. | header `typ: at+jwt` |
| OAuth | Open Authorization (OAuth 2.0, RFC 6749) | The authorization framework whose access tokens a service token follows. |  |
| MCP | Model Context Protocol | The protocol AI clients use to call tools. Core runs an MCP server (its backend MCP); this service runs one at `/mcp`. | `world_model_get_entity` |
| `core-mcp`, `core-web` | core's channels | The part of core that asked, in a token's `azp`: its MCP server (reads only) or its web interface (a person). | `azp: core-web` |
| `iss` | issuer | Who minted the token; must be a trusted issuer. | `https://core.axelrod.ai` |
| `aud` | audience | Who the token is for: this service. | `https://world-model.axelrod.ai` |
| `sub` | subject | Who the token speaks for: the organization user (a person) or the key's caller. | `org_user_9` |
| `azp` | authorized party | The part of core that asked (OpenID Connect). | `core-mcp` |
| `act` | actor (RFC 8693) | The agent acting for the person, `{sub, name}`. A token with `act` reads only and never decides. | `{sub: mcp-client:claude}` |
| `jti` | JWT ID | A token's unique id: the join key between core's log and this audit log. | `5f1c…` |
| `exp`, `iat`, `nbf` | expiration time, issued at, not before | A token's validity window, checked with 60 seconds of leeway. | `exp` = issue + 5 minutes |
| `kid` | key ID | Which key of the JWKS signed the token. | `core-2026-10` |
| TTL | time to live | How long something is kept before it expires. Idempotency keys and the audit log have none: they are kept forever. | the JWKS cache: 10 minutes |
| RFC | Request for Comments | An Internet standard published by the IETF (Internet Engineering Task Force). | RFC 9457 |
| RFC 9457 | Problem Details for HTTP APIs | The error format: `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, and our `code`. | `404 entity_not_found` |
| HTTP | Hypertext Transfer Protocol | The protocol of every call. Status codes used: 200 OK, 201 Created, 202 Accepted, 204 No Content, 304 Not Modified, 4xx client errors, 5xx server errors. | `202 Accepted` |
| ETag | entity tag (RFC 9110) | An opaque version identifier of a response; here the model's state hash. Under review (Manav). | `"9c1f…"` |
| If-Match, If-None-Match | conditional request headers (RFC 9110) | If-Match: act only if the model is still at this ETag (412 if it moved; 428 without it). If-None-Match: 304 if unchanged. Under review (Manav). | `If-Match: "9c1f…"` |
| Idempotency-Key |  | A client's key that makes a create safe to retry: the same key and request return the first answer. Kept forever. | `Idempotency-Key: upload-42` |
| Cursor |  | An opaque position in a list, returned as `meta.next_cursor`; it keeps the version it started on. | `eyJvIjo1MCwidiI6M30` |
| Job |  | Long work answered `202 Accepted` with a job to poll. | `job_8f2a…` |
| `traceparent` | W3C Trace Context header | Distributed-tracing context, accepted and echoed. W3C is the World Wide Web Consortium. | `00-4bf9…-00f0…-01` |
| OpenAPI | the OpenAPI Specification 3.1 | The machine-readable contract of this API, world_model/docs/api/openapi.yaml. |  |
| CRUD | create, read, update, delete | The plain operations; actions that are not CRUD create a resource instead. | `POST …/approvals` |
| Lakehouse catalog |  | The service's store of documents, chunks, bundles, the registry, the audit log, idempotency keys and jobs (SQLite). |  |
| Bitemporal |  | Two times on every fact: when it applies (`valid_at`) and when the model learned it (`observed_at`). |  |
| sd | standard deviation | The unit of an effect size: a move in the target, in its standard deviations, per standard deviation of the source. | `effect: 0.4` |
| LLM | large language model | An optional extraction step in ingestion. |  |
<!-- terms:end -->

## Who it is for

Direct access is for **internal staff and backend services only**; clients use the products built on the world model
(the API review, Oct 19).

- **A person in the web interface** reads, writes, and approves or rejects each proposed change. This takes a session
  or a core-web token.
- **The data-ingestion pipeline** uploads documents and proposes changes with a static key that holds
  `documents:create` and `changes:create`. It never approves.
- **Core's backend MCP server** reads, with core-minted service tokens. It does not write, to start.
- **Internal staff and scripts** read with static keys (a key with no scopes listed reads only), and read the unified
  world model, `/v1/erid`.

The service owns the world model. It does not own the agents that use it.

## Authentication and scopes

The organization and the person always come from a credential the service can verify. A header or a path never
supplies them. There are three kinds of credential, plus an open local mode:

| Credential | Who it names | How |
|---|---|---|
| **Service token** (`serviceToken`) | a person in an organization, and the agent host when one drives the call | a short-lived JWT (JSON Web Token) signed ES256, which core mints per call, verified against a trusted issuer's JWKS (JSON Web Key Set). Claims are `iss` (issuer), `aud` (audience), `exp` (expiry, 5 min), `iat` (issued at), `jti` (token id), `sub` (the organization user), `org`, `scope`, `azp` (authorized party: `core-mcp` or `core-web`), `name`, and `act` (the agent acting) |
| **Static key** (`apiKey`) | a backend service of an organization (no person) | `Authorization: Bearer <key>`, from `WORLD_MODEL_API_KEYS` entries `caller:key:org[:scope+scope…]`; with no scopes listed, `world_model:read` only |
| **Session** (`session`) | a person signed in to this service | the sign-in cookie (the review UI, `/docs`) |
| *Local* | `local` | with no keys, logins or issuers configured, `/v1` is open with every scope except `changes:approve` |

**Scopes** are `resource:action`, with one verb per action used the same way on every resource: read, create,
approve, plus `admin`. Each operation in the reference names the scope it needs (`x-required-scope`). A credential
without it gets `403 insufficient_scope`.

| Scope | Allows | Routes |
|---|---|---|
| `world_model:read` | reading a world model and everything in it | every `GET` |
| `documents:create` | adding documents and bundles | `POST` documents, bundles, re-extraction |
| `changes:create` | proposing changes | `POST /changes` |
| `simulations:create` | posing theses and running simulations | `POST` theses and simulations |
| `changes:approve` | approving or rejecting a change (a person only) | `POST /changes/{id}/approvals` and `/rejections` |
| `admin` | administration | `DELETE /documents/{id}`, the audit log |

What each channel can do:

| Channel | Scopes | Can |
|---|---|---|
| Core's backend MCP (`azp: core-mcp`), or any token with `act` | `world_model:read`, capped by the service whatever the token asks | read |
| A person: the web interface (`azp: core-web`, no `act`) or a session | as granted, up to every scope | read, write, approve |
| The data-ingestion pipeline (static key) | `world_model:read documents:create changes:create` | read, upload, propose |
| Another backend service (static key, no scopes listed) | `world_model:read` | read |

- **Approval is human-only.** A decision from a static key, or from a token that carries `act` or `azp: core-mcp`, is
  `403 human_approval_required`, before any scope check. A static key never carries `changes:approve`: the service
  refuses to start with such an entry.
- **Tenancy.** Each world model belongs to one organization (the `world_models` registry). A world model of another
  organization answers `404 world_model_not_found`, the same as one that does not exist.
- **Audit.** Every write records its actor (`kind`, `org`, `sub`, `name`, `azp`, `act`, `jti`) in the world model's
  audit log (`GET …/audit-events`, `admin`). Changes carry it as `proposed_by` and `decided_by`. **The audit log is
  kept forever**: there is no route that deletes it and no expiry.
- **Failures.** A missing or invalid credential is `401` (`authentication_required`, `invalid_token`) with
  `WWW-Authenticate: Bearer`. A token that names an unknown signing key, when the issuer's JWKS cannot be reached, is
  `503 issuer_unavailable`.

## Conventions

- **Envelope.** A resource answers `{"data": {…}, "meta": {"request_id", "version"}}`. A collection answers
  `{"data": […], "meta": {"request_id", "version", "limit", "next_cursor"}}`.
- **Errors** are RFC 9457 problem details ("Problem Details for HTTP APIs"), `application/problem+json`, with a stable
  `code`. See [Errors](#errors).
- **Pinning.** Reads of the model take `version=N` or `as_of=<date-time>`, and `meta.version` names what was served:
  `number`, `state_hash`, `committed_at`, `latest`, `clock`. A version outside the model, or a date before it begins,
  is `404 version_not_found`.
- **Pagination** is by cursor: `limit` (1–200, default 50), then the previous page's `meta.next_cursor`. A cursor
  keeps the version it started on. A cursor the service did not issue is `400 invalid_cursor`.
- **Idempotency.** A `POST` that creates takes `Idempotency-Key`. The same key with the same request returns the first
  answer; the same key with another request is `422 idempotency_key_reused`. **Keys are permanent**: kept in the
  lakehouse catalog per organization, world model and operation, with no TTL (time to live), so they survive a
  restart. Document uploads and bundles are also keyed on their **content**, with or without the header: the same
  files (names and bytes), or the same bundle, get the same answer whoever sends them and whenever. A request that
  fails is not kept, so its retry runs again. Deleting a document forgets the answers that named it.
- **Async work** (uploads, re-extraction, proposing changes, simulations) answers `202 Accepted` with a job and
  `Location: …/jobs/{id}`. Poll the job until it succeeds or fails. Jobs are kept in the lakehouse catalog too. The work runs before the answer
  unless you send **`Prefer: respond-async`** (RFC 7240): then the `202` comes at once with the job `running` and
  `Preference-Applied: respond-async`, and the job at `Location` ends `succeeded` (with `result`) or `failed` (with an
  RFC 9457 problem in `error`). Use it for reading a large document again, which can outlast a proxy's request limit
  (Railway's is 300 s). A job running when the service restarts is lost; send the request again. A replay with the same
  `Idempotency-Key` returns the same job.
- **Concurrency.** Reads of the model carry `ETag: "<state_hash>"` (an entity tag), and `If-None-Match` gives `304`.
  A decision on a change needs `If-Match` with the ETag of the version it was reviewed against. Without one it is
  `428 precondition_required`; if the model has moved, it is `412 version_moved`. **Under review (Manav):** ETag and
  If-Match stay as built until his review.
- **Facts and inferences.** Every claim carries an `epistemic_type` (documented, observed, reported, broker,
  guidance, model, assumption, expert_judgment, inferred). Theses and simulations never write facts. A change becomes
  fact only when a person approves it.
- **Time.** Observations are bitemporal (`valid_at`, `observed_at`, and `occurred_at` for when a reported fact
  happened). Documents have `published_at` and `ingested_at`. Relationships have `valid_from` and `valid_to`.
- **Headers.** Every response carries `X-Request-Id` (yours, if you sent one) and `X-Axelrod-API-Version: 1`. A W3C
  `traceparent` (Trace Context) is echoed.
- **Determinism.** The same file (name and bytes), read against the same model, gives the same document, chunks,
  signals, and bundle ids, and the same answer to its upload. The same bundle proposed and approved on the same
  version gives the same `state_hash`.
- **Restarts.** The lakehouse (documents, bundles, audit, idempotency keys, jobs) survives a restart. The model reloads
  from its initial snapshot, so replay its approved changes to rebuild later versions.

## Entities and attributes

An **entity** is a company, an agency, a market, or a factor, with a stable internal id (`toyota`) that is never a
ticker. Tickers live in `identifiers`. Its **attributes** are its measured quantities. An attribute's id is
`<entity id>.<key>`: `toyota.operating_profit` is the attribute `operating_profit` of `toyota`. Attributes are nested
in their entity. `/entities/{entity_id}/attributes/{attribute_key}` takes the key or the full id.

A **relationship** runs between two attributes: `source_attribute_id` → `target_attribute_id`, with its `type`
(causal, accounting, identity, stock_flow), `confidence` (0–1), `effect` (target sd per source sd; sd is a standard
deviation), and its retrieval `profile` (exposure, unit, date, hedge, pass-through, endpoint, calculation, source). An
uncalibrated relationship has a sign but no size, so its `effect` is `null`, never 0. Its `evidence` records cite
their sources.

In the code, an attribute is a *subentity* and a relationship is an *interaction*. A simulation is the engine's
*forecast*, and a change is its *proposal* (see [vocab.md](../vocab.md)).

## The unified world model: erid

`/v1/erid` is the unified world model: the whole graph, beside the per-client `/v1/world-models/{id}`, which stays.
It is the main engine's world model (a deployment runs its fullest scenario there, `sally_demo` today), named in
`GET /v1/erid` as `world_model_id`.

- **The whole graph** is for internal staff only: an organization in `WORLD_MODEL_INTERNAL_ORGS` (default: the one
  that owns the backing world model). Anyone else gets `403 internal_only`.
- **Compartments.** A client's view is a compartment, defined as a focused world is (`engine/focus.py`): its
  companies, every player upstream of their values, and one link downstream. Each scenario focused on the unified one
  is a compartment (`sally_focus`). Pass `compartment=<id>` to any graph read under `/v1/erid` (entities and their
  attributes, observations, states, compositions, paths, construction, traces; relationships and evidence; the graph;
  versions). A compartment is read by internal staff or by the organization it is assigned to
  (`WORLD_MODEL_COMPARTMENTS`); to anyone else it is `404 compartment_not_found`.
- **Writes** go through the backing world model (`/v1/world-models/{world_model_id}/…`), with its review and audit,
  and land in the unified graph, so every compartment sees them.

```bash
curl -s -H "$AUTH" $API/erid | jq '.data | {scenario, compartment_ids}'
curl -s -H "$AUTH" "$API/erid/entities?compartment=sally_focus&limit=200" | jq '[.data[].id]'
```

## A walk-through

```bash
API=https://world-model-dev.up.railway.app/v1
AUTH="Authorization: Bearer $WORLD_MODEL_KEY"          # the ingestion pipeline's key: read, documents, changes
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

# a what-if, run as a simulation (simulations:create)
curl -s -H "$REVIEWER" -H 'Content-Type: application/json' \
     -d '{"question": "What if the BoJ hiked by 25bp next quarter?"}' $WM/theses
curl -s -H "$REVIEWER" -X POST $WM/theses/<thesis-id>/simulations
curl -s -H "$AUTH" $WM/simulations/<simulation-id>/coverage
```

`$REVIEWER` is a person's credential: a session or a core-web token. A key cannot approve.

Under the default `standards` review policy a proposal never blocks the next one: items that meet the standards apply
(their changes read `auto_applied`), items that do not stay `pending`, and each carries `review_reasons`, the checks it
failed, one string each (for example `third-party material without its publisher (R21)`). A pending change is decided
at any later time, against the model as it is then: approving it commits a new version, and answers `409 conflict`
(nothing changes, the change stays pending) when a value, link or entity it names has since been retired; rejecting
closes it. Only under `review_all` does an unreviewed change hold the next proposal (`409 update_in_progress`).

## MCP

`/mcp` is an MCP (Model Context Protocol) server (`axelrod-world-model`) over stateless Streamable HTTP, built on the
official `mcp` 2.x SDK. It takes the same credentials, and the same scopes and access boundary apply. Each tool calls
the REST route in process, so answers, auth, and errors are identical. A REST error comes back as a tool error,
`"<code>: <detail>"`. Every tool takes `world_model_id`, which defaults to the organization's only world model;
`world_model_id="erid"` reads the unified world model, and the graph reads take `compartment`. No tool decides a
change: approval is a person's step in a review UI.

| Tool | Route | Annotation |
|---|---|---|
| `world_model_list_world_models` | `GET /world-models` | read-only |
| `world_model_get_world_model` | `GET {wm}` | read-only |
| `world_model_get_unified` | `GET /erid` | read-only |
| `world_model_list_compartments` | `GET /erid/compartments` | read-only |
| `world_model_list_versions` | `GET {wm}/versions` | read-only |
| `world_model_graph` | `GET {wm}/graph` | read-only |
| `world_model_list_entities` | `GET {wm}/entities` | read-only |
| `world_model_get_entity` | `GET {wm}/entities/{entity_id}` | read-only |
| `world_model_get_attribute` | `GET {wm}/entities/{entity_id}/attributes/{attribute_key}` | read-only |
| `world_model_list_observations` | `GET …/attributes/{attribute_key}/observations` | read-only |
| `world_model_list_states` | `GET …/attributes/{attribute_key}/states` | read-only |
| `world_model_list_relationships` | `GET {wm}/relationships` (with each retrieval profile) | read-only |
| `world_model_get_relationship` | `GET {wm}/relationships/{id}` and its evidence | read-only |
| `world_model_list_concepts` | `GET {wm}/concepts` | read-only |
| `world_model_construction` | `GET {wm}/entities/{entity_id}/construction` (json or markdown) | read-only |
| `world_model_list_compositions` | `GET {wm}/entities/{entity_id}/compositions` | read-only |
| `world_model_list_paths` | `GET {wm}/entities/{entity_id}/paths` | read-only |
| `world_model_trace` | `GET {wm}/entities/{entity_id}/traces` (`through_totals`, `max_depth`) | read-only |
| `world_model_list_events` | `GET {wm}/events` | read-only |
| `world_model_impact_analysis` | `GET {wm}/events/{event_id}/impact-analysis` | read-only |
| `world_model_search` | `GET {wm}/search` | read-only |
| `world_model_ingest_document` | `POST {wm}/documents` (`content_base64` or `text`; `documents:create`) | write, idempotent |
| `world_model_list_documents` | `GET {wm}/documents` | read-only |
| `world_model_get_bundle` | `GET {wm}/bundles/{id}` and its items | read-only |
| `world_model_propose_changes` | `POST {wm}/changes` (`changes:create`) | write |
| `world_model_list_changes` | `GET {wm}/changes` | read-only |
| `world_model_get_change` | `GET {wm}/changes/{id}` and its diff | read-only |
| `world_model_simulate` | `POST {wm}/theses`, then `POST {wm}/theses/{id}/simulations` (`simulations:create`) | write |
| `world_model_get_simulation` | `GET {wm}/simulations/{id}`, with its coverage | read-only |
| `world_model_simulation_brief` | `GET {wm}/simulations/{id}/brief` | read-only |
| `world_model_export_v4` | `GET {wm}/exports/v4.1.4` | read-only |
| `world_model_get_job` | `GET {wm}/jobs/{id}` | read-only |

The read tools take `version` and `as_of` where their routes do. To use it from Claude Code:

```bash
claude mcp add --transport http world-model https://world-model-dev.up.railway.app/mcp --header "Authorization: Bearer $WORLD_MODEL_KEY"
```

## Mounting it from core

Core re-publishes the **read** tools in its own MCP catalog, under its own sign-in. The proposal is
[world_model/integrations/core](../../integrations/core/README.md): 17 read tools and no write tool, since core's backend MCP reads
only, to start. For each call, core mints a service token for the signed-in org user (`azp: core-mcp`, `act` naming
the MCP host) and calls `/v1/world-models/{id}/…`; the service caps such a token at `world_model:read`.

## Configuration

Settings live in two places, following core's convention (`world_model/src/axelrod_wm/settings.py`):

- **Non-secret settings are checked in:** `configs/world_model.toml`, overlaid by `configs/world_model.<stage>.toml`
  (`[auth]`: `trusted_issuers`, `internal_orgs`, `main_login_org`, `deny`, `owners`; `[compartments]`). The loader
  turns them into the variables below.
- **Secrets are in one gitignored file per stage**, `.creds.<stage>` (dotenv): the logins, the session secret, static
  API keys and model-provider keys. Locally the service reads it at start; for Railway,
  `.railway/railway-sync-creds.sh <stage>` pushes it to the service's variables without printing a value or deploying.
  A creds file holding a non-secret name, or a profile holding a secret, stops the server.
- The stage is `WORLD_MODEL_PROFILE`, else Railway's environment name, else `local`. A process variable always wins,
  then the creds file, then the profile.

Core needs no secret here: its tokens are verified against each core stage's public JWKS. Its one secret, the
signing key, lives in core's own `.creds.<stage>`.

| Variable | Default | What it sets |
|---|---|---|
| `WORLD_MODEL_API_KEYS` | none | static keys, `caller:key:org[:scope+scope…]`. With no scopes listed, a key reads only (`world_model:read`). `changes:approve` is refused. Each caller may hold two keys, so keys can rotate by overlap |
| `WORLD_MODEL_TRUSTED_ISSUERS` | none | `issuer;jwks_url;audience` entries, comma-separated, one per core stage. JWT verification is off unless this is set |
| `WORLD_MODEL_DENY` | none | `kid:…`, `org:…` or `sub:…` entries, refused at once |
| `WORLD_MODEL_INTERNAL_ORGS` | the main world model's organization | organizations whose principals read the whole unified world model (`/v1/erid`) |
| `WORLD_MODEL_COMPARTMENTS` | none | `compartment=org` entries: the organization each compartment of the unified world model is assigned to |
| `WORLD_MODEL_LAKE_DIR` | `var/lake` | the lakehouse: the SQLite catalog (documents, bundles, the world model registry, the audit log, idempotency keys, jobs) and raw files per organization |
| `WORLD_MODEL_EMBEDDER` | `auto` | `fastembed` (IBM granite-embedding-small), `hashing` (exact; used in tests), or `auto` |
| `WORLD_MODEL_EMBED_CACHE` | fastembed's default | where the embedding model is cached |
| `WORLD_MODEL_LLM_PROVIDER` | off | `anthropic` or `openai` for the optional extraction step (LLM: large language model) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `WORLD_MODEL_LLM_MODEL` | none | the provider's key and model |

The organization of a login is its username. The main login's organization is `WORLD_MODEL_BASIC_AUTH_USERNAME`, or
`default` with no logins; `main_login_org` in the profile maps it without naming the login. Secrets are never in the
repository.

## Code and tests

| Part | Code | Tests |
|---|---|---|
| The contract | `world_model/docs/api/openapi.yaml` | `world_model/tests/service/test_openapi_contract.py` (lint, route parity, response schemas, this reference and the terms) |
| REST routes | `world_model/src/axelrod_wm/api/v1/` (API models in `schemas.py`, projections from the domain in `project.py`) | `world_model/tests/service/` |
| The unified world model | `world_model/src/axelrod_wm/api/v1/routes_erid.py`, `compartments.py` | `world_model/tests/service/test_v1_erid.py` |
| Credentials, tokens, scopes | `world_model/src/axelrod_wm/api/keys.py`, `api/tokens.py`, `api/auth.py` | `world_model/tests/service/test_keys.py`, `test_tokens.py`, `test_v1_auth.py` |
| MCP server | `world_model/src/axelrod_wm/api/mcp.py` | `world_model/tests/service/test_mcp.py` |
| End-to-end flows | the service, MCP, lakehouse, engine and snapshots together | `world_model/tests/integration/service/` |

[world_model/tests/README.md](../../tests/README.md) lists every suite.

## Reference

<!-- reference:start -->
All 84 operations, from the contract ([openapi.yaml](openapi.yaml)). Paths are under `/v1`; `{wm}` is `/world-models/{world_model_id}`.

### World models

The organization's world models and the credential's identity.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET /me` | Who the credential is: organization, caller, scopes, world models | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET /world-models` | The organization's world models | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}` | One world model: its latest version, clock and counts | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/audit-events` | The world model's audit log, newest first | `admin` |  | 200, 400, 401, 403, 404, 422, 503 |

### Unified world model

erid: the unified world model, the whole graph, beside the per-client world models. Its reads take an optional `compartment` (a client's view, defined as a focused world is). The whole graph is for internal staff only; a compartment is read by internal staff or the organization it is assigned to.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET /erid` | The unified world model: the whole graph (internal staff) | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/compartments` | The compartments of the unified model the credential may read | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/compartments/{compartment_id}` | One compartment: its companies and size | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/versions` | Committed versions, newest first (the unified model, or a compartment) | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/versions/{version_ref}` | One committed version (`latest` for the newest) (the unified model, or a compartment) | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities` | Entities, filtered by type, concept, group or name (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}` | One entity, with its attributes (and relationships) (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/attributes` | An entity's attributes (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/attributes/{attribute_key}` | One attribute: level, spread, unit, view, basis, and its latest observation (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/attributes/{attribute_key}/observations` | An attribute's dated observations (valid_at, observed_at) (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/attributes/{attribute_key}/states` | The model's state of an attribute over time, oldest first (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/compositions` | An entity's business views (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/compositions/{composition_id}` | One business view (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/paths` | An entity's named paths (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/paths/{path_id}` | One named path, each step a relationship (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/construction` | A company's whole construction in one read (JSON, or markdown) (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/entities/{entity_id}/traces` | Every route from a change in one attribute to a company's accounts (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/relationships` | Relationships, filtered (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/relationships/{relationship_id}` | One relationship (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/relationships/{relationship_id}/evidence` | A relationship's evidence (the unified model, or a compartment) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET /erid/evidence/{evidence_id}` | One evidence record (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET /erid/graph` | A subgraph for an agent's context window (the unified model, or a compartment) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Versions

Committed, immutable versions.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/versions` | Committed versions, newest first | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/versions/{version_ref}` | One committed version (`latest` for the newest) | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |

### Entities

Entities, their attributes, observations and states.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/entities` | Entities, filtered by type, concept, group or name | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}` | One entity, with its attributes (and relationships) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes` | An entity's attributes | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}` | One attribute: level, spread, unit, view, basis, and its latest observation | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}/observations` | An attribute's dated observations (valid_at, observed_at) | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/attributes/{attribute_key}/states` | The model's state of an attribute over time, oldest first | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |

### Construction

How a company is built: compositions, paths, the whole construction, traces.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/entities/{entity_id}/compositions` | An entity's business views | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/compositions/{composition_id}` | One business view | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/paths` | An entity's named paths | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/paths/{path_id}` | One named path, each step a relationship | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/construction` | A company's whole construction in one read (JSON, or markdown) | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/entities/{entity_id}/traces` | Every route from a change in one attribute to a company's accounts | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Relationships

Relationships between attributes, and their evidence.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/relationships` | Relationships, filtered | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/relationships/{relationship_id}` | One relationship | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/relationships/{relationship_id}/evidence` | A relationship's evidence | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/evidence/{evidence_id}` | One evidence record | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Taxonomy

Concepts and groups.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/concepts` | The taxonomy's concepts | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/concepts/{concept_id}` | One concept and its entities | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/groups` | Recurring configurations of entities | `world_model:read` | yes | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/groups/{group_id}` | One group | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Events

Market events and what they did.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/events` | Market events, by publication time | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/events/{event_id}` | One market event | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/events/{event_id}/impact-analysis` | What an event did: the attributes it moves, directly and one relationship on | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Documents

Uploaded files and their passages.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/documents` | Stored documents | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/documents` | Upload files: store, parse, chunk, index, and read each into a bundle | `documents:create` |  | 202, 400, 401, 403, 404, 413, 415, 422, 503 |
| `GET {wm}/documents/{document_id}` | One document | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `DELETE {wm}/documents/{document_id}` | Delete a document, its text, chunks, indexes and mentions; its bundles and changes stay as history | `admin` |  | 204, 401, 403, 404, 503 |
| `GET {wm}/documents/{document_id}/chunks` | A document's passages and the names in each | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/documents/{document_id}/chunks/{ordinal}` | One passage | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |
| `GET {wm}/documents/{document_id}/content` | The extracted text, or the file as uploaded | `world_model:read` |  | 200, 401, 403, 404, 409, 422, 503 |
| `POST {wm}/documents/{document_id}/bundles` | Read a stored document again, against the model as it is now | `documents:create` |  | 202, 401, 403, 404, 422, 503 |
| `GET {wm}/sync` | What the lake sync has done for this model | `world_model:read` |  | 200, 401, 403, 404, 503 |

### Bundles

Research read into dated items with signals.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/bundles` | Stored bundles, oldest first | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/bundles` | Store a bundle an agent wrote (axelrod.import/v1) | `documents:create` |  | 201, 400, 401, 403, 404, 415, 422, 503 |
| `GET {wm}/bundles/{bundle_id}` | One bundle | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/bundles/{bundle_id}/items` | A bundle's dated items and their signals | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |

### Search

Search over passages and names.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/search` | Search passages and the model's names | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |

### Changes

Proposed changes and their review.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/changes` | Proposed changes, pending by default | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/changes` | Propose one change per bundle item, in event-time order | `changes:create` |  | 202, 401, 403, 404, 409, 422, 503 |
| `GET {wm}/changes/{change_id}` | One change; its ETag is the model's current version | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/changes/{change_id}/diff` | What approving the change would do | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `POST {wm}/changes/{change_id}/approvals` | Approve a change: commits a version | `changes:approve` |  | 201, 401, 403, 404, 409, 412, 422, 428, 503 |
| `POST {wm}/changes/{change_id}/rejections` | Reject a change, with a reason | `changes:approve` |  | 201, 401, 403, 404, 409, 412, 422, 428, 503 |

### Theses

What-if questions.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/thesis-templates` | Ready theses the world model ships with | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/theses` | Theses posed so far | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `POST {wm}/theses` | Pose a what-if: a question, or a ready thesis | `simulations:create` |  | 201, 401, 403, 404, 422, 503 |
| `GET {wm}/theses/{thesis_id}` | One thesis | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `POST {wm}/theses/{thesis_id}/simulations` | Run a thesis on the latest version | `simulations:create` |  | 202, 401, 403, 404, 422, 503 |

### Simulations

Theses run on a version.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/simulations` | Simulations run so far, oldest first | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/simulations/{simulation_id}` | One simulation: targets with ranges, scenario table | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/simulations/{simulation_id}/transmission` | The shock's path, by order | `world_model:read` |  | 200, 400, 401, 403, 404, 422, 503 |
| `GET {wm}/simulations/{simulation_id}/coverage` | What the simulation's numbers are made of | `world_model:read` |  | 200, 401, 403, 404, 503 |
| `GET {wm}/simulations/{simulation_id}/brief` | A reader's summary of a simulation | `world_model:read` |  | 200, 401, 403, 404, 503 |

### Graph

Subgraphs for agents.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/graph` | A subgraph for an agent's context window | `world_model:read` | yes | 200, 401, 403, 404, 422, 503 |

### Exports

The model in clients' formats.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/exports/v4.1.4` | The world model in the client's v4.1.4 format | `world_model:read` |  | 200, 401, 403, 404, 422, 503 |

### Jobs

Asynchronous work.

| Route | What it does | Scope | Pinned | Answers |
|---|---|---|---|---|
| `GET {wm}/jobs/{job_id}` | One job | `world_model:read` |  | 200, 401, 403, 404, 503 |

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

Codes: `invalid_request`, `invalid_json`, `invalid_cursor`, `authentication_required`, `insufficient_scope`, `not_found`, `world_model_not_found`, `version_not_found`, `entity_not_found`, `attribute_not_found`, `relationship_not_found`, `evidence_not_found`, `composition_not_found`, `path_not_found`, `event_not_found`, `document_not_found`, `chunk_not_found`, `file_missing`, `bundle_not_found`, `change_not_found`, `thesis_not_found`, `simulation_not_found`, `concept_not_found`, `group_not_found`, `job_not_found`, `invalid_token`, `issuer_unavailable`, `internal_error`, `human_approval_required`, `conflict`, `update_in_progress`, `already_decided`, `not_parsed`, `version_moved`, `payload_too_large`, `too_many_files`, `unsupported_media_type`, `idempotency_key_reused`, `note_required`, `question_not_understood`, `thesis_unbound`, `precondition_required`, `internal_only`, `compartment_not_found`.

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
| `Scope` | What a credential may do, named `resource:action` with three actions (read, create, approve) and `admin`. world_model:read reads a world model and everything in it; documents:create uploads documents and creates bundles; changes:create proposes changes; simulations:create poses theses and runs simulations; changes:approve approves or rejects a change (a person only: never a static key or an agent-driven token); admin deletes documents and reads the audit log. |
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
| `LinkCounts` | Counts of the relationships touching a company's attributes. Sized and uncalibrated causal links are the estimated part; fixed links (accounting, identity, stock-flow) carry derived weights and are counted by type. |
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
| `LakeSync` | What the lake sync has done for the model's organization: documents added to the lake are read against the model and imported by themselves. seen, skipped, waiting, and pending are as of the last tick; read and imported count since the process started. |
| `CompartmentCounts` | How many of each object it holds now. |
| `Compartment` | A client's view of the unified world model: its companies, every player upstream of their values, and one link downstream (as engine/focus.py defines a focused world). |
| `UnifiedWorldModel` | erid: the unified world model, the whole graph. |
<!-- reference:end -->
