# Axelrod World Model: design

This folder is the design of record for the world model. It describes the target system as modules that can each be built, tested, and swapped on their own. The code today is close to it but not there yet; [migration.md](migration.md) lists the steps from one to the other.

Two parts, kept separate on purpose:

- **The world model**: a causal graph of the economy, with entities, subentities, interactions, and superentities. It learns from vetted events and forecasts through its interactions. Axelrod owns it end to end, because the quantitative causal dynamics are the product.
- **The context layer**: how agents and people reach the model. They can recall what it knows, ask it a what-if question, trace where a number came from, and propose what it should learn. It borrows from Cognee and Semantica ([frameworks.md](frameworks.md)), but it never replaces the model.

## Architecture

The system is a pipeline from news to version-controlled memory, plus a read-only path from a question to a forecast:

```text
Sources → Intake (translate · refine) → Shared read (parse · classify · recall · bind · prefill · analyze)
   → [ Learning · working memory  ·  Learning · long-term memory ] → Staged change → Human review
   → Commit (ledger · snapshots · versions) → Committed version
   → Inference on a branch (isolate · simulate · couple · weigh · unify · explain) → Forecast + brief
   → Views · Context layer (MCP · REST) · Web · CLI
```

- **Sources:** news, data releases, filings, import bundles from a research agent, and a backend user's own knowledge.
- **Intake:** a translator turns a market event into a graph update event. The refiner narrows each fuzzy end from kind to entity to subentity, or hedges it across candidates.
- **Shared read:** the read that learning and inference share. It applies operations, classifies new items into kinds, recalls similar superentities and episodes, binds patterns, and simulates the ripple by order.
- **Learning · working memory:** folds the event into the current state. That covers values, interactions, and hedges.
- **Learning · long-term memory:** records what the event teaches across time and entities. That covers kinds, entity memories, the correlation frontier, superentity support, and prior states.
- **Human review:** the event's whole learning runs on a staged copy. A person approves all of it, some of it, or none, down to the third-order ripple.
- **Commit:** a single writer turns each approved change into a change set in an append-only ledger. Snapshots plus the ledger reproduce any version.
- **Inference:** a thesis runs on a branch of a committed version that is never merged. Rival scenarios are mixed into one forecast, which is read out by order and transmission path.
- **Interfaces:** read models for the web app, REST and WebSocket, the CLI, and the context layer for agents.

→ [architecture.md](architecture.md) has the diagrams: the module map, the dependency layers, every pipeline, the sequence diagrams, the data model, and the lifecycles.

## Modules

There are 19 modules in six layers. A module depends only on modules in layers below it. Every algorithm sits behind a **slot**: an abstract base class (ABC) with a written contract, chosen by name in `configs/*.yaml`.

| Layer | # | Module | Package (target) | What it does | Spec |
|---|---|---|---|---|---|
| 0 Foundation | M01 | Core | `core/` | Ids, canonical serialization, named random substreams, the trace bus, the slot registry | [M01](modules/M01-core.md) |
| | M02 | Ports | `ports/` | Every slot's ABC, its record types, and its contract, in one place | [M02](modules/M02-ports.md) |
| 1 Domain | M03 | Model | `model/` | Entities, subentities, interactions, superentities, distributions, kernels, evidence; market events, graph update events, theses | [M03](modules/M03-model.md) |
| 2 State | M04 | Memory | `memory/` | Working memory and long-term memory, as state only | [M04](modules/M04-memory.md) |
| | M05 | Repo | `repo/` | The one writer, change sets, the ledger, snapshots, branches, history | [M05](modules/M05-repo.md) |
| 3 Engines | M06 | Intake | `intake/` | Sources, translators, entity resolution, refinement and hedges, import bundles | [M06](modules/M06-intake.md) |
| | M07 | Shared read | `shared/` | Parse, classify, recall, bind, prefill, analyze, transmission, explain | [M07](modules/M07-shared-read.md) |
| | M08 | Dynamics | `dynamics/` | Kernels, Monte Carlo propagation, the daily filter | [M08](modules/M08-dynamics.md) |
| | M09 | Learning · WM | `learning/working/` | Fold, hedges, ripple judgments, kernel learning, hypothesis scoring | [M09](modules/M09-learning-working.md) |
| | M10 | Learning · LTM | `learning/long_term/` | Kinds, entity memories, correlation frontier, superentity induction, distillation | [M10](modules/M10-learning-long-term.md) |
| | M11 | Inference | `inference/` | Isolate, predict, couple, weigh and unify, groups, transmission paths | [M11](modules/M11-inference.md) |
| | M12 | Evaluation | `evaluation/` | Scoring, backtests, track records, decisions | [M12](modules/M12-evaluation.md) |
| 4 Runtime | M13 | Runtime | `runtime/` | The composition root, the orchestrators, the day loop, sandboxes | [M13](modules/M13-runtime.md) |
| | M14 | Services | `control/` | Review, update, thesis, structure, and source services | [M14](modules/M14-services.md) |
| 5 Interfaces | M15 | Views | `views/` | Read models: graph, staged review, briefs, find, checks | [M15](modules/M15-views.md) |
| | M16 | Context layer | `context/` | Agent-facing verbs over MCP and REST: recall, ask, trace, propose, feedback | [M16](modules/M16-context-layer.md) |
| | M17 | API and CLI | `api/`, `cli.py` | Thin adapters over services and views | [M17](modules/M17-api-cli.md) |
| | M18 | Web | `web/` | The browser app: canvas, panels, the trace player | [M18](modules/M18-web.md) |
| Side | M19 | Demo | `demo/` | The synthetic world, scenarios, the tutorial's examples | [M19](modules/M19-demo.md) |

Each spec has the same sections, so it can be handed to an engineer or a coding agent as one unit: purpose, what the module owns, its interface (signatures), its slots, its dependencies, a flowchart, its invariants, known issues and planned methods, and the tests that define done.

## Decisions in brief

| Decision | Choice | Why |
|---|---|---|
| Core model | Our own causal world model (custom) | Neither Cognee nor Semantica has quantitative interactions, propagation, or forecasts ([frameworks.md](frameworks.md#what-neither-provides)) |
| Context layer | Custom, with Cognee's agent verbs and Semantica's provenance and time model | Their good ideas come without their storage or their LLM-first extraction |
| Research memory, upstream | Optionally Cognee, behind the import bundle | It is strong at unstructured documents and sessions, and the bundle is a clean seam |
| Provenance | PROV-shaped change sets (entity, activity, agent) in our ledger | We already have one writer and an append-only ledger. Semantica's PROV-O vocabulary makes it exportable. |
| Time | Bitemporal: valid time and recorded time on every fact | Backtests without leakage, and "what did the model believe on date X" |
| Writes | One writer, staged review, nothing learned unvetted | A person sees and approves what is committed, including the ripple |
| Plugins | Slots: ABC + contract + registry + config | Every method can be swapped and tested against its contract |

[decisions.md](decisions.md) records each decision with its alternatives. It also settles the places where older documents disagree.

## Reading order

1. This page, then [architecture.md](architecture.md) for the pictures.
2. [glossary.md](glossary.md) for the terms. The academic names (entity, subentity, interaction, superentity, hypothesis frontier, Entity memories, Pose a thesis…) are the canonical ones.
3. The module specs in [modules/](modules/), in layer order.
4. [frameworks.md](frameworks.md): Cognee and Semantica, compared, with what we borrow.
5. [migration.md](migration.md): from the code today to these modules, as ordered tasks.

For the methods themselves, read [../ml-stack.md](../ml-stack.md) (what the code computes, with its adversarial review) and [../ml-roadmap.md](../ml-roadmap.md) (what replaces each heuristic, R0–R19). The module specs cite them by section rather than repeat them.
