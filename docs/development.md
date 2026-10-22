# Development

How to run the tests, where things are, and the conventions. The repository is a uv workspace of two members, and
each is developed and tested on its own.

<!-- toc -->
**Contents**

- [Setup](#setup)
- [Tests](#tests)
- [Coverage](#coverage)
- [Continuous integration](#continuous-integration)
- [Layout](#layout)
- [Conventions](#conventions)
- [Demo videos](#demo-videos)
<!-- /toc -->

## Setup

You need [uv](https://docs.astral.sh/uv/). It installs Python 3.12, as pinned in `.python-version`.

```bash
uv sync                                # both members, to run the app (the root's dev group names them)
uv sync --all-packages                 # also each member's test tools: what the tests need
uv sync --package axelrod-ingest       # ingestion alone: the world model is not installed
uv run axelrod small_demo              # run a demo (the world model's CLI)
```

## Tests

Each member runs its tests from its own folder, with its own `conftest.py`:

```bash
cd ingestion   && uv run pytest                          # about ten seconds
cd world_model && uv run pytest                          # unit, scenario, and API tests; the slow runs are skipped
cd world_model && uv run pytest tests/unit               # the fast part, for a quick check
cd world_model && uv run pytest -m integration           # the service's end-to-end flows
cd world_model && uv run pytest --runslow                # also the full checklist run, every slot alternative, the browser test
uv run pytest                                            # from the root: the repository's own tests
uv run ruff check . --extend-exclude scripts/video       # lint the workspace
```

[world_model/tests/README.md](../world_model/tests/README.md) describes every world model suite: its count, markers, the
data and extras it needs, the coverage policy, and the design of the service's integration tests. Ingestion's
[README](../ingestion/docs/README.md#running-it) says how its own are run.

| Where | Covers |
|---|---|
| `ingestion/tests/` | `contract/` the bundle and the world view; `ingest/` parsing, chunking, recognition, extraction, determinism, the benchmark; `lake/` the lakehouse and search; `test_boundary.py` that ingestion never imports the world model |
| `world_model/tests/unit` and `integration` | The model, its memory, repository, intake, learning, inference, control, flows, the engine; the demo's API and `/ws` |
| `world_model/tests/service`, `integration/service` | The outward API (`/v1`) and MCP: every route against the OpenAPI schema, every error code, tenancy, idempotency; the end-to-end flows |
| `world_model/tests/scenario`, `ui` | Initialization, determinism, restore, the demos example by example; a Playwright smoke test (slow) |
| `tests/` (the root) | The Railway drift verifier, the coverage gate, and that every link in the Markdown resolves |

**Client data.** Only the world model's tests read it, and only through `skip_without_client(...)`, which skips a test
module with its reason when the client's content is absent. Ingestion's tests never read `data/`.

## Coverage

Every source file of each member is held at **100% lines and 100% branches, by that member's own tests**. There is no
floor to ratchet, no strict list, no pragma, and no omission: an unreachable line is deleted. `scripts/coverage_gate.py`
checks one member at a time, and so can you:

```bash
cd ingestion && uv run pytest --cov --cov-report=json:coverage.json --junitxml=junit.xml
uv run python scripts/coverage_gate.py ingestion/coverage.json --member ingestion --junit ingestion/junit.xml
```

Without client data the world model reaches 100% too: point `WORLD_MODEL_DATA_DIR` at an empty folder to check.

## Continuous integration

`.github/workflows/tests.yml` runs three jobs in parallel on every pull request and on `main`:

| Job | Runs | Takes |
|---|---|---|
| `ingestion` | Installs only `axelrod-ingest`; its tests with coverage; the gate | about 15 minutes |
| `world_model` | Installs both members; the unit tests first, then the full suite with coverage; the gate | up to 150 minutes |
| `repo` | `ruff`, the root tests, and the checks of the table of contents and the diagrams | a few minutes |

## Layout

```text
pyproject.toml, uv.lock   the workspace root (virtual): members, shared lint settings
ingestion/                axelrod-ingest: src/axelrod_ingest, tests, scripts, docs
world_model/              axelrod-world-model: src/axelrod_wm, tests, examples, taxonomy, configs, web, skills, scripts, docs
docs/                     this front door: architecture, reading order, decisions, the ML stack, deployment, development
configs/                  stage settings (world_model*.toml), read by axelrod_wm/settings.py
tests/, scripts/          the repository's own tests; the coverage gate, the docs tools, the Railway checks, video/
data/, feedback/, var/    local and gitignored: client content, meeting notes, runtime data
integrations/core/        the proposed patch to core's MCP server
.railway/, Dockerfile     the hosted deployment
```

[../world_model/docs/design/](../world_model/docs/design/README.md) maps each module to its package; each [module spec](../world_model/docs/design/modules/README.md) lists the files it holds today.

## Conventions

- **Where paths come from.** `axelrod_wm/paths.py` is the one source of the repository's roots (`REPO_ROOT`, `WM_ROOT`,
  and `AXELROD_ROOT` for an installed copy); `world_model/tests/where.py` names the tests' inputs. No code or test reads a
  path relative to the working directory.
- **The boundary.** Ingestion never imports the world model; the contract between them is `axelrod_ingest.contract`
  ([the contract](../ingestion/docs/contract.md)). The service's ingestion routes (`routes_ingest.py`) import only ingestion and the v1 plumbing.
- **The front end has no build step.** It is plain HTML, CSS, and ES modules, with d3 v7 vendored in `world_model/web/vendor/`. It never computes model results: it renders the server's views and replays trace events.
- **Decisions.** Where [the original plan](../world_model/docs/archive/plan.md) was silent, the simplest option was chosen and marked `# DECISION:`. `grep -rn DECISION world_model/src world_model/configs world_model/web` lists them.
- **§ references** in the code point to sections of [the original plan](../world_model/docs/archive/plan.md). The code has moved past it in places; where they differ, the code and these docs are current.
- **The flowchart picture is checked.** After changing `world_model/src/axelrod_wm/flows/`, run `uv run axelrod flows --svg docs/flowchart.svg`; a test fails while it is stale.
- **Diagrams.** The design's diagrams are SVGs rendered from Mermaid sources in `world_model/docs/design/diagrams/*.mmd`, in the app's palette: mark nodes with classes (`:::start`, `:::check`, `:::store`, `:::wm`, `:::ltm`, `:::inf`, `:::opt`) and the happy path with `==>`, declared first. Run `uv run --with playwright python scripts/docs/diagrams.py` after editing a source; `--check` fails while an SVG is stale.
- **Contents.** Every document starts with a table of contents between `<!-- toc -->` markers; `uv run python scripts/docs/toc.py` writes them and `--check` fails while one is stale.
- **Links.** `uv run python scripts/docs/links.py` lists every relative link or section that does not resolve; the root tests run it.
- **Data stays synthetic.** Real names make the graph concrete, but no headline reports a real event and nothing is a claim about any company. Client content lives only in the gitignored `data/` (and, hosted, on the volume).

## Demo videos

`docs/media/` holds the videos and their voiceovers locally; it is gitignored, so ask the team for the files. [scripts/video/README.md](../scripts/video/README.md) explains how they were recorded and edited.
