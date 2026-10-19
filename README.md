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

The full demo runs on Railway's `dev` environment at **https://world-model-dev.up.railway.app**, behind a sign-in page. Ask the team for the credentials. Everyone who opens it shares one session, so a review approved there is approved for everyone. [docs/guides/deployment.md](docs/guides/deployment.md) covers the infrastructure, the release runbook, and the checks.

## API

The world model is also a service: REST under `/v1/world-models/{id}` (contract: [docs/api/openapi.yaml](docs/api/openapi.yaml)) and MCP tools at `/mcp`, on the same deploy, with core-minted service tokens or scoped keys. Upload research (PDF, Office, HTML, CSV, text), read it into proposed graph updates, import them through review, search everything ingested, read the model at any past version, and pose forecasts. Each entity's attributes (`toyota.operating_profit`) are nested in the entity. See [docs/api/](docs/api/README.md) and, for how a file becomes graph updates, [docs/guides/ingestion.md](docs/guides/ingestion.md).

## Tests

The badge above is the CI run on `main`. The table is the last full run (`scripts/coverage_gate.py`): tests per suite, and line and branch coverage per package. CI fails if a strict module loses a line or branch of coverage, or if the repository falls below its floor. [tests/README.md](tests/README.md) describes every suite, how to run it, what needs local data or extras, and the design of the service's integration tests.

<!-- tests:start -->

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| ✅ `tests/ingest` | 582 | 0 | 0 |
| ✅ `tests/integration` | 111 | 0 | 12 |
| ✅ `tests/lake` | 146 | 0 | 0 |
| ✅ `tests/scenario` | 75 | 0 | 2 |
| ✅ `tests/service` | 84 | 0 | 0 |
| ✅ `tests/ui` | 0 | 0 | 3 |
| ✅ `tests/unit` | 1012 | 0 | 0 |

| Package | Lines | Branches | Gate |
|---|---:|---:|---|
| `(top level)` | 100.0% | 100.0% | ratchet |
| `api` | 100.0% | 100.0% | 100% for service, mcp, keys; ratchet |
| `context` | 100.0% | 100.0% | ratchet |
| `control` | 100.0% | 100.0% | ratchet |
| `dynamics` | 100.0% | 100.0% | ratchet |
| `engine` | 100.0% | 100.0% | ratchet |
| `evaluation` | 100.0% | 100.0% | ratchet |
| `events` | 100.0% | 100.0% | ratchet |
| `flows` | 100.0% | 100.0% | ratchet |
| `inference` | 100.0% | 100.0% | ratchet |
| `ingest` | 100.0% | 100.0% | 100% required |
| `intake` | 100.0% | 100.0% | ratchet |
| `lake` | 100.0% | 100.0% | 100% required |
| `learning` | 100.0% | 100.0% | ratchet |
| `memory` | 100.0% | 100.0% | ratchet |
| `model` | 100.0% | 100.0% | ratchet |
| `repo` | 100.0% | 100.0% | ratchet |
| `shared` | 100.0% | 100.0% | ratchet |
| `sim` | 100.0% | 100.0% | ratchet |
| **all** | **100.0%** | **100.0%** | floor in `coverage-floor.json` |

Slow scenario runs (`--runslow`) are not in these numbers. Regenerate with `scripts/coverage_gate.py` (see its docstring).

<!-- tests:end -->

## Documentation

[docs/README.md](docs/README.md) is the map: where to go for each kind of question. The usual first stops:

| Read | For |
|---|---|
| [docs/guides/](docs/README.md#where-to-go-for) | Running it: the demos, the interface, the CLI, ingestion, development, deployment |
| [docs/api/](docs/api/README.md) | The outward API and MCP server: auth, routes, errors, and mounting it from core |
| [docs/design/README.md](docs/design/README.md) | **The design**: architecture, data model, 17 module specs, diagrams, decisions |
| [docs/vocab.md](docs/vocab.md) | Every term, defined once |

Inside the demo, **How it works** (`H`) explains the model itself: the five stages of learning and the seven of inference, each with its flowchart; the literature review; and the implementation.

Videos (a two-minute devlog, a one-minute tour of learning, and the external trailer of Emily's demo) are kept out of the repository: ask the team for them. Locally they go in `docs/media/`, which is gitignored, and [scripts/video](scripts/video/README.md) records and cuts them.
