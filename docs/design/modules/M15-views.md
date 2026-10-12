# M15 · Views

| | |
|---|---|
| Layer | 5 · Interfaces |
| Status | **Split out**: read models are spread across `api/` and `control/` |
| Code today | `api/views.py` (924 lines), `api/brief.py`, `api/find.py`, `api/checks.py`; `control/stage.py` (`_review`, `_lessons`, the staged graph); `memory/open_world.py`; view logic in `api/routes.py` (`_config`, `_grid_view`, `_proposal_after`) |
| Target | `axelrod_wm/views/`: `graph.py`, `entity.py`, `staged_review.py`, `forecast.py`, `brief.py`, `grid.py`, `find.py`, `checks.py`, `memory.py`, `history.py`, `open_world.py`, `provenance.py` (new) |

## Purpose

Read models: pure functions from state and service records to DTOs. The web app, the API, and the context layer all render these. The front end never computes model results, and neither does any adapter.

## Owns

| View | Input → output |
|---|---|
| `graph_view(wm, ltm, version, detail)` | nodes (entities, subentities, superentity outlines and cards), interactions, open nodes, layout hints |
| `staged_review_view(staged)` | grouped by stage (Intake, WM, LTM, Your review): the article with phrases marked, each change with its checkbox and dependencies, pending ends, the ripple by order with paths, recall, lessons, conflicts |
| `forecast_view(forecast)`, `brief_view(forecast)` | values by order and path, groups, binding constraints, and a written brief |
| `grid_view(source, method, outputs)` | the transmission grid: input, each order, output |
| `find(query, filters, hops)` | semantic search and filters over entities, values, interactions, and superentities; widens one or two hops |
| `checks_view(wm, ltm)` | what is being tested now (fuzzy ends, co-movements, candidate superentities), with progress toward each bound; when each kind of check runs and what it updates |
| `memory_view(ltm, tab)` | the five long-term memory tabs |
| `open_node(item)` | the share of a value's movement its interactions do not explain, or a kind's reserve for one not seen yet |
| `history_view` | log, show, diff |
| `provenance_view(item_id, version)` (new) | the lineage of a value or interaction: change sets → proposal → review decision → evidence → market event → source |

## Interface

```python
# every view: (state, records, params) -> pydantic DTO; no writes, no trace emission
def graph_view(wm, ltm, *, version: int, detail: Detail) -> GraphDTO
def staged_review_view(staged: StagedChange, wm, ltm) -> StagedReviewDTO
...
```

## Depends on / used by

- Depends on: [M03](M03-model.md), [M04](M04-memory.md), [M05](M05-repo.md) (history, records), [M07](M07-shared-read.md) (grid), and service records from [M14](M14-services.md).
- Used by: [M16](M16-context-layer.md), [M17](M17-api-cli.md).

## Invariants

- **Pure.** A view never writes state, never emits a trace, and never calls a slot.
- **Names are consistent.** Every view names items the same way (`web/js/names.js` mirrors it).
- **Canonical terms in labels** ([glossary.md](../glossary.md)).

## Done when

- Snapshot tests for each DTO on the small demo after examples 4, 15, and 24.
- `views/` imports nothing from `api/`, and no module below layer 5 imports `views/`.
