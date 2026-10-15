# Documentation

Read as deep as you need. Start with the design's front page; each level links to the next.

<!-- toc -->
<!-- /toc -->

| Level | Page | For |
|---|---|---|
| 1 | [design/README.md](design/README.md) | The design front page: problem, audience, scope, principles (P0–P3), requirements, the system at a glance, the dependency graph, components, infrastructure |
| 2 | [design/requirements.md](design/requirements.md) | User stories from a PM's workflow; measured limits today; next-horizon targets |
| 2 | [design/data-model.md](design/data-model.md) | Every type and its fields, the units, the invariants |
| 2 | [design/interfaces.md](design/interfaces.md) | Slots, service commands, REST and `/ws`, context verbs, the import bundle, the ledger, traces |
| 2 | [design/architecture.md](design/architecture.md) | The pictures: at a glance, the dependency graph, components, learning's five stages, inference's seven, the day loop, the ledger, infrastructure |
| 2 | [design/cognition.md](design/cognition.md) | The cognitive framings behind memory and recall, and why they beat standard search |
| 2 | [design/frameworks.md](design/frameworks.md) | Cognee and Semantica: what we borrow, and why the core is ours |
| 3 | [design/modules/](design/modules/README.md) | One spec per module, with its own detail diagrams; each ready to hand to an engineer or a coding agent |
| 3 | [design/decisions.md](design/decisions.md), [design/glossary.md](design/glossary.md), [design/migration.md](design/migration.md) | Decisions and settled conflicts; terms; the refactor as ordered tasks |
| 4 | [ml-stack.md](ml-stack.md), [ml-roadmap.md](ml-roadmap.md) | The math as built, with its adversarial review; the plan R0–R19 |

## Using and running it

| Page | For |
|---|---|
| [demos.md](demos.md) | The five demos, the 24 examples, and how the review works |
| [interface.md](interface.md) | A tour of the interface and every shortcut |
| [cli.md](cli.md) | The command line, configuration, and environment variables |
| [development.md](development.md) | Tests, the repository layout, and conventions |
| [deployment.md](deployment.md) | The Railway dev deployment, sign-in, and the container |
| [flowchart.svg](flowchart.svg) | The README's overview: learning, inference, and the architecture (`axelrod flows --svg`) |
| [media/](media/) | The video plans |
| [archive/plan.md](archive/plan.md) | The original specification (historical); the code's § references point here |

Inside the demo, **How it works** (`H`) explains the model with its flowcharts, the literature review, and the implementation.
