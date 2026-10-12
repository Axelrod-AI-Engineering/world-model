# M19 · Demo

| | |
|---|---|
| Layer | Side: it uses the product; nothing in the product uses it |
| Status | **Split**: `sim/` mixes fixtures, content, and product paths |
| Code today | `sim/world.py` (`SyntheticWorld`, `SyntheticDataFeed`), `sim/scenario.py`, `sim/runner.py` (`ScenarioRunner` with the init cache), `sim/checklist.py`, `sim/imports.py` (`ImportRunner`, which is product), `sim/examples/` (catalog, small, prod, session) |
| Target | `axelrod_wm/demo/`: `world.py`, `scenario.py`, `runner.py` (implements the `Session` protocol from [M17](M17-api-cli.md)), `checklist.py`, `examples/`. `ImportRunner` moves to [M06](M06-intake.md)/[M14](M14-services.md), and the init cache to [M13](M13-runtime.md) `bootstrap.py`. |

## Purpose

The demos and their synthetic world.

- **Small demo:** a blank canvas built by 24 examples.
- **Production demo:** the same examples in the oil-shock world, after three years of synthetic history.
- **Full demo:** the oil-shock scenario, with 53 real actors and ideas and 18 scripted steps.
- **Emily's demo:** a PM's model brought up to date by importing research.

The data stays synthetic. Real names make the graph concrete, but no headline reports a real event and nothing in it is a claim about any company.

## Owns

- `SyntheticWorld` and its truth (`truth.yaml`), the scenario script format (steps can update, pose, evaluate, decide, or edit structure), the oil demo's 17-item checklist.
- The tutorial: `Example` and article models, the small and production catalogs, and `ExampleSession` (a chain with rewind and replay of decisions, plus "more like this").
- Fixture plugins, registered from here only:
  - the source `synthetic_data_feed`;
  - the translator `example`.
- Data: `data/worlds/`, `data/scenarios/`, `data/taxonomy/`; configs `demo.yaml`, `small_demo.yaml`, `emily_demo.yaml`.

## Interface

```python
class DemoSession(Session):                       # M17's protocol
    capabilities = {"examples"} | {"scripted_story"} | {"import"}
    def run_example(self, n_or_id) -> None        # plays 1..n−1 first; rewinds if earlier
    def more_like_this(self, example_id) -> None
    def step(self) / play(self) / pause(self) / reset(self)
```

## Depends on / used by

- Depends on: [M14](M14-services.md), [M13](M13-runtime.md).
- Used by: the CLI demo commands, and the hosted demo.

## Invariants

- **Nothing in layers 0–5 imports `demo/`.**
- **The small demo comes first.** New features are shown and tested in the small demo before the oil demo and its slow tests change.
- **Synthetic data.**

## Done when

- `tests/scenario/test_small_demo.py` (example by example, with rewind), `test_prod_demo.py`, and `test_oil_shock_demo.py` (the checklist) pass.
- The import-graph test shows no edge into `demo/` from below.

User guides: [../../demos.md](../../demos.md).
