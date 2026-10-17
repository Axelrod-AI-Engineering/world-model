// The canvas (§13.3). Drawing sits behind the GraphRenderer interface, so a canvas or WebGL renderer
// can replace SVG if the node count passes about 2,000.
/* global d3 */
import { conceptGroups, conceptStyles } from "./concepts.js";
import { densityCurve } from "../charts/density.js";
import { createSimulation, resolveCollisions, staticLayout } from "./forces.js";
import { drawRibbons, prettyNode } from "./fuzzy.js";
import { buildGroups, hullContourCached, hullPolygon, PAD, superentityMarks } from "./hulls.js";
import { figurePosition, slotPosition } from "./layouts.js";
import { computeModel, fmtMove, fmtValue, GEOM, kinKey, ROW_GEOM, rowCenterY, rowLabels, textWidth, truncate, valueWidth } from "./model.js";
import { openNode } from "./open-node.js";
import { createAttention } from "./attention.js";
import { filterView } from "./isolate.js";
import { hierarchicalLayout } from "./layout-hier.js";
import { createLOD } from "./lod.js";
import { createZoom, installGrid } from "./zoom.js";
import { cubicAt, rectOf, routeEdges } from "./edge-route.js";

/** The interface every renderer implements. */
export class GraphRenderer {
  setLayout(_layout) {}
  setData(_view, _extras) {}
  setExtras(_extras) {}
  setDetail(_level) {}
  toggleEntity(_id, _open) {}
  setLayoutMode(_mode) {}
  setOptions(_opts) {}
  fit() {}
  zoomBy(_factor) {}
  focusNode(_id) {}
  reveal(_id) {}
  setHighlight(_hl) {}
  pulse(_ids, _color, _ms) {}
  pulseLinks(_ids, _color, _ms) {}
  halos(_zById, _ms, _opts) {}
  clearHalos() {}
  flashHull(_instanceId, _ms) {}
  flashCandidates(_candidates, _ms) {}
  select(_sel) {}
}

const ARROW = 8;                // arrowhead length (world units): a routed edge stops this far from the border
const EDGE_IN_MS = 300;         // an interaction that is new draws itself in from its cause
const EDGE_OUT_MS = 180;
const LABEL_SETTLE = 3;        // layouts in a row a hidden label needs room before it shows again
// theme colors, read once a frame: reading computed style on every tick forced the page's styles to be recomputed
const cssCache = new Map();
const css = (name) => {
  if (!cssCache.size) requestAnimationFrame(() => cssCache.clear());
  let v = cssCache.get(name);
  if (v == null) { v = getComputedStyle(document.documentElement).getPropertyValue(name).trim(); cssCache.set(name, v); }
  return v;
};
const NAME_FONT = "600 13px Instrument Sans";
const TAB_FONT = "700 13px Instrument Sans";


// Where a segment from the center of a box toward (tx, ty) leaves the box.
function boxExit(n, tx, ty, pad = 2) {
  const r = rectOf(n);
  const cx = (r.x0 + r.x1) / 2;
  const cy = (r.y0 + r.y1) / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  const hw = (r.x1 - r.x0) / 2 + pad;
  const hh = (r.y1 - r.y0) / 2 + pad;
  const s = Math.min(hw / Math.abs(dx || 1e-9), hh / Math.abs(dy || 1e-9));
  return [cx + dx * Math.min(s, 1), cy + dy * Math.min(s, 1)];
}

export class SvgRenderer extends GraphRenderer {
  constructor(container, handlers = {}) {
    super();
    this.container = container;
    this.handlers = handlers;
    this.svg = d3.select(container).select("svg");
    this.defs = this.svg.append("defs");
    this.makeMarkers();
    const grid = installGrid(this.svg, this.defs);
    this.root = this.svg.append("g").attr("class", "root");
    this.layers = {};
    for (const name of ["lane", "netlines", "edges", "frontier", "ghosts", "fuzzy", "nodes", "overlays"]) {
      this.layers[name] = this.root.append("g").attr("class", `layer-${name}`);
    }
    this.layout = null;
    this.view = null;
    this.extras = { ribbons: [], ghostEdges: [], ghostSubs: [], pendingPatterns: new Set() };
    this.ui = { expanded: new Set(), showCandidates: false };
    this.mode = "figure1";
    this.opts = { figure1LinksOnly: false, groupByCategory: false, reducedMotion: false };
    this.nodes = new Map();
    this.homes = new Map();
    this.gravHomes = new Map();       // homes the static gravity layout found (Oct 9); Figure 1's stay in `homes`
    this.pinnedHomes = new Map();
    this.lane = null;             // a staged review's transmission lane (setLane): {cols, ids}
    this.laneHomes = null;        // where the lane puts its entities
    // superentities as data (graph/hulls.js), for the panels, the walkthrough, and framing; not drawn (Oct 17)
    this.groupsInfo = { groups: [], byKey: new Map(), ofEntity: new Map(), ofInstance: new Map() };
    this.marks = new Map();
    // the taxonomy's concepts, which arrange the canvas (graph/concepts.js); not drawn either
    this.layoutGroups = { groups: [], byKey: new Map(), ofEntity: new Map() };
    this.model = null;
    this.subIndex = new Map();
    this.highlight = null;
    this.focus = null;
    this.selection = null;
    this.haloData = new Map();
    this.lastContourPos = new Map();
    this.tickCount = 0;
    this.undoStack = [];
    this.redoStack = [];
    this.overlayGroups = [];      // the walkthrough's outlined networks: {key, members, color, label}
    this.flowData = new Map();    // the walkthrough's edge flows: interaction id -> signed flow
    this.peeked = null;           // what the walkthrough opened temporarily
    this.sim = createSimulation({
      getMode: () => this.mode,
      getBlocks: () => this.blocks(),
      getGroups: () => this.layoutGroups.groups,
      groupByCategory: () => this.opts.groupByCategory,
      onTick: () => this.ticked(),
    });
    // DECISION (Oct 8): in the gravity layout the graph floats to a new shape after each structural change; once it
    // settles, the view re-frames it, unless a person has panned or zoomed since that change
    this.autoFrame = false;
    // DECISION (Oct 11): detail follows zoom when "Auto" is on, gradually and node by node, like a map (graph/lod.js);
    // the zoom levels a person settles at and what they look at are learned (graph/attention.js) for the zoom slider.
    // Any detail picked by hand turns Auto off.
    this.autoDetail = true;
    this.attention = createAttention("default");
    this.lod = createLOD(this, this.attention);
    this.lastMove = 0;
    this.personZoomUntil = 0;
    this.zoom = createZoom(this.svg, this.root, { grid, onRest: () => this.releaseLayout(), onZoom: (t, byUser) => {
      this.lastMove = performance.now();
      if (byUser) {
        this.autoFrame = false;
        this.userMoved = true;
        // buffered (Oct 11): a layout still floating holds still while a person zooms or pans, so the moving view is
        // one composited layer that nothing redraws underneath; it floats on from where it was once the view rests
        this.holdLayout();
        // while a person zooms or pans, what slides under a still cursor is not being pointed at: no hover pop-ups or
        // focus dimming flick on and off; the canvas takes the pointer again once the view has rested
        if (!document.body.classList.contains("zooming")) {
          document.body.classList.add("zooming");
          if (this.hoverFocus) this.setFocus(null);
          this.handlers.onHover?.(null);
        }
        clearTimeout(this.zoomingTimer);
        this.zoomingTimer = setTimeout(() => document.body.classList.remove("zooming"), 260);
      }
      // detail follows zooms a person makes (wheel, pinch, drag, the slider, + and −), never the app's own framing,
      // so the first view stays as laid out
      if (byUser || performance.now() < this.personZoomUntil) this.lod.update();
      this.handlers.onZoomChange?.(t);
    } });
    // attention: every half second the view is still, the nodes in its middle count as looked at
    this.attentionTimer = setInterval(() => this.observeAttention(), 500);
    this.sim.on("end.frame", () => {
      // not while a walkthrough, a staged review, or a transmission path (Oct 17: its own framing was undone by this one)
      // frames what it is showing
      const framed = document.body.classList.contains("staging") || document.body.classList.contains("txpath")
        || document.querySelector("#walkthrough:not(.hidden)");
      if (this.autoFrame && this.mode === "gravity" && !framed) { this.autoFrame = false; this.frameAll(500); }
    });
    const isBackground = (ev) => ev.target === this.svg.node() || ev.target.closest?.(".grid-bg");
    this.svg.on("click", (ev) => { if (isBackground(ev)) this.handlers.onSelect?.(null); });
    this.svg.on("contextmenu", (ev) => {
      if (!isBackground(ev)) return;
      ev.preventDefault();
      this.handlers.onContext?.(ev, { kind: "canvas" });
    });
  }

  holdLayout() {
    if (this.layoutHeld || performance.now() - (this.lastTickAt ?? 0) > 120) return;
    this.layoutHeld = true;
    this.sim.stop();
  }

  releaseLayout() {
    if (!this.layoutHeld) return;
    this.layoutHeld = false;
    this.sim.restart();
  }

  makeMarkers() {
    // DECISION (Oct 14): a routed edge stops short of its box by the arrowhead's length and the arrowhead is drawn from
    // there (its base on the curve's end, refX 0), so the tip lands exactly on the border. Sizes are in world units, so
    // an arrowhead keeps its proportion to the boxes at every zoom and does not grow with the stroke's width.
    const mk = (id, color, size = 6, { start = false, base = true } = {}) => {
      this.defs.append("marker").attr("id", id).attr("viewBox", "0 0 10 10").attr("refX", base ? 0 : 9).attr("refY", 5)
        .attr("markerWidth", size).attr("markerHeight", size).attr("orient", start ? "auto-start-reverse" : "auto")
        .attr("markerUnits", "userSpaceOnUse")
        .append("path").attr("d", "M0 0.6L10 5L0 9.4z").attr("fill", color);
    };
    mk("arr", "#857C70", ARROW);
    mk("arr-s", "#857C70", ARROW, { start: true });
    mk("arr-learned", "#7C64C4", ARROW);
    mk("arr-hl", "#874B2B", ARROW);
    mk("arr-hl-s", "#874B2B", ARROW, { start: true });
    mk("arr-ghost", "#7C64C4", 8, { base: false });     // ghost edges run center to center and are not routed
    mk("arr-front", "#93465F", ARROW);
    // a soft glow for deviation outlines and the guide's spotlight
    const f = this.defs.append("filter").attr("id", "soft-glow").attr("x", "-30%").attr("y", "-30%").attr("width", "160%").attr("height", "160%");
    f.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", 2.4).attr("result", "b");
    const m = f.append("feMerge");
    m.append("feMergeNode").attr("in", "b");
    m.append("feMergeNode").attr("in", "SourceGraphic");
  }

  // -- data -----------------------------------------------------------------------------------------
  setLayout(layout) {
    this.layout = layout;
    this.homes.clear();
  }

  // another world: none of the last one's placements apply
  resetHomes() {
    this.gravHomes.clear();
    this.savedHomes = null;
    this.userMoved = false;
  }

  setOptions(opts) {
    Object.assign(this.opts, opts);
    if ("colorBy" in opts) this.paintNodes();
    if ("groupByCategory" in opts) { this.relayout(true); this.sim.alpha(0.6).restart(); }
    if ("figure1LinksOnly" in opts) this.drawEdges();
  }

  setLayoutMode(mode) {
    if (mode !== this.mode) this.record(mode === "figure1" ? "switch to the Figure 1 layout" : "switch to the gravity layout", { camera: true });
    this.mode = mode;
    if (mode === "gravity" && this.nodes.size) this.relayout(true);
    for (const n of this.nodes.values()) {
      n.flow = false;
      if (!n.dragging) { n.fx = null; n.fy = null; }
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
    if (mode === "figure1") this.applyFlow();
    this.sim.alpha(mode === "figure1" ? 0.6 : 0.9).restart();
  }

  setData(view, extras = {}) {
    const first = !this.view;
    this.fullView = view;
    this.view = this.isolated ? filterView(view, this.isolated.keep) : view;
    Object.assign(this.extras, extras);
    this.recompute(first ? "first" : "data");
  }

  setExtras(extras) {
    const before = [...(this.extras.pendingPatterns ?? [])].join("|");
    Object.assign(this.extras, extras);
    if ([...(this.extras.pendingPatterns ?? [])].join("|") !== before) { this.recompute("data"); return; }
    this.drawGhosts();
    this.drawFuzzy(true);
    this.applyStaged();
  }

  updateHomes() {
    const regions = [];
    for (const g of this.layoutGroups.groups) {
      if (g.children.length) continue;
      const pts = [...g.members].map((m) => figurePosition(this.layout, m)).filter(Boolean);
      if (pts.length < 2) continue;
      regions.push({ x0: Math.min(...pts.map((p) => p.x)), x1: Math.max(...pts.map((p) => p.x)),
                     y0: Math.min(...pts.map((p) => p.y)), y1: Math.max(...pts.map((p) => p.y)) });
    }
    for (const e of this.view.entities) {
      if (this.homes.has(e.id)) continue;
      const p = figurePosition(this.layout, e.id) ?? slotPosition(e.id, this.view, this.homes, regions);
      this.homes.set(e.id, p);
    }
  }

  // gravity places an entity in the Gravity layout, and in the Figure 1 layout when Figure 1 does not place it
  byGravity(id) {
    return this.mode === "gravity" || !figurePosition(this.layout, id);
  }

  // a home nothing moves: placed by hand (pinnedHomes, part of undo), or by the transmission grid's isolation (isoHomes)
  fixedHome(id) { return this.pinnedHomes.get(id) ?? this.laneHomes?.get(id) ?? (this.isolated ? this.isoHomes?.get(id) : undefined); }
  hasFixedHome(id) { return this.fixedHome(id) != null; }

  entityHome(id) {
    return this.fixedHome(id) ?? (this.byGravity(id) ? this.gravHomes.get(id) : null) ?? this.homes.get(id);
  }

  homeOf(box) {
    const h = this.layoutHome(box);
    const d = this.shifts?.get(box.id);
    return d ? { x: h.x + d.dx, y: h.y + d.dy } : h;
  }

  // Oct 14: an entity opens where it is. The layout keeps closed sizes, so an open entity makes room by pushing the boxes
  // in its way; nothing else moves. Oct 15: in both directions. What lies beneath an open entity moves down, and what
  // sits beside it (an open entity is wider than its pill) moves aside, to the right; a box pushed into another
  // pushes that one in turn, a few rounds, so no open entity overlaps its neighbors at any zoom.
  openShifts() {
    const shifts = new Map();
    this.shifts = shifts;
    // Oct 17: an isolated graph too (a forecast's entities in Predict open after they are placed), unless its homes are
    // fixed (the transmission grid's), which hasFixedHome leaves out below
    if (!this.model || this.mode !== "gravity") return;
    const GAP = 12;
    const boxes = this.model.boxes.filter((b) => !this.hasFixedHome(b.id)).map((b) => {
      const h = this.layoutHome(b);
      return { b, x: h.x, y: h.y, top: h.y + b.oy, w: b.w, h: b.h, dx: 0, dy: 0,
               open: b.kind === "entity" && b.open && b.h > GEOM.HEAD_H };
    });
    if (!boxes.some((o) => o.open)) return;
    // reading order: what comes first stays, what comes after makes room
    boxes.sort((a, z) => a.top - z.top || a.x - z.x);
    const rect = (o) => ({ x0: o.x + o.dx - o.w / 2, x1: o.x + o.dx + o.w / 2, y0: o.top + o.dy, y1: o.top + o.dy + o.h });
    for (let round = 0; round < 24; round++) {
      let moved = false;
      for (let i = 0; i < boxes.length; i++) {
        const a = boxes[i];
        for (let j = i + 1; j < boxes.length; j++) {
          const b = boxes[j];
          // two closed boxes keep the layout's own spacing, unless one was pushed into the other (Oct 17: a column of
          // pills beneath an open entity used to land on one spot, each pushed just clear of the open box)
          if (!a.open && !b.open && !a.dx && !a.dy && !b.dx && !b.dy) continue;
          const ra = rect(a);
          const rb = rect(b);
          const ox = Math.min(ra.x1, rb.x1) - Math.max(ra.x0, rb.x0) + GAP;
          const oy = Math.min(ra.y1, rb.y1) - Math.max(ra.y0, rb.y0) + GAP;
          if (ox <= GAP || oy <= GAP) continue;
          // pushes only ever go right or down (Oct 16): the box that began beneath the other's head moves down, else the
          // box on the right moves right. A push to the left could land on a box already settled, and the rounds would
          // trade the overlap back and forth; pushes in two directions only always settle
          if (Math.abs(b.top - a.top) >= GEOM.HEAD_H * 0.75) (b.top > a.top ? b : a).dy += oy;
          else (b.x >= a.x ? b : a).dx += ox;
          moved = true;
        }
      }
      if (!moved) break;
    }
    for (const o of boxes) if (o.dx || o.dy) shifts.set(o.b.id, { dx: o.dx, dy: o.dy });
  }

  layoutHome(box) {
    return this.entityHome(box.id) ?? { x: 600, y: 440 };
  }

  recompute(reason) {
    if (!this.view) return;
    this.subIndex = new Map(this.view.subentities.map((s) => [s.id, s]));
    this.entIndex = new Map(this.view.entities.map((e) => [e.id, e]));
    this.groupsInfo = buildGroups(this.view, { showCandidates: this.ui.showCandidates,
                                               pendingPatterns: this.extras.pendingPatterns ?? new Set() });
    this.marks = superentityMarks(this.view, this.groupsInfo);
    this.layoutGroups = conceptGroups(this.view);
    for (const id of [...this.ui.expanded]) if (!this.view.entities.some((e) => e.id === id)) this.ui.expanded.delete(id);
    this.updateHomes();
    this.model = computeModel(this.view, this.ui);
    this.openShifts();
    // an entity opened or closed by hand also grows over a few frames, so its edges and outline follow its border
    this.easeSizes = reason === "lod" || (reason === "structure" && this.animOK());
    const structural = this.syncNodes();
    const nodes = [...this.nodes.values()];
    this.sim.nodes(nodes);
    this.sim.force("link").links(this.model.edges.filter((e) => this.nodes.has(e.a.box) && this.nodes.has(e.b.box))
      .map((e) => ({ source: e.a.box, target: e.b.box, significance: e.sig })));
    // a change of detail (lod) keeps every box's home: an opened entity grows in place and its neighbors step aside
    const unplaced = nodes.some((n) => n.kind === "entity" && this.byGravity(n.id) && !this.gravHomes.has(n.id) && !this.hasFixedHome(n.id));
    // DECISION (Oct 11, supersedes "a change of detail keeps every home"): a change of structure (a new entity) re-packs
    // the arrangement, so blocks stay separate and in order. The order is the same every time, so blocks only make room;
    // the entity nearest the middle of the view stays put.
    // Oct 14: the layout is solved at full detail (fullDetail), so a change of detail (lod) moves nothing; only a change of
    // structure (an entity added or retired) lays the graph out again
    if (reason !== "first" && ((structural && reason !== "lod") || unplaced) && this.blocks()) this.repack();
    else if (unplaced || reason === "first" || (structural && reason !== "lod")) this.relayout();
    // homes may have moved (a layout); the pushes of open entities follow them
    this.openShifts();
    for (const n of this.nodes.values()) {
      if (n.kind === "entity" && n.flow) continue;
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
    this.draw();
    if (reason === "first") {
      resolveCollisions(nodes, 6);
      this.ticked(true);
      // the first view (Oct 11): the gravity layout shows the whole graph, with detail following that zoom, so it opens on
      // the top of the hierarchy and zooming in opens it level by level; the hand-placed Figure 1 opens readable
      setTimeout(() => this.frameAll(0), 30);
    }
    if (reason === "lod") {
      // before a person has moved the view, the first view keeps framing the whole graph as it opens (only the camera
      // moves; the boxes keep their places)
      if (!this.userMoved) this.autoFrame = true;
      this.sim.alpha(Math.max(this.sim.alpha(), 0.22)).restart();
    } else if (structural || reason === "structure") {
      if (structural) this.autoFrame = true;
      this.sim.alpha(Math.max(this.sim.alpha(), 0.55)).restart();
    }
    this.handlers.onDetail?.(this.detailLevel());
  }

  syncNodes() {
    const old = this.nodes;
    const next = new Map();
    let structural = false;
    for (const b of this.model.boxes) {
      let n = old.get(b.id);
      if (!n) {
        structural = true;
        const p = this.startPosition(b, old);
        n = { id: b.id, x: p.x, y: p.y, vx: 0, vy: 0 };
      }
      if (n.w !== b.w || n.h !== b.h) structural = true;
      const home = this.homeOf(b);
      n.pinned = this.hasFixedHome(b.id);
      // free: Figure 1 does not place it, so gravity and tension do (graph/forces.js)
      n.free = !this.hasFixedHome(b.id) && !figurePosition(this.layout, b.id);
      // a change of detail grows a box over a few frames (ticked eases w and h), so its neighbors slide aside
      if (this.easeSizes && old.has(b.id) && (n.w !== b.w || n.h !== b.h)) { n.wGoal = b.w; n.hGoal = b.h; }
      else { n.w = b.w; n.h = b.h; n.wGoal = null; n.hGoal = null; }
      Object.assign(n, { kind: b.kind, ref: b.ref, oy: b.oy, box: b, hx: home.x, hy: home.y,
                         tags: b.entity?.category_tags,
                         groupKeys: this.layoutGroups.ofEntity.get(b.id) ?? [] });
      next.set(b.id, n);
    }
    if (old.size !== next.size) structural = true;
    this.nodes = next;
    if (this.mode === "figure1") this.applyFlow();
    return structural;
  }

  repack() {
    // before a person has moved the view, the first view keeps framing the whole graph as it changes
    if (!this.userMoved) this.autoFrame = true;
    const t = this.zoom.transform();
    const { width, height } = this.zoom.rect();
    const cx = (width / 2 - t.x) / t.k;
    const cy = (height / 2 - t.y) / t.k;
    let anchor = null;
    let best = Infinity;
    for (const [id, h] of this.gravHomes) {
      const d = Math.hypot(h.x - cx, h.y - cy);
      if (d < best) { best = d; anchor = id; }
    }
    const was = anchor ? { ...this.gravHomes.get(anchor) } : null;
    this.relayout(true);
    const now = anchor ? this.gravHomes.get(anchor) : null;
    if (!was || !now) return;
    const dx = was.x - now.x;
    const dy = was.y - now.y;
    for (const [id, h] of this.gravHomes) this.gravHomes.set(id, { x: h.x + dx, y: h.y + dy });
    for (const [k, h] of this.laneHomes ?? []) this.laneHomes.set(k, { x: h.x + dx, y: h.y + dy });
    if (this.laneBox) {
      const lb = this.laneBox;
      this.laneBox = { ...lb, x0: lb.x0 + dx, x1: lb.x1 + dx, y0: lb.y0 + dy, y1: lb.y1 + dy, cols: lb.cols.map((c) => ({ ...c, x: c.x + dx })) };
      this.drawLane();
    }
    for (const n of this.nodes.values()) {
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
  }

  // Gravity, solved off-screen (Oct 9): every box gravity places gets a home, and keeps it until the structure
  // changes. Boxes already placed are anchored near their homes, so a change moves what it must and little else;
  // `fresh` lays everything out anew (switching to the Gravity layout, grouping by category).
  // The layout's input (Oct 14): every entity at its closed size. Where things sit then does not depend on what
  // detail-follows-zoom has opened, so zooming changes detail and moves almost nothing, like a map: an entity that opens
  // pushes aside only what is in its way (openShifts). An isolated graph keeps the entities it pins open at their open size.
  fullDetail() {
    const open = this.isolated ? new Set(this.ui.expanded) : new Set();
    const m = computeModel(this.view, { ...this.ui, expanded: open });
    const boxes = new Map(m.boxes.map((b) => [b.id, b]));
    const links = m.edges.filter((e) => boxes.has(e.a.box) && boxes.has(e.b.box) && e.a.box !== e.b.box)
      .map((e) => ({ source: e.a.box, target: e.b.box, significance: e.sig }));
    return { boxes, links };
  }

  relayout(fresh = false) {
    const nodes = [...this.nodes.values()];
    if (!nodes.length) return;
    const movableId = (id) => !this.hasFixedHome(id) && this.byGravity(id);
    // a transmission lane's entities sit in the lane, not in their blocks: the layout places everything else
    const inLane = (n) => n.kind === "entity" && !!this.lane?.ids.has(n.id);
    const full = this.fullDetail();
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const copies = [...full.boxes.values()].filter((b) => !this.lane?.ids.has(b.id)).map((b) => {
      const was = fresh ? null : this.gravHomes.get(b.id) ?? null;
      const fixed = !movableId(b.id);
      const n = byId.get(b.id);
      const start = fixed ? (this.fixedHome(b.id) ?? this.homes.get(b.id) ?? { x: 600, y: 440 })
        : was ?? (n ? { x: n.x, y: n.y } : this.homes.get(b.id) ?? { x: 600, y: 440 });
      return { id: b.id, kind: "entity", w: b.w, h: b.h, oy: b.oy, tags: b.entity?.category_tags,
               groupKeys: this.layoutGroups.ofEntity.get(b.id) ?? [], x: start.x, y: start.y, fixed, anchor: was };
    });
    const laneIds = new Set(nodes.filter(inLane).map((n) => n.id));
    const links = full.links.filter((l) => !laneIds.has(l.source) && !laneIds.has(l.target));
    // DECISION (Oct 11): a fresh placement follows the hierarchy (graph/layout-hier.js): regions inside regions, causes
    // left of effects, nothing overlapping. Later changes keep boxes near their homes with the gravity physics, so a
    // new entity finds its place without reshuffling the rest. Oct 17: the regions are the taxonomy's concepts.
    const fresh0 = fresh || copies.every((c) => !c.anchor);
    const groups = this.layoutGroups.groups;
    const placed = fresh0 && !this.opts.groupByCategory && copies.every((c) => !c.fixed)
      ? hierarchicalLayout(copies, links, groups)
      : staticLayout(copies, links, { groups, groupByCategory: this.opts.groupByCategory });
    for (const c of copies) {
      const p = placed.get(c.id);
      if (p && !c.fixed) this.gravHomes.set(c.id, p);
    }
    this.placeLane(nodes);
    for (const n of nodes) {
      if (n.kind === "entity" && n.flow) continue;
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
  }

  // -- the transmission lane (Oct 11) ------------------------------------------------------------------
  // A staged review's path, on the canvas itself: the entities it moves leave their blocks and line up in a lane above
  // the rest of the world model, one column per order (what drives it, the event's own move, then the first, second,
  // and third order), so the ripple reads left to right while everything else stays in frame below. `lane` is
  // {cols: [{key, label, ids}]} or null; the entities it holds are opened, and given back when it clears.
  setLane(lane) {
    const ids = new Set((lane?.cols ?? []).flatMap((c) => c.ids));
    const key = lane ? lane.cols.map((c) => `${c.key}:${c.ids.join(",")}`).join("|") : "";
    if (key === (this.lane?.key ?? "")) return;
    if (!ids.size) lane = null;
    if (lane && !this.lane) this.laneSaved = { expanded: new Set(this.ui.expanded) };
    this.lane = lane ? { ...lane, ids, key } : null;
    this.laneHomes = null;
    if (lane) {
      for (const id of ids) this.ui.expanded.add(id);
    } else if (this.laneSaved) {
      this.ui.expanded = this.laneSaved.expanded;
      this.laneSaved = null;
    }
    this.ui.lane = this.lane ? ids : null;
    this.recompute("lane");
    if (this.mode === "gravity") this.relayout(true);
    this.draw();
    this.sim.alpha(Math.max(this.sim.alpha(), 0.6)).restart();
    // frame the whole world model, lane and all, once the boxes have glided to their places
    clearTimeout(this.laneFit);
    this.laneFit = setTimeout(() => this.fit(this.opts.reducedMotion ? 0 : 420), this.opts.reducedMotion ? 30 : 520);
  }

  placeLane(nodes) {
    this.laneHomes = null;
    this.laneBox = null;
    const lane = this.lane;
    if (!lane) return;
    const byId = new Map(nodes.map((n) => [n.id, n]));
    // the rest of the world model, where the layout put it
    let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity;
    for (const n of nodes) {
      if (n.kind === "entity" && lane.ids.has(n.id)) continue;
      const h = this.homeOf(n.box);
      const w = n.wGoal ?? n.w;
      x0 = Math.min(x0, h.x - w / 2); x1 = Math.max(x1, h.x + w / 2); y0 = Math.min(y0, h.y + n.oy);
    }
    if (!Number.isFinite(x0)) { x0 = 400; x1 = 800; y0 = 440; }
    const GAP_X = 132;
    const GAP_Y = 18;
    const cols = lane.cols.map((c) => {
      const ns = c.ids.map((id) => byId.get(id)).filter(Boolean);
      return { ...c, ns, w: Math.max(150, ...ns.map((n) => n.wGoal ?? n.w)),
               h: ns.reduce((t, n) => t + (n.hGoal ?? n.h), 0) + GAP_Y * Math.max(0, ns.length - 1) };
    }).filter((c) => c.ns.length);
    if (!cols.length) return;
    const W = cols.reduce((t, c) => t + c.w, 0) + GAP_X * (cols.length - 1);
    const H = Math.max(...cols.map((c) => c.h));
    const top = y0 - 150 - H;
    let x = (x0 + x1) / 2 - W / 2;
    this.laneHomes = new Map();
    for (const c of cols) {
      let y = top + (H - c.h) / 2;
      for (const n of c.ns) {
        this.laneHomes.set(n.id, { x: x + c.w / 2, y: y - n.oy });
        y += (n.hGoal ?? n.h) + GAP_Y;
      }
      c.x = x;
      x += c.w + GAP_X;
    }
    this.laneBox = { x0: (x0 + x1) / 2 - W / 2 - 36, x1: (x0 + x1) / 2 + W / 2 + 36, y0: top - 64, y1: top + H + 30,
                     title: lane.title, cols: cols.map((c) => ({ key: c.key, label: c.label, x: c.x + c.w / 2, cls: c.cls })) };
  }

  drawLane() {
    const b = this.lane ? this.laneBox : null;
    const sel = this.layers.lane.selectAll("g.lane").data(b ? [b] : [], () => "lane");
    sel.exit().transition().duration(this.opts.reducedMotion ? 0 : 160).style("opacity", 0).remove();
    const enter = sel.enter().append("g").attr("class", "lane").style("opacity", 0);
    enter.append("rect").attr("class", "lane-band").attr("rx", 18);
    enter.append("text").attr("class", "lane-title");
    enter.transition().duration(this.opts.reducedMotion ? 0 : 220).style("opacity", 1);
    const all = enter.merge(sel);
    all.select("rect.lane-band").attr("x", (d) => d.x0).attr("y", (d) => d.y0).attr("width", (d) => d.x1 - d.x0).attr("height", (d) => d.y1 - d.y0);
    all.select("text.lane-title").attr("x", (d) => d.x0 + 18).attr("y", (d) => d.y0 - 12).text((d) => d.title ?? "Transmission path");
    const heads = all.selectAll("text.lane-col").data((d) => d.cols.map((c) => ({ ...c, y: d.y0 + 30 })), (c) => c.key);
    heads.exit().remove();
    heads.enter().append("text").merge(heads).attr("class", (c) => `lane-col ${c.cls ?? ""}`)
      .attr("x", (c) => c.x).attr("y", (c) => c.y).attr("text-anchor", "middle").text((c) => c.label);
    // arrows between the columns' headings: the ripple runs left to right
    const arrows = all.selectAll("text.lane-arrow").data((d) => d.cols.slice(1).map((c, i) => ({ key: c.key, x: (d.cols[i].x + c.x) / 2, y: d.y0 + 30 })), (c) => c.key);
    arrows.exit().remove();
    arrows.enter().append("text").merge(arrows).attr("class", "lane-arrow").attr("x", (c) => c.x).attr("y", (c) => c.y)
      .attr("text-anchor", "middle").text("→");
  }

  // DECISION: in the Figure 1 layout, opening entities reflows Figure 1's grid like a table. Each row
  // grows by its tallest open entity and each column by its widest pill, so nothing overlaps, the
  // figure's alignment survives, and closing everything restores the figure exactly. Oct 17: sizes are the ones boxes
  // are growing to, so a row or column opened a moment ago is not measured at its old size (pills overlapped).
  applyFlow() {
    const nodes = [...this.nodes.values()];
    const flowing = nodes.filter((n) => n.kind === "entity" && !this.hasFixedHome(n.id));
    const rows = new Map();
    const cols = new Map();
    const homeOf = (id) => this.fixedHome(id) ?? this.homes.get(id);
    for (const n of flowing) {
      const h = homeOf(n.id);
      if (!h) continue;
      const ry = Math.round(h.y);
      const cx = Math.round(h.x);
      rows.set(ry, Math.max(rows.get(ry) ?? 0, (n.hGoal ?? n.h) - GEOM.HEAD_H));
      cols.set(cx, Math.max(cols.get(cx) ?? 0, (n.wGoal ?? n.w) - GEOM.PILL_MIN_W));
    }
    const ys = [...rows.keys()].sort((a, b) => a - b);
    const xs = [...cols.keys()].sort((a, b) => a - b);
    const yAt = new Map();
    const xAt = new Map();
    let acc = 0;
    ys.forEach((y, i) => { if (i) acc += rows.get(ys[i - 1]); yAt.set(y, y + acc); });
    acc = 0;
    xs.forEach((x, i) => { if (i) acc += (cols.get(xs[i - 1]) + cols.get(x)) / 2; xAt.set(x, x + acc); });
    const flowed = (id) => {
      if (this.hasFixedHome(id)) return this.fixedHome(id);
      const h = this.homes.get(id);
      return h ? { x: xAt.get(Math.round(h.x)) ?? h.x, y: yAt.get(Math.round(h.y)) ?? h.y } : null;
    };
    for (const n of nodes) {
      n.flow = !this.hasFixedHome(n.id) && !n.free;
      const f = flowed(n.id);
      if (f) { n.hx = f.x; n.hy = f.y; }
    }
  }

  // A new free entity grows out of the boxes it interacts with (so it arrives next to them, not in a far grid slot).
  startPosition(b, old) {
    if (!figurePosition(this.layout, b.id) && !this.hasFixedHome(b.id)) {
      const near = (this.view?.entity_links ?? []).flatMap((l) => (l.source === b.id ? [l.target] : l.target === b.id ? [l.source] : []))
        .map((id) => old.get(id)).filter(Boolean);
      if (near.length) {
        const a = (b.id.length * 2.39996) % (Math.PI * 2);      // a stable angle, so siblings fan out
        return { x: near.reduce((t, n) => t + n.x, 0) / near.length + 150 * Math.cos(a),
                 y: near.reduce((t, n) => t + n.y, 0) / near.length + 90 * Math.sin(a) };
      }
    }
    return this.homeOf(b);
  }

  // -- detail: per node, or all at once ---------------------------------------------------------------
  entityName(id) {
    return this.view?.entities.find((e) => e.id === id)?.name ?? id;
  }

  toggleEntity(id, open = null) {
    const want = open ?? !this.ui.expanded.has(id);
    if (want === this.ui.expanded.has(id)) return;
    this.record(`${want ? "open" : "close"} ${this.entityName(id)}`);
    if (want) this.ui.expanded.add(id);
    else this.ui.expanded.delete(id);
    this.recompute("structure");
  }

  // candidate superentities in the panels' lists (they are not drawn on the canvas)
  setShowCandidates(on) {
    this.ui.showCandidates = on;
    this.recompute("structure");
  }

  // -- undo and redo of view changes (open, close, presets, moves, layout) ---------------------------
  // DECISION: undo covers what the user does to the view; decisions on the model itself (approvals,
  // updates) are recorded in the ledger and are not undone from the canvas.
  // `camera`: the change also moves the view (a preset refits it), so undo returns the view as well
  snapshot(camera = false) {
    const t = camera ? this.zoom.transform() : null;
    return { expanded: [...this.ui.expanded], showCandidates: this.ui.showCandidates,
             pinned: [...this.pinnedHomes.entries()].map(([k, v]) => [k, { ...v }]), mode: this.mode,
             camera: t ? { x: t.x, y: t.y, k: t.k } : null };
  }

  record(label, { camera = false } = {}) {
    if (this.quiet) return;
    this.undoStack.push({ label, camera, state: this.snapshot(camera) });
    if (this.undoStack.length > 200) this.undoStack.shift();
    this.redoStack = [];
    this.handlers.onHistory?.(this.undoStack.length, this.redoStack.length);
  }

  restore(state) {
    this.ui.expanded = new Set(state.expanded);
    this.ui.showCandidates = state.showCandidates;
    this.pinnedHomes = new Map(state.pinned.map(([k, v]) => [k, { ...v }]));
    if (state.mode !== this.mode) {
      this.mode = state.mode;
      for (const n of this.nodes.values()) n.flow = false;
      this.handlers.onLayoutMode?.(state.mode);
    }
    this.recompute("structure");
    if (state.camera) this.zoom.set(state.camera, this.opts.reducedMotion ? 0 : 280);
    this.handlers.onHistory?.(this.undoStack.length, this.redoStack.length);
  }

  undo() {
    const e = this.undoStack.pop();
    if (!e) return null;
    this.redoStack.push({ label: e.label, camera: e.camera, state: this.snapshot(e.camera) });
    this.restore(e.state);
    return e.label;
  }

  redo() {
    const e = this.redoStack.pop();
    if (!e) return null;
    this.undoStack.push({ label: e.label, camera: e.camera, state: this.snapshot(e.camera) });
    this.restore(e.state);
    return e.label;
  }

  scheduleAutoDetail(delay = 0) {
    if (!this.autoDetail) return;
    if (delay) this.lod.update(); else this.lod.now();
  }

  // a stable key per world, so what is learned about one demo does not steer another
  useAttention(key) {
    this.attention.flush();
    this.attention = createAttention(key);
    this.lod = createLOD(this, this.attention);
    this.handlers.onZoomChange?.(this.zoom.transform());
  }

  observeAttention() {
    if (!this.model || document.hidden || performance.now() - this.lastMove < 700) return;
    if (document.querySelector("#modal-root")?.innerHTML) return;
    const t = this.zoom.transform();
    const v = this.lod.viewBox(t);
    const rx = (v.x1 - v.x0) / 2;
    const ry = (v.y1 - v.y0) / 2;
    const seen = [];
    for (const n of this.nodes.values()) {
      const dx = (n.x - v.cx) / rx;
      const dy = (n.y - v.cy) / ry;
      const d2 = dx * dx + dy * dy;
      if (d2 > 1) continue;
      seen.push({ id: n.kind === "entity" ? n.id : n.id, w: Math.exp(-2.5 * d2) });
    }
    this.attention.observe(t.k, seen, 0.5);
    this.handlers.onAttention?.();
  }

  // frame the graph (Oct 11): the gravity layout shows all of it, with detail following that zoom, so a view opens on the
  // top of the hierarchy and zooming in opens it level by level; the hand-placed Figure 1 opens at a readable zoom
  frameAll(duration = 0) {
    if (this.mode !== "gravity" || !this.autoDetail) { this.fitReadable(duration); return; }
    this.fit(duration);
    this.personZoomUntil = performance.now() + duration + 200;
    setTimeout(() => this.lod.now(), duration + 40);
  }

  // isolate (Oct 11): show only `keep` (a set of entity ids), laid out fresh; null brings the full graph back where it was
  setIsolation(iso) {
    if (!this.fullView) return;
    if (iso && !this.isolated) this.savedHomes = { grav: new Map(this.gravHomes), mode: this.mode };
    // an isolated graph is always laid out by the hierarchy, even over the hand-placed Figure 1
    if (iso) this.mode = "gravity";
    else if (this.savedHomes) this.mode = this.savedHomes.mode;
    this.isolated = iso;
    this.isoHomes = iso?.homes ?? null;
    this.view = iso ? filterView(this.fullView, iso.keep, { subs: iso.subs, links: iso.links, hulls: iso.hulls }) : this.fullView;
    if (iso) {
      this.gravHomes.clear();
      // a small isolated graph opens its entities, so its values and their links show at once; the transmission
      // grid's isolation (iso.open === false) starts compact, since the grid beside it already shows the values
      this.ui.expanded = new Set(iso.expand ?? (iso.open === false ? [] : iso.keep.size <= 8 ? iso.keep : iso.ids));
      this.lod.reset();
      this.lod.pin(this.ui.expanded);
    } else if (this.savedHomes) {
      this.gravHomes = this.savedHomes.grav;
      this.ui.expanded.clear();
    }
    this.recompute(iso ? "first" : "structure");
    // boxes go straight to their places, so the view frames where they will be, not where they were
    for (const n of this.nodes.values()) { if (n.hx != null) { n.x = n.hx; n.y = n.hy; } }
    this.ticked(true);
    if (!iso) { this.savedHomes = null; this.lod.reset(); setTimeout(() => this.frameAll(320), 60); }
    document.body.classList.toggle("isolated", !!iso);
    this.handlers.onIsolation?.(iso);
  }

  // the point to zoom about: the middle of the view, pulled toward what has been looked at most (screen pixels)
  focusPoint() {
    const t = this.zoom.transform();
    const v = this.lod.viewBox(t);
    let sx = 0;
    let sy = 0;
    let sw = 0;
    for (const n of this.nodes.values()) {
      if (n.x < v.x0 || n.x > v.x1 || n.y < v.y0 || n.y > v.y1) continue;
      const w = this.attention.weight(n.id, t.k);
      if (w <= 0) continue;
      sx += n.x * w; sy += n.y * w; sw += w;
    }
    const wx = sw ? 0.6 * (sx / sw) + 0.4 * v.cx : v.cx;
    const wy = sw ? 0.6 * (sy / sw) + 0.4 * v.cy : v.cy;
    return { x: wx * t.k + t.x, y: wy * t.k + t.y };
  }

  // zoom to scale k about a screen point (the focus point unless given), easing like a map
  zoomToScale(k, { duration = 260, anchor = null } = {}) {
    const t = this.zoom.transform();
    const kk = Math.max(0.2, Math.min(3.5, k));
    const a = anchor ?? this.focusPoint();
    const wx = (a.x - t.x) / t.k;
    const wy = (a.y - t.y) / t.k;
    this.autoFrame = false;
    this.personZoomUntil = performance.now() + duration + 120;
    this.zoom.set({ x: a.x - wx * kk, y: a.y - wy * kk, k: kk }, this.opts.reducedMotion ? 0 : duration);
  }

  // a person opened or closed an entity's values: remembered by detail-follows-zoom, and it teaches the threshold
  toggleEntityByHand(id, open = null) {
    const want = open ?? !this.ui.expanded.has(id);
    if (this.autoDetail) this.lod.hand(id, want);
    this.toggleEntity(id, want);
  }

  // two levels (Oct 17: the superentity level left the canvas with the superentities): every entity closed, or open
  setDetail(level) {
    this.record({ entity: "close every entity", sub: "open every entity" }[level] ?? level, { camera: true });
    if (level === "entity") this.ui.expanded.clear();
    else if (level === "sub") this.ui.expanded = new Set(this.view?.entities.map((e) => e.id) ?? []);
    this.recompute("structure");
    setTimeout(() => this.fit(320), this.opts.reducedMotion ? 30 : 220);
  }

  detailLevel() {
    const nEnt = this.view?.entities.length ?? 0;
    const { expanded } = this.ui;
    if (!expanded.size) return "entity";
    if (expanded.size === nEnt) return "sub";
    return null;
  }

  // Make sure a node is on screen: open its entity if it is a subentity.
  reveal(id) {
    if (!this.view) return false;
    const before = this.snapshot();
    const sub = this.subIndex.get(id);
    const eid = sub ? sub.entity_id : id;
    let changed = false;
    if (sub && !this.ui.expanded.has(eid)) { this.ui.expanded.add(eid); changed = true; }
    if (changed) {
      if (!this.quiet) {
        this.undoStack.push({ label: `show ${sub ? sub.name : this.entityName(eid)}`, state: before });
        this.redoStack = [];
        this.handlers.onHistory?.(this.undoStack.length, this.redoStack.length);
      }
      this.recompute("structure");
    }
    return changed;
  }

  // The walkthrough opens what a step needs to show, measured from the view before the walkthrough
  // began, and closes it again afterwards; none of it enters the undo history.
  peek(ids) {
    if (!this.peeked) this.peeked = { expanded: new Set(this.ui.expanded) };
    const expanded = new Set(this.peeked.expanded);
    for (const id of ids) {
      const sub = this.subIndex.get(id);
      const eid = sub ? sub.entity_id : id;
      if (!this.view?.entities.some((e) => e.id === eid)) continue;
      if (sub) expanded.add(eid);
    }
    const same = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));
    if (same(expanded, this.ui.expanded)) return;
    this.ui.expanded = expanded;
    this.recompute("structure");
  }

  // -- walkthrough overlays: outlined networks and flows along edges -------------------------------
  setOverlayGroups(groups) {
    this.overlayGroups = groups ?? [];
    const sel = this.layers.netlines.selectAll("g.netline").data(this.overlayGroups, (d) => d.key);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "netline").each((d) => { d.fresh = true; });
    enter.append("path").attr("class", "shape").attr("fill-rule", "evenodd");
    const tab = enter.append("g").attr("class", "net-tab");
    tab.append("rect").attr("rx", 7).attr("height", 22).attr("y", -11);
    tab.append("text").attr("x", 8);
    const all = enter.merge(sel);
    all.select("path.shape").attr("stroke", (d) => d.color).attr("fill", (d) => d.color).attr("fill-opacity", 0.08)
      .attr("stroke-dasharray", "5 3").attr("stroke-width", 2);
    all.select("g.net-tab rect").attr("stroke", (d) => d.color).attr("fill", css("--sheet"))
      .attr("width", (d) => textWidth(d.label, TAB_FONT) + 16);
    all.select("g.net-tab text").attr("fill", (d) => d.color).text((d) => d.label);
    this.netSel = all;
    this.contourDirty = true;
    this.ticked(true);
  }

  // emphasize one of the walkthrough's or forecast's network outlines (null: all equal)
  focusOverlay(key) {
    this.netSel?.classed("active", (d) => key != null && d.key === key).classed("dim", (d) => key != null && d.key !== key);
  }

  setFlows(flows) {
    this.flowData = new Map();
    for (const [k, v] of Object.entries(flows ?? {})) {
      const id = String(k).split(/[:~]/)[0];
      if (Math.abs(v) > Math.abs(this.flowData.get(id) ?? 0)) this.flowData.set(id, v);
    }
    this.applyFlows();
  }

  applyFlows() {
    if (!this.edgeSel) return;
    const on = this.flowData.size > 0;
    const flowOf = (d) => d.ids.reduce((m, i) => (Math.abs(this.flowData.get(i) ?? 0) > Math.abs(m) ? this.flowData.get(i) : m), 0);
    this.edgeSel.each((d) => { d.flow = on ? flowOf(d) : 0; d.flowing = Math.abs(d.flow) > 0.02; });
    this.edgeSel.classed("flowing", (d) => d.flowing)
      .select("path.line")
      .style("stroke", (d) => (d.flowing ? (d.flow > 0 ? css("--up") : css("--down")) : null))
      .style("stroke-width", (d) => (d.flowing ? `${1.2 + 2.6 * Math.min(1, Math.abs(d.flow) / 1.2)}px` : null));
    // dashes march along the edge in the causal direction, faster the more it carries
    this.edgeSel.select("path.flow")
      .style("display", (d) => (d.flowing && !this.opts.reducedMotion ? null : "none"))
      .attr("d", (d, i, els) => (d.flowing ? d3.select(els[i].parentNode).select("path.line").attr("d") : null))
      .style("stroke", (d) => (d.flowing ? (d.flow > 0 ? css("--up") : css("--down")) : null))
      .style("stroke-width", (d) => (d.flowing ? `${2 + 2.6 * Math.min(1, Math.abs(d.flow) / 1.2)}px` : null))
      .style("animation-duration", (d) => (d.flowing ? `${(1.6 - 1.0 * Math.min(1, Math.abs(d.flow) / 1.2)).toFixed(2)}s` : null));
  }

  unpeek() {
    if (!this.peeked) return;
    this.ui.expanded = this.peeked.expanded;
    this.peeked = null;
    this.recompute("structure");
  }

  // -- drawing --------------------------------------------------------------------------------------
  draw() {
    this.drawLane();
    this.drawEdges();
    this.drawFrontier();
    this.drawGhosts();
    this.drawFuzzy(false);
    this.drawNodes();
    this.applyFocus();
    this.drawnOnce = true;
    this.applyHighlight();
    this.applyStaged();
    if (this.selection) this.select(this.selection);
    this.ticked(true);
  }

  // a staged review on screen (restructure, Oct 8): what it would add gets a dashed outline, what it would
  // retire a red one, and each value the event moves is tinted by its order (0: the event's own move;
  // 1, 2, 3: the ripple); the interactions on the ripple's paths are drawn heavier
  applyStaged() {
    const st = this.extras.staged ?? null;
    const any = (d, set) => !!st && (d.ids ?? [d.id]).some((i) => set.has(i));
    const touched = (eid) => !!st && this.view.subentities.some((s) => s.entity_id === eid && st.orders.has(s.id));
    document.body.classList.toggle("staging", !!st);
    document.body.classList.toggle("laned", !!st && !!this.laneHomes);
    this.pillSel?.classed("in-lane", (d) => !!this.laneHomes?.has(d.id));
    this.pillSel?.classed("staged-new", (d) => !!st && st.new.has(d.id))
      .classed("staged-retired", (d) => !!st && st.retired.has(d.id))
      .classed("staged-touched", (d) => !!st && !st.new.has(d.id) && touched(d.id));
    this.pillSel?.selectAll("g.row").classed("staged-new", (r) => !!st && st.new.has(r.sid))
      .classed("staged-retired", (r) => !!st && st.retired.has(r.sid))
      .attr("data-order", (r) => (st && st.orders.has(r.sid) ? Math.min(3, st.orders.get(r.sid)) : null));
    this.edgeSel?.classed("staged-new", (d) => any(d, st?.new ?? new Set()))
      .classed("staged-retired", (d) => any(d, st?.retired ?? new Set()))
      .classed("staged-path", (d) => any(d, st?.path ?? new Set()));
  }

  drawNodes() {
    const ents = this.model.boxes;
    const sel = this.layers.nodes.selectAll("g.pill:not(.exiting)").data(ents, (d) => d.id);
    const dur = this.animOK() ? 200 : 0;
    sel.exit().classed("exiting", true).style("pointer-events", "none")
      .transition().duration(dur ? 120 : 0).style("opacity", 0).remove();
    const enter = sel.enter().append("g").attr("class", "pill").attr("tabindex", 0).attr("role", "button")
      .attr("data-kind", "entity");
    const inner = enter.append("g").attr("class", "inner");
    inner.append("rect").attr("class", "halo");
    inner.append("rect").attr("class", "body").attr("rx", 8);
    inner.append("line").attr("class", "sep");
    inner.append("text").attr("class", "name").attr("y", 0.5);
    inner.append("text").attr("class", "dev").attr("y", 0.5);
    inner.append("text").attr("class", "code").attr("y", 0.5);
    inner.append("g").attr("class", "rows");
    inner.append("g").attr("class", "open-slot");
    // a new entity grows in where it is placed
    if (dur) {
      inner.attr("transform", "scale(0.35)").style("opacity", 0)
        .transition().duration(dur + 30).ease(d3.easeBackOut.overshoot(1.05)).attr("transform", "scale(1)").style("opacity", 1);
    }
    const all = enter.merge(sel);
    const subsOf = (d) => this.view.subentities.filter((s) => s.entity_id === d.id);
    all.attr("data-id", (d) => d.id)
      .classed("loose", (d) => d.entity.loose)
      .classed("open", (d) => d.open)
      .classed("fresh", (d) => d.entity.origin !== "construction")
      .attr("aria-label", (d) => `${d.entity.name}, ${(d.entity.category_tags ?? []).join(" ")}${d.open ? ", open" : ""}`)
      .attr("aria-expanded", (d) => String(d.open));
    // its outline: the concept in long-term memory it belongs to (Oct 15)
    const concepts = conceptStyles(this.fullView ?? this.view);
    this.concepts = concepts;
    all.each((d, i, els) => {
      const c = concepts.get(d.entity.generalization_id);
      const el = els[i];
      el.style.setProperty("--concept", c ? c.color : null);
      el.style.setProperty("--concept-w", c ? `${c.width}px` : null);
      el.dataset.concept = c ? c.name : "";
    });
    // an entity opening or closing grows and shrinks rather than jumping
    all.select("rect.body").attr("y", -GEOM.HEAD_H / 2)
      .each((d, i, els) => {
        const el = d3.select(els[i]);
        const was = +el.attr("height");
        const tr = dur && was && (was !== d.h || +el.attr("width") !== d.w) ? el.transition("size").duration(220).ease(d3.easeCubicOut) : el;
        tr.attr("x", -d.w / 2).attr("width", d.w).attr("height", d.h);
      });
    all.select("line.sep").attr("x1", (d) => -d.w / 2 + 1).attr("x2", (d) => d.w / 2 - 1).attr("y1", GEOM.HEAD_H / 2).attr("y2", GEOM.HEAD_H / 2)
      .style("display", (d) => (d.open ? null : "none"));
    const codeW = (d) => textWidth((d.entity.category_tags ?? []).join(" "), "500 12.7px IBM Plex Mono");
    // Oct 17: no ownership stripes (superentities left the canvas); the concept outline says what kind of thing it is
    all.select("text.name").attr("x", (d) => -d.w / 2 + 12)
      .text((d) => truncate(d.entity.name, d.w - 36 - codeW(d) - 14, NAME_FONT));
    all.select("text.code").attr("x", (d) => d.w / 2 - 10).text((d) => (d.entity.category_tags ?? []).join(" "));
    // the largest deviation: ▲ or ▼, with a halo that is solid when today's value was observed and
    // dotted when it came from daily propagation
    const devOf = (d) => {
      let best = null;
      for (const s of subsOf(d)) if (!best || Math.abs(s.z) > Math.abs(best.z)) best = s;
      return best;
    };
    all.each((d) => { d.dev = devOf(d); });
    all.select("text.dev").attr("x", (d) => d.w / 2 - 20 - codeW(d))
      .attr("fill", (d) => (d.dev?.z > 0 ? css("--up") : css("--down")))
      .text((d) => (!d.dev || Math.abs(d.dev.z) < 0.5 ? "" : d.dev.z > 0 ? "▲" : "▼"));
    all.select("rect.halo")
      .attr("x", (d) => -d.w / 2 - 3.5).attr("y", -GEOM.HEAD_H / 2 - 3.5).attr("width", (d) => d.w + 7).attr("height", GEOM.HEAD_H + 7).attr("rx", 10)
      .attr("stroke", (d) => (d.dev?.z > 0 ? css("--up") : css("--down")))
      .attr("stroke-opacity", (d) => (d.dev ? Math.min(0.8, Math.max(0, (Math.abs(d.dev.z) - 0.5) * 0.45)) : 0))
      .classed("dotted", (d) => d.dev && !d.dev.observed_today);
    all.each((d, i, nodes) => this.drawRows(d3.select(nodes[i]).select("g.rows"), d));
    this.pillSel = all;
    this.paintNodes();
    // the open node (Oct 9): the share of the entity's movement the graph does not explain yet; an open entity shows
    // one per value instead, on its rows
    all.each((d, i, nodes) => {
      const slot = d3.select(nodes[i]).select("g.open-slot").style("display", d.open ? "none" : null);
      if (!d.open) openNode(slot, d.w / 2, 0, d.entity.open);
    });
    this.bindNodeEvents(all);
    this.pillSel = all;
  }

  // Color by (Oct 9): one question at a time. "change" tints each pill by its largest move from normal (green up, red
  // down); "open" by how much of its movement the graph does not explain yet (amber: a blind spot); "category" by its
  // first category tag; "none" leaves pills plain. Hues keep one meaning each across the app.
  paintNodes() {
    if (!this.pillSel) return;
    const mode = this.opts.colorBy ?? "change";
    const paper = css("--sheet");
    const fillOf = (d) => {
      if (mode === "change") {
        const z = d.dev?.z ?? 0;
        const a = Math.min(1, Math.max(0, (Math.abs(z) - 0.25) / 3));
        return a ? d3.interpolateRgb(paper, z > 0 ? "#CFE8D6" : "#F2CFC9")(a) : paper;
      }
      if (mode === "open") return d3.interpolateRgb(paper, css("--open-hi"))(Math.max(0, Math.min(1, d.entity.open ?? 1)));
      if (mode === "category") {
        const t = (d.entity.category_tags ?? [])[0];
        return t ? css(`--cat-${t}`) || paper : paper;
      }
      return paper;
    };
    this.pillSel.select("rect.body").style("fill", fillOf);
    document.body.dataset.colorBy = mode;
  }

  // sid -> z to show instead of today's (a forecast's effect), or null for today's state
  setRowOverride(map) {
    this.rowOverride = map && map.size ? map : null;
    this.pillSel?.each((d, i, nodes) => this.drawRows(d3.select(nodes[i]).select("g.rows"), d));
  }

  // An open entity's values, one row each (Oct 17, after the user's notes): its name, a small picture of its posterior
  // in its own unit, and its mean in that unit ("3.88%", "¥156.0 per $", "$109.7bn/yr"); the move from normal in sd is
  // in its hover card (main.js). In Predict, a value the forecast reaches shows the forecast's move instead, in its unit
  // where it can ("▲2.4%" for a value that moves in logs, "▲0.25pp" for a rate).
  drawRows(g, d) {
    const rows = d.open ? d.rows.map((sid, k) => ({ sid, k, s: this.subIndex.get(sid), w: d.w, eid: d.id })) : [];
    const labels = rowLabels(rows.map((r) => r.s ?? { id: r.sid }));
    const anim = this.animOK();
    const rs = g.selectAll("g.row:not(.exiting)").data(rows, (r) => r.sid);
    // closing an entity: its values fade as the box shrinks around them
    if (anim) rs.exit().classed("exiting", true).style("pointer-events", "none").transition().duration(120).style("opacity", 0).remove();
    else rs.exit().remove();
    const re = rs.enter().append("g").attr("class", "row").attr("data-kind", "subentity").attr("tabindex", 0).attr("role", "button");
    re.append("rect").attr("class", "bg").attr("rx", 4);
    re.append("circle").attr("class", "obs").attr("r", 3);
    re.append("text").attr("class", "rname").attr("y", 0.5);
    re.append("g").attr("class", "glyph");
    re.append("text").attr("class", "rz").attr("y", 0.5);
    re.append("g").attr("class", "open-slot");
    const ra = re.merge(rs);
    ra.attr("data-id", (r) => r.sid).attr("transform", (r) => `translate(0,${rowCenterY(r.k)})`).classed("alt", (r) => r.k % 2 === 1)
      .attr("aria-label", (r) => r.s?.name ?? r.sid);
    ra.select("rect.bg").attr("x", (r) => -r.w / 2 + 4).attr("width", (r) => r.w - 8).attr("y", -GEOM.ROW_H / 2 + 1).attr("height", GEOM.ROW_H - 2);
    ra.select("circle.obs").attr("cx", (r) => -r.w / 2 + 13)
      .attr("fill", (r) => (r.s?.observed_today ? css("--ink-2") : "none"))
      .attr("stroke", (r) => (r.s?.observed === false ? css("--ink-3") : css("--ink-2")))
      .attr("stroke-dasharray", (r) => (r.s?.observed_today ? null : "1.5 1.5"));
    // a forecast shown in Predict (Oct 11): the values it reaches show its effect, not today's state
    const zOf = (r) => this.rowOverride?.get(r.sid);
    const textOf = (r) => (this.rowOverride?.has(r.sid) ? fmtMove(+zOf(r), r.s) : r.s ? fmtValue(r.s.summary?.mean, r.s.unit) : "");
    // the values' column is as wide as the widest of this entity's, so the curves line up
    const valW = Math.max(valueWidth(rows.map((r) => r.s).filter(Boolean)),
                          ...rows.filter((r) => this.rowOverride?.has(r.sid)).map((r) => textWidth(textOf(r), ROW_GEOM.VAL_FONT)));
    const glyphX = (r) => r.w / 2 - ROW_GEOM.RIGHT - valW - ROW_GEOM.GAP - ROW_GEOM.GLYPH_W / 2;
    ra.select("text.rname").attr("x", (r) => -r.w / 2 + ROW_GEOM.LEFT)
      .text((r) => truncate(labels.get(r.sid) ?? r.sid, r.w - ROW_GEOM.LEFT - ROW_GEOM.RIGHT - valW - 2 * ROW_GEOM.GAP - ROW_GEOM.GLYPH_W - 4, ROW_GEOM.ROW_FONT));
    ra.each((r, i, nodes) => {
      const gl = d3.select(nodes[i]).select("g.glyph").attr("transform", `translate(${glyphX(r)},0)`);
      // the posterior in its own unit (the server's points are native values); the tick marks its mean. Redrawn only
      // when the distribution changes; a change cross-fades in, so a moved value is seen to move
      const sig = r.s?.density ? `${r.s.density.length}|${r.s.density[0]}|${r.s.density.at(-1)}|${r.s.density[r.s.density.length >> 1]}|${r.s.summary?.mean}` : "";
      const glNode = gl.node();
      if (glNode.__sig === sig) return;
      const changed = glNode.__sig != null;
      glNode.__sig = sig;
      densityCurve(gl, r.s?.density, { width: ROW_GEOM.GLYPH_W, height: 10, marker: r.s?.summary?.mean });
      if (anim && changed) gl.interrupt().style("opacity", 0.25).transition().duration(260).style("opacity", 1);
    });
    ra.select("text.rz").attr("x", (r) => r.w / 2 - ROW_GEOM.RIGHT)
      .classed("forecast", (r) => !!this.rowOverride?.has(r.sid))
      .attr("fill", (r) => {
        if (!this.rowOverride?.has(r.sid)) return css("--ink-2");
        const z = +zOf(r);
        return z > 0.25 ? css("--up") : z < -0.25 ? css("--down") : css("--ink-3");
      })
      .each((r, i, els) => {
        // a value that changes counts to its new reading (the mean, or the forecast's move)
        const el = els[i];
        const fc = !!this.rowOverride?.has(r.sid);
        const v = fc ? +zOf(r) : r.s?.summary?.mean ?? null;
        const was = el.__v;
        const wasFc = el.__fc;
        el.__v = v;
        el.__fc = fc;
        const sel = d3.select(el);
        const fmt = (x) => (fc ? fmtMove(x, r.s) : fmtValue(x, r.s?.unit));
        const moved = v != null && was != null && wasFc === fc && Number.isFinite(was) && Number.isFinite(v)
          && Math.abs(was - v) > 1e-9 * Math.max(1, Math.abs(v)) && fmt(was) !== fmt(v);
        if (anim && moved) {
          sel.interrupt("value").transition("value").duration(320).ease(d3.easeCubicOut)
            .tween("text", () => { const f = d3.interpolateNumber(was, v); return (t) => { el.textContent = fmt(f(t)); }; });
        } else {
          sel.interrupt("value");
          el.textContent = v == null ? "" : textOf(r);
        }
      });
    ra.each((r, i, nodes) => openNode(d3.select(nodes[i]).select("g.open-slot"), r.w / 2, 0, r.s?.open, { min: 1.5, max: 4, stub: 2.5 }));
    ra.on("click", (ev, r) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "subentity", id: r.sid }); })
      .on("dblclick", (ev) => ev.stopPropagation())
      .on("contextmenu", (ev, r) => { ev.preventDefault(); ev.stopPropagation(); this.handlers.onContext?.(ev, { kind: "subentity", id: r.sid }); })
      .on("keydown", (ev, r) => {
        if (ev.key === "Enter") { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "subentity", id: r.sid }); }
        if (ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
          ev.preventDefault();
          ev.stopPropagation();
          const b = ev.currentTarget.getBoundingClientRect();
          this.handlers.onContext?.({ clientX: b.left + 20, clientY: b.bottom, keyboard: true }, { kind: "subentity", id: r.sid });
        }
      })
      .on("mouseenter", (ev, r) => { this.setFocus({ box: r.eid, row: r.k }); this.handlers.onHover?.(ev, { kind: "subentity", id: r.sid }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", (ev, r) => { this.setFocus({ box: r.eid }); this.handlers.onHover?.(null); });
  }

  // A single click selects after a short pause, so a double-click only opens or closes the node.
  delayedSelect(sel) {
    clearTimeout(this.clickTimer);
    this.clickTimer = setTimeout(() => this.handlers.onSelect?.(sel), 230);
  }

  bindNodeEvents(sel) {
    this.dragBehavior(sel);
    sel.on("click", (ev, d) => { ev.stopPropagation(); this.delayedSelect({ kind: "entity", id: d.id }); })
      .on("dblclick", (ev, d) => { ev.stopPropagation(); clearTimeout(this.clickTimer); this.toggleEntityByHand(d.id); })
      .on("contextmenu", (ev, d) => { ev.preventDefault(); ev.stopPropagation(); this.handlers.onContext?.(ev, { kind: "entity", id: d.id }); })
      .on("keydown", (ev, d) => {
        if (ev.target !== ev.currentTarget) return;
        if (ev.key === "Enter") this.handlers.onSelect?.({ kind: "entity", id: d.id });
        else if (ev.key === "o" || ev.key === "O") this.toggleEntity(d.id);
        else if (ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
          ev.preventDefault();
          const r = ev.currentTarget.getBoundingClientRect();
          this.handlers.onContext?.({ clientX: r.left, clientY: r.top + 34, keyboard: true }, { kind: "entity", id: d.id });
        }
      })
      .on("mouseenter", (ev, d) => { this.setFocus({ box: d.id }); this.handlers.onHover?.(ev, { kind: "entity", id: d.id }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => { this.setFocus(null); this.handlers.onHover?.(null); });
  }

  dragBehavior(sel) {
    const drag = d3.drag()
      .filter((ev) => !this.handlers.isDrawMode?.() && !ev.button && !ev.target.closest?.("g.row"))
      .on("start", (ev, d) => {
        const n = this.nodes.get(d.id);
        if (!n) return;
        if (!ev.active) this.sim.alphaTarget(0.25).restart();
        n.fx = n.x; n.fy = n.y; n.dragging = true;
      })
      .on("drag", (ev, d) => {
        const n = this.nodes.get(d.id);
        if (!n) return;
        n.fx = ev.x; n.fy = ev.y;
      })
      .on("end", (ev, d) => {
        const n = this.nodes.get(d.id);
        if (!n) return;
        if (!ev.active) this.sim.alphaTarget(0);
        n.dragging = false;
        // DECISION: a dropped node keeps its new place as its home (it is pinned there), so the
        // layout does not pull it back; "Return to its place" in its menu unpins it
        if (Math.hypot(n.fx - n.hx, n.fy - n.hy) > 4) {
          this.record(`move ${this.entityName(n.id)}`);
          this.pinnedHomes.set(n.id, { x: n.fx, y: n.fy });
          n.hx = n.fx; n.hy = n.fy;
          n.pinned = true;
        }
        n.fx = null; n.fy = null;
        if (this.mode === "figure1" && n.kind === "entity") this.applyFlow();
      });
    sel.call(drag);
  }

  unpin(id) {
    this.record(`return ${this.entityName(id)} to its place`);
    this.pinnedHomes.delete(id);
    const n = this.nodes.get(id);
    if (n) {
      n.pinned = false;
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
    if (this.mode === "figure1") this.applyFlow();
    this.sim.alpha(0.5).restart();
  }

  resetLayout() {
    this.record("return every node to its place");
    this.pinnedHomes.clear();
    this.relayout(true);                 // gravity lays the graph out anew
    for (const n of this.nodes.values()) {
      n.pinned = false;
      const h = this.homeOf(n.box);
      n.hx = h.x; n.hy = h.y;
    }
    if (this.mode === "figure1") this.applyFlow();
    this.sim.alpha(0.8).restart();
  }

  drawEdges() {
    let data = this.model.edges;
    if (this.opts.figure1LinksOnly) data = data.filter((d) => !d.demo);
    const internal = this.model.internal.map((x) => ({ ...x, key: `int:${x.id}`, internalArc: true }));
    const all = [...data, ...internal];
    const sel = this.layers.edges.selectAll("g.edge:not(.exiting)").data(all, (d) => d.key);
    // DECISION (Oct 14): only a genuine change animates. An edge whose interactions are still drawn (re-anchored because
    // an entity opened) is swapped at once; one whose interactions left the view fades out, and
    // one whose interactions are new draws itself in from its cause (enterEdges, once it has a path).
    const ids = new Set(all.flatMap((d) => d.ids ?? []));
    const before = this.drawnIds ?? null;
    this.drawnIds = ids;
    const anim = this.animOK();
    sel.exit().each((d, i, els) => {
      const gone = !(d.ids ?? []).some((x) => ids.has(x));
      if (!anim || !gone) { els[i].remove(); return; }
      d3.select(els[i]).classed("exiting", true).classed("entering", false).style("pointer-events", "none")
        .transition("exit").duration(EDGE_OUT_MS).ease(d3.easeCubicOut).style("opacity", 0).remove();
    });
    const enter = sel.enter().append("g").attr("class", "edge");
    if (anim && before) enter.filter((d) => !(d.ids ?? []).some((x) => before.has(x))).classed("entering", true);
    enter.append("path").attr("class", "hit");
    enter.append("path").attr("class", "line");
    enter.append("path").attr("class", "flow");
    enter.append("text").attr("class", "label").attr("dy", -5);
    enter.append("text").attr("class", "badge-l").text("L");
    const a = enter.merge(sel);
    a.classed("learned", (d) => d.learned).classed("demo", (d) => !!d.demo)
      .classed("hedged", (d) => !!d.hedge);
    // a hedged edge (one candidate of a fuzzy end) is as visible as it is probable
    a.style("opacity", (d) => (d.hedge ? (0.3 + 0.7 * Math.min(1, d.hedgeP)).toFixed(2) : null));
    // a weight that changes (an interaction's significance) eases to its new width
    const widthOf = (d) => (d.learned ? 0.9 + 1.4 * Math.min(1, d.sig) : 1 + 2.2 * Math.min(1, d.sig));
    a.select("path.line").each((d, i, els) => {
      const el = els[i];
      const w = +widthOf(d).toFixed(2);
      const was = el.__w;
      el.__w = w;
      if (anim && was != null && Math.abs(was - w) > 0.15) d3.select(el).transition("width").duration(280).attr("stroke-width", w);
      else if (was !== w) el.setAttribute("stroke-width", w);
    });
    a.select("path.line")
      .attr("marker-end", (d) => (d.learned ? "url(#arr-learned)" : "url(#arr)"))
      .attr("marker-start", (d) => (d.bidir ? "url(#arr-s)" : null));
    a.select("text.label").text((d) => (d.hedge ? `≈ ${Math.round(100 * d.hedgeP)}% · ${d.label ?? ""}` : d.label ?? ""));
    a.select("text.badge-l").style("display", (d) => (d.learned ? null : "none"));
    this.edgeSel = a;
    this.applyFlows();
    a.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "interaction", id: d.ids[0], ids: d.ids }); })
      .on("contextmenu", (ev, d) => { ev.preventDefault(); ev.stopPropagation(); this.handlers.onContext?.(ev, { kind: "edge", ids: d.ids }); })
      .on("mouseenter", (ev, d) => { this.setFocus({ edge: d.key }); this.handlers.onHover?.(ev, { kind: "link", ids: d.ids }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => { this.setFocus(null); this.handlers.onHover?.(null); });
    this.edgeSel = a;
    this.pendingDrawIn = anim && !enter.filter(".entering").empty();
  }

  // Motion is for genuine changes only: never before the first view, never with reduced motion (the app setting or
  // the system's), and never while the view moves (zooming and panning slide one buffered layer; nothing animates in it).
  animOK() {
    if (!this.drawnOnce || this.opts.reducedMotion) return false;
    if (document.body.classList.contains("reduced-motion") || document.body.classList.contains("zooming")) return false;
    if (this.container?.classList?.contains("buffering") || this.svg.node().parentNode?.classList?.contains("buffering")) return false;
    return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  }

  // New interactions draw themselves in, from cause to effect, once they have a path: the stroke is dashed to its own
  // length and the dash slides in, then the dash is cleared so dashed styles (learned, hedged, staged) apply again. The
  // arrowhead and the label wait for the line to arrive (CSS: .edge.entering).
  enterEdges() {
    if (!this.pendingDrawIn) return;
    this.pendingDrawIn = false;
    this.edgeSel?.filter(".entering").each((d, i, els) => {
      const g = els[i];
      const line = g.querySelector("path.line");
      const L = line?.getAttribute("d") ? line.getTotalLength() : 0;
      const done = () => { g.classList.remove("entering"); line?.style.removeProperty("stroke-dasharray"); line?.style.removeProperty("stroke-dashoffset"); };
      if (!(L > 0)) { done(); return; }
      const len = L + 24;      // a little slack, for a path that grows while the layout settles
      line.style.strokeDasharray = `${len} ${len}`;
      line.style.strokeDashoffset = `${len}`;
      d3.select(line).transition("draw").delay(60).duration(EDGE_IN_MS).ease(d3.easeCubicOut)
        .styleTween("stroke-dashoffset", () => (t) => `${len * (1 - t)}`)
        .on("end", done).on("interrupt", done);
    });
  }

  drawFrontier() {
    const data = this.model.frontier;
    const sel = this.layers.frontier.selectAll("g.frontier:not(.exiting)").data(data, (d) => d.id);
    const fade = this.animOK() ? EDGE_OUT_MS : 0;
    sel.exit().classed("exiting", true).style("pointer-events", "none")
      .transition("exit").duration(fade).style("opacity", 0).remove();
    const enter = sel.enter().append("g").attr("class", "frontier");
    if (fade) enter.style("opacity", 0).transition("enter").delay(60).duration(EDGE_IN_MS).style("opacity", 1);
    enter.append("path").attr("class", "hit").attr("stroke", "transparent").attr("stroke-width", 12).attr("fill", "none");
    enter.append("path").attr("class", "line").attr("marker-end", "url(#arr-front)");
    enter.append("text").attr("class", "label").attr("dy", -5);
    const all = enter.merge(sel);
    all.select("text.label").text((d) => (d.status === "promotion_proposed" ? "co-moves · promotion proposed" : d.seeded ? "co-moves" : ""));
    all.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "frontier", id: d.id }); })
      .on("mouseenter", (ev, d) => this.handlers.onHover?.(ev, { kind: "frontier", entry: d }))
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => this.handlers.onHover?.(null));
    this.frontSel = all;
  }

  drawGhosts() {
    if (!this.model) return;
    const edges = this.extras.ghostEdges ?? [];
    const sel = this.layers.ghosts.selectAll("path.ghost-edge").data(edges, (d) => d.key);
    sel.exit().transition().duration(150).style("opacity", 0).remove();
    this.ghostSel = sel.enter().append("path").attr("class", "ghost-edge").attr("marker-end", "url(#arr-ghost)").merge(sel)
      .attr("stroke", (d) => (d.hyp ? css("--hyp-line") : css("--real-line")));
    const subs = (this.extras.ghostSubs ?? []).filter((g) => !this.subIndex.has(g.id));
    const gs = this.layers.ghosts.selectAll("g.ghost-sub").data(subs, (d) => d.id);
    gs.exit().remove();
    const ge = gs.enter().append("g").attr("class", "ghost-sub");
    ge.append("rect").attr("rx", 6).attr("height", 18).attr("y", -9).attr("fill", css("--sheet"))
      .attr("stroke", css("--real-line")).attr("stroke-dasharray", "3 2");
    ge.append("text").attr("x", 8).attr("dy", 3.5).attr("font-size", 10).attr("fill", css("--real-ink"));
    this.ghostSubSel = ge.merge(gs);
    this.ghostSubSel.select("text").text((d) => `+ ${prettyNode(d.id.split(".").slice(1).join("."))}`);
    this.ghostSubSel.select("rect").attr("width", (d) => 20 + 5.6 * prettyNode(d.id.split(".").slice(1).join(".")).length);
  }

  anchorFor(end) {
    if (!end) return null;
    const ref = String(end.ref ?? "").replace(/^new:/, "");
    if (end.level === "subentity") {
      const p = this.posOf(ref);
      if (p) return p;
      const e = this.posOf(ref.split(".")[0]);
      return e ? { x: e.x, y: e.y + 14 } : null;
    }
    if (end.level === "entity") return this.posOf(ref);
    // a generalization: a soft blob around its candidate entities (ids, or [id, score] pairs), else
    // around every entity the taxonomy places under it
    let ids = (end.candidates ?? []).map((c) => (Array.isArray(c) ? c[0] : c));
    if (!ids.length && this.generalizationMembers) ids = this.generalizationMembers(ref) ?? [];
    const rects = [...new Set(ids.map((id) => this.model?.boxOfEntity(id)).filter(Boolean))]
      .map((b) => this.nodes.get(b)).filter(Boolean).map(rectOf);
    if (rects.length) {
      const poly = hullPolygon(rects, 10);
      const c = d3.polygonCentroid(poly);
      return { x: c[0], y: c[1], blob: poly };
    }
    return { x: -260, y: 170, blob: [[-310, 148], [-210, 148], [-196, 170], [-210, 192], [-310, 192], [-324, 170]] };
  }

  drawFuzzy(animate) {
    if (!this.model) return;
    this.fuzzySel = drawRibbons(this.layers.fuzzy, this.extras.ribbons ?? [], (end) => this.anchorFor(end), {
      real: css("--real-line"), hyp: css("--hyp-line"), realFill: css("--real-fill"), hypFill: css("--hyp-fill"),
      realInk: css("--real-ink"), hypInk: css("--hyp-ink"),
      fuzzy: css("--loose-line"), fuzzyFill: css("--rule-soft"), fuzzyInk: css("--ink-2"),
    }, { animate: animate && !this.opts.reducedMotion, duration: this.opts.reducedMotion ? 120 : 340 });
    this.labelsDirty = true;
  }

  // Labels never sit on other text. Every label that is showing (a focused edge's, every edge's when
  // "every link label" is on, the frontier's, the fuzzy ribbons') tries spots along its own
  // path, the most important first, and takes the first spot clear of every box and label placed
  // before it; a label with no free spot is hidden (hovering its edge shows it in the tooltip).
  layoutLabels() {
    if (!this.model || !this.edgeSel) return;
    this.labelsDirty = false;
    const occupied = [];
    for (const n of this.nodes.values()) {
      const r = rectOf(n);
      occupied.push({ x0: r.x0 - 3, x1: r.x1 + 3, y0: r.y0 - 3, y1: r.y1 + 3 });
    }
    const free = (r) => !occupied.some((o) => r.x0 < o.x1 && r.x1 > o.x0 && r.y0 < o.y1 && r.y1 > o.y0);
    const labelsOn = document.body.classList.contains("labels");
    const items = [];
    this.edgeSel.each((d, i, els) => {
      const g = els[i];
      const t = g.querySelector("text.label");
      const badge = g.querySelector("text.badge-l");
      const focus = g.classList.contains("focus");
      const shown = !!d.label && (labelsOn || focus) && g.style.display !== "none";
      if (!shown) {
        t.classList.add("lbl-hidden");
        badge?.classList.toggle("lbl-hidden", !d.learned);
        // a learned edge without its label still shows its "L", at the middle of its own path
        if (badge && d.learned) {
          if (g.__route) {
            const m = cubicAt(g.__route, 0.5);
            badge.setAttribute("x", m[0] + 4);
            badge.setAttribute("y", m[1] - 4);
          } else badge.classList.add("lbl-hidden");
        }
        return;
      }
      items.push({ el: t, badge: d.learned ? badge : null, route: g.__route, text: d.label,
                   font: "500 11.5px Instrument Sans", h: 15, pri: (focus ? 2 : 0) + d.sig, now: focus });
    });
    this.frontSel?.each((d, i, els) => {
      const g = els[i];
      const t = g.querySelector("text.label");
      if (!t.textContent || g.style.display === "none" || t.style.display === "none") { t.classList.add("lbl-hidden"); return; }
      items.push({ el: t, route: g.__route, text: t.textContent, font: "500 11.5px Instrument Sans", h: 15, pri: 1.5 });
    });
    // steadiness (Oct 11): a label on screen keeps its place in the queue and tries its last spot first; a hidden one
    // comes back only once it has had room LABEL_SETTLE layouts in a row, so labels do not blink while boxes move
    for (const it of items) if (!it.el.classList.contains("lbl-hidden")) it.pri += 1;
    items.sort((a, b) => b.pri - a.pri);
    const FS = [0.5, 0.4, 0.6, 0.3, 0.7, 0.22, 0.78];
    let waiting = false;
    for (const it of items) {
      const w = textWidth(it.text, it.font) + 8;
      const was = it.el.__lbl;
      let spot = null;
      // spots along the edge's own curve (its route, so no layout is read back from the page)
      if (it.route) {
        const tries = FS.flatMap((f) => [-5, 15].map((dy) => [f, dy]));
        if (was?.f != null) tries.unshift([was.f, was.dy]);
        for (const [f, dy] of tries) {
          const [px, py] = cubicAt(it.route, f);
          const r = { x0: px - w / 2, x1: px + w / 2, y0: py + dy - it.h + 3, y1: py + dy + 4 };
          if (free(r)) { spot = { x: px, y: py + dy + 5, r, f, dy }; break; }
        }
      }
      const hidden = it.el.classList.contains("lbl-hidden");
      const ok = spot ? (was?.ok ?? 0) + 1 : 0;
      it.el.__lbl = { f: spot?.f ?? was?.f, dy: spot?.dy ?? was?.dy, ok };
      if (!spot || (hidden && ok < LABEL_SETTLE && !it.now)) {
        if (spot) waiting = true;
        it.el.classList.add("lbl-hidden");
        it.badge?.classList.add("lbl-hidden");
        continue;
      }
      it.el.classList.remove("lbl-hidden");
      it.el.setAttribute("x", spot.x);
      it.el.setAttribute("y", spot.y);
      occupied.push(spot.r);
      if (it.badge) {
        const b = { x0: spot.r.x1 + 2, x1: spot.r.x1 + 11, y0: spot.r.y0, y1: spot.r.y1 };
        const ok = free(b);
        it.badge.classList.toggle("lbl-hidden", !ok);
        if (ok) { it.badge.setAttribute("x", b.x0); it.badge.setAttribute("y", spot.y); occupied.push(b); }
      }
    }
    // a label waiting to come back gets its next layouts even when nothing moves
    clearTimeout(this.labelTimer);
    if (waiting) this.labelTimer = setTimeout(() => this.layoutLabels(), 90);
    // the fuzzy ribbons' labels: above the middle of the ribbon, else along it, else hidden
    this.fuzzySel?.each((d, i, els) => {
      const t = els[i].querySelector("text.fuzzy-label");
      if (!t || !t.textContent) return;
      const w = textWidth(t.textContent, "600 11.5px Instrument Sans") + 8;
      const pts = d.b
        ? [0.5, 0.35, 0.65, 0.2, 0.8].map((f) => {
          const mx = (d.a.x + d.b.x) / 2;
          const my = (d.a.y + d.b.y) / 2 - 24;
          const u = 1 - f;
          return [u * u * d.a.x + 2 * u * f * mx + f * f * d.b.x, u * u * d.a.y + 2 * u * f * my + f * f * d.b.y];
        })
        : [[d.a.x + 18, d.a.y], [d.a.x + 18, d.a.y + 36]];
      let spot = null;
      for (const [x, y] of pts) {
        for (const dy of [-14, 16]) {
          const r = { x0: x - w / 2, x1: x + w / 2, y0: y + dy - 12, y1: y + dy + 4 };
          if (free(r)) { spot = { x, y: y + dy, r }; break; }
        }
        if (spot) break;
      }
      if (!spot) { t.classList.add("lbl-hidden"); return; }
      t.classList.remove("lbl-hidden");
      t.setAttribute("x", spot.x);
      t.setAttribute("y", spot.y);
      occupied.push(spot.r);
    });
  }

  // -- focus (hover or selection brings a node's edges forward) ------------------------------------------
  setFocus(f) {
    this.hoverFocus = f;
    this.applyFocus();
  }

  applyFocus() {
    const f = this.hoverFocus ?? this.selFocus ?? null;
    if (!this.edgeSel) return;
    if (!f) {
      this.edgeSel.classed("focus", false).classed("unfocus", false);
      this.frontSel?.classed("unfocus", false);
      this.applyKinFocus(null);
      this.layoutLabels();
      return;
    }
    const hit = (d) => {
      if (f.edge) return d.key === f.edge;
      if (f.group) {
        const g = this.groupsInfo.byKey.get(f.group);
        const ids = new Set(g?.hulls.flatMap((h) => h.interaction_ids ?? []) ?? []);
        return d.ids.some((i) => ids.has(i));
      }
      if (d.internalArc) return d.box === f.box && (f.row == null || d.ra === f.row || d.rb === f.row);
      const ends = [d.a, d.b];
      return ends.some((e) => e.box === f.box && (f.row == null || e.row === f.row));
    };
    // the rest step back, still visible: hovering focuses, it does not hide
    this.edgeSel.classed("focus", hit).classed("unfocus", (d) => !hit(d));
    this.frontSel?.classed("unfocus", (d) => !(d.a.box === f.box || d.b.box === f.box));
    this.applyKinFocus(f);
    this.layoutLabels();
  }

  // hovering a value lights the same value in similar entities (its kin: every airline's jet fuel cost): the
  // rows of other open entities, and the pills of closed entities that have one
  applyKinFocus(f) {
    const box = f?.box != null && f.row != null ? this.model?.boxes.find((b) => b.id === f.box) : null;
    const sid = box?.kind === "entity" && box.open ? box.rows[f.row] : null;
    const key = sid ? kinKey(this.subIndex.get(sid), this.entIndex) : null;
    const kin = (x) => !!key && kinKey(this.subIndex.get(x), this.entIndex) === key;
    const has = (eid) => !!key && eid !== box.id && (this.entIndex.get(eid)?.subentity_ids ?? []).some(kin);
    this.pillSel?.classed("kin", (d) => !d.open && has(d.id));
    this.pillSel?.selectAll("g.row").classed("kin", (r) => r.sid !== sid && r.eid !== box?.id && kin(r.sid));
  }

  // -- tick -------------------------------------------------------------------------------------------
  ticked(force = false) {
    if (!this.view || !this.model) return;
    this.lastTickAt = performance.now();
    const nodes = [...this.nodes.values()];
    for (const n of nodes) {
      if (n.hGoal == null) continue;
      n.w += (n.wGoal - n.w) * 0.3;
      n.h += (n.hGoal - n.h) * 0.3;
      if (Math.abs(n.hGoal - n.h) < 0.5 && Math.abs(n.wGoal - n.w) < 0.5) { n.w = n.wGoal; n.h = n.hGoal; n.hGoal = n.wGoal = null; }
      else if (this.sim.alpha() < 0.05) this.sim.alpha(0.05);
    }
    // in the gravity layout the homes never overlap, so boxes glide through one another to them; pushing them apart on
    // the way could stop two that must swap places
    if (!this.blocks()) resolveCollisions(nodes, 3);
    if (this.sim.alpha() < 0.02) {
      for (const n of nodes) {
        if (n.fx == null && Math.hypot(n.x - n.hx, n.y - n.hy) < 0.6) { n.x = n.hx; n.y = n.hy; }
      }
    }
    this.pillSel?.attr("transform", (d) => { const n = this.nodes.get(d.id); return n ? `translate(${n.x},${n.y})` : null; });
    this.tickEdges();
    this.enterEdges();
    this.tickFrontier();
    this.tickGhosts();
    this.tickCount += 1;
    if (force || this.contourDirty || (this.netSel?.size() && this.tickCount % 2 === 0 && this.moved())) this.updateContours();
    if (this.fuzzySel && this.sim.alpha() > 0.03) this.drawFuzzy(false);
    this.tickOverlays();
    if (force || this.labelsDirty || this.tickCount % 5 === 0) this.layoutLabels();
  }

  moved() {
    for (const n of this.nodes.values()) {
      const p = this.lastContourPos.get(n.id);
      if (!p || Math.abs(p[0] - n.x) > 0.5 || Math.abs(p[1] - n.y) > 0.5 || p[2] !== n.h) return true;
    }
    return false;
  }

  centerOf(anchor) {
    const n = this.nodes.get(anchor.box);
    if (!n) return null;
    if (anchor.row >= 0) return { x: n.x, y: n.y + rowCenterY(anchor.row) };
    const r = rectOf(n);
    return { x: (r.x0 + r.x1) / 2, y: (r.y0 + r.y1) / 2 };
  }

  // the arrowhead an edge ends in, and so how far its curve stops short of the border (see makeMarkers)
  arrowOf() {
    return ARROW;
  }

  // Every edge and frontier co-movement, routed together (graph/edge-route.js): ports spread along the borders, curves
  // clipped to them, detours around other boxes. While the layout moves this runs once a tick; at rest, once.
  routeAll() {
    const specs = [];
    this.edgeSel?.each((d) => {
      if (d.internalArc) return;
      specs.push({ key: d.key, a: d.a, b: d.b, gapA: d.bidir ? ARROW : 1, gapB: this.arrowOf(d) });
    });
    this.frontSel?.each((d) => specs.push({ key: `front:${d.id}`, a: d.a, b: d.b, gapA: 1, gapB: ARROW }));
    this.routes = routeEdges(specs, this.nodes, { rowY: rowCenterY, headH: GEOM.HEAD_H, obstacles: [] });
  }

  tickEdges() {
    this.routeAll();
    const setD = (el, dAttr) => { if (el && el.__d !== dAttr) { el.__d = dAttr; el.setAttribute("d", dAttr); } };
    this.edgeSel?.each((d, i, els) => {
      const g = els[i];
      let r;
      if (d.internalArc) {
        const n = this.nodes.get(d.box);
        if (n) {
          // two values of one entity: a loop out of its right side and back, ending in an arrow on the border
          const x = n.x + n.w / 2;
          const ya = n.y + rowCenterY(d.ra);
          const yb = n.y + rowCenterY(d.rb);
          const bulge = 16 + 4 * Math.abs(d.rb - d.ra);
          r = { p0: [x + 1, ya], c1: [x + bulge, ya], c2: [x + bulge, yb], p3: [x + this.arrowOf(d), yb] };
          r.d = `M${r.p0[0]} ${r.p0[1]}C${r.c1[0]} ${r.c1[1]} ${r.c2[0]} ${r.c2[1]} ${r.p3[0]} ${r.p3[1]}`;
        }
      } else r = this.routes.get(d.key);
      if (!r) { if (g.style.display !== "none") g.style.display = "none"; return; }
      if (g.style.display === "none") g.style.display = "";
      g.__route = r;
      setD(g.querySelector("path.line"), r.d);
      setD(g.querySelector("path.hit"), r.d);
      if (d.flowing) setD(g.querySelector("path.flow"), r.d);
      // labels are placed by layoutLabels (clear of other text)
    });
  }

  tickFrontier() {
    this.frontSel?.each((d, i, els) => {
      const g = d3.select(els[i]);
      const r = this.routes?.get(`front:${d.id}`);
      if (!r) { g.style("display", "none"); return; }
      g.style("display", null);
      els[i].__route = r;
      g.select("path.line").attr("d", r.d);
      g.select("path.hit").attr("d", r.d);
      const a = this.centerOf(d.a);
      const b = this.centerOf(d.b);
      const long = a && b && Math.hypot(a.x - b.x, a.y - b.y) > 90;
      // its position is chosen by layoutLabels, clear of other text
      g.select("text.label").style("display", long ? null : "none");
    });
  }

  tickGhosts() {
    this.ghostSel?.attr("d", (d) => {
      const a = this.posOf(d.a);
      const b = this.posOf(d.b);
      if (!a || !b) return null;
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2 - 26;
      return `M${a.x} ${a.y}Q${mx} ${my} ${b.x} ${b.y}`;
    });
    this.ghostSubSel?.attr("transform", (d) => {
      const n = this.nodes.get(this.model?.boxOfEntity(d.id.split(".")[0]) ?? "");
      return n ? `translate(${n.x + n.w / 2 + 8},${n.y + n.oy + n.h + 4})` : "translate(-9999,-9999)";
    });
  }

  // the gravity layout places every box (graph/layout-hier.js), so homes never overlap and each box glides straight home
  // (Oct 11, "blocks"); Oct 17: the blocks are the taxonomy's concepts, not drawn
  blocks() {
    return this.mode === "gravity" && !this.opts.groupByCategory;
  }

  // the world-space box the view shows, grown by `margin` of its size on each side
  viewWorld(margin = 0) {
    const t = this.zoom.transform();
    const { width, height } = this.zoom.rect();
    const w = width / t.k;
    const h = height / t.k;
    const x0 = -t.x / t.k;
    const y0 = -t.y / t.k;
    return { x0: x0 - w * margin, y0: y0 - h * margin, x1: x0 + w * (1 + margin), y1: y0 + h * (1 + margin) };
  }

  // The walkthrough's and forecasts' outlined networks (setOverlayGroups), traced around their members. Oct 17: the only
  // outlines left on the canvas; superentities are not drawn.
  updateContours() {
    this.contourDirty = false;
    const nodes = [...this.nodes.values()];
    const rects = new Map(nodes.map((n) => [n.id, rectOf(n)]));
    this.lastContourPos = new Map(nodes.map((n) => [n.id, [n.x, n.y, n.h]]));
    const netPlaced = [];
    this.netSel?.each((d, i, els) => {
      const ids = new Set(d.members.map((m) => this.model.boxOfEntity(m)).filter(Boolean));
      const members = [...ids].map((id) => rects.get(id)).filter(Boolean);
      const obstacles = nodes.filter((n) => !ids.has(n.id)).map((n) => rects.get(n.id));
      const c = hullContourCached(`net:${d.key}`, members, obstacles, PAD + 4 + 6 * i);
      const g = d3.select(els[i]);
      const path = g.select("path.shape").attr("d", c?.d ?? null);
      // a new network outline draws itself in, then settles into a dashed line
      if (d.fresh && c?.d && !this.opts.reducedMotion) {
        d.fresh = false;
        const L = path.node().getTotalLength();
        path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).attr("fill-opacity", 0)
          .transition().duration(380).ease(d3.easeCubicInOut).attr("stroke-dashoffset", 0).attr("fill-opacity", 0.08)
          .on("end", function () { d3.select(this).attr("stroke-dasharray", "5 3").attr("stroke-dashoffset", null); });
      } else if (d.fresh && c?.d) d.fresh = false;
      const b = c?.bbox;
      // rival networks over the same entities have nearly the same outline, so their tabs would land on one
      // corner: each tab steps down past the tabs already placed
      const w = textWidth(d.label, TAB_FONT) + 16;
      const x = b ? b.x1 - w - 2 : 0;
      let y = b ? b.y1 : 0;
      while (b && netPlaced.some((p) => x < p.x1 + 4 && x + w > p.x0 - 4 && Math.abs(p.y - y) < 24)) y += 24;
      if (b) netPlaced.push({ x0: x, x1: x + w, y });
      g.select("g.net-tab").style("display", b ? null : "none").attr("transform", b ? `translate(${x},${y})` : null);
    });
    this.labelsDirty = true;
  }

  // -- highlight and selection ---------------------------------------------------------------------
  setHighlight(hl) {
    this.highlight = hl;
    this.applyHighlight();
  }

  applyHighlight() {
    const hl = this.highlight;
    const on = !!hl;
    const ents = new Set(hl?.entities ?? []);
    const links = hl?.links ?? new Set();
    const hot = hl?.hot ?? new Set();
    // a highlighted superentity (Oct 17: not drawn) lights its members
    const hullKeys = new Set([...(hl?.hulls ?? [])].map((i) => this.groupsInfo.ofInstance.get(i)).filter(Boolean));
    for (const k of hullKeys) for (const m of this.groupsInfo.byKey.get(k)?.members ?? []) ents.add(m);
    // find (Oct 9): matches stand out, their neighbors one and two hops out step down, the rest dims
    const found = hl?.found ?? new Set();
    const ring1 = hl?.ring1 ?? new Set();
    const ring2 = hl?.ring2 ?? new Set();
    this.pillSel?.classed("dim", (d) => on && !ents.has(d.id))
      .classed("found", (d) => found.has(d.id)).classed("ring1", (d) => ring1.has(d.id)).classed("ring2", (d) => ring2.has(d.id));
    this.edgeSel?.classed("dim", (d) => on && !d.ids.some((i) => links.has(i)))
      .classed("hl", (d) => d.ids.some((i) => hot.has(i)))
      .classed("chain", (d) => d.ids.some((i) => hl?.chain?.has(i)));
    this.edgeSel?.select("path.line").attr("marker-end", (d) => (d.ids.some((i) => hot.has(i)) ? "url(#arr-hl)"
      : d.learned ? "url(#arr-learned)" : "url(#arr)"));
  }

  select(sel) {
    this.selection = sel;
    const sid = sel?.kind === "entity" ? sel.id : sel?.kind === "subentity" ? this.subIndex?.get(sel.id)?.entity_id : null;
    if (sid) this.attention.touch(sid, this.zoom.transform().k, 2);
    this.pillSel?.classed("selected", (d) => sel?.kind === "entity" && sel.id === d.id);
    this.pillSel?.selectAll("g.row").classed("selected", (r) => sel?.kind === "subentity" && sel.id === r.sid);
    if (sel?.kind === "entity") this.selFocus = { box: this.model?.boxOfEntity(sel.id) };
    else if (sel?.kind === "subentity") {
      const a = this.model?.anchorOf(sel.id);
      this.selFocus = a ? { box: a.box, row: a.row >= 0 ? a.row : null } : null;
    } else if (sel?.kind === "pattern" && sel.group) this.selFocus = { group: sel.group };
    else this.selFocus = null;
    this.applyFocus();
  }

  // what the side panels cover, in screen pixels (main.js reports it); the camera works in the rest
  freePad(pad = { top: 64, right: 24, bottom: 64, left: 24 }) {
    const i = this.insets?.() ?? { left: 0, right: 0 };
    return { ...pad, top: Math.max(pad.top, (i.top ?? 0) + 12), left: pad.left + i.left, right: pad.right + i.right };
  }

  // after a panel opens over a node (a click opens the inspector), slide the canvas so the node shows
  keepVisible(id, margin = 24) {
    const r = this.screenOf(id);
    if (!r) return;
    const i = this.insets?.() ?? { left: 0, right: 0 };
    const box = this.zoom.rect();
    const lo = box.left + i.left + margin;
    const hi = box.right - i.right - margin;
    if (hi - lo < 40) return;
    let dx = 0;
    if (r.right - r.left > hi - lo) dx = (lo + hi) / 2 - (r.left + r.right) / 2;
    else if (r.right > hi) dx = hi - r.right;
    else if (r.left < lo) dx = lo - r.left;
    if (Math.abs(dx) > 1) this.zoom.panBy(dx, 0, this.opts.reducedMotion ? 0 : 260);
  }

  focusNode(id) {
    this.reveal(id);
    const go = () => {
      const p = this.posOf(id);
      if (!p) return;
      const i = this.insets?.() ?? { left: 0, right: 0 };
      this.zoom.centerOn(p.x, p.y, Math.max(this.zoom.transform().k, 1.05), 300, (i.left - i.right) / 2);
      const sub = this.subIndex.has(id);
      this.handlers.onSelect?.({ kind: sub ? "subentity" : "entity", id });
    };
    setTimeout(go, this.opts.reducedMotion ? 30 : 200);
  }

  // `settled`: where boxes are heading, not where they are mid-glide (outlines are then allowed for with a margin)
  bounds(settled = false) {
    const ns = [...this.nodes.values()];
    if (!ns.length) return null;
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    for (const n of ns) {
      const r = rectOf(settled && n.hx != null ? { ...n, x: n.hx, y: n.hy, w: n.wGoal ?? n.w, h: n.hGoal ?? n.h } : n);
      x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1);
    }
    if (settled) { x0 -= 48; y0 -= 64; x1 += 48; y1 += 48; }
    if (this.lane && this.laneBox) {
      const b = this.laneBox;
      x0 = Math.min(x0, b.x0); y0 = Math.min(y0, b.y0 - 28); x1 = Math.max(x1, b.x1); y1 = Math.max(y1, b.y1);
    }
    return [[x0 - 16, y0 - 16], [x1 + 16, y1 + 16]];
  }

  // DECISION (Oct 11): a fit frames where the boxes are heading, and it is the last word: the layout settling no longer
  // re-frames a second time (two camera moves for one click read as the canvas refreshing)
  fit(duration = 320) {
    this.autoFrame = false;
    this.zoom.fit(this.bounds(true), duration, { pad: this.freePad() });
  }

  // DECISION: the first view fits everything unless that would shrink names below about 9 px; on a
  // small screen it then shows the middle of the graph at a readable size, and F still fits everything.
  fitReadable(duration = 320) {
    this.autoFrame = false;
    this.zoom.fit(this.bounds(true), duration, { minK: 0.68, pad: this.freePad({ top: 132, right: 24, bottom: 64, left: 24 }) });
    setTimeout(() => this.lod.mark(), duration + 40);
  }

  // Frame the boxes that hold these entities, subentities, or superentity instances in the part of the
  // canvas below `top` pixels (the walkthrough card). Uses where nodes are heading, not where they are
  // mid-animation, so a step that also opens entities frames the settled picture.
  frame(ids, { top = 0, left = 0, right = 0, duration = 360, maxK = 1.0 } = {}) {
    if (!this.model) return false;
    const boxes = new Set();
    for (const raw of ids ?? []) {
      const id = String(raw ?? "").replace(/^new:/, "");
      const gk = this.groupsInfo.ofInstance.get(id) ?? (this.groupsInfo.byKey.has(id) ? id : null);
      const eids = gk ? [...(this.groupsInfo.byKey.get(gk)?.members ?? [])]
        : [this.subIndex.get(id)?.entity_id ?? (id.includes(".") ? id.split(".")[0] : id)];
      for (const e of eids) {
        const b = this.model.boxOfEntity(e);
        if (b && this.nodes.has(b)) boxes.add(b);
      }
    }
    if (!boxes.size) return false;
    let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
    for (const b of boxes) {
      const n = this.nodes.get(b);
      const settled = n.hx != null ? { ...n, x: n.hx, y: n.hy } : n;
      const r = rectOf(settled);
      x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1);
    }
    // a margin wide enough to show the neighbors of what is framed
    this.zoom.fit([[x0 - 90, y0 - 70], [x1 + 90, y1 + 70]], this.opts.reducedMotion ? 0 : duration,
      { maxK, pad: this.freePad({ top: top + 12, right: right + 24, bottom: 64, left: left + 24 }) });
    return true;
  }

  zoomBy(factor) {
    this.zoomToScale(this.zoom.transform().k * factor, { duration: 240 });
  }

  // -- animation overlays (the animator calls these; it never computes model results) -------------------
  posOf(id) {
    if (!this.model) return null;
    const ref = String(id ?? "").replace(/^new:/, "");
    if (this.subIndex.has(ref)) {
      const a = this.model.anchorOf(ref);
      const n = a && this.nodes.get(a.box);
      if (!n) return null;
      return a.row >= 0 ? { x: n.x - n.w / 2 + 14, y: n.y + rowCenterY(a.row), row: true } : { x: n.x, y: n.y };
    }
    const bid = this.model.boxOfEntity(ref);
    if (bid && this.nodes.has(bid)) {
      const n = this.nodes.get(bid);
      return { x: n.x, y: n.y };
    }
    // a superentity (not drawn, Oct 17): the middle of its members
    const gk = this.groupsInfo.ofInstance.get(ref) ?? (this.groupsInfo.byKey.has(ref) ? ref : null);
    if (gk) {
      const ns = [...(this.groupsInfo.byKey.get(gk)?.members ?? [])].map((m) => this.nodes.get(m)).filter(Boolean);
      if (ns.length) return { x: ns.reduce((t, n) => t + n.x, 0) / ns.length, y: ns.reduce((t, n) => t + n.y, 0) / ns.length };
    }
    // an entity id that is part of a subentity reference
    if (ref.includes(".")) return this.posOf(ref.split(".")[0]);
    return null;
  }

  // The drawn shape that stands for an id: a subentity's row when its entity is open, else its entity's
  // box. Returns {key, box, row}.
  targetOf(id) {
    if (!this.model) return null;
    const ref = String(id ?? "").replace(/^new:/, "");
    if (this.subIndex.has(ref) || (ref.includes(".") && !this.model.boxOfEntity(ref))) {
      const a = this.model.anchorOf(ref);
      if (!a || !this.nodes.has(a.box)) return null;
      return { key: `${a.box}#${a.row}`, box: a.box, row: a.row };
    }
    const bid = this.model.boxOfEntity(ref);
    return bid && this.nodes.has(bid) ? { key: `${bid}#-1`, box: bid, row: -1 } : null;
  }

  shapeOf(t, pad = 4) {
    const n = this.nodes.get(t.box);
    if (!n) return null;
    if (t.row >= 0) {
      const y = n.y + rowCenterY(t.row);
      return { x: n.x - n.w / 2 + 3 - pad / 2, y: y - GEOM.ROW_H / 2 + 1 - pad / 2, w: n.w - 6 + pad, h: GEOM.ROW_H - 2 + pad, rx: 5 + pad / 2 };
    }
    return { x: n.x - n.w / 2 - pad, y: n.y + n.oy - pad, w: n.w + 2 * pad, h: n.h + 2 * pad, rx: 8 + pad };
  }

  // A ripple in the shape of what it marks: the outline grows a little and fades.
  pulse(ids, color = css("--real-line"), ms = 600) {
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : Math.max(ms, 240);
    const seen = new Set();
    const shapes = [];
    for (const id of ids ?? []) {
      const t = this.targetOf(id);
      if (!t || seen.has(t.key)) continue;
      seen.add(t.key);
      const r = this.shapeOf(t, 2);
      if (r) shapes.push(r);
    }
    const g = this.layers.overlays.append("g").attr("class", "ripples");
    g.selectAll("rect").data(shapes).join("rect").attr("class", "ripple")
      .attr("x", (d) => d.x).attr("y", (d) => d.y).attr("width", (d) => d.w).attr("height", (d) => d.h).attr("rx", (d) => d.rx)
      .attr("stroke", color).style("opacity", 0.95)
      .transition().duration(dur).ease(d3.easeCubicOut)
      .attr("x", (d) => d.x - 9).attr("y", (d) => d.y - 9).attr("width", (d) => d.w + 18).attr("height", (d) => d.h + 18)
      .attr("rx", (d) => d.rx + 9).style("opacity", 0);
    g.transition().delay(dur + 30).remove();
    return new Promise((r) => setTimeout(r, dur));
  }

  // A comet: a short bright stroke that runs along each edge from cause to effect.
  pulseLinks(ids, color = css("--real-line"), ms = 400) {
    const set = new Set(ids);
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : Math.max(ms, 300);
    const paths = this.edgeSel?.filter((d) => d.ids.some((i) => set.has(i))).select("path.line").nodes() ?? [];
    for (const el of paths) {
      const dAttr = el.getAttribute("d");
      if (!dAttr) continue;
      const L = el.getTotalLength();
      const head = Math.max(16, L * 0.22);
      this.layers.overlays.append("path").attr("class", "comet").attr("d", dAttr).attr("stroke", color)
        .attr("stroke-dasharray", `${head} ${L + head}`).attr("stroke-dashoffset", head)
        .transition().duration(dur).ease(d3.easeCubicInOut).attr("stroke-dashoffset", -L)
        .transition().duration(90).style("opacity", 0).remove();
    }
    return new Promise((r) => setTimeout(r, dur));
  }

  // Deviation glows while something propagates: an outline that hugs the pill (or the open row), red
  // for up and blue for down, stronger for bigger moves; dashed when the value came from propagation
  // rather than an observation. (They replace the earlier rings, which sat on top of the names.)
  halos(zById, ms = 120, { dotted = false } = {}) {
    for (const [id, z] of Object.entries(zById ?? {})) this.haloData.set(id, { z, dotted });
    this.drawHalos(Math.min(ms, 260));
    return new Promise((r) => setTimeout(r, this.opts.reducedMotion ? Math.min(ms, 60) : ms));
  }

  clearHalos() {
    this.haloData.clear();
    this.drawHalos(140);
  }

  drawHalos(ms = 200) {
    const agg = new Map();
    for (const [id, v] of this.haloData) {
      if (Math.abs(v.z) < 0.08) continue;
      const t = this.targetOf(id);
      if (!t) continue;
      const cur = agg.get(t.key);
      if (!cur || Math.abs(v.z) > Math.abs(cur.z)) agg.set(t.key, { ...t, z: v.z, dotted: v.dotted });
    }
    const data = [...agg.values()];
    const dur = this.opts.reducedMotion ? 0 : ms;
    const sel = this.layers.overlays.selectAll("rect.glow").data(data, (d) => d.key);
    sel.exit().transition().duration(dur).style("opacity", 0).remove();
    const enter = sel.enter().append("rect").attr("class", "glow").style("opacity", 0);
    this.haloSel = enter.merge(sel).classed("dotted", (d) => d.dotted).classed("row", (d) => d.row >= 0);
    this.tickOverlays();
    const k = (d) => Math.min(1, Math.abs(d.z) / 2);
    this.haloSel.transition().duration(dur).ease(d3.easeCubicOut)
      .attr("stroke", (d) => (d.z > 0 ? css("--up") : css("--down")))
      .attr("fill", (d) => (d.z > 0 ? css("--up") : css("--down")))
      .attr("fill-opacity", (d) => (d.row >= 0 ? 0.06 + 0.16 * k(d) : 0.03 + 0.05 * k(d)))
      .attr("stroke-width", (d) => 1.3 + 2.2 * k(d))
      .style("opacity", (d) => 0.45 + 0.5 * k(d));
  }

  tickOverlays() {
    this.haloSel?.each((d, i, els) => {
      const r = this.shapeOf(d, d.row >= 0 ? 0 : 4);
      const sel = d3.select(els[i]);
      if (!r) { sel.style("display", "none"); return; }
      sel.style("display", null).attr("x", r.x).attr("y", r.y).attr("width", r.w).attr("height", r.h).attr("rx", r.rx);
    });
    this.spotSel?.each((d, i, els) => {
      const r = this.shapeOf(d, 7);
      if (r) d3.select(els[i]).attr("x", r.x).attr("y", r.y).attr("width", r.w).attr("height", r.h).attr("rx", r.rx);
    });
  }

  // The guide's spotlight: a soft violet glow on what it is talking about.
  spotlight(ids) {
    const seen = new Set();
    const data = [];
    for (const id of ids ?? []) {
      const t = this.targetOf(id);
      if (t && !seen.has(t.key)) { seen.add(t.key); data.push(t); }
    }
    const sel = this.layers.overlays.selectAll("rect.spot").data(data, (d) => d.key);
    sel.exit().transition().duration(130).style("opacity", 0).remove();
    this.spotSel = sel.enter().append("rect").attr("class", "spot").style("opacity", 0).merge(sel);
    this.tickOverlays();
    this.spotSel.transition().duration(150).style("opacity", 1);
  }

  // Where an id is on screen (client coordinates), for the guide and other HTML overlays.
  screenOf(id) {
    const t = typeof id === "string" ? this.targetOf(id) : null;
    const r = t ? this.shapeOf(t, 0) : null;
    if (!r) return null;
    const tr = this.zoom.transform();
    const box = this.zoom.rect();
    const [x0, y0] = tr.apply([r.x, r.y]);
    const [x1, y1] = tr.apply([r.x + r.w, r.y + r.h]);
    return { left: box.left + x0, top: box.top + y0, right: box.left + x1, bottom: box.top + y1 };
  }

  // a superentity the animation names (Oct 17: superentities are not drawn): its members ripple
  flashHull(instanceId, ms = 800) {
    const dur = this.opts.reducedMotion ? 150 : ms;
    const h = (this.view?.hulls ?? []).find((x) => x.id === instanceId);
    const key = this.groupsInfo.ofInstance.get(instanceId);
    const members = h?.members ?? [...(this.groupsInfo.byKey.get(key)?.members ?? [])];
    if (members.length) return this.pulse(members, h?.transient ? css("--hyp-line") : css("--real-line"), dur);
    return new Promise((r) => setTimeout(r, dur));
  }

  flashCandidates(candidates, ms = 700) {
    const dur = this.opts.reducedMotion ? 150 : Math.max(ms, 600);
    const items = [];
    const seen = new Set();
    for (const c of candidates ?? []) {
      const [id, score] = Array.isArray(c) ? c : [c, null];
      const t = this.targetOf(id);
      if (!t || seen.has(t.key)) continue;
      seen.add(t.key);
      const r = this.shapeOf(t, 3);
      if (r) items.push({ r, score });
    }
    const g = this.layers.overlays.append("g").attr("class", "cand-flash").style("opacity", 0);
    g.selectAll("rect.cand").data(items).join("rect").attr("class", "cand")
      .attr("x", (d) => d.r.x).attr("y", (d) => d.r.y).attr("width", (d) => d.r.w).attr("height", (d) => d.r.h).attr("rx", (d) => d.r.rx);
    const chip = g.selectAll("g.score").data(items.filter((d) => d.score != null)).join("g").attr("class", "score")
      .attr("transform", (d) => `translate(${d.r.x + d.r.w + 5},${d.r.y + d.r.h / 2})`);
    chip.append("rect").attr("x", 0).attr("y", -8).attr("width", 34).attr("height", 16).attr("rx", 8);
    chip.append("text").attr("x", 17).attr("y", 0.5).text((d) => d.score.toFixed(2));
    g.transition().duration(110).style("opacity", 1).transition().delay(dur).duration(180).style("opacity", 0).remove();
  }
}
