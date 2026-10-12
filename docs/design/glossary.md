# Glossary

The canonical terms. They follow the naming guide ("Axelrod World Model Vision", October 4, 2026) and the World Model artifact. Usability work may add a tooltip or a description, but it never replaces a term. Where older documents use another word, it is listed under **Not**, so a search finds both.

## Objects

| Term | Meaning | Not |
|---|---|---|
| **Entity** | An actor or an idea: a firm, agency, market, person, or macro factor. It is itself a small graph of subentities. | node |
| **Subentity** | One of an entity's values, with a prior and a posterior. Its id is `<entity>.<slug>`. The UI may say "value" when speaking of a subentity's number. | attribute |
| **Interaction** | A directed causal relation between two subentities. It has an existence probability, an effect (sd of the target per sd of the source), a kernel (delay, lag, duration), moderators, and evidence. | link, edge (in the UI) |
| **Channel** | One direction of an interaction, as the dynamics simulate it | |
| **Kernel** | An interaction's step response: zero before the delay, a ramp over the lag, then a fade over the duration | |
| **Superentity** | A reusable configuration of entities, interactions, and other superentities: a sector, a rivalry, a shock. A *pattern* lives in long-term memory; an *instance* is bound in working memory. Superentities nest. | schema, configuration, cluster |
| **Super-interaction** | An abstraction over the interactions between two superentity instances | |
| **Kind** | A node of a taxonomy: an object generalization or an interaction generalization. Every item is classified into one and inherits its priors. | category |
| **Category tag** | One of eight display labels (SD, MF, SC, DI, DF, EN, EX, SH). It has no causal meaning. | |
| **Open node** | The dashed node on every item: what the graph does not explain yet | |
| **Soft economic constraint** | A bound that bends a value as it nears a limit, rather than clipping it | hard rule |

## Events and operations

| Term | Meaning | Not |
|---|---|---|
| **Market event** | Something that happened and was published: news, a data release, a filing, an imported item. Its publication time decides its day. | article (generic) |
| **Imported item** | One dated piece of research in an import bundle (`axelrod.import/v1`), already read and categorized by a research agent | |
| **Graph update event** | The operations one market event stands for, with their evidence. It is real or hypothetical. | |
| **Operation** | One change: add or retire an item, change or observe a value, reweight or annotate an interaction, propose a hypothesis, group or dissolve a superentity | op |
| **Fuzzy end** | An operation's end that names a kind ("an airline") rather than a value | abstract target |
| **Refinement levels** | generalization → entity → subentity | "a kind of thing", "one value" |
| **Hedge** | A fuzzy end held across candidates, with a probability each plus an open share, drawn as soft interactions | pending refinement (older) |
| **Ripple** | The moves a change sets off downstream, order by order | |
| **Order** | The fewest interactions from the shock to a value | hop |
| **Transmission path** | The most significant path a move travels, with its arrival and peak | |
| **Transmission grid** | Input → each order → output, keeping only what carries the effect | |
| **Ripple judgment** | A reviewer's probability that a value's ripple arrives | |

## Memory

| Term | Meaning | Not |
|---|---|---|
| **Working memory** | What the world is like now: the graph, daily deviations, channel states, the hypothesis frontier, hedges, ripple judgments, the forecast layer | |
| **Long-term memory** | What generalizes across time and entities. It has five parts, in this order: | |
| · **Object generalizations** | Kinds of objects, and superentity patterns | |
| · **Interaction generalizations** | Kinds of interactions | |
| · **Entity memories** | Each actor's decisions, by context | entity memory (lowercase in prose is fine) |
| · **Correlation frontier** | Co-movements with no interaction. They are counted, never propagated, and promoted only by review. | |
| · **Prior states** | Episodes (distilled days) and explanations | |
| **Hypothesis frontier** | Open hypotheses about interactions and about entities' decisions, sorted by informational value | hypotheses board |
| **Episode** | One distilled day, kept for recall. An *analog* is a recalled episode. | |

## Processes

| Term | Meaning | Not |
|---|---|---|
| **Learning** | Folding a vetted event into memory. It has five stages: intake, learning · working memory, learning · long-term memory, human review, commit. | |
| **Inference** | Answering a thesis on a branch. It has six stages: pose a thesis, isolate the networks, simulate and couple, weigh and unify, read out and explain, score against outcomes. | performance task |
| **Shared read** | What learning and inference share: parse, classify, recall, bind, prefill, analyze | shared process |
| **Isolated prediction** | Each network predicted alone | |
| **Distributed prediction** | The networks coupled through the interactions between them | |
| **Unify** | Rival scenarios mixed by weight into one forecast | average |
| **Pose a thesis** | Ask a what-if question in Predict | ask a question (as a label) |
| **Thesis** | A hypothetical graph update event posed as a question. With no shocks, it gives a baseline forecast. | |
| **Branch** | A copy of a committed version that a thesis runs on. It is never merged. | forecast layer (older) |
| **Distill** | The day's consolidation of working memory into long-term memory (`day.distill`) | consolidation (older; the slot keeps the name `consolidator`) |
| **Network** | A bound superentity instance used for prediction; also the residual and context (watch) networks | |
| **Context network** | Paths from the shock to every watched name, so no tracked name is dropped silently | |
| **Staged change / proposal** | An event's whole learning run on a copy, waiting for review | |
| **Commit / version** | One change set in the ledger; any version can be reopened read-only or compared | |
| **Learn / Predict** | The two views: Learn for backend users who teach the model, Predict for external users who ask it | |

## Architecture

| Term | Meaning |
|---|---|
| **Slot** | A swappable component: an ABC, its records, a contract, and registered implementations chosen by config |
| **Contract** | A slot's process, cadence, inputs, outputs, reads, writes, and when it runs |
| **Port** | The ABC side of a slot (layer 0) |
| **Service** | A command workflow: review, update, thesis, structure |
| **View** | A pure read model: state → DTO |
| **Context layer** | The agent-facing verbs over the model: recall, ask, trace, propose, feedback, status |
| **Session** | What the API serves: services, views, a tracer, a lock, and capabilities |
