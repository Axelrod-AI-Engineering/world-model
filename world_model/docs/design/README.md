# Axelrod World Model: design

The design of record. Each section stays at a high level and links to the detail; read only as deep as you need.

<!-- toc -->
**Contents**

- [1. Problem and motivation](#1-problem-and-motivation)
- [2. Audience](#2-audience)
- [3. Scope](#3-scope)
- [4. Design principles](#4-design-principles)
- [5. Requirements](#5-requirements)
- [6. The system at a glance](#6-the-system-at-a-glance)
- [7. Core concepts](#7-core-concepts)
- [8. Dependency graph](#8-dependency-graph)
- [9. Architecture: components by workflow step](#9-architecture-components-by-workflow-step)
- [10. Infrastructure](#10-infrastructure)
- [11. Data model and interfaces](#11-data-model-and-interfaces)
- [12. Modules](#12-modules)
- [13. Read more](#13-read-more)
<!-- /toc -->

## 1. Problem and motivation

A portfolio manager's question is causal and quantitative: *if oil stays high for six months, where does it show up in my book, and when?* The answer runs through chains of effects: oil → inflation → central banks → the US–Japan rate gap → USD/JPY → a Japanese insurer's earnings. Analysts trace these chains by hand. The second- and third-order effects are where they miss things, and where the edge is.

General AI assistants don't solve this. They have no persistent, quantitative model of how the economy is wired; they can't say how big an effect is or how long it takes; and they can't show where a number came from.

**We are building a world model of the economy that a PM can ask.** It has two halves:

- **It learns.** It keeps a causal graph current from vetted news, data, and research, and a person checks every change before it is committed.
- **It predicts.** It answers what-if questions with the effect on each name, its timing, its uncertainty, and the transmission path it travels, without ever changing itself to answer.

## 2. Audience

| Who | Uses | Needs |
|---|---|---|
| Portfolio managers (external) | Predict | Answers by name, by time, by path; reasons they can defend |
| Axelrod analysts (internal) | Learn | To keep the model current, with nothing learned unchecked |
| Agents | The context layer | Recall, ask, and propose, never write |
| Engineers (this document) | The code | Modules small enough to build and test alone |

## 3. Scope

| In scope (this horizon) | Out of scope (this horizon) | Next horizon |
|---|---|---|
| One causal world model per client, of about 50 names and their drivers | Many clients in one model; multi-tenant accounts and roles | Accounts, roles, and a model per client team |
| Learning from vetted news, data releases, research bundles, and analysts' own knowledge | Learning anything unreviewed; live market data feeds | Vintage-aware data feeds, still reviewed |
| What-if forecasts by name, sector, and superentity, with orders and transmission paths | Trading signals, execution, portfolio optimization, intraday or high-frequency use | Decision support tied to the PM's positions |
| Version control: staged review, the ledger, restore any version | Editing history (it is append-only) | Point-in-time queries (bitemporal) |
| A hosted demo per login; synthetic data; an outward API (REST `/v1` and MCP) for other services and agents | Client data in the repository | The context layer's verbs for agents ([M15](modules/M15-context-layer.md)) |

## 4. Design principles

**Design for the next horizon, build for the current one.** Interfaces, data shapes, and module boundaries are designed for where the system is going (bigger graphs, proper statistical methods, agents, point-in-time data). What is built behind them is the simplest thing that works now. For example, every method sits behind a slot so a better one can replace it, and every new field has a default so old versions load.

The principles, in priority order. When two conflict, the higher one wins.

| Priority | Principle | What it means here | How the design keeps it |
|---|---|---|---|
| **P0** | **Interpretability, usability, trust** | Every number can be explained: its path, its evidence, who approved it. A PM sees the answer first and detail on request. | Transmission paths by order; staged review of every change; the ledger; academic terms used consistently; a minimal first view |
| **P1** | **Determinism, reliability, groundedness** | The same question on the same version gives the same answer. Everything learned traces to evidence a person approved. | Named random substreams; one writer; restore by hash; inference never learns; hedges instead of guesses |
| **P2** | **Streamability, generalization** | The model takes in events one at a time, as they happen, and what it learns carries over to new names and new shocks. | Incremental learning per event and per day; concepts that pass priors to new members; superentities and analogs ([cognition.md](cognition.md)) |
| **P3** | **Scalability, cost, performance** | Fast enough for the current book, and with a path to bigger ones. | Isolating only what a shock reaches; caches; swappable propagators and stores; measured limits ([requirements.md](requirements.md#nonfunctional-requirements)) |

## 5. Requirements

[requirements.md](requirements.md) lists them in full.

- **Functional:** 21 user stories across four personas. They follow a PM's oil-to-portfolio workflow: pick a scenario, see where it lands and when, follow the path, compare rival scenarios, drill into one name, separate fact from assumption, re-run, and share a brief. 15 are built, 5 partial, 1 planned.
- **Nonfunctional:**
  - **Measured today:** 53 entities and 165 interactions in the production demo. Staging a review takes 2–3 s; a forecast takes 7–10 s; three years of history fit in about 0.7 GB.
  - **Hard limits:** 400 Monte Carlo samples, a 182-day horizon, and up to 8 scenarios per thesis.
  - **Next horizon:** 500–2,000 entities, and forecasts under 5 s.

## 6. The system at a glance

![The system at a glance](diagrams/high-level.svg)

Events from the world are read into the model; a person reviews every change; the model is versioned like code. Questions run on a copy that is never merged, and only outcomes flow back, scoring the forecasts.

## 7. Core concepts

| Term | Meaning |
|---|---|
| **Entity** | An actor or an idea: a company, an agency, a market, a macro factor |
| **Subentity** | One of an entity's values, such as a price, a rate, or a share |
| **Interaction** | A causal relation between two values: whether it exists, how big, how slow |
| **Superentity** | A recurring configuration of entities and interactions, such as a sector, a rivalry, or a shock; superentities nest |
| **Working memory · long-term memory** | The world now · what generalizes (concepts, Entity memories, the correlation frontier, superentity patterns, episodes) |
| **Graph update event · thesis** | What an article is read into (learned from, after review) · a what-if question (asked, never learned from) |

The full data model is in [data-model.md](data-model.md), and every term is in [../vocab.md](../vocab.md).

## 8. Dependency graph

There are 17 modules in six layers. Every arrow points up, to what a module depends on, and no layer reaches down.

![Dependency graph](diagrams/dependency-graph.svg)

## 9. Architecture: components by workflow step

| Step | Components (module · slot) | What they do |
|---|---|---|
| **Learn** · collect | Intake (M05) · `source` | Poll news, data, and imports; drop duplicates; queue events by day |
| · translate and refine | Intake (M05) · `translator`, `refiner`, `entity_resolver` | Turn an article into operations; narrow vague mentions, or hedge them |
| · read | Shared read (M06) · `parser`, `classifier`, `recaller`, `binder`, `prefiller`, `analyzer` | Apply operations, classify new items, recall similar cases, simulate the ripple by order |
| · learn working memory | Learning · WM (M08) · `folder`, `daily_propagator` | Fold reports into values and interactions; open and close each day |
| · learn long-term memory | Learning · LTM (M09) · `generalization_updater`, `frontier`, `inducer`, `consolidator` | Update concepts, Entity memories, the correlation frontier, superentities |
| · review | Services (M13) · `review_policy`; Runtime (M12) sandbox | Stage the whole learning on a copy; a person approves all, some, or none |
| · commit | Repo (M04) · `storage` | One change set per transaction, in the ledger; snapshots; versions |
| **Predict** · pose a thesis | Services (M13); Intake (M05) `refiner` | Read the question into a hypothetical event with concrete ends |
| · isolate | Inference (M10) · `isolator` | Find the networks the shock can reach |
| · isolated prediction | Inference (M10) · `network_predictor`; Dynamics (M07) | Each network alone, with and without the shock |
| · distributed prediction | Inference (M10) · `rival_detector`, `scenario_weighter`, `coupler` | Form and weigh scenarios; couple each one's networks |
| · unify | Inference (M10) · `unifier` | One forecast, the scenarios mixed by weight |
| · read out | Shared read (M06) transmission, `explainer`; Views (M14) | Orders, paths, groups, constraints, the brief |
| · evaluate | Evaluation (M11) · `scorer` | Score recorded decisions at the horizon; update track records |

[architecture.md](architecture.md) has the diagrams for each process; each module's spec has its own detail.

## 10. Infrastructure

| Component | Today | Next horizon |
|---|---|---|
| Runtime | Python 3.12 (uv), FastAPI + uvicorn; one engine per login, in process | Engines as workers behind the API |
| Storage | Ledger (JSONL) and gzip snapshots on a volume (`var/`) | Append-only columnar tables |
| Front end | Static HTML, CSS, and ES modules; d3 v7; no build step | Same |
| Hosting | Railway, one replica, Dockerfile, IaC in `.railway/railway.ts`; a push to `main` is a release | More replicas, by login |
| Auth | Sign-in page, HMAC session cookie, logins per scenario; for `/v1` and `/mcp`, core-minted service tokens and scoped keys ([core-mcp-auth.md](core-mcp-auth.md)) | Accounts and roles |
| Tests and checks | pytest (unit, integration, scenario, UI), ruff; GitHub Actions on pull requests | Same, plus nightly backtests |
| Docs tooling | `axelrod flows --svg` (the README picture), `scripts/docs/diagrams.py` (these diagrams), `scripts/docs/toc.py` (contents) | Same |

The deployment is drawn in [docs/deployment.md](../../../docs/deployment.md).

## 11. Data model and interfaces

- [data-model.md](data-model.md): every type, its fields, the units, and the invariants.
- [interfaces.md](interfaces.md): the boundaries between parts.
  - **Slots:** the swappable algorithms, with their signatures.
  - **Service commands, REST and `/ws`, context-layer verbs.**
  - **The import bundle, the ledger, and the trace format.**
- [api.md](api.md): the outward API's design (domain model, conventions, routes, decisions), with its contract
  ([../api/openapi.yaml](../api/openapi.yaml)) and reference ([../api/README.md](../api/README.md)).
- [core-mcp-auth.md](core-mcp-auth.md): how core's MCP server and other callers authenticate to it.
- [specificity.md](specificity.md): the rules a model must meet to be specific enough (R1–R21), and where each is
  enforced.

## 12. Modules

| Layer | Module | Package | What it does |
|---|---|---|---|
| 0 | [M01 Foundation](modules/M01-foundation.md) | `core/`, `ports/` | Ids, canonical bytes, rng substreams, the trace bus, the registry; every slot's ABC and contract |
| 1 | [M02 Model](modules/M02-model.md) | `model/` | The data model |
| 2 | [M03 Memory](modules/M03-memory.md) | `memory/` | Working memory and long-term memory, as state |
| 2 | [M04 Repo](modules/M04-repo.md) | `repo/` | The one writer, the ledger, snapshots, branches, provenance |
| 3 | [M05 Intake](modules/M05-intake.md) | `intake/` | Sources, translators, refinement and hedges, import bundles |
| 3 | [M06 Shared read](modules/M06-shared-read.md) | `shared/` | Parse, classify, recall, bind, prefill, analyze, transmission, explain |
| 3 | [M07 Dynamics](modules/M07-dynamics.md) | `dynamics/` | Kernels, Monte Carlo propagation, the daily filter |
| 3 | [M08 Learning · WM](modules/M08-learning-working.md) | `learning/working/` | Fold, hedges, ripple judgments, kernels, the hypothesis frontier |
| 3 | [M09 Learning · LTM](modules/M09-learning-long-term.md) | `learning/long_term/` | Concepts, Entity memories, correlation frontier, superentities, distillation |
| 3 | [M10 Inference](modules/M10-inference.md) | `inference/` | Isolate, isolated and distributed prediction, unify |
| 3 | [M11 Evaluation](modules/M11-evaluation.md) | `evaluation/` | Scores, backtests, track records, decisions |
| 4 | [M12 Runtime](modules/M12-runtime.md) | `runtime/` | Composition root, orchestrators, the day loop, sandboxes |
| 4 | [M13 Services](modules/M13-services.md) | `control/` | Review, update, thesis, structure, sources |
| 5 | [M14 Views, API, CLI](modules/M14-interfaces.md) | `views/`, `api/`, `cli.py` | Read models and thin adapters |
| 5 | [M15 Context layer](modules/M15-context-layer.md) | `context/` | Agent verbs over MCP and REST |
| 5 | [M16 Web](modules/M16-web.md) | `web/` | Learn and Predict in the browser |
| side | [M17 Demo](modules/M17-demo.md) | `demo/` | The synthetic world, scenarios, the tutorial |

## 13. Read more

| You want | Read |
|---|---|
| The processes, drawn | [architecture.md](architecture.md) |
| Why memory works like a mind, not a search index | [cognition.md](cognition.md) |
| Why not just use Cognee or Semantica | [frameworks.md](frameworks.md) |
| Why a choice was made | [decisions.md](decisions.md) (architecture), [api.md §9](api.md#9-decisions) (the API), [specificity.md](specificity.md#decisions) (business construction) |
| What to code next | [migration.md](migration.md) |
| The math | [../ml/stack.md](../ml/stack.md) and [../ml/roadmap.md](../ml/roadmap.md) |
| A term | [../vocab.md](../vocab.md) |
