# Axelrod World Model: design

The design of record. It is written in levels, so read only as deep as you need: this page, then the diagrams, then one module's spec, then the methods.

## Read by need

| You want | Read |
|---|---|
| What the system is, in five minutes | This page |
| How it flows | [architecture.md](architecture.md): eight overview diagrams |
| To build or change one part | That part's spec in [modules/](modules/README.md), plus the layer rules ([architecture.md §2](architecture.md#2-module-layers)) |
| Why memory works like a mind and not like a search index | [cognition.md](cognition.md) |
| Why not just use Cognee or Semantica | [frameworks.md](frameworks.md) |
| Why a choice was made, or which old doc is right | [decisions.md](decisions.md) |
| A term | [glossary.md](glossary.md) |
| What to code next | [migration.md](migration.md): ordered tasks |
| The math | [../ml-stack.md](../ml-stack.md) (as built) and [../ml-roadmap.md](../ml-roadmap.md) (R0–R19) |

## Two parts

- **The world model** is a causal graph of the economy, made of entities, subentities, interactions, and superentities. It learns from vetted events and forecasts through its interactions. We own it end to end, because the quantitative causal dynamics are the product.
- **The context layer** is how agents and people reach the model: recall, ask, trace, propose, feedback. It borrows Cognee's verbs and Semantica's provenance and time model. It never replaces the model, and it never writes without review.

## Architecture

```text
Sources → Intake (translate · refine) → Shared read (parse · classify · recall · bind · prefill · analyze)
   → [ Learning · working memory  ·  Learning · long-term memory ] → Staged change → Human review
   → Commit (ledger · snapshots · versions) → Committed version
   → Inference on a branch (isolate · simulate · couple · weigh · unify · explain) → Forecast + brief
   → Views · API · Context layer (MCP) · Web
```

- **Intake:** a market event becomes operations. A fuzzy end binds only when the article names it; otherwise it is hedged across candidates.
- **Shared read:** learning and inference read events the same way. Each new item is classified into a kind, similar cases are recalled, and the ripple is simulated by order.
- **Learning:** working memory folds the event into the current state. Long-term memory learns kinds, Entity memories, the correlation frontier, and superentities.
- **Human review:** the event's whole learning runs on a staged copy, and a person approves all of it, some of it, or none, down to the third-order ripple.
- **Commit:** one writer and an append-only ledger. Any version can be restored and its hash verified.
- **Inference:** a thesis runs on a branch that is never merged. Rival scenarios are mixed into one forecast, read out by order and transmission path.

## Modules

There are 17 modules in six layers. Imports only go down. Every algorithm sits behind a **slot** (an ABC, a contract, and a config choice), so it can be swapped and tested by ablation.

| Layer | Module | Package | What it does |
|---|---|---|---|
| 0 | [M01 Foundation](modules/M01-foundation.md) | `core/`, `ports/` | Ids, canonical bytes, rng substreams, the trace bus, the registry; every slot's ABC and contract |
| 1 | [M02 Model](modules/M02-model.md) | `model/` | Entities, subentities, interactions, superentities, events, theses, forecasts |
| 2 | [M03 Memory](modules/M03-memory.md) | `memory/` | Working memory and long-term memory, as state |
| 2 | [M04 Repo](modules/M04-repo.md) | `repo/` | The one writer, the ledger, snapshots, branches, provenance |
| 3 | [M05 Intake](modules/M05-intake.md) | `intake/` | Sources, translators, refinement and hedges, import bundles, conflict flags |
| 3 | [M06 Shared read](modules/M06-shared-read.md) | `shared/` | Parse, classify, recall, bind, prefill, analyze, transmission, explain |
| 3 | [M07 Dynamics](modules/M07-dynamics.md) | `dynamics/` | Kernels, Monte Carlo propagation, the daily filter |
| 3 | [M08 Learning · WM](modules/M08-learning-working.md) | `learning/working/` | Fold, hedges, ripple judgments, kernels, the hypothesis frontier |
| 3 | [M09 Learning · LTM](modules/M09-learning-long-term.md) | `learning/long_term/` | Kinds, Entity memories, correlation frontier, superentities, distillation |
| 3 | [M10 Inference](modules/M10-inference.md) | `inference/` | Isolate, predict, couple, weigh, unify, groups |
| 3 | [M11 Evaluation](modules/M11-evaluation.md) | `evaluation/` | Scores, backtests, track records, decisions |
| 4 | [M12 Runtime](modules/M12-runtime.md) | `runtime/` | Composition root, orchestrators, the day loop, sandboxes |
| 4 | [M13 Services](modules/M13-services.md) | `control/` | Review, update, thesis, structure, sources |
| 5 | [M14 Views, API, CLI](modules/M14-interfaces.md) | `views/`, `api/`, `cli.py` | Read models and thin adapters |
| 5 | [M15 Context layer](modules/M15-context-layer.md) | `context/` | Agent verbs over MCP and REST |
| 5 | [M16 Web](modules/M16-web.md) | `web/` | Learn and Predict in the browser |
| side | [M17 Demo](modules/M17-demo.md) | `demo/` | The synthetic world, scenarios, the tutorial |

## Invariants

These hold across every module, and tests check each one:

1. **One writer.** Every change goes through a transaction, which becomes one change set in the ledger.
2. **Vetted learning.** Nothing that needs review is learned before a person approves it, and what they approve is what they saw staged.
3. **Two learning commits per event** (working memory, then long-term memory). `day.close` is always the day's last commit.
4. **Inference never learns.** A thesis reads a branch; only outcomes feed back, through track records.
5. **Explicit randomness.** Every draw comes from a named substream. Analyses run with and without a shock on the same draws.
6. **Restore.** The init snapshot plus the change sets reproduce the live hash.
7. **Contracts.** Each slot has an ABC, a contract, and a flowchart node, and a test keeps the three in step.
8. **The front end computes nothing.** It renders views and replays traces.
9. **Canonical terms** ([glossary.md](glossary.md)), and **synthetic data** in every demo.

## Decisions in brief

- **Own the causal core; borrow for the context layer.** Neither framework has quantitative interactions or forecasts ([frameworks.md](frameworks.md)).
- **Memory organized as a cognitive architecture.** Two memories, concept trees, schemas, analogy by structure, an open world, and a hypothesis frontier, each testable against the standard method by ablation ([cognition.md](cognition.md)).
- **Bitemporal facts and PROV-shaped change sets,** from Semantica.
- **Stable identity across imports, and supersede rather than delete,** from Cognee.
- **One branch mechanism** for staging and for theses.
- **Agents write only by proposal.**

All of them, with alternatives: [decisions.md](decisions.md).
