# Development

<!-- toc -->
**Contents**

- [Tests](#tests)
- [Layout](#layout)
- [Conventions](#conventions)
- [Demo videos](#demo-videos)
<!-- /toc -->

## Tests

[tests/README.md](../../tests/README.md) describes every suite, its count, markers, the data and extras it needs, the
coverage policy, and the design of the service's integration tests.

```bash
uv run pytest                              # unit, scenario, and API tests
uv run pytest -m integration               # the service's end-to-end flows (tests/integration/service)
uv run pytest --runslow                    # also the full checklist run, every slot alternative, and the browser smoke test
uv run ruff check src tests
uv run --with playwright pytest tests/ui --runslow   # the smoke test alone (run `playwright install chromium` once)
```

| Directory | Covers |
|---|---|
| `tests/unit/model`, `repo`, `intake`, `shared`, `dynamics`, `learning`, `inference`, `control` | Each package's units. This includes the two-process commit order, retirement, and review. |
| `tests/unit/flows`, `tests/unit/engine` | The flowchart is well formed and current in `docs/flowchart.svg`; its trace kinds exist; every registry slot has a contract |
| `tests/integration/` | The demo's API and `/ws`, including update runs, staged review and selective approval, the examples and the library, the log, and structure edits; every slot alternative (slow) |
| `tests/integration/service/` | The outward service end to end (marked `integration`): upload → review → pinned read, the same over MCP, forecast coverage, restart, export → re-import, tenancy, concurrent updates |
| `tests/service/` | The outward API (`/v1`) and MCP: every route's shape against the OpenAPI schema, every error code, bounds, pinning, tenancy, idempotency, conventions |
| `tests/ingest/`, `tests/lake/` | The ingestion pipeline and the lakehouse (strict: 100% line and branch) |
| `tests/scenario/` | Initialization, determinism, restore; the full oil-demo checklist (slow); the small demo, example by example, with rewind; the production demo (slow) |
| `tests/ui/` | A Playwright smoke test (slow; skipped without Playwright) |
| `tests/unit/test_basic_auth.py`, `test_railway_drift.py` | The auth middleware; the Railway drift verifier rejects unrelated and destructive changes |

## Layout

```text
src/axelrod_wm/   model/ memory/ events/ repo/ intake/ shared/ dynamics/ learning/ inference/ engine/
                  control/ flows/ evaluation/ sim/ api/ trace.py cli.py
web/              index.html literature.md implementation.html css/ js/{graph,panels,animator,charts}/ vendor/
data/             worlds/{economy,small_demo}/ taxonomy/ scenarios/{oil_shock_demo,small_demo,prod_demo}/
configs/          default.yaml demo.yaml small_demo.yaml
tests/            unit/ integration/ service/ ingest/ lake/ scenario/ ui/ (tests/README.md)
docs/             guides/ api/ design/ ml/ construction/ briefs/ archive/ (map: docs/README.md), flowchart.svg, media/
scripts/          start-railway.sh, the Railway release checks, video/
.railway/         railway.ts: the Railway infrastructure as code
Dockerfile        the image Railway builds
var/              runtime data: init caches, sessions, snapshots, ledger, traces (gitignored)
```

[../design/](../design/README.md) maps each module to its package; each [module spec](../design/modules/README.md) lists the files it holds today.

## Conventions

- **The front end has no build step.** It is plain HTML, CSS, and ES modules, with d3 v7 vendored in `web/vendor/`. It never computes model results: it renders the server's views and replays trace events.
- **Decisions.** Where [../archive/plan.md](../archive/plan.md) was silent, the simplest option was chosen and marked `# DECISION:`. `grep -rn DECISION src configs data web` lists them.
- **§ references** in the code point to sections of [../archive/plan.md](../archive/plan.md), the original specification. The code has moved past it in places; where they differ, the code and these docs are current.
- **The flowchart picture is checked.** After changing `flows/`, run `uv run axelrod flows --svg docs/flowchart.svg`; a test fails while it is stale.
- **Diagrams.** The design's diagrams are SVGs rendered from Mermaid sources in `docs/design/diagrams/*.mmd`, in the app's palette: mark nodes with classes (`:::start`, `:::check`, `:::store`, `:::wm`, `:::ltm`, `:::inf`, `:::opt`) and the happy path with `==>`, declared first. Run `uv run --with playwright python scripts/docs/diagrams.py` after editing a source; `--check` fails while an SVG is stale.
- **Contents.** Every document starts with a table of contents between `<!-- toc -->` markers; `uv run python scripts/docs/toc.py` writes them and `--check` fails while one is stale.
- **Data stays synthetic.** Real names make the graph concrete, but no headline reports a real event and nothing is a claim about any company.

## Demo videos

`docs/media/` holds the videos and their voiceovers locally; it is gitignored, so ask the team for the files. [scripts/video/README.md](../../scripts/video/README.md) explains how they were recorded and edited.
