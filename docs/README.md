# Documentation

A map: find the question you have, and go to the one page that answers it.

<!-- toc -->
**Contents**

- [Start here](#start-here)
- [Where to go for…](#where-to-go-for)
- [Folder layout](#folder-layout)
<!-- /toc -->

## Start here

New to the repository? Read these four, in order (about an hour):

1. [design/README.md](design/README.md): what the world model is for, its principles, and the system at a glance.
2. [guides/demos.md](guides/demos.md): run `uv run axelrod small_demo` and follow the 24 examples.
3. [guides/development.md](guides/development.md): tests, the layout, and the conventions.
4. [vocab.md](vocab.md): the terms. Every page uses them; none renames them.

## Where to go for…

| I want to… | Go to |
|---|---|
| Run a demo, or see what each one shows | [guides/demos.md](guides/demos.md) |
| Find a control, panel, or shortcut in the app | [guides/gui.md](guides/gui.md) |
| Run a command, or set a config file or environment variable | [guides/cli.md](guides/cli.md) |
| Run the tests, or follow the conventions (TOCs, diagrams, decisions) | [guides/development.md](guides/development.md), [../tests/README.md](../tests/README.md) |
| Release, verify a deploy, or manage logins and keys | [guides/deployment.md](guides/deployment.md) |
| Know how a file becomes graph updates; the lakehouse, search, the benchmark | [guides/ingestion.md](guides/ingestion.md) |
| Call the API or MCP: routes, auth, errors, configuration | [api/README.md](api/README.md) (generated from [api/openapi.yaml](api/openapi.yaml)) |
| Know why the API looks the way it does | [design/api.md](design/api.md) |
| Know how core and other callers authenticate | [design/core-mcp-auth.md](design/core-mcp-auth.md) |
| Answer the open questions for Manav and Zsolt | [design/questions-for-manav-and-zsolt.md](design/questions-for-manav-and-zsolt.md) |
| Understand the design: problem, scope, principles, modules | [design/README.md](design/README.md) |
| See the user stories and measured limits | [design/requirements.md](design/requirements.md) |
| Look up a type, field, unit, or invariant | [design/data-model.md](design/data-model.md) |
| See a process drawn | [design/architecture.md](design/architecture.md) |
| Find a slot's signature, a service command, the bundle or ledger format | [design/interfaces.md](design/interfaces.md) |
| Build or change one module | [design/modules/](design/modules/README.md) |
| Know why a choice was made | [design/decisions.md](design/decisions.md) (architecture), [design/api.md §9](design/api.md#9-decisions) (API), [design/specificity.md](design/specificity.md#decisions) (construction) |
| Pick the next refactor task | [design/migration.md](design/migration.md) |
| Know why memory works like a mind, not a search index | [design/cognition.md](design/cognition.md) |
| Know why we don't just use Cognee or Semantica | [design/frameworks.md](design/frameworks.md) |
| Check a model is specific enough (rules R1–R17) | [design/specificity.md](design/specificity.md) |
| Build a company's business construction | [construction/pipeline.md](construction/pipeline.md) (the stages), [construction/README.md](construction/README.md) (the method), then the company's page (local client content, not tracked) |
| Read the math as built, and what is wrong with it | [ml/stack.md](ml/stack.md) |
| See the plan to replace each heuristic (R0–R20) | [ml/roadmap.md](ml/roadmap.md) |
| Brief a colleague on what core needs from us | [briefs/sally-onboarding.md](briefs/sally-onboarding.md) (dated Oct 17) |
| Define a term | [vocab.md](vocab.md) |
| Follow a `§` reference in the code | [archive/plan.md](archive/plan.md) (historical) |

Inside the demo, **How it works** (`H`) explains the model with its flowcharts, the literature review, and the
implementation.

## Folder layout

```text
docs/
  README.md           this map
  vocab.md            every term, defined once
  flowchart.svg       the root README's overview (axelrod flows --svg)
  guides/             running it: demos, gui, cli, ingestion, development, deployment
  api/                README.md (the reference, generated) and openapi.yaml (the contract)
  design/             the design of record: README (front page), requirements, data model, architecture,
                      interfaces, api, core-mcp-auth, specificity, cognition, frameworks, decisions, migration,
                      questions-for-manav-and-zsolt; modules/ (M01–M17); diagrams/ (Mermaid sources and SVGs)
  construction/       the business-construction method, and one page per company
  ml/                 stack.md (the math as built) and roadmap.md (the plan)
  briefs/             dated status briefs for colleagues
  archive/            superseded documents, kept for their references
  media/              videos (gitignored; ask the team)
```

**Where a new page goes.** How to run or use something: `guides/`. Why it is built the way it is: `design/`. A
term: a row in [vocab.md](vocab.md), never a second glossary. A dated status note: `briefs/`. A page something else
replaced: `archive/`, with a line at the top naming its replacement.
