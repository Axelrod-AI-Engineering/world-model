# Glossary

The canonical terms. They follow the naming guide ("Axelrod World Model Vision", October 4, 2026) and the World Model artifact. The order follows importance: the data model first, then memory, then the two processes that use them.

- A tooltip may clarify a term; nothing replaces it.
- The **Not** column lists older words for the same thing, so a search finds both.

<!-- toc -->
**Contents**

- [Data model](#data-model)
- [Memory](#memory)
- [Learning (five stages)](#learning-five-stages)
- [Inference (seven stages)](#inference-seven-stages)
- [Architecture](#architecture)
<!-- /toc -->

## Data model

The full field lists are in [data-model.md](data-model.md).

| Term | Meaning | Not |
|---|---|---|
| **Entity** | An actor or an idea: a company, an agency, a market, a person, a macro factor. It is itself a small graph of subentities. | node |
| **Subentity** | One of an entity's values, with a prior and a posterior; always shown with its entity ("Tokio Marine · share price") | attribute |
| **Interaction** | A directed causal relation between two subentities: its existence (a probability), its effect (sd of target per sd of source), and its kernel (delay, lag, duration) | link, edge (in the UI) |
| **Kernel** | An interaction's timing: zero before the delay, a ramp over the lag, a fade over the duration | |
| **Moderator** | A third value that scales, gates, or adds to an interaction | parameter |
| **Channel** | One direction of an interaction, as the dynamics simulate it | |
| **Superentity** | A recurring configuration of entities and interactions, with roles: a sector, a rivalry, a shock. A *pattern* lives in long-term memory; an *instance* is bound in working memory. Superentities nest. | schema, configuration, cluster |
| **Super-interaction** | The interactions between two superentity instances, abstracted | |
| **Concept** | A node of a taxonomy (an object or interaction generalization). Every item is sorted into one and inherits its priors. | kind, category |
| **Soft economic constraint** | A bound that bends a value as it nears a limit, rather than clipping it | hard rule |
| **Standard units (z)** | (link(x) − anchor) / scale: how every value is compared | |
| **Category tag** | One of eight display labels; no causal meaning | |
| **Market event** | Something that happened and was published: news, a data release, a filing, an imported item. Its publication time decides its day. | article (generic) |
| **Imported item** | One dated piece of research in an import bundle (`axelrod.import/v1`) | |
| **Graph update event** | The operations one market event stands for, with their evidence; real or hypothetical | |
| **Operation** | One change: add or retire an item, change or observe a value, reweight or annotate an interaction, propose a hypothesis, group or dissolve a superentity | op |
| **Fuzzy end** | An operation's end that names a concept ("an airline") rather than a value | abstract target |
| **Refinement levels** | generalization → entity → subentity | "a kind of thing", "one value" |
| **Hedge** | A fuzzy end held across candidates, with a probability each plus an open share | pending refinement |
| **Thesis** | A what-if question, posed as a hypothetical graph update event. It is never learned from; with no shocks, it gives a baseline forecast. | |
| **Evidence** | What a belief rests on: its source, the excerpt, when it was observed, how strong | |

## Memory

| Term | Meaning | Not |
|---|---|---|
| **Working memory** | The world now: the graph, daily deviations, channel states, the hypothesis frontier, hedges, ripple judgments, the forecast layer | |
| **Long-term memory** | What generalizes, in five parts: | |
| · **Object generalizations** | Concepts of objects, and superentity patterns | |
| · **Interaction generalizations** | Concepts of interactions | |
| · **Entity memories** | Each actor's decisions, by context | |
| · **Correlation frontier** | Co-movements with no interaction; counted, never propagated, promoted only by review | |
| · **Prior states** | Episodes (distilled days) and explanations | |
| **Hypothesis frontier** | Open hypotheses about interactions and about actors' decisions, ranked by informational value | hypotheses board |
| **Episode · analog** | A distilled day · a recalled episode | |
| **Open node** | What the graph does not explain yet, drawn on every node | |

## Learning (five stages)

| Term | Meaning | Not |
|---|---|---|
| **Learning** | Folding a vetted event into memory: intake → learning · working memory → learning · long-term memory → human review → commit | |
| **Shared read** | The read learning and inference share: parse, classify, recall, bind, prefill, analyze | shared process |
| **Ripple · order · transmission path** | The moves a change sets off downstream · the fewest interactions from the shock to a value · the most significant path of that length | hop |
| **Fold** | Correct a value from a report, and update each interaction into it by how much it explains | |
| **Distill** | The day's consolidation of working memory into long-term memory | consolidation |
| **Staged change · proposal** | An event's whole learning, run on a copy, waiting for review | |
| **Ripple judgment** | A reviewer's probability that a value's ripple arrives | |
| **Commit · version** | One change set in the ledger; any version can be reopened or compared | |

## Inference (seven stages)

The stages are mutually exclusive and collectively exhaustive. Each answers one question.

| Term | Question it answers | Not |
|---|---|---|
| **Pose a thesis** | What is asked? | ask a question (as a label) |
| **Isolate** | What can the shock reach? (the **networks**: superentities, a residual network, a **context network** for watched values) | isolate the networks |
| **Isolated prediction** | How does each network respond alone? | simulate |
| **Distributed prediction** | How do the networks move together? (**scenarios**: rival choices × open hypotheses, weighed once, each coupled) | couple; simulate and couple |
| **Unify** | One answer from rival stories: the scenarios mixed by weight | weigh and unify; average |
| **Read out** | What moves, when, by which path, and why (orders, paths, groups, constraints, the brief) | read out and explain |
| **Evaluate** | Did it come true? (score at the horizon; track records) | score against outcomes |
| **Branch** | A copy of a committed version a thesis runs on; never merged | forecast layer |

## Architecture

| Term | Meaning |
|---|---|
| **Slot** | A swappable algorithm: an ABC, its records, a contract, and implementations chosen by config |
| **Contract** | A slot's process, cadence, inputs, outputs, reads, writes, and when it runs |
| **Port** | The ABC side of a slot |
| **Service** | A command workflow: review, update, thesis, structure |
| **View** | A pure read model: state → DTO |
| **Context layer** | The agent-facing verbs: recall, ask, trace, propose, feedback, status |
| **Session** | What the API serves: services, views, a tracer, a lock, capabilities |
| **Learn · Predict** | The two views: Learn for analysts who teach the model, Predict for clients who ask it |
