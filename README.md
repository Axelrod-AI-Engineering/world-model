# Axelrod World Model

[![Tests](https://github.com/Axelrod-AI-Engineering/world-model/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Axelrod-AI-Engineering/world-model/actions/workflows/tests.yml)

The **Axelrod World Model**, v0. It is one causal world model of the economy, built like version control:

<!-- toc -->
**Contents**

- [Quick start](#quick-start)
- [Hosted demo](#hosted-demo)
- [API](#api)
- [Tests](#tests)
- [Documentation](#documentation)
<!-- /toc -->

- **Backend users** teach it (the Learn view). Each event's learning runs on a staged copy, first working memory and then long-term memory. A person checks everything it would commit, down to the second- and third-order ripple. They keep what makes sense, and only that is committed.
- **Everyone else** only asks it (the Predict view). A thesis runs on a branch of a committed version that is never merged.

![Overview: learning, inference, and the architecture](docs/flowchart.svg)

The repository has two parts:

- **`axelrod_wm`**, a Python package. It holds a causal graph of actors in an environment of actors:
  - **entities**: companies, agencies, and the economic ideas they act in;
  - **subentities**: each entity's values;
  - **interactions**: causal relations with uncertain effects and timing;
  - **superentities**: schemas such as sectors, rivalries, and shocks.
- **A browser demo** in `web/`. It runs locally, and a shared copy is hosted on Railway (see [Hosted demo](#hosted-demo)).

**All news, data, and numbers are synthetic.** Real company and agency names make the graph concrete. No headline reports a real event, and nothing in it is a claim about any company. The Fed chair is a role, not a person.

## Quick start

You need [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). It installs Python 3.12, as pinned in `.python-version`.

```bash
uv sync
uv run axelrod small_demo          # a blank canvas, built one example at a time: http://127.0.0.1:8765
uv run axelrod prod_demo ripple    # the same examples in the oil-shock world
uv run axelrod demo --port 8765    # the full scripted oil-shock demo (the one the hosted demo runs)
uv run pytest                      # the tests
```

The production and full demos replay three years of synthetic history the first time they start (about two and a half minutes) and cache it in `var/`. Later starts take seconds.

## Hosted demo

The full demo runs on Railway's `dev` environment at **https://world-model-dev.up.railway.app**, behind Basic Auth. Ask the team for the credentials. Everyone who opens it shares one session, so a review approved there is approved for everyone. [docs/deployment.md](docs/deployment.md) covers the infrastructure, the release runbook, and the checks.

## API

The world model is also a service: REST under `/api/world-model` and MCP tools at `/mcp`, on the same deploy, with an API key per caller. Upload research (PDF, Office, HTML, CSV, text), read it into proposed graph updates, import them through review, search everything ingested, read the model at any past version, and pose forecasts. See [docs/api.md](docs/api.md) and, for how a file becomes graph updates, [docs/ingestion.md](docs/ingestion.md).

## Tests

The badge above is the CI run on `main`. The table is the last full run (`scripts/coverage_gate.py`): tests per suite, and line and branch coverage per package. CI fails if a strict module loses a line or branch of coverage, or if the repository falls below its floor.

<!-- tests:start -->

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| ✅ `tests/ingest` | 270 | 0 | 0 |
| ✅ `tests/integration` | 50 | 0 | 12 |
| ✅ `tests/lake` | 146 | 0 | 0 |
| ✅ `tests/scenario` | 20 | 0 | 2 |
| ✅ `tests/service` | 77 | 0 | 0 |
| ✅ `tests/ui` | 0 | 0 | 2 |
| ✅ `tests/unit` | 244 | 0 | 0 |

| Package | Lines | Branches | Gate |
|---|---:|---:|---|
| `(top level)` | 33.5% | 22.6% | ratchet |
| `api` | 87.5% | 76.7% | 100% for service, mcp, keys; ratchet |
| `context` | 93.8% | 86.5% | ratchet |
| `control` | 86.3% | 73.7% | ratchet |
| `dynamics` | 89.4% | 77.8% | ratchet |
| `engine` | 94.2% | 80.7% | ratchet |
| `evaluation` | 23.4% | 0.0% | ratchet |
| `events` | 97.5% | 75.0% | ratchet |
| `flows` | 98.9% | 90.5% | ratchet |
| `inference` | 93.8% | 83.3% | ratchet |
| `ingest` | 100.0% | 100.0% | 100% required |
| `intake` | 90.5% | 78.4% | ratchet |
| `lake` | 100.0% | 100.0% | 100% required |
| `learning` | 97.3% | 90.5% | ratchet |
| `memory` | 97.1% | 89.6% | ratchet |
| `model` | 92.2% | 71.0% | ratchet |
| `repo` | 96.0% | 89.0% | ratchet |
| `shared` | 92.9% | 83.7% | ratchet |
| `sim` | 76.1% | 62.3% | ratchet |
| **all** | **88.9%** | **78.7%** | floor in `coverage-floor.json` |

Slow scenario runs (`--runslow`) are not in these numbers. Regenerate with `scripts/coverage_gate.py` (see its docstring).

<!-- tests:end -->

## Documentation

| Read | For |
|---|---|
| [docs/design/README.md](docs/design/README.md) | **The design**: the architecture, 17 modules with specs, diagrams, the cognitive framings, Cognee vs Semantica, decisions, and the migration plan |
| [docs/demos.md](docs/demos.md) | The five demos, the 24 examples, and how the review works |
| [docs/interface.md](docs/interface.md) | A tour of the interface: the top bar, the canvas, the panels, and every shortcut |
| [docs/cli.md](docs/cli.md) | The command line and configuration |
| [docs/ml-stack.md](docs/ml-stack.md) | The ML stack as built, stated formally, with its adversarial review |
| [docs/ml-roadmap.md](docs/ml-roadmap.md) | The plan to replace each heuristic with a method we can defend |
| [docs/api.md](docs/api.md) | The outward API and MCP server: auth, routes, errors, and mounting it from core |
| [docs/ingestion.md](docs/ingestion.md) | The ingestion pipeline and the lakehouse: parsing, extraction, event time, determinism, search |
| [docs/deployment.md](docs/deployment.md) | The Railway dev deployment, sign-in, and running the container locally |
| [docs/development.md](docs/development.md) | Tests, the repository layout, conventions, and the demo videos |
| [docs/archive/plan.md](docs/archive/plan.md) | The original specification (historical), which the code's § references point to |

Inside the demo, **How it works** (`H`) explains the model itself: the five stages of learning and the seven of inference, each with its flowchart; the literature review; and the implementation.

Videos (a two-minute devlog, a one-minute tour of learning, and the external trailer of Emily's demo) are kept out of the repository: ask the team for them. Locally they go in `docs/media/`, which is gitignored, and [scripts/video](scripts/video/README.md) records and cuts them.
