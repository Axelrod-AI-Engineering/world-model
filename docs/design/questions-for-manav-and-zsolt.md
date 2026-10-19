# Questions for Manav and Zsolt

What we need from each of you before the world model's API v1 and core's MCP integration go further. It is one page;
each question links to the section that explains it.

<!-- toc -->
**Contents**

- [What to read](#what-to-read)
- [Settled in the API review (Oct 18)](#settled-in-the-api-review-oct-18)
- [For Manav: the API and the data model](#for-manav-the-api-and-the-data-model)
- [For Zsolt: authentication and core's MCP](#for-zsolt-authentication-and-cores-mcp)
- [For both](#for-both)
<!-- /toc -->

## What to read

| Document | What it is | Who |
|---|---|---|
| [api.md](api.md) | The API design: the three models, the domain model, conventions, routes, the old-to-new map, and the decisions | Manav |
| [../api/openapi.yaml](../api/openapi.yaml) | The contract: 61 operations, 148 schemas, 41 problem codes, and the scope each operation requires | Manav |
| [core-mcp-auth.md](core-mcp-auth.md) | How core's MCP authenticates to the world model, and the changes core would need (§6) | Zsolt, Manav |

The API follows Manav's *Data Model and API Design Best Practices*. The decisions taken on Oct 18 are in
[api.md §9](api.md#9-decisions).

## Settled in the API review (Oct 18)

The plan that follows from the review is in [architecture-plan.md](architecture-plan.md).

- **Audit:** kept forever (D-22). Who may read it is still open.
- **Access:** only internal staff and backend services reach the world model. Core's backend MCP reads only, to
  start. Writes come from the web interface and the ingestion pipeline (D-21).
- **Scopes:** one verb per action, used the same way on every resource. The rename is in progress.
- **Idempotency:** keys are permanent and keyed on content too (D-23). This answers the first deferred item below.
- **ETag and If-Match:** kept as built. Manav is reviewing them.
- **One world model or several:** a structured analysis is in
  [architecture-plan.md §4](architecture-plan.md#4-one-world-model-or-several), to decide together.
- **Unified endpoint:** a separate top-level resource, name to be confirmed. It is designed as a proposal in
  [api.md §4](api.md#4-resources-and-routes).

## For Manav: the API and the data model

1. **Organization, world model and actor.** Should `organization`, `world_model` and the structured actor (`org`,
   `sub`, `azp`, `act`, `jti`) be first-class records in the canonical data model, or stay API metadata?
   ([core-mcp-auth.md §9](core-mcp-auth.md#9-open-questions)) *Deferred until every term is defined: see the terms
   table in [api.md](api.md).*
2. **Scopes.** *Settled and built (Oct 19):* kept granular, named `resource:action` with one verb per action:
   `world_model:read`; `documents:create`, `changes:create`, `simulations:create`; `changes:approve`; and `admin`
   ([api.md §3](api.md#3-api-conventions)).
3. **Shared models.** Should a shared base world model (Axelrod's) be readable across organizations? That needs a
   grants table rather than one owning organization per model.
4. **Audit.** Who may read the audit log? *How long it is kept is settled: forever.*
5. **Nouns.** The API uses entity, attribute, relationship, evidence, event, thesis, simulation and change; the code
   keeps its own nouns behind the three-model separation. Do the API nouns match the canonical model you want?
   ([api.md §7](api.md#7-terms-grounded))
6. **Deferred items.** Is it acceptable for v1 to ship without the following? ([api.md §9](api.md#9-decisions))
   - ~~durable idempotency~~ *settled: permanent keys, being built;*
   - jobs that outlive the request (a job finishes before its `202` returns, and clients already poll);
   - `POST /v1/world-models` and credential routes.

## For Zsolt: authentication and core's MCP

The recommendation: core mints a short-lived signed token (ES256, 5 minutes) for each call, and the world model
verifies it against core's JWKS. MCP calls get read only, to start (settled in the API review). Approval comes only from a person's decision in a
UI. Our side is built; core's side is a proposal ([§6](core-mcp-auth.md#6-changes-in-core)). Until core mints
tokens, it calls with an organization key.

1. **JWKS path.** Is `/.well-known/jwks.json` on core's origin acceptable, or would you prefer `/api/auth/jwks.json`?
   Should core's OAuth metadata advertise `jwks_uri`?
2. **Naming the agent host.** Can `load_access_token` carry the MCP `client_id` and the client name, so the token's
   `act` names the host? Registered clients are held in memory and lost on restart.
3. **Per-model access.** Until core has RBAC, is "every user in an organization sees every world model of that
   organization" enough?
4. **Self-approval.** May a person approve, in a UI, a change they proposed through an agent?
5. **Review UI.** Where does human review live for client organizations: the world model's review UI, or core's
   future expert review screen? Two login systems split the audit trail until one wins.
6. **Names in tokens.** May the token carry the user's display name, or should we look names up in core?
7. **Direct MCP.** Should clients ever connect straight to the world model's `/mcp`, or only through core? *Settled
   in the API review: never directly. Only internal staff and backend services reach the world model.*
8. **Networking.** Are core and the world model service in one Railway project, so calls can use private
   networking?

## For both

- **Rollout order** ([core-mcp-auth.md §8](core-mcp-auth.md#8-rollout-and-migration)):
  1. agree on the contract;
  2. build our side (done);
  3. build core's side, dev first;
  4. staging, then production, each with its own keys;
  5. retire the static keys issued to core.

  Is that the order you want?
- **Core patch.** [integrations/core/](../../integrations/core/README.md) holds a patch that core can apply. It has
  20 tools on `/v1` and passes core's tests in a read-only clone. Nothing has been written to core. Should it land
  before or after the token work?
