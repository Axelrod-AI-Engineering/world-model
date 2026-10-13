# M14 · Views, API, and CLI

**Layer** 5 · **Package** `views/`, `api/`, `cli.py` · **Status** views are gathered from `api/` and `control/`; the API is thinned.

**Code today:**
- `api/views.py` (924 lines), `brief.py`, `find.py`, `checks.py`;
- the view half of `control/stage.py`;
- `memory/open_world.py`;
- `api/app.py`, `routes.py` (1,330 lines, 79 routes), `ws.py`, `auth.py`;
- `cli.py`.

## Purpose

- **Views** are read models: pure functions from state and records to DTOs.
- **The API and CLI** are adapters. They parse a request, call a service or a view, and serialize the result.

Neither computes model results, and neither holds business logic.

## Owns

| View | Gives |
|---|---|
| `graph_view` | Nodes (entities, subentities, superentity outlines and cards), interactions, open nodes |
| `staged_review_view` | Grouped by Intake · WM · LTM · Your review: the article with phrases marked, each change with its checkbox and dependencies, pending ends, the ripple by order, recall, lessons, conflicts |
| `forecast_view`, `brief_view`, `grid_view` | Values by order and path, groups, binding constraints, a brief, the transmission grid |
| `find`, `checks_view`, `memory_view` (five tabs), `history_view`, `open_node` | Search and filters; what is being tested; long-term memory; log, show, diff; what the graph doesn't explain |
| **new** `provenance_view` | A value's lineage: change sets → proposal → review → evidence → market event → source |

**API.** Routes are grouped one file per group: state, entities, proposals, theses, updates, structure, examples, import, repo, trace, and context (new). They are adapters over services and views.
- `/ws` replays traces since `since_seq`, then streams them live.
- **Auth:** an HMAC session cookie; `/api/health` is open; there is one engine per login ([../../deployment.md](../../deployment.md)).
- **New `Session` protocol:** services, views, tracer, lock, and `capabilities` (examples, import, scripted_story). It replaces today's `hasattr(runner, …)` probes.

**CLI.** The commands are in [../../cli.md](../../cli.md). New: `axelrod mcp`, which serves the context layer.

## Depends on

[M13](M13-services.md), and [M02](M02-model.md)–[M04](M04-repo.md) for reads. Never [M17](M17-demo.md): the demo implements `Session`.

## Invariants

- **Views are pure.** They never write, never emit a trace, and never call a slot.
- **Routes are adapters,** each under about 15 lines.
- **Work runs off the event loop**, under the session lock.
- **Canonical terms in every label** ([glossary](../glossary.md)).

## Done when

- The API integration and auth tests pass.
- Every view has a snapshot test on the small demo after examples 4, 15, and 24.
- The API doesn't import `sim/` or `demo/`.
