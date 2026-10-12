# M18 · Web

| | |
|---|---|
| Layer | 5 · Interfaces |
| Status | **Exists**; split the two monoliths and give each feature a boundary |
| Code today | `web/index.html`, `css/`, `js/main.js` (1,460 lines), `js/api.js`, `js/store.js`, `js/graph/` (17 files; `renderer.js` is 2,527 lines), `js/panels/` (26 files), `js/animator/`, `js/charts/`, `literature.md`, `implementation.html` |
| Target | `web/js/shell/` (boot, router, views, keyboard, menus), `web/js/canvas/` (renderer split into `nodes.js`, `edges.js`, `hulls.js`, `animate.js`; layouts, zoom, lod, lens), `web/js/features/<feature>/` (each with `panel.js`, `api.js` slice, `store.js` slice, `trace.js` handlers), `web/js/core/` (api client, store, Stream, names, util) |

## Purpose

The browser app. It renders the server's views and replays trace events. It **never computes model results**. There is no build step: plain HTML, CSS, and ES modules, with d3 v7 vendored.

## Owns

- **Two views of one model.**
  - **Learn** is for backend users: import, tutorial, update, review, structure edits.
  - **Predict** is for external users. It opens on a blank canvas, and a forecast brings forward only what it reaches. **Show the whole model** shows the rest as of the forecast's version.
- **The canvas.**
  - Entities are pills; subentities are rows; superentities are outlines that close into cards.
  - With **Auto** on, detail follows zoom, and the threshold is learned.
  - Every node carries an open node. The hierarchical layout puts causes left of their effects, with nothing overlapping.
  - Also: isolate, find, levels, color, the lens, and the draw tool.
- **Features** (one folder each): review, examples (the tutorial), import, update, manual (Add from your own knowledge), thesis and forecast (Pose a thesis), briefs, transmission grid (paths), hypotheses, decisions, memory (five tabs), checks, console, timeline, walkthrough, How it works (methods, flowcharts, literature, implementation), admin, chat (becomes a client of [M16](M16-context-layer.md)).
- **The trace player** (`animator/`): applies trace payloads to animate learning and inference step by step.

## Interface

```js
// core/api.js — one function per REST route; core/stream.js — /ws with since_seq replay
// core/store.js — a reducer: applyTrace(ev) dispatches to features' trace handlers, then emits topics
// features/<f>/index.js
export function init({ api, store, canvas, shell }) { /* register panel, shortcuts, trace handlers */ }
```

## Depends on / used by

- Depends on: [M17](M17-api-cli.md) (HTTP and `/ws`) only.
- Used by: people.

## Invariants

- **The front end never computes model results.**
- **Canonical terms in every label** ([glossary.md](../glossary.md)). Usability work may change layout, order, help text, and navigation, but never rename a concept. A tooltip may clarify a term; it never replaces it.
- **Minimal first view.** The first screen is the graph, a caption, and one row of controls. Panels open on demand, and `Esc` closes the top thing.
- **Undo is for view changes only**, never for commits.

## Done when

- The Playwright smoke test passes (`tests/ui/test_smoke.py`).
- `renderer.js` and `main.js` are each under 800 lines, and no feature imports another feature's files.
- [../../interface.md](../../interface.md) is still accurate (it is the user guide for this module).
