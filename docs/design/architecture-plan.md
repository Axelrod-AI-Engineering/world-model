# Architecture plan after the API review

This page turns the API and interface review with Manav (Oct 18) into a plan. It has four parts: what was decided,
what still needs analysis, the order of work, and the analysis of one world model against several. The decisions are
also recorded in [decisions.md](decisions.md) as D-20 to D-24. Open questions stay on
[questions-for-manav-and-zsolt.md](questions-for-manav-and-zsolt.md).

<!-- toc -->
**Contents**

- [1. Decided](#1-decided)
- [2. Needs analysis](#2-needs-analysis)
- [3. Order of work](#3-order-of-work)
- [4. One world model or several](#4-one-world-model-or-several)
<!-- /toc -->

## 1. Decided

| Topic | Decision | Where it lands |
|---|---|---|
| Who may reach the world model | Only internal staff and backend services, never a client directly. Clients use the products built on top. Read and write are distinct permissions. | [core-mcp-auth.md §5](core-mcp-auth.md#5-recommendation), D-21 |
| Core's backend MCP | Read only, to start | The scope table and the core patch |
| Who may write | The web interface (a signed-in person) and the data-ingestion pipeline (a scoped service key) | The scope table |
| Scope names | One verb per action, used the same way on every resource. No near-synonyms such as review/approve or propose/write. Scopes stay fine-grained; finer admin and approval roles come later. | [api.md §3](api.md#3-api-conventions) |
| Audit log | Kept forever: no deletion and no expiry | D-22 |
| Idempotency | Keys are permanent, and creation is keyed on content as well, so the same content always gives the same result. Determinism comes first. Grouping several articles about one event comes later. | D-23 |
| Acronyms | Every acronym and short field name in the API docs is spelled out and defined | [api.md](api.md) |
| ETag and If-Match | Kept as built. Manav is reviewing them. | [api.md §3](api.md#3-api-conventions) |
| A unified endpoint | A separate top-level resource for the unified world model, beside the per-client `/v1/world-models/{id}`, which stays for now. Named `/v1/erid` (the notes' `/erit`; core calls the world model state Erid) and built Oct 19, with compartments defined as focused worlds. | [api.md §4](api.md#the-unified-world-model-erid-built-oct-19) (built) |
| Onboarding first | The world model goes to the client as its JSON export. Core integration waits: Manav opens a basic integration PR to refine later. | Section 3 below |

## 2. Needs analysis

- **One world model or several.** The analysis is in [section 4](#4-one-world-model-or-several). The proposed default
  is one unified model served in compartments. Manav and Karthik decide together after reading it.
- **The object model.** Manav proposed entity types (company, product, metric, and so on) on one base class, with
  strictly typed relationships, so filters can be precise. This is for a joint session. The starting point is the
  current split into entities and attributes ([data-model.md](data-model.md)).
- **First-class records.** Should organization, world model and the structured actor be records in the data model,
  or API metadata? This waits until every term is defined (see the terms table in [api.md](api.md)).
- **Search from a question.** Agreed direction (D-24): start from the nearest neighbours of the question in the
  semantic space, then expand best-first by edge weight rather than by hop count. Today `graph_search` expands one
  hop from what the question names (`lake/search.py`). In the Toyota golden tests it missed a link when the
  question's wording named no value (seed T02A).

## 3. Order of work

1. **Now: onboarding.** Send the client the JSON export of the focused Toyota and Tokio Marine world model. Merge the
   two open code PRs: first the construction standard, then API v1 and the docs.
2. **Next: the API review fixes.** Scope names, the access boundary, permanent idempotency, the audit retention, the
   definitions, and the unified endpoint once its name is confirmed. The work is on a branch and goes in its own PR.
3. **Then: core integration.** Manav's basic integration PR first. Our patch in `integrations/core/` is then
   regenerated against the agreed scopes.
4. **When the team is ready: the architecture changes.**
   - one unified world model, with compartments (section 4);
   - the typed object model;
   - best-first search.

## 4. One world model or several

The question: build one world model for everything, or one per client? Karthik's framing in the meeting was that
the goal was never separate models; it was a compartmentalized service. The focused world (`sally_focus`,
[construction/focus.md](../construction/focus.md)) already does this. It narrows a world to some companies and the
players that reach them, and is recomputed from the full world on every load.

| | One model per client | One unified model, served in compartments | One unified model, served whole |
|---|---|---|---|
| What a client sees | Only their use case | Only their use case (a compartment) | Everything |
| Shared knowledge (macro, markets, sectors) | Copied, and drifts apart | Learned once, read by every compartment | Learned once |
| Learning from one client's documents | Stays in that model | Lands in the shared graph; review decides what crosses compartments | Reaches everyone |
| Risk of one client's data shaping another's answers | None | Controlled: a compartment reads only its subgraph, and the review plus the audit log show what crossed | High |
| Context control and data validity | Simple | Needs explicit rules for what each compartment includes | Hardest |
| Cost of a new client | A new model built from scratch | A new compartment definition | None |
| Fit with "the end goal is one model" | Must be merged later | Already is | Already is |
| Built today | Yes (per-login worlds) | Yes for reads (Oct 19): `/v1/erid` with `compartment`, narrowed as focus narrows | Yes for internal staff: `/v1/erid` |

**Proposed default: one unified model, served in compartments** (D-20). Each client's view is a compartment of the
unified graph, defined the way focus defines one today: the companies in scope, and the players they connect to.
Learning writes to the unified graph through review. Inference and the client's reads see only the compartment.

Manav's framing applies here: what a compartment includes is a kind of bias, a choice on a spectrum, not a leak to be
eliminated. So the rule for what crosses compartments is explicit and reviewed.

Open points for the analysis:

- Does learning run per compartment or on the whole graph? Running on the whole graph is simpler, but it needs
  review to stop one client's documents silently reshaping another client's companies.
- How are compartments addressed in the API? **Chosen and built (Oct 19):** the unified endpoint, `/v1/erid`, plus
  a `compartment` parameter on its graph reads; `/world-models/{id}` stays the per-client resource for now. A
  compartment is any scenario focused on the unified one, so its definition stays in one place (`engine/focus.py`).
- How do audit and permissions attach to compartments? **Built:** reads need `world_model:read`; the whole graph is
  for internal organizations (`WORLD_MODEL_INTERNAL_ORGS`), and a compartment is assigned to a client organization
  (`WORLD_MODEL_COMPARTMENTS`). Writes go through the backing world model, with its review and its audit log, so the
  audit attaches to the unified model. Per-compartment audit views are open.
