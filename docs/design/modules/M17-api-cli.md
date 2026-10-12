# M17 · API and CLI

| | |
|---|---|
| Layer | 5 · Interfaces |
| Status | **Exists**; thin it out |
| Code today | `api/app.py` (`create_app`, `AppState` wrapping a `ScenarioRunner`, per-login engines), `api/routes.py` (1,330 lines, 79 routes), `api/ws.py`, `api/auth.py`, `api/login.html`; `cli.py` (Typer) |
| Target | `axelrod_wm/api/`: `app.py`, `session.py` (a `Session` protocol replaces `hasattr(runner, …)`), `routes/` (one file per group), `ws.py`, `auth.py`; `axelrod_wm/cli.py` |

## Purpose

Adapters. They parse a request, call a service or a view, and serialize the result. No business logic and no view assembly live here.

## Owns

- **Route groups**, one file each:
  - health, session, config;
  - state, versions;
  - entities, interactions, superentities, taxonomies;
  - find, checks, memory;
  - frontier, hypotheses;
  - market events, graph update events;
  - proposals;
  - theses, forecasts, paths, explanations;
  - updates, evaluate, decisions;
  - scenarios, sim;
  - trace, flows, contracts;
  - repo;
  - structure;
  - examples, library, import, manual, vocabulary;
  - context (new: the M16 verbs over REST).
- **`/ws`.** The client sends `{"type":"hello","since_seq":n}`. The server replays the trace since then, then streams live `trace` and `status` messages, and supports ping and pong.
- **Auth.** A sign-in page sets an HttpOnly HMAC session cookie. `/api/health` stays open for the readiness probe. Per-login engines come from `WORLD_MODEL_LOGINS`. See [../../deployment.md](../../deployment.md).
- **CLI.** `small_demo`, `prod_demo`, `demo`, `init`, `update`, `log`, `show`, `diff`, `run-scenario`, `thesis`, `evaluate`, `export-trace`, `flows`, `contracts`; new `mcp` (serve the context layer). See [../../cli.md](../../cli.md).

## Interface

```python
class Session(Protocol):          # what the API needs from whatever it serves (a demo or a real model)
    services: Services            # review, updates, theses, structure, sources
    views: Views
    tracer: BroadcastTracer
    lock: RLock
    capabilities: set[str]        # "examples", "import", "scripted_story" — replaces hasattr probes
```

## Depends on / used by

- Depends on: [M14](M14-services.md), [M15](M15-views.md), [M16](M16-context-layer.md), [M13](M13-runtime.md) (CLI only). It does not import [M19](M19-demo.md): a demo session implements `Session` and registers its capabilities.
- Used by: [M18](M18-web.md), scripts, and agents.

## Invariants

- **Adapters only.** A route is under about 15 lines: parse, call, return.
- **Work runs off the event loop.** Handlers call `await session.call(fn)`, which runs it in a worker thread under the session lock.
- **Everything requires a session except `GET`/`HEAD /api/health`.**

## Done when

- The existing API integration tests and `test_basic_auth.py` pass.
- `api/` has no import of `sim/` or `demo/`, and no route function exceeds 25 lines (a lint test).
