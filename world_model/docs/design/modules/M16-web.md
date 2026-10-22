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

The browser app. It renders the server's views and replays trace events, and it **never computes model results**. There is no build step: plain HTML, CSS, and ES modules, with d3 v7 vendored. The user guide is [../../guides/gui.md](../../guides/gui.md).

## Owns

- **Two views of one model.**
  - **Learn**, for backend users.
  - **Predict**, for clients. It opens blank; a forecast brings forward only what it reaches, and **Show the whole model** shows the rest as of the forecast's version.
- **The canvas.**
  - Entities are pills and subentities are rows. A large model (40 entities or more) reads as **nested superentities** first: boxes that open into their members as the view closes in (see below).
  - Detail follows zoom (Auto). Every node has an open node. A hierarchical layout places causes left of effects, region inside region.
  - Isolate, find, levels, color, the lens, and draw.
- **Features**: review, examples, import, update, manual, thesis and forecast, briefs, the transmission grid, hypotheses, decisions, memory, checks, console, timeline, walkthrough, How it works, admin, and chat (which becomes a client of [M15](M15-context-layer.md)).

| File today | Role |
|---|---|
| `index.html`, `css/` | Layout, palette, faint grid, the two views |
| `js/main.js` | Boot, views, panels, tooltips, right-click menus, shortcuts |
| `js/api.js`, `js/store.js` | The REST client and `/ws`; the client model and `applyTrace` |
| `js/graph/` | Renderer, layouts (`layout-hier.js`), zoom, `lod.js` (an entity opens into its values) and `semantic.js` (a superentity opens into its parts), `attention.js`, lens, menus, fuzzy ribbons, open nodes, isolate, draw |
| `js/panels/` | One file per panel; `review.js`, `paths.js` (the grid), `methods.js` (How it works) |
| `js/animator/`, `js/charts/` | The trace player and guide; fan charts, glyphs, sparklines |

## Target

```text
world_model/web/js/core/      api.js · stream.js · store.js (applyTrace dispatches to features) · names.js · util.js
world_model/web/js/shell/     boot · views · router · keyboard · menus
world_model/web/js/canvas/    nodes.js · edges.js · hulls.js · animate.js · layouts · zoom · lod · lens
world_model/web/js/features/<name>/index.js   export function init({ api, store, canvas, shell })
```

**Nested superentities and semantic zoom (Oct 22).** The server computes the hierarchy; the browser only chooses which level to draw.

- **Source.** `GET /api/state` carries `clusters` (`api/hierarchy.py`, `ClusterView`): `id`, `parent`, `depth`, `label`, `keywords`, `source` (`keywords` or `llm`), `size`, `subentities`, `children`, `entity_ids` (held directly), `members`. Average-linkage agglomerative clustering on link structure, co-activation (shared learned superentities), and concept, kind, and sector, entities indexed by sorted id with ties to the lowest pair, so the same model gives the same groups. The dendrogram is cut by size (`LEAF_MAX` 10, `FANOUT` 5, `MIN_CLUSTER` 3). A model under `MIN_ENTITIES` (40) has none.
- **Labels.** c-TF-IDF keywords over members' names, kinds, and sectors, siblings as the classes. Optional language-model names (`POST /api/clusters/relabel`): provider chosen as in the import's LLM step (`axelrod_ingest.llm.provider_from_env`), temperature 0, cached in the lake by a hash of the member ids, so a name never changes; building a view only reads that cache, and with no provider nothing is called.
- **Cut.** `semantic.js` keeps the set of open groups. A group opens when it is in view and its screen size passes `EXPAND_PX`, nearest the middle first, for as long as the boxes in view fit a budget of canvas area (the view's pixels over `SPACING`; a closed box costs `MIN_BOX_PX`, a pill its on-screen area, at least `MIN_PILL_PX`), so a larger window shows more at the same zoom; it closes below `COLLAPSE` of that size (hysteresis). It is chosen when the view rests (debounced), by hand overrides it, and only the boxes that change are redrawn, fading.
- **Stable layout.** `layout-hier.js` places the superentities as regions, once, so a box is the box around its members' homes; zooming moves nothing and no layout runs. An interaction to a closed group is anchored to its box and aggregated (`model.js`).
- **Rendering cost.** The svg sits in one layer 40% larger than the canvas on each side, clipped, so the compositor scales it instead of drawing it again at every zoom step (an unbounded `overflow: visible` layer cost 14 s of painting against 0.1 s); the layer is a div, because a transform on the svg root made the browser lay the drawing out again every frame; the grid is two CSS gradients on a layer of its own; a tier change dips one layer of arrows rather than fading each; interaction labels are capped (`MAX_LABELS`) and dropped below `LABEL_MIN_K`.

## Depends on

[M14](M14-interfaces.md), over HTTP and `/ws` only.

## Invariants

- **No model results are computed in the browser.**
- **Canonical terms.** A tooltip may clarify a term but never replaces it.
- **A minimal first view.** The graph, a caption, and one row of controls; panels open on demand.
- **Undo applies to view changes only.**
- **Zoom moves nothing.** No layout runs on a change of zoom; a tier change redraws only the boxes it changes, and the same model always gives the same groups and names.

## Done when

- The Playwright smoke test passes, and the semantic-zoom test (`tests/ui/test_semantic_zoom.py`) shows a large model's boxes opening, folding, and not toggling around one zoom.
- `renderer.js` and `main.js` are each under 800 lines.
- No feature imports another feature.
