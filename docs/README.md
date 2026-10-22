# Axelrod: documentation

The front door. Find the question you have and go to the page that answers it. Each member keeps its own detail in its
own `docs/`; this folder holds what spans them.

<!-- toc -->
**Contents**

- [The repository in one paragraph](#the-repository-in-one-paragraph)
- [Where to go for…](#where-to-go-for)
- [Folder layout](#folder-layout)
<!-- /toc -->

## The repository in one paragraph

Axelrod is one causal world model of the economy, and the machinery that keeps it current. The repository is a uv
workspace of two members. **`ingestion/`** (`axelrod-ingest`) turns documents into dated, quoted signals and keeps them
in a searchable lakehouse. **`world_model/`** (`axelrod-world-model`) holds the causal graph, learns from reviewed
changes, answers what-if questions, and serves the demo and the outward API. They meet at one small contract, and
ingestion never imports the world model. [architecture.md](architecture.md) draws it.

![Overview: learning, inference, and the architecture](flowchart.svg)

## Where to go for…

| I want to… | Go to |
|---|---|
| See how the pieces fit: the two members, their contract, the data and determinism conventions | [architecture.md](architecture.md) |
| Know what to read, in what order, by role | [reading-order.md](reading-order.md) |
| Know why a choice was made, in any part of the system | [decisions.md](decisions.md) |
| See each model and update in one page, with links to the math | [ml-stack.md](ml-stack.md) |
| Release, verify a deploy, manage logins and keys | [deployment.md](deployment.md) |
| Run the tests, follow the conventions, understand CI | [development.md](development.md) |
| Follow a file from upload to bundle; the lakehouse; the bundle format; the benchmark | [../ingestion/docs/README.md](../ingestion/docs/README.md) |
| Run a demo, use the app, run a command | [../world_model/docs/README.md](../world_model/docs/README.md) |
| Call the API or MCP | [../world_model/docs/api/README.md](../world_model/docs/api/README.md) |
| Look up a term | [../world_model/docs/vocab.md](../world_model/docs/vocab.md) |

## Folder layout

```text
docs/                 this front door
  README.md           this map
  architecture.md     the two members and their contract; data and determinism conventions
  reading-order.md    what to read first, by role
  decisions.md        an index of every decision log, and the repository-level decisions
  ml-stack.md         one page: each model and update, and where its math is
  deployment.md       releasing, verifying, logins and keys, running the container
  development.md      tests, coverage, CI, layout, conventions
  flowchart.svg       the overview picture (axelrod flows --svg)
  media/              videos (gitignored; ask the team)
ingestion/docs/       pipeline, lake, contract, bench
world_model/docs/     guides, api, design, ml, construction, briefs, archive, vocab
```
