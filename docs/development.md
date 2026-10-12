# Development

## Tests

```bash
uv run pytest                              # unit, scenario, and API tests
uv run pytest --runslow                    # also the full checklist run, every slot alternative, and the browser smoke test
uv run ruff check src tests
uv run --with playwright pytest tests/ui --runslow   # the smoke test alone (run `playwright install chromium` once)
```

[architecture.md](architecture.md#tests) says what each test directory covers.

## Layout

```text
src/axelrod_wm/   model/ memory/ events/ repo/ intake/ shared/ dynamics/ learning/ inference/ engine/
                  control/ flows/ evaluation/ sim/ api/ trace.py cli.py
web/              index.html literature.md implementation.html css/ js/{graph,panels,animator,charts}/ vendor/
data/             worlds/{economy,small_demo}/ taxonomy/ scenarios/{oil_shock_demo,small_demo,prod_demo}/
configs/          default.yaml demo.yaml small_demo.yaml
tests/            unit/ integration/ scenario/ ui/
docs/             this documentation, flowchart.svg, media/
scripts/          start-railway.sh, the Railway release checks, video/
.railway/         railway.ts: the Railway infrastructure as code
Dockerfile        the image Railway builds
var/              runtime data: init caches, sessions, snapshots, ledger, traces (gitignored)
```

[architecture.md](architecture.md) maps each package and front-end file to what it does.

## Conventions

- **The front end has no build step.** It is plain HTML, CSS, and ES modules, with d3 v7 vendored in `web/vendor/`. It never computes model results: it renders the server's views and replays trace events.
- **Decisions.** Where [archive/plan.md](archive/plan.md) was silent, the simplest option was chosen and marked `# DECISION:`. `grep -rn DECISION src configs data web` lists them.
- **§ references** in the code point to sections of [archive/plan.md](archive/plan.md), the original specification. The code has moved past it in places; where they differ, the code and these docs are current.
- **The flowchart picture is checked.** After changing `flows/`, run `uv run axelrod flows --svg docs/flowchart.svg`; a test fails while it is stale.
- **Data stays synthetic.** Real names make the graph concrete, but no headline reports a real event and nothing is a claim about any company.

## Demo videos

`docs/media/` holds the videos and their voiceovers locally; it is gitignored, so ask the team for the files. [scripts/video/README.md](../scripts/video/README.md) explains how they were recorded and edited.
