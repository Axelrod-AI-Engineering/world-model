# karthik-init-world-model

Repository for development of Karthik's ideal world model! Has an object-oriented instantiation of everything, as well as a simulator to showcase the events!

This is v0 of the **Axelrod World Model**, built from [PLAN.md](PLAN.md) (revision 2). It has two parts:

- **`axelrod_wm`**, a Python package. It holds a causal graph of the economy as **actors in an environment of actors**: 48 entities, from real companies and agencies (NVIDIA, AMD, TSMC, Samsung, ASML, Tokyo Electron, Microsoft, OPEC+, Saudi Aramco, ExxonMobil, Delta, United, JPMorgan, US regional banks, the Fed, the ECB, US Commerce, China's commerce ministry) to the economic ideas they act in (oil, inflation, credit, trade, confidence…), each tagged with one of eight categories (spending and demand, money and finance, supply and capacity, distribution, deep foundations, environment, expectations, shocks). An entity's attributes are its **subentities** (a firm's revenue, capex, market share, share price), and links between entities carry uncertain effects and timing. **Superentities** group entities that move together: sectors (oil producers, airlines), supply chains (the AI chip chain), rivalries (NVIDIA and AMD, TSMC and Samsung, US–China tech), and macro patterns (credit tightening, an energy price shock); they can nest. The model keeps a daily state. **Update runs** collect news and data up to a date and fold them in one day at a time; between observations, daily propagation carries moves through the graph. The model learns new links and new superentities, and it forecasts hypothetical theses ("What if OPEC cuts output by 10%?") for single values and for whole actors, sectors, superentities, and categories.
- **A browser demo** in `web/`. It shows the graph, one line of story per step, and opens detail only where you look: hover to see what something is, click to inspect it, double-click or right-click to open entities into subentities and to open or close superentities. A **walkthrough** steps through what the model did with any piece of news (from fuzzy ops to real graph updates) or any question (from networks to scenarios to the forecast).

**All news, data, and numbers in the demo are synthetic.** Real company and agency names make the graph concrete; no headline reports a real event, and nothing in it is a claim about any company. The Fed chair is a role, not a person.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). uv installs Python 3.12 for you, as pinned in `.python-version`.
- A browser for the demo. d3 v7 is vendored in `web/vendor/`. Google Fonts load when you are online, and system fonts are used when you are not.

## Quick start

```bash
uv sync                                   # create .venv and install the package and dev tools
uv run axelrod demo                       # serve the demo at http://127.0.0.1:8000
```

Open http://127.0.0.1:8000. The first start replays three years of synthetic daily history to build the initial state (about a minute and a half) and caches it in `var/oil_shock_demo/`. Later starts take a few seconds. The cache rebuilds by itself when the data, config, or engine code changes.

The first screen is the graph: each pill is an entity with its category code, shaded regions are superentities, and S10 is a superentity made of two others. An entity that two superentities share wears a colored stripe for each owner, and where two outlines overlap the shared part is striped in both colors; close one of them into a card and the card lists its members as chips, with a dashed tether from each shared one to where it is still drawn. Then:

| Do this | To |
|---|---|
| Hover anything | see what it is, in one plain sentence, and how it is moving |
| Click | inspect it in the side panel |
| Double-click an entity | open it into its subentities (double-click again to close) |
| Double-click a superentity's tab or region | close it into one card; double-click the card to open it |
| Right-click anything | every option: open or close a superentity or its parts, show subentities, ask "what if it moves?", **forecast it**, walk through the latest news about it |
| **Superentities / Entities / Subentities**, or `1` / `2` / `3` | close every superentity, open every superentity, or open every entity at once |
| Scroll, `+` / `−`, `F` | zoom and fit. Zoom never changes what is open. |
| **Update** or `U` | read news and data up to a date; the run pauses when something needs your review |
| **Step ▸** or `→`, **Play** or `Space` | follow the scripted demo (18 steps; its captions explain each idea) |
| **News**, **Review** (`A` / `R` approve or reject) | the market events by update and day; the proposals that wait for you |
| **Ask** or `Q` | pose a what-if, and pick what to forecast as chips: any value, actor, idea, sector, superentity, or category. The Forecast tab shows progress while it runs, and the first time, a small raccoon walks you through what the model is doing on the canvas (Admin › Settings › The guide: first time, every time, or off) |
| **Briefs** or `B` | a written brief of each forecast, opened after you ask: the bottom line, what moves and when, who is affected, why, the news that shaped it and the news since, how it is tracking, what to watch. Select any text in it to ask about it (a mock-up: chat is not implemented yet) |
| the **Forecast** tab | actors, sectors, superentities, and categories first (their average effect, its distribution at the horizon, the members that move most), then single values as small cards that open into a full chart; scenarios and the paths that explain them |
| **How it learned ▸** / **How it forecast ▸** in the caption, `W`, or **Walk through** in News, Inspect, and Forecast | step through the model's work with `←` / `→`: the news, its fuzzy ops narrowing to real subentities, review, parse, classify, recall, the expected ripple, the fold; or for a question, the isolated networks, day-by-day propagation (with a scrubber), coupling, scenarios, the forecast, and why |
| `Ctrl-Z` / `Ctrl-Y` (`⌘Z` / `⇧⌘Z`) | undo and redo a view change: opening, closing, moving, presets, layout |
| **Memory** | long-term memory: object and interaction generalizations, entity memories, the correlation frontier, prior states |
| **Draw** or `D` | drag from a subentity, entity, or superentity to another to propose an edge |
| the timeline, `Shift+←` / `Shift+→` | open an earlier state version read-only |
| **Admin** or `,` | a small window that starts minimized: Story (every scripted step, with walkthroughs), Map (the eight categories, superentities by kind, actors, the key of symbols), View, and Settings. Drag it, minimize it, or pop it out into its own window |
| **Methods** | a technical briefing on the proposed implementation and ML stack, grounded in the cognitive science of concept formation (also at `/methods.html`) |
| `/` or `Ctrl-K` search, `Esc` close, `?` every shortcut | |

The scenario script is in `data/scenarios/oil_shock_demo/scenario.yaml`. Each step's caption appears above the canvas.

## The model from the command line

```bash
uv run axelrod init oil_shock_demo                          # build the init snapshot; start a session in var/axelrod
uv run axelrod update --until 2026-02-02 --auto-approve     # fold news and data through Feb 2 into that session
```

`update` collects from the configured sources (the mock web scraper and the synthetic data feed) and prints the update report. Without `--auto-approve`, anything that needs review is deferred, and it can still be approved later. `--event news.json` adds a news item of your own (a JSON object with `headline` and optionally `body`, `kind`, and `published_at`), and `--draw edit.json` attaches a drawn model edit (a `GraphUpdateEvent`).

## Headless run and checklist

```bash
uv run axelrod run-scenario oil_shock_demo --headless --auto-approve
```

This runs all 18 steps without the browser and prints the scenario checklist from PLAN.md §15.3. It exits non-zero if any item fails. Add `-v` to print each step, and `--until-step N` to stop early.

Other commands (`uv run axelrod --help`):

```bash
uv run axelrod thesis oil_shock_demo "What if oil prices doubled next quarter?" --until-step 12
uv run axelrod evaluate oil_shock_demo --freeze-at 2026-01-31 --market-events ME-02 --horizon-days 63
uv run axelrod export-trace <run-id> trace.jsonl   # traces are written to var/axelrod/traces/
uv run axelrod demo --port 8001 --config configs/default.yaml
```

## Tests

```bash
uv run pytest                             # unit, scenario, and API tests
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
- `data/construction/` is the graph: entities (each with a one-line description), interactions, and translation templates. The actors and their links are tagged `demo_addition`. `data/scenarios/oil_shock_demo/` holds the seeded superentities (including the nested S10 and the actor groups S11 to S17), the Figure 1 layout, the market events, and `truth.yaml`, the synthetic world's ground truth.
- Values tuned so the checklist passes carry `# DECISION:` comments, as do choices where the plan was silent. Run `grep -rn DECISION src configs data web` to list them.

## Layout

```text
src/axelrod_wm/   core/ memory/ events/ ingest/ control/ engine/ evaluation/ sim/ api/ trace.py cli.py
web/              index.html css/ js/{graph,panels,animator,charts}/ vendor/d3.v7.min.js
data/             construction/ taxonomy/ scenarios/oil_shock_demo/
configs/          default.yaml demo.yaml
tests/            unit/ integration/ scenario/ ui/
var/              runtime data: init cache, sessions, snapshots, ledger, traces (gitignored)
```

[docs/architecture.md](docs/architecture.md) maps each module to its section of the plan.

## Railway deployment

See [.railway/README.md](.railway/README.md) for the dev infrastructure, deployment,
persistent storage, and validation workflow.
