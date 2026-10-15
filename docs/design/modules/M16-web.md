# M16 · Web

**Layer** 5 · **Package** `web/` · **Status** exists. The two monoliths get split, and each feature gets a boundary.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Target](#target)
- [Depends on](#depends-on)
- [Invariants](#invariants)
- [Done when](#done-when)
<!-- /toc -->

**Code today:**
- `js/main.js` (1,460 lines);
- `js/graph/renderer.js` (2,527 lines);
- 26 panels, plus `store.js` and `api.js`.

## Purpose

The browser app. It renders the server's views and replays trace events, and it **never computes model results**. There is no build step: plain HTML, CSS, and ES modules, with d3 v7 vendored. The user guide is [../../interface.md](../../interface.md).

## Owns

- **Two views of one model.**
  - **Learn**, for backend users.
  - **Predict**, for clients. It opens blank; a forecast brings forward only what it reaches, and **Show the whole model** shows the rest as of the forecast's version.
- **The canvas.**
  - Entities are pills, subentities are rows, and superentities are outlines that close into cards.
  - Detail follows zoom (Auto). Every node has an open node. A hierarchical layout places causes left of effects.
  - Isolate, find, levels, color, the lens, and draw.
- **Features**: review, examples, import, update, manual, thesis and forecast, briefs, the transmission grid, hypotheses, decisions, memory, checks, console, timeline, walkthrough, How it works, admin, and chat (which becomes a client of [M15](M15-context-layer.md)).

| File today | Role |
|---|---|
| `index.html`, `css/` | Layout, palette, faint grid, the two views |
| `js/main.js` | Boot, views, panels, tooltips, right-click menus, shortcuts |
| `js/api.js`, `js/store.js` | The REST client and `/ws`; the client model and `applyTrace` |
| `js/graph/` | Renderer, layouts (`layout-hier.js`), zoom and `lod.js`, `attention.js`, lens, menus, fuzzy ribbons, open nodes, isolate, draw |
| `js/panels/` | One file per panel; `review.js`, `paths.js` (the grid), `methods.js` (How it works) |
| `js/animator/`, `js/charts/` | The trace player and guide; fan charts, glyphs, sparklines |

## Target

```text
web/js/core/      api.js · stream.js · store.js (applyTrace dispatches to features) · names.js · util.js
web/js/shell/     boot · views · router · keyboard · menus
web/js/canvas/    nodes.js · edges.js · hulls.js · animate.js · layouts · zoom · lod · lens
web/js/features/<name>/index.js   export function init({ api, store, canvas, shell })
```

## Depends on

[M14](M14-interfaces.md), over HTTP and `/ws` only.

## Invariants

- **No model results are computed in the browser.**
- **Canonical terms.** A tooltip may clarify a term but never replaces it.
- **A minimal first view.** The graph, a caption, and one row of controls; panels open on demand.
- **Undo applies to view changes only.**

## Done when

- The Playwright smoke test passes.
- `renderer.js` and `main.js` are each under 800 lines.
- No feature imports another feature.
