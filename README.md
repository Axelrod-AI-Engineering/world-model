# karthik-init-world-model

Repository for development of Karthik's ideal world model! Has an object-oriented instantiation of everything, as well as a simulator to showcase the events!

This is v0 of the **Axelrod World Model**, built from [PLAN.md](PLAN.md). It has two parts:

- **`axelrod_wm`**, a Python package. It holds a causal graph of entities, subentities, and interactions with uncertain effects and timing. A synthetic world feeds it market events. It learns from them, and it forecasts hypothetical theses ("What if oil prices doubled next quarter?").
- **A browser demo** in `web/`. It shows the graph, the review queue, and forecasts, and it animates every step the engine traces.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). uv installs Python 3.12 for you, as pinned in `.python-version`.
- A browser for the demo. d3 v7 is vendored in `web/vendor/`. Google Fonts load when you are online, and system fonts are used when you are not.

## Quick start

```bash
uv sync                                   # create .venv and install the package and dev tools
uv run axelrod demo                       # serve the demo at http://127.0.0.1:8000
```

Open http://127.0.0.1:8000. The first start replays three years of synthetic history to build the initial state (about 30 s), and caches it in `var/oil_shock_demo/`. Later starts take a few seconds. The cache rebuilds by itself when the data, config, or engine code changes.

Inside the demo:

| Do this | To |
|---|---|
| **Step ▶** or `→` | run the next scenario step (17 steps in all) |
| **▶ Play** or `Space` | play until a proposal needs review, or until you pause |
| **Approve** / **Reject** / **Edit** / **Defer** in the review queue (`A` / `R` approve or reject the focused proposal) | decide on structural changes and news. Set **Review** to *auto-approve all* to skip review. |
| **Superentities / Entities / Subentities**, or `1` / `2` / `3`, or zoom | switch between the three zoom levels |
| **Figure 1** / **Gravity** | pin the architecture page's layout, or let the forces run |
| **Draw** or `D` | drag from a subentity, entity, or hull to another to propose an edge |
| **Thesis** tab, **Run** | pose your own thesis; the **Forecast** tab shows fan charts and **Compare with…** overlays two forecasts |
| **Memory ▴** | open the taxonomies, episodes, frontier, explanations, entity memories, and versions |
| timeline scrubber, `Shift+←` / `Shift+→` | open an earlier state version read-only |
| `F` fit, `/` search, `Esc` close | |

The scenario script is in `data/scenarios/oil_shock_demo/scenario.yaml`. Each step's caption appears above the canvas.

## Headless run and checklist

```bash
uv run axelrod run-scenario oil_shock_demo --headless --auto-approve
```

This runs all 17 steps without the browser and prints the scenario checklist from PLAN.md §15.3. It exits non-zero if any item fails. Add `-v` to print each step, and `--until-step N` to stop early.

Other commands (`uv run axelrod --help`):

```bash
uv run axelrod init                       # build and cache the init snapshot only
uv run axelrod thesis oil_shock_demo "What if oil prices doubled next quarter?" --until-step 12
uv run axelrod evaluate oil_shock_demo --freeze-at 2026-01-31 --market-events ME-02 --horizon-days 63
uv run axelrod export-trace <run-id> trace.jsonl   # traces are written to var/axelrod/traces/
uv run axelrod demo --port 8001 --config configs/default.yaml
```

## Tests

```bash
uv run pytest                             # unit, scenario, and API tests (under 2 minutes)
uv run pytest --runslow                   # also: the full checklist run, every shipped slot alternative
                                          # run to the end (§15.2), and the browser smoke test
uv run ruff check src tests
```

The browser smoke test (`tests/ui/`) needs Playwright and Chromium, which are not project dependencies. Without them it is skipped. To run it without installing anything into the project:

```bash
uv run --with playwright pytest tests/ui --runslow
```

(If Chromium is missing, run `uv run --with playwright playwright install chromium` once.)

## Configuration

- `configs/default.yaml` holds every engine setting and the component chosen for each slot (§8.2, §8.16). To swap in an alternative, such as `propagator: deterministic_mean` or `unifier: weighted_mixture`, copy the file, edit `components:`, and pass it with `--config`.
- `configs/demo.yaml` holds the demo's overrides. The scenario applies them on top of the config.
- `data/scenarios/oil_shock_demo/truth.yaml` is the synthetic world's ground truth. Values that were tuned so the checklist passes carry `# DECISION:` comments, as do choices where the plan was silent. Run `grep -rn DECISION src configs data` to list them.

## Layout

```text
src/axelrod_wm/   core/ memory/ events/ ingest/ control/ engine/ evaluation/ sim/ api/ trace.py cli.py
web/              index.html css/ js/{graph,panels,animator,charts}/ vendor/d3.v7.min.js
data/             construction/ taxonomy/ scenarios/oil_shock_demo/
configs/          default.yaml demo.yaml
tests/            unit/ integration/ scenario/ ui/
var/              runtime data: init cache, snapshots, ledger, traces (gitignored)
```

[docs/architecture.md](docs/architecture.md) maps each module to its section of the plan.
