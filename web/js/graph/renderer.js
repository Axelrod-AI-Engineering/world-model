// The canvas (§13.3). Drawing sits behind the GraphRenderer interface, so a canvas or WebGL renderer
// can replace SVG if the node count passes about 2,000.
/* global d3 */
import { densityCurve } from "../charts/density.js";
import { createSimulation, resolveCollisions } from "./forces.js";
import { drawRibbons, prettyNode } from "./fuzzy.js";
import { ancestors, buildGroups, hullContour, hullPolygon, hullStyle, NEST_PAD, PAD, paletteOf } from "./hulls.js";
import { figurePosition, slotPosition } from "./layouts.js";
import { CHIP, computeModel, GEOM, rowCenterY, textWidth, truncate } from "./model.js";
import { createZoom, installGrid } from "./zoom.js";

/** The interface every renderer implements. */
export class GraphRenderer {
  setLayout(_layout) {}
  setData(_view, _extras) {}
  setExtras(_extras) {}
  setDetail(_level) {}
  toggleEntity(_id, _open) {}
  toggleGroup(_key, _closed) {}
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

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const NAME_FONT = "600 13px Instrument Sans";
const ROW_FONT = "500 11.5px Instrument Sans";
const TAB_FONT = "700 13px Instrument Sans";

function rectOf(n) {
  return { x0: n.x - n.w / 2, y0: n.y + n.oy, x1: n.x + n.w / 2, y1: n.y + n.oy + n.h };
}

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

function cubicPoint(p0, c1, c2, p3, t) {
  const u = 1 - t;
  return [u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p3[0],
          u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p3[1]];
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
    for (const name of ["hulls", "lenses", "netlines", "edges", "tethers", "frontier", "ghosts", "fuzzy", "nodes", "tabs", "overlays"]) {
      this.layers[name] = this.root.append("g").attr("class", `layer-${name}`);
    }
    this.layout = null;
    this.view = null;
    this.extras = { ribbons: [], ghostEdges: [], ghostSubs: [], pendingPatterns: new Set() };
    this.ui = { expanded: new Set(), collapsed: new Set(), showCandidates: false };
    this.mode = "figure1";
    this.opts = { figure1LinksOnly: false, groupByCategory: false, reducedMotion: false };
    this.nodes = new Map();
    this.homes = new Map();
    this.pinnedHomes = new Map();
    this.groupsInfo = { groups: [], byKey: new Map(), ofEntity: new Map(), ofInstance: new Map() };
    this.model = null;
    this.subIndex = new Map();
    this.highlight = null;
    this.focus = null;
    this.selection = null;
    this.haloData = new Map();
    this.contours = new Map();
    this.lastContourPos = new Map();
    this.tickCount = 0;
    this.undoStack = [];
    this.redoStack = [];
    this.overlayGroups = [];      // the walkthrough's outlined networks: {key, members, color, label}
    this.flowData = new Map();    // the walkthrough's edge flows: interaction id -> signed flow
    this.peeked = null;           // what the walkthrough opened temporarily
    this.sim = createSimulation({
      getMode: () => this.mode,
      getGroups: () => this.groupsInfo.groups.filter((g) => !g.transient),
      groupByCategory: () => this.opts.groupByCategory,
      onTick: () => this.ticked(),
    });
    this.zoom = createZoom(this.svg, this.root, { grid });
    const isBackground = (ev) => ev.target === this.svg.node() || ev.target.closest?.(".grid-bg");
    this.svg.on("click", (ev) => { if (isBackground(ev)) this.handlers.onSelect?.(null); });
    this.svg.on("contextmenu", (ev) => {
      if (!isBackground(ev)) return;
      ev.preventDefault();
      this.handlers.onContext?.(ev, { kind: "canvas" });
    });
  }

  makeMarkers() {
    const mk = (id, color, size = 6, start = false) => {
      this.defs.append("marker").attr("id", id).attr("viewBox", "0 0 10 10").attr("refX", start ? 1 : 9).attr("refY", 5)
        .attr("markerWidth", size).attr("markerHeight", size).attr("orient", start ? "auto-start-reverse" : "auto")
        .attr("markerUnits", "userSpaceOnUse").attr("viewBox", "0 0 10 10")
        .append("path").attr("d", "M0 0L10 5L0 10z").attr("fill", color);
    };
    mk("arr", "#857C70", 8);
    mk("arr-s", "#857C70", 8, true);
    mk("arr-learned", "#7C64C4", 8);
    mk("arr-hl", "#874B2B", 9);
    mk("arr-hl-s", "#874B2B", 9, true);
    mk("arr-super", "#665E54", 11);
    mk("arr-ghost", "#7C64C4", 8);
    mk("arr-front", "#93465F", 8);
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

  setOptions(opts) {
    Object.assign(this.opts, opts);
    if ("groupByCategory" in opts) this.sim.alpha(0.6).restart();
    if ("figure1LinksOnly" in opts) this.drawEdges();
  }

  setLayoutMode(mode) {
    if (mode !== this.mode) this.record(mode === "figure1" ? "switch to the Figure 1 layout" : "switch to the gravity layout", { camera: true });
    this.mode = mode;
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
    this.view = view;
    Object.assign(this.extras, extras);
    this.recompute(first ? "first" : "data");
  }

  setExtras(extras) {
    const before = [...(this.extras.pendingPatterns ?? [])].join("|");
    Object.assign(this.extras, extras);
    if ([...(this.extras.pendingPatterns ?? [])].join("|") !== before) { this.recompute("data"); return; }
    this.drawGhosts();
    this.drawFuzzy(true);
  }

  updateHomes() {
    const regions = [];
    for (const g of this.groupsInfo.groups) {
      if (g.transient || g.composite) continue;
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

  homeOf(box) {
    if (box.kind === "entity") return this.pinnedHomes.get(box.id) ?? this.homes.get(box.id) ?? { x: 600, y: 440 };
    const pts = [...box.group.members].map((m) => this.pinnedHomes.get(m) ?? this.homes.get(m)).filter(Boolean);
    if (!pts.length) return { x: 600, y: 440 };
    return { x: pts.reduce((a, p) => a + p.x, 0) / pts.length, y: pts.reduce((a, p) => a + p.y, 0) / pts.length };
  }

  recompute(reason) {
    if (!this.view) return;
    this.subIndex = new Map(this.view.subentities.map((s) => [s.id, s]));
    this.groupsInfo = buildGroups(this.view, { showCandidates: this.ui.showCandidates,
                                               pendingPatterns: this.extras.pendingPatterns ?? new Set() });
    for (const k of [...this.ui.collapsed]) if (!this.groupsInfo.byKey.has(k)) this.ui.collapsed.delete(k);
    for (const id of [...this.ui.expanded]) if (!this.view.entities.some((e) => e.id === id)) this.ui.expanded.delete(id);
    this.updateHomes();
    this.model = computeModel(this.view, this.groupsInfo, this.ui);
    const structural = this.syncNodes();
    const nodes = [...this.nodes.values()];
    this.sim.nodes(nodes);
    this.sim.force("link").links(this.model.edges.filter((e) => this.nodes.has(e.a.box) && this.nodes.has(e.b.box))
      .map((e) => ({ source: e.a.box, target: e.b.box, significance: e.sig })));
    this.draw();
    if (reason === "first") {
      resolveCollisions(nodes, 6);
      this.ticked(true);
      setTimeout(() => this.fitReadable(0), 30);
    }
    if (structural || reason === "structure") this.sim.alpha(Math.max(this.sim.alpha(), 0.55)).restart();
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
      n.pinned = this.pinnedHomes.has(b.id);
      Object.assign(n, { kind: b.kind, ref: b.ref, w: b.w, h: b.h, oy: b.oy, box: b, hx: home.x, hy: home.y,
                         tags: b.entity?.category_tags,
                         groupKeys: b.kind === "entity" ? this.groupsInfo.ofEntity.get(b.id) ?? [] : [] });
      next.set(b.id, n);
    }
    if (old.size !== next.size) structural = true;
    this.nodes = next;
    if (this.mode === "figure1") this.applyFlow();
    return structural;
  }

  // DECISION: in the Figure 1 layout, opening entities reflows Figure 1's grid like a table. Each row
  // grows by its tallest open entity and each column by its widest pill, so nothing overlaps, the
  // figure's alignment survives, and closing everything restores the figure exactly. A closed
  // superentity's card sits at the center of its members' places.
  applyFlow() {
    const nodes = [...this.nodes.values()];
    const flowing = nodes.filter((n) => n.kind === "entity" && !this.pinnedHomes.has(n.id));
    const rows = new Map();
    const cols = new Map();
    const homeOf = (id) => this.pinnedHomes.get(id) ?? this.homes.get(id);
    for (const n of flowing) {
      const h = homeOf(n.id);
      if (!h) continue;
      const ry = Math.round(h.y);
      const cx = Math.round(h.x);
      rows.set(ry, Math.max(rows.get(ry) ?? 0, n.h - GEOM.HEAD_H));
      cols.set(cx, Math.max(cols.get(cx) ?? 0, n.w - GEOM.PILL_MIN_W));
    }
    // also count the rows and columns of hidden members, so a card's place follows the grid
    for (const e of this.view?.entities ?? []) {
      const h = homeOf(e.id);
      if (!h) continue;
      if (!rows.has(Math.round(h.y))) rows.set(Math.round(h.y), 0);
      if (!cols.has(Math.round(h.x))) cols.set(Math.round(h.x), 0);
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
      if (this.pinnedHomes.has(id)) return this.pinnedHomes.get(id);
      const h = this.homes.get(id);
      return h ? { x: xAt.get(Math.round(h.x)) ?? h.x, y: yAt.get(Math.round(h.y)) ?? h.y } : null;
    };
    for (const n of nodes) {
      n.flow = n.kind === "entity" && !this.pinnedHomes.has(n.id);
      if (n.kind === "entity") {
        const f = flowed(n.id);
        if (f) { n.hx = f.x; n.hy = f.y; }
      } else {
        const pts = [...n.box.group.members].map(flowed).filter(Boolean);
        if (pts.length) {
          n.hx = pts.reduce((a, p) => a + p.x, 0) / pts.length;
          n.hy = pts.reduce((a, p) => a + p.y, 0) / pts.length;
        }
      }
    }
  }

  // A box that appears grows out of whatever held it a moment ago.
  startPosition(b, old) {
    if (b.kind === "entity") {
      for (const [id, n] of old) {
        if (n.kind === "card" && n.box.group.members.has(b.id)) return { x: n.x, y: n.y };
      }
      return this.homeOf(b);
    }
    const pts = [...b.group.members].map((m) => old.get(m)).filter(Boolean);
    if (pts.length) return { x: pts.reduce((a, p) => a + p.x, 0) / pts.length, y: pts.reduce((a, p) => a + p.y, 0) / pts.length };
    for (const a of ancestors(this.groupsInfo.byKey, b.ref)) {
      const n = old.get(`card:${a}`);
      if (n) return { x: n.x, y: n.y };
    }
    return this.homeOf(b);
  }

  // -- detail: per node, or all at once ---------------------------------------------------------------
  entityName(id) {
    return this.view?.entities.find((e) => e.id === id)?.name ?? id;
  }

  groupName(key) {
    return this.groupsInfo.byKey.get(key)?.label ?? key;
  }

  toggleEntity(id, open = null) {
    const want = open ?? !this.ui.expanded.has(id);
    if (want === this.ui.expanded.has(id)) return;
    this.record(`${want ? "open" : "close"} ${this.entityName(id)}`);
    if (want) this.ui.expanded.add(id);
    else this.ui.expanded.delete(id);
    this.recompute("structure");
  }

  toggleGroup(key, closed = null) {
    const want = closed ?? !this.ui.collapsed.has(key);
    if (want === this.ui.collapsed.has(key)) return;
    this.record(`${want ? "close" : "open"} ${this.groupName(key)}`);
    if (want) this.ui.collapsed.add(key);
    else this.ui.collapsed.delete(key);
    this.recompute("structure");
  }

  setGroupChildren(key, closed) {
    const g = this.groupsInfo.byKey.get(key);
    if (!g) return;
    this.record(`open ${this.groupName(key)} with its parts ${closed ? "closed" : "open"}`);
    this.ui.collapsed.delete(key);
    for (const c of g.children) if (closed) this.ui.collapsed.add(c); else this.ui.collapsed.delete(c);
    this.recompute("structure");
  }

  setMembersOpen(key, open) {
    const g = this.groupsInfo.byKey.get(key);
    if (!g) return;
    this.record(`${open ? "show" : "hide"} the subentities in ${this.groupName(key)}`);
    for (const m of g.members) if (open) this.ui.expanded.add(m); else this.ui.expanded.delete(m);
    this.recompute("structure");
  }

  setShowCandidates(on) {
    this.record(`${on ? "show" : "hide"} candidate superentities`);
    this.ui.showCandidates = on;
    this.recompute("structure");
  }

  // -- undo and redo of view changes (open, close, presets, moves, layout) ---------------------------
  // DECISION: undo covers what the user does to the view; decisions on the model itself (approvals,
  // updates) are recorded in the ledger and are not undone from the canvas.
  // `camera`: the change also moves the view (a preset refits it), so undo returns the view as well
  snapshot(camera = false) {
    const t = camera ? this.zoom.transform() : null;
    return { expanded: [...this.ui.expanded], collapsed: [...this.ui.collapsed], showCandidates: this.ui.showCandidates,
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
    this.ui.collapsed = new Set(state.collapsed);
    this.ui.showCandidates = state.showCandidates;
    this.pinnedHomes = new Map(state.pinned.map(([k, v]) => [k, { ...v }]));
    if (state.mode !== this.mode) {
      this.mode = state.mode;
      for (const n of this.nodes.values()) n.flow = false;
      this.handlers.onLayoutMode?.(state.mode);
    }
    this.recompute("structure");
    if (state.camera) this.zoom.set(state.camera, this.opts.reducedMotion ? 0 : 450);
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

  setDetail(level) {
    const tops = this.groupsInfo.groups.filter((g) => !g.transient && !g.parents.length).map((g) => g.key);
    this.record({ super: "close every superentity", entity: "open every superentity", sub: "open every entity" }[level] ?? level, { camera: true });
    if (level === "super") {
      this.ui.collapsed = new Set(tops);
      this.ui.expanded.clear();
    } else if (level === "entity") {
      this.ui.collapsed.clear();
      this.ui.expanded.clear();
    } else if (level === "sub") {
      this.ui.collapsed.clear();
      this.ui.expanded = new Set(this.view?.entities.map((e) => e.id) ?? []);
    }
    this.recompute("structure");
    setTimeout(() => this.fit(), this.opts.reducedMotion ? 60 : 700);
  }

  detailLevel() {
    const tops = this.groupsInfo.groups.filter((g) => !g.transient && !g.parents.length);
    const nEnt = this.view?.entities.length ?? 0;
    const { collapsed, expanded } = this.ui;
    if (!collapsed.size && !expanded.size) return "entity";
    if (!collapsed.size && expanded.size === nEnt) return "sub";
    if (!expanded.size && tops.length && tops.every((g) => collapsed.has(g.key)) && collapsed.size === tops.length) return "super";
    return null;
  }

  // Make sure a node is on screen: open the cards that hold it, and its entity if it is a subentity.
  reveal(id) {
    if (!this.view) return false;
    const before = this.snapshot();
    const sub = this.subIndex.get(id);
    const eid = sub ? sub.entity_id : id;
    let changed = false;
    if (!this.model.visible.has(eid)) {
      for (const k of this.groupsInfo.ofEntity.get(eid) ?? []) {
        for (const a of [k, ...ancestors(this.groupsInfo.byKey, k)]) {
          if (this.ui.collapsed.delete(a)) changed = true;
        }
      }
    }
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
    if (!this.peeked) this.peeked = { expanded: new Set(this.ui.expanded), collapsed: new Set(this.ui.collapsed) };
    const expanded = new Set(this.peeked.expanded);
    const collapsed = new Set(this.peeked.collapsed);
    for (const id of ids) {
      const sub = this.subIndex.get(id);
      const eid = sub ? sub.entity_id : id;
      if (!this.view?.entities.some((e) => e.id === eid)) continue;
      for (const k of this.groupsInfo.ofEntity.get(eid) ?? []) {
        for (const a of [k, ...ancestors(this.groupsInfo.byKey, k)]) collapsed.delete(a);
      }
      if (sub) expanded.add(eid);
    }
    const same = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));
    if (same(expanded, this.ui.expanded) && same(collapsed, this.ui.collapsed)) return;
    this.ui.expanded = expanded;
    this.ui.collapsed = collapsed;
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
    this.ui.collapsed = this.peeked.collapsed;
    this.peeked = null;
    this.recompute("structure");
  }

  // -- drawing --------------------------------------------------------------------------------------
  draw() {
    this.drawHulls();
    this.drawEdges();
    this.drawFrontier();
    this.drawGhosts();
    this.drawFuzzy(false);
    this.drawNodes();
    this.drawCards();
    this.drawTethers();
    this.applyFocus();
    this.drawnOnce = true;
    this.applyHighlight();
    if (this.selection) this.select(this.selection);
    this.ticked(true);
  }

  drawHulls() {
    const st = this.model.state;
    const groups = this.groupsInfo.groups.filter((g) => st.get(g.key) === "open")
      .sort((a, b) => (b.level - a.level) || (b.members.size - a.members.size) || a.key.localeCompare(b.key));
    this.openGroups = groups;
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.hulls.selectAll("g.hull:not(.exiting)").data(groups, (g) => g.key);
    const fade = this.drawnOnce && !this.opts.reducedMotion ? 320 : 0;
    sel.exit().classed("exiting", true).style("pointer-events", "none").transition().duration(fade).style("opacity", 0).remove();
    const enter = sel.enter().append("g").attr("class", "hull");
    enter.append("path").attr("class", "shape").attr("fill-rule", "evenodd");
    if (fade) enter.style("opacity", 0).transition().duration(fade).delay(120).style("opacity", 1);
    const all = enter.merge(sel).order();
    all.attr("data-instance", (g) => g.key).classed("composite", (g) => g.composite).classed("transient", (g) => g.transient);
    all.each((g, i, nodes) => {
      const p = paletteOf(g, pal);
      const s = hullStyle(g, p);
      g.pal = p;
      d3.select(nodes[i]).select("path.shape").attr("fill", s.fill).attr("fill-opacity", s.fillOpacity)
        .attr("stroke", s.stroke).attr("stroke-dasharray", s.dash);
    });
    this.bindGroupEvents(all);
    this.hullSel = all;
    // tabs: one per pattern (rivals side by side), above links and nodes so they stay readable
    const tsel = this.layers.tabs.selectAll("g.hull-tabs").data(groups.filter((g) => !g.transient || g.hulls.length), (g) => g.key);
    tsel.exit().remove();
    const tenter = tsel.enter().append("g").attr("class", "hull-tabs");
    const tall = tenter.merge(tsel);
    tall.attr("data-instance", (g) => g.key);
    tall.each((g, i, nodes) => {
      const tabs = d3.select(nodes[i]).selectAll("g.hull-tab").data(g.hulls.map((h) => ({ h, g })), (x) => x.h.id);
      tabs.exit().remove();
      const te = tabs.enter().append("g").attr("class", "hull-tab hull").attr("tabindex", 0).attr("role", "button");
      te.append("rect").attr("rx", 7).attr("height", 22).attr("y", -11);
      te.append("text").attr("x", 8);
      const ta = te.merge(tabs);
      ta.attr("data-instance", (x) => x.g.key);
      // DECISION: rival patterns that share an outline get one compact tab each (their ids); hovering a
      // tab gives the full name, so the pair labels its outline without crowding its neighbors
      ta.each((x) => {
        const base = x.g.hulls.length > 1 ? x.h.pattern_id : x.h.label;
        x.text = truncate(`${base}${x.h.status === "candidate" ? "  (candidate)" : ""}${x.g.transient ? "  (hypothetical)" : ""}`, 190, TAB_FONT);
        x.w = textWidth(x.text, TAB_FONT) + 16;
      });
      ta.select("rect").attr("width", (x) => x.w).attr("stroke", (x) => (x.g.transient ? css("--hyp-line") : x.g.pal.line))
        .attr("stroke-dasharray", (x) => (x.h.status === "candidate" ? "2 2" : null));
      ta.select("text").text((x) => x.text).attr("fill", (x) => (x.g.transient ? css("--hyp-ink") : x.g.pal.ink));
      this.bindGroupEvents(ta, (x) => x.g, (x) => x.h);
    });
    this.tabSel = tall;
    this.contourDirty = true;
  }

  bindGroupEvents(sel, groupOf = (d) => d, hullOf = (d) => d.hulls[0]) {
    sel.on("click", (ev, d) => {
      ev.stopPropagation();
      const g = groupOf(d);
      const h = hullOf(d);
      this.delayedSelect({ kind: "pattern", id: h.pattern_id, instance: h.id, group: g.key });
    })
      .on("dblclick", (ev, d) => {
        ev.stopPropagation();
        clearTimeout(this.clickTimer);
        const g = groupOf(d);
        if (!g.transient) this.toggleGroup(g.key, true);
      })
      .on("contextmenu", (ev, d) => {
        ev.preventDefault();
        ev.stopPropagation();
        this.handlers.onContext?.(ev, { kind: "group", key: groupOf(d).key, pattern: hullOf(d).pattern_id });
      })
      .on("keydown", (ev, d) => {
        if (ev.key === "Enter") this.handlers.onSelect?.({ kind: "pattern", id: hullOf(d).pattern_id, instance: hullOf(d).id, group: groupOf(d).key });
        if (ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
          ev.preventDefault();
          const r = ev.currentTarget.getBoundingClientRect();
          this.handlers.onContext?.({ clientX: r.left, clientY: r.bottom, keyboard: true }, { kind: "group", key: groupOf(d).key, pattern: hullOf(d).pattern_id });
        }
      })
      .on("mouseenter", (ev, d) => { this.setFocus({ group: groupOf(d).key }); this.handlers.onHover?.(ev, { kind: "group", key: groupOf(d).key, hull: hullOf(d) }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => { this.setFocus(null); this.handlers.onHover?.(null); });
  }

  drawNodes() {
    const ents = this.model.boxes.filter((b) => b.kind === "entity");
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.nodes.selectAll("g.pill:not(.exiting)").data(ents, (d) => d.id);
    // closing a superentity: its members fly into the card that now holds them
    const dur = this.drawnOnce && !this.opts.reducedMotion ? 420 : 0;
    sel.exit().classed("exiting", true).style("pointer-events", "none").each((d, i, els) => {
      const g = d3.select(els[i]);
      const hk = this.model.host.get(d.id);
      const card = hk ? this.nodes.get(`card:${hk}`) : null;
      if (card && dur) {
        g.transition().duration(dur).ease(d3.easeCubicIn).attr("transform", `translate(${card.x},${card.y})`).remove();
        g.select("g.inner").transition().duration(dur).ease(d3.easeCubicIn).attr("transform", "scale(0.3)").style("opacity", 0);
      } else {
        g.transition().duration(dur ? 200 : 0).style("opacity", 0).remove();
      }
    });
    const enter = sel.enter().append("g").attr("class", "pill").attr("tabindex", 0).attr("role", "button")
      .attr("data-kind", "entity");
    const inner = enter.append("g").attr("class", "inner");
    inner.append("rect").attr("class", "halo");
    inner.append("rect").attr("class", "body").attr("rx", 8);
    inner.append("line").attr("class", "sep");
    inner.append("g").attr("class", "owners");
    inner.append("text").attr("class", "name").attr("y", 0.5);
    inner.append("text").attr("class", "dev").attr("y", 0.5);
    inner.append("text").attr("class", "code").attr("y", 0.5);
    inner.append("g").attr("class", "rows");
    // opening a superentity: its members grow out of the card that held them (they start at its place)
    if (dur) {
      inner.attr("transform", "scale(0.35)").style("opacity", 0)
        .transition().duration(dur + 80).ease(d3.easeBackOut.overshoot(1.1)).attr("transform", "scale(1)").style("opacity", 1);
    }
    const all = enter.merge(sel);
    const subsOf = (d) => this.view.subentities.filter((s) => s.entity_id === d.id);
    all.attr("data-id", (d) => d.id)
      .classed("loose", (d) => d.entity.loose)
      .classed("open", (d) => d.open)
      .classed("fresh", (d) => d.entity.origin !== "construction")
      .attr("aria-label", (d) => `${d.entity.name}, ${(d.entity.category_tags ?? []).join(" ")}${d.open ? ", open" : ""}`)
      .attr("aria-expanded", (d) => String(d.open));
    all.select("rect.body").attr("x", (d) => -d.w / 2).attr("y", -GEOM.HEAD_H / 2).attr("width", (d) => d.w).attr("height", (d) => d.h);
    all.select("line.sep").attr("x1", (d) => -d.w / 2 + 1).attr("x2", (d) => d.w / 2 - 1).attr("y1", GEOM.HEAD_H / 2).attr("y2", GEOM.HEAD_H / 2)
      .style("display", (d) => (d.open ? null : "none"));
    const codeW = (d) => textWidth((d.entity.category_tags ?? []).join(" "), "500 12.7px IBM Plex Mono");
    // ownership stripes: one per superentity that owns this entity, shown when it is shared by two or
    // more, or when an owner is closed into a card (a tether then runs from the card's chip to here)
    all.each((d, i, nodes) => {
      const os0 = this.model.owners.get(d.id) ?? [];
      const os = os0.length > 1 || os0.some((o) => o.drawn === "card") ? os0 : [];
      d.stripeW = os.length ? os.length * 4.5 + 3 : 0;
      d.owners = os;
      const ss = d3.select(nodes[i]).select("g.owners").selectAll("rect").data(os, (o) => o.key);
      ss.exit().remove();
      ss.enter().append("rect").attr("width", 3).attr("rx", 1.5).merge(ss)
        .attr("x", (o, j) => -d.w / 2 + 5 + j * 4.5).attr("y", -GEOM.HEAD_H / 2 + 5).attr("height", GEOM.HEAD_H - 10)
        .attr("fill", (o) => paletteOf(this.groupsInfo.byKey.get(o.key), pal).line)
        .classed("closed-owner", (o) => o.drawn === "card")
        .each(function (o) {
          const t = d3.select(this).selectAll("title").data([o]);
          t.enter().append("title").merge(t).text(`${o.drawn === "card" ? "Also in the closed" : "In"} ${o.key.replace(/^inst-/, "")}`);
        });
    });
    all.select("text.name").attr("x", (d) => -d.w / 2 + 10 + d.stripeW)
      .text((d) => truncate(d.entity.name, d.w - 34 - codeW(d) - 14 - d.stripeW, NAME_FONT));
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
    this.bindNodeEvents(all);
    this.pillSel = all;
  }

  drawRows(g, d) {
    const pal = this.view?.palettes ?? {};
    const rows = d.open ? d.rows.map((sid, k) => ({ sid, k, s: this.subIndex.get(sid), w: d.w, eid: d.id })) : [];
    const rs = g.selectAll("g.row").data(rows, (r) => r.sid);
    rs.exit().remove();
    const re = rs.enter().append("g").attr("class", "row").attr("data-kind", "subentity").attr("tabindex", 0).attr("role", "button");
    re.append("rect").attr("class", "bg").attr("rx", 4);
    re.append("g").attr("class", "marks");
    re.append("circle").attr("class", "obs").attr("r", 3);
    re.append("text").attr("class", "rname").attr("y", 0.5);
    re.append("g").attr("class", "glyph");
    re.append("text").attr("class", "rz").attr("y", 0.5);
    const ra = re.merge(rs);
    ra.attr("data-id", (r) => r.sid).attr("transform", (r) => `translate(0,${rowCenterY(r.k)})`).classed("alt", (r) => r.k % 2 === 1)
      .attr("aria-label", (r) => r.s?.name ?? r.sid);
    ra.select("rect.bg").attr("x", (r) => -r.w / 2 + 4).attr("width", (r) => r.w - 8).attr("y", -GEOM.ROW_H / 2 + 1).attr("height", GEOM.ROW_H - 2);
    // superentities of subentities: a colored bar per drawn superentity whose relations use this one
    ra.each((r, i, nodes) => {
      const ks = (this.model.marks.get(r.sid) ?? []).slice(0, 4);
      const ms = d3.select(nodes[i]).select("g.marks").selectAll("rect").data(ks, (k) => k);
      ms.exit().remove();
      ms.enter().append("rect").attr("width", 3).attr("height", 14).attr("y", -7).attr("rx", 1.5).merge(ms)
        .attr("x", (k, j) => -r.w / 2 + 7 + j * 4.5)
        .attr("fill", (k) => paletteOf(this.groupsInfo.byKey.get(k), pal).line);
    });
    const markW = (r) => Math.min(4, (this.model.marks.get(r.sid) ?? []).length) * 4.5;
    ra.select("circle.obs").attr("cx", (r) => -r.w / 2 + 13 + markW(r))
      .attr("fill", (r) => (r.s?.observed_today ? css("--ink-2") : "none"))
      .attr("stroke", (r) => (r.s?.observed === false ? css("--ink-3") : css("--ink-2")))
      .attr("stroke-dasharray", (r) => (r.s?.observed_today ? null : "1.5 1.5"));
    ra.select("text.rname").attr("x", (r) => -r.w / 2 + 21 + markW(r))
      .text((r) => truncate(r.s?.name ?? r.sid, r.w - 118 - markW(r), ROW_FONT));
    ra.each((r, i, nodes) => {
      const gl = d3.select(nodes[i]).select("g.glyph").attr("transform", `translate(${r.w / 2 - 70},0)`);
      densityCurve(gl, r.s?.density, { width: 32, height: 10, marker: r.s?.summary?.q50 });
    });
    ra.select("text.rz").attr("x", (r) => r.w / 2 - 9)
      .attr("fill", (r) => (r.s?.z > 0.25 ? css("--up") : r.s?.z < -0.25 ? css("--down") : css("--ink-3")))
      .text((r) => (r.s ? `${r.s.z > 0.25 ? "▲" : r.s.z < -0.25 ? "▼" : ""}${Math.abs(r.s.z).toFixed(1)}` : ""));
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

  drawCards() {
    const cards = this.model.boxes.filter((b) => b.kind === "card");
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.nodes.selectAll("g.card-super:not(.exiting)").data(cards, (d) => d.id);
    const dur = this.drawnOnce && !this.opts.reducedMotion ? 380 : 0;
    sel.exit().classed("exiting", true).style("pointer-events", "none")
      .call((x) => x.select("g.inner").transition().duration(dur).ease(d3.easeCubicOut).attr("transform", "scale(1.12)").style("opacity", 0))
      .transition().duration(dur).remove();
    const enter = sel.enter().append("g").attr("class", "card-super hull").attr("tabindex", 0).attr("role", "button");
    const inner = enter.append("g").attr("class", "inner");
    inner.append("rect").attr("class", "body").attr("rx", 12);
    inner.append("text").attr("class", "title");
    inner.append("text").attr("class", "meta");
    inner.append("g").attr("class", "chips");
    if (dur) {
      inner.attr("transform", "scale(0.6)").style("opacity", 0)
        .transition().delay(dur * 0.55).duration(dur).ease(d3.easeBackOut.overshoot(1.2)).attr("transform", "scale(1)").style("opacity", 1);
    }
    const all = enter.merge(sel);
    all.attr("data-instance", (d) => d.group.key).attr("data-id", (d) => d.id)
      .attr("aria-label", (d) => `${d.group.label}, closed`).attr("aria-expanded", "false");
    all.each((d) => { d.pal = paletteOf(d.group, pal); });
    all.select("rect.body").attr("x", (d) => -d.w / 2).attr("y", (d) => -d.h / 2).attr("width", (d) => d.w).attr("height", (d) => d.h)
      .attr("fill", (d) => (d.group.status === "candidate" ? css("--sheet") : d.pal.fill))
      .attr("fill-opacity", (d) => (d.group.composite ? 0.6 : 0.85))
      .attr("stroke", (d) => d.pal.line)
      .attr("stroke-dasharray", (d) => (d.group.status === "candidate" ? "1.5 4" : d.group.composite ? "12 4 2 4" : "6 4"));
    all.select("text.title").attr("x", (d) => -d.w / 2 + 12).attr("y", (d) => -d.h / 2 + 16).attr("fill", (d) => d.pal.ink)
      .text((d) => truncate(d.group.label, d.w - 24, "700 13px Instrument Sans"));
    all.select("text.meta").attr("x", (d) => -d.w / 2 + 12).attr("y", (d) => -d.h / 2 + 32).text((d) => {
      const g = d.group;
      const n = g.members.size;
      const shared = (d.chips ?? []).filter((c) => c.hosted === false).length;
      const sh = shared ? ` · ${shared} shared` : "";
      if (g.composite) {
        const inParts = new Set(g.children.flatMap((k) => [...this.groupsInfo.byKey.get(k).members]));
        const extra = [...g.members].filter((m) => !inParts.has(m)).length;
        return `${g.children.length} superentities${extra ? ` + ${extra} entit${extra === 1 ? "y" : "ies"}` : ""}${sh} · open ▸`;
      }
      return `${n} entit${n === 1 ? "y" : "ies"}${sh} · open ▸`;
    });
    // its members as chips: solid if the card holds them, dashed if they are drawn elsewhere (shared)
    all.each((d, i, els) => {
      const box = d3.select(els[i]).select("g.chips").attr("transform", `translate(${-d.w / 2 + 12},${-d.h / 2 + CHIP.TOP})`);
      const cs = box.selectAll("g.chip").data(d.chips ?? [], (c) => c.eid ?? "more");
      cs.exit().remove();
      const ce = cs.enter().append("g").attr("class", "chip");
      ce.append("rect").attr("rx", CHIP.H / 2).attr("height", CHIP.H);
      ce.append("circle").attr("class", "port").attr("r", 2.6);
      ce.append("text").attr("y", CHIP.H / 2 + 0.5);
      const ca = ce.merge(cs);
      ca.attr("transform", (c) => `translate(${c.x},${c.y})`).classed("shared", (c) => c.hosted === false).classed("more", (c) => !!c.more)
        .attr("data-eid", (c) => c.eid ?? null);
      ca.select("rect").attr("width", (c) => c.w).attr("stroke", (c) => (c.more ? "none" : d.pal.line));
      ca.select("circle.port").attr("cx", (c) => c.w - 6).attr("cy", CHIP.H / 2).attr("fill", d.pal.line)
        .style("display", (c) => (c.hosted === false ? null : "none"));
      ca.select("text").attr("x", CHIP.PADX).text((c) => c.label).attr("fill", (c) => (c.hosted === false ? d.pal.ink : null));
      ca.on("click", (ev, c) => {
        if (!c.eid) return;
        ev.stopPropagation();
        clearTimeout(this.clickTimer);
        if (c.hosted === false) this.focusNode(c.eid);
        this.handlers.onSelect?.({ kind: "entity", id: c.eid });
      })
        .on("dblclick", (ev) => ev.stopPropagation())
        .on("mouseenter", (ev, c) => { if (c.eid) { this.setFocus({ box: d.id, chip: c.eid }); this.handlers.onHover?.(ev, { kind: "entity", id: c.eid }); } })
        .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
        .on("mouseleave", () => { this.setFocus({ box: d.id }); this.handlers.onHover?.(null); });
    });
    all.on("click", (ev, d) => {
      ev.stopPropagation();
      const h = d.group.hulls[0];
      this.delayedSelect({ kind: "pattern", id: h.pattern_id, instance: h.id, group: d.group.key });
    })
      .on("dblclick", (ev, d) => { ev.stopPropagation(); clearTimeout(this.clickTimer); this.toggleGroup(d.group.key, false); })
      .on("contextmenu", (ev, d) => { ev.preventDefault(); ev.stopPropagation(); this.handlers.onContext?.(ev, { kind: "group", key: d.group.key, pattern: d.group.pattern_id }); })
      .on("keydown", (ev, d) => {
        if (ev.key === "Enter") this.toggleGroup(d.group.key, false);
        if (ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) {
          ev.preventDefault();
          const r = ev.currentTarget.getBoundingClientRect();
          this.handlers.onContext?.({ clientX: r.left, clientY: r.bottom, keyboard: true }, { kind: "group", key: d.group.key, pattern: d.group.pattern_id });
        }
      })
      .on("mouseenter", (ev, d) => { this.setFocus({ box: d.id }); this.handlers.onHover?.(ev, { kind: "group", key: d.group.key, hull: d.group.hulls[0] }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => { this.setFocus(null); this.handlers.onHover?.(null); });
    this.dragBehavior(all);
    this.cardSel = all;
  }

  // Tethers: from a card's dashed chip to wherever that shared member is drawn (an entity's pill, or the
  // chip of the card that holds it), so one entity owned by two superentities reads as one thing.
  drawTethers() {
    const data = [];
    for (const [key, list] of this.model.cardMembers ?? []) {
      for (const m of list) {
        if (m.hosted) continue;
        data.push({ key: `${key}>${m.eid}`, card: `card:${key}`, group: key, eid: m.eid, where: m.where });
      }
    }
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.tethers.selectAll("g.tether").data(data, (d) => d.key);
    sel.exit().transition().duration(this.opts.reducedMotion ? 0 : 200).style("opacity", 0).remove();
    const enter = sel.enter().append("g").attr("class", "tether");
    enter.append("path").attr("class", "line");
    enter.append("circle").attr("class", "end").attr("r", 3.2);
    const all = enter.merge(sel);
    all.each((d) => { d.color = paletteOf(this.groupsInfo.byKey.get(d.group), pal).line; });
    all.select("path.line").attr("stroke", (d) => d.color);
    all.select("circle.end").attr("fill", (d) => d.color);
    if (this.drawnOnce && !this.opts.reducedMotion) {
      enter.style("opacity", 0).transition().delay(380).duration(420).style("opacity", 1);
    }
    this.tetherSel = all;
    this.tickTethers();
  }

  chipCenter(cardId, eid) {
    const n = this.nodes.get(cardId);
    const c = n?.box?.chips?.find((x) => x.eid === eid);
    if (!n || !c) return null;
    return { x: n.x - n.w / 2 + 12 + c.x + c.w - 6, y: n.y - n.h / 2 + CHIP.TOP + c.y + CHIP.H / 2, chip: c, n };
  }

  tickTethers() {
    this.tetherSel?.each((d, i, els) => {
      const g = d3.select(els[i]);
      const a = this.chipCenter(d.card, d.eid);
      let b = null;
      if (String(d.where).startsWith("card:")) {
        const c = this.chipCenter(d.where, d.eid);
        if (c) b = { x: c.x - c.chip.w + 12, y: c.y };
      } else {
        const n = this.nodes.get(d.where);
        if (n && a) {
          const p = boxExit(n, a.x, a.y, 3);
          b = { x: p[0], y: p[1] };
        }
      }
      if (!a || !b) { g.style("display", "none"); return; }
      g.style("display", null);
      const mx = (a.x + b.x) / 2;
      const my = Math.min(a.y, b.y) - Math.min(60, 12 + Math.abs(a.x - b.x) * 0.12);
      g.select("path.line").attr("d", `M${a.x} ${a.y}Q${mx} ${my} ${b.x} ${b.y}`);
      g.select("circle.end").attr("cx", b.x).attr("cy", b.y);
    });
  }

  // A single click selects after a short pause, so a double-click only opens or closes the node.
  delayedSelect(sel) {
    clearTimeout(this.clickTimer);
    this.clickTimer = setTimeout(() => this.handlers.onSelect?.(sel), 230);
  }

  bindNodeEvents(sel) {
    this.dragBehavior(sel);
    sel.on("click", (ev, d) => { ev.stopPropagation(); this.delayedSelect({ kind: "entity", id: d.id }); })
      .on("dblclick", (ev, d) => { ev.stopPropagation(); clearTimeout(this.clickTimer); this.toggleEntity(d.id); })
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
          this.record(`move ${n.kind === "entity" ? this.entityName(n.id) : this.groupName(n.ref)}`);
          if (n.kind === "entity") this.pinnedHomes.set(n.id, { x: n.fx, y: n.fy });
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
    const sel = this.layers.edges.selectAll("g.edge").data(all, (d) => d.key);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "edge");
    enter.append("path").attr("class", "hit");
    enter.append("path").attr("class", "line");
    enter.append("path").attr("class", "flow");
    enter.append("text").attr("class", "label").attr("dy", -5);
    enter.append("text").attr("class", "badge-l").text("L");
    const a = enter.merge(sel);
    a.classed("learned", (d) => d.learned).classed("super", (d) => !!d.super).classed("demo", (d) => !!d.demo);
    a.select("path.line")
      .attr("stroke-width", (d) => (d.super ? 2.4 + 3 * Math.min(1, d.sig) : d.learned ? 0.9 + 1.4 * Math.min(1, d.sig) : 1 + 2.2 * Math.min(1, d.sig)))
      .attr("marker-end", (d) => (d.super ? "url(#arr-super)" : d.learned ? "url(#arr-learned)" : "url(#arr)"))
      .attr("marker-start", (d) => (d.bidir ? "url(#arr-s)" : null));
    a.select("text.label").text((d) => d.label ?? "");
    a.select("text.badge-l").style("display", (d) => (d.learned ? null : "none"));
    this.edgeSel = a;
    this.applyFlows();
    a.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "interaction", id: d.ids[0], ids: d.ids }); })
      .on("contextmenu", (ev, d) => { ev.preventDefault(); ev.stopPropagation(); this.handlers.onContext?.(ev, { kind: "edge", ids: d.ids }); })
      .on("mouseenter", (ev, d) => { this.setFocus({ edge: d.key }); this.handlers.onHover?.(ev, { kind: "link", ids: d.ids }); })
      .on("mousemove", (ev) => this.handlers.onHoverMove?.(ev))
      .on("mouseleave", () => { this.setFocus(null); this.handlers.onHover?.(null); });
    this.edgeSel = a;
  }

  drawFrontier() {
    const data = this.model.frontier;
    const sel = this.layers.frontier.selectAll("g.frontier").data(data, (d) => d.id);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "frontier");
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
    sel.exit().transition().duration(300).style("opacity", 0).remove();
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
    }, { animate: animate && !this.opts.reducedMotion, duration: this.opts.reducedMotion ? 150 : 700 });
    this.labelsDirty = true;
  }

  // Labels never sit on other text. Every label that is showing (a focused or super edge's, every
  // edge's when "every link label" is on, the frontier's, the fuzzy ribbons') tries spots along its own
  // path, the most important first, and takes the first spot clear of every box, tab, and label placed
  // before it; a label with no free spot is hidden (hovering its edge shows it in the tooltip).
  layoutLabels() {
    if (!this.model || !this.edgeSel) return;
    this.labelsDirty = false;
    const occupied = [];
    for (const n of this.nodes.values()) {
      const r = rectOf(n);
      occupied.push({ x0: r.x0 - 3, x1: r.x1 + 3, y0: r.y0 - 3, y1: r.y1 + 3 });
    }
    for (const t of this.tabRects ?? []) occupied.push(t);
    const free = (r) => !occupied.some((o) => r.x0 < o.x1 && r.x1 > o.x0 && r.y0 < o.y1 && r.y1 > o.y0);
    const labelsOn = document.body.classList.contains("labels");
    const items = [];
    this.edgeSel.each((d, i, els) => {
      const g = els[i];
      const t = g.querySelector("text.label");
      const badge = g.querySelector("text.badge-l");
      const focus = g.classList.contains("focus");
      const shown = !!d.label && (labelsOn || d.super || focus) && g.style.display !== "none";
      if (!shown) { t.classList.add("lbl-hidden"); badge?.classList.toggle("lbl-hidden", !d.learned); return; }
      items.push({ el: t, badge: d.learned ? badge : null, path: g.querySelector("path.line"), text: d.label,
                   font: d.super ? "700 12.5px Instrument Sans" : "500 11.5px Instrument Sans", h: d.super ? 16 : 15,
                   pri: (d.super ? 4 : 0) + (focus ? 2 : 0) + d.sig });
    });
    this.frontSel?.each((d, i, els) => {
      const g = els[i];
      const t = g.querySelector("text.label");
      if (!t.textContent || g.style.display === "none" || t.style.display === "none") { t.classList.add("lbl-hidden"); return; }
      items.push({ el: t, path: g.querySelector("path.line"), text: t.textContent, font: "500 11.5px Instrument Sans", h: 15, pri: 1.5 });
    });
    items.sort((a, b) => b.pri - a.pri);
    for (const it of items) {
      const w = textWidth(it.text, it.font) + 8;
      const L = it.path?.getTotalLength?.() ?? 0;
      let spot = null;
      if (L > 0) {
        for (const f of [0.5, 0.4, 0.6, 0.3, 0.7, 0.22, 0.78]) {
          const p = it.path.getPointAtLength(L * f);
          for (const dy of [-5, 15]) {
            const r = { x0: p.x - w / 2, x1: p.x + w / 2, y0: p.y + dy - it.h + 3, y1: p.y + dy + 4 };
            if (free(r)) { spot = { x: p.x, y: p.y + dy + 5, r }; break; }
          }
          if (spot) break;
        }
      }
      if (!spot) {
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
      this.edgeSel.classed("focus", false).classed("fade", false);
      this.frontSel?.classed("fade", false);
      this.applyOwnerFocus(null);
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
    this.edgeSel.classed("focus", hit).classed("fade", (d) => !hit(d));
    this.frontSel?.classed("fade", (d) => !(d.a.box === f.box || d.b.box === f.box));
    this.applyOwnerFocus(f);
    this.layoutLabels();
  }

  // hovering a shared entity (or a card's chip) lights up everything that owns it, and the tethers
  applyOwnerFocus(f) {
    const eid = f?.chip ?? (f?.box && this.nodes.get(f.box)?.kind === "entity" ? f.box : null);
    const owners = new Set((this.model?.owners.get(eid) ?? []).map((o) => o.card ?? o.key));
    this.lensSel?.classed("lit", (d) => !!eid && d.shared.includes(eid));
    this.tetherSel?.classed("lit", (d) => !!eid && d.eid === eid);
    this.hullSel?.classed("owner-lit", (g) => !!eid && owners.size > 1 && owners.has(g.key));
    this.cardSel?.classed("owner-lit", (d) => !!eid && owners.has(d.group.key));
    this.cardSel?.selectAll("g.chip").classed("lit", (c) => !!eid && c.eid === eid);
  }

  // -- tick -------------------------------------------------------------------------------------------
  ticked(force = false) {
    if (!this.view || !this.model) return;
    const nodes = [...this.nodes.values()];
    resolveCollisions(nodes, 3);
    if (this.sim.alpha() < 0.02) {
      for (const n of nodes) {
        if (n.fx == null && Math.hypot(n.x - n.hx, n.y - n.hy) < 0.6) { n.x = n.hx; n.y = n.hy; }
      }
    }
    this.pillSel?.attr("transform", (d) => { const n = this.nodes.get(d.id); return n ? `translate(${n.x},${n.y})` : null; });
    this.cardSel?.attr("transform", (d) => { const n = this.nodes.get(d.id); return n ? `translate(${n.x},${n.y})` : null; });
    this.tickEdges();
    this.tickTethers();
    this.tickFrontier();
    this.tickGhosts();
    this.tickCount += 1;
    if (force || this.contourDirty || (this.tickCount % 2 === 0 && this.moved())) this.updateContours();
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

  endpoint(anchor, other) {
    const n = this.nodes.get(anchor.box);
    if (!n) return null;
    if (anchor.row >= 0) {
      const y = n.y + rowCenterY(anchor.row);
      const left = other.x < n.x;
      return { x: n.x + (left ? -n.w / 2 : n.w / 2), y, dir: left ? -1 : 1, port: true };
    }
    return { n };
  }

  centerOf(anchor) {
    const n = this.nodes.get(anchor.box);
    if (!n) return null;
    if (anchor.row >= 0) return { x: n.x, y: n.y + rowCenterY(anchor.row) };
    const r = rectOf(n);
    return { x: (r.x0 + r.x1) / 2, y: (r.y0 + r.y1) / 2 };
  }

  edgePath(a, b, curve) {
    const ca = this.centerOf(a);
    const cb = this.centerOf(b);
    if (!ca || !cb) return null;
    const ea = this.endpoint(a, cb);
    const eb = this.endpoint(b, ca);
    let p1 = ea.port ? [ea.x, ea.y] : null;
    let p2 = eb.port ? [eb.x, eb.y] : null;
    if (!p1) p1 = boxExit(ea.n, p2 ? p2[0] : cb.x, p2 ? p2[1] : cb.y, 2);
    if (!p2) p2 = boxExit(eb.n, p1[0], p1[1], 4);
    if (ea.port || eb.port) {
      const dx = Math.max(36, Math.abs(p2[0] - p1[0]) / 2.5);
      const c1 = ea.port ? [p1[0] + ea.dir * dx, p1[1]] : [p1[0] + (p2[0] - p1[0]) / 3, p1[1] + (p2[1] - p1[1]) / 3];
      const c2 = eb.port ? [p2[0] + eb.dir * dx, p2[1]] : [p2[0] - (p2[0] - p1[0]) / 3, p2[1] - (p2[1] - p1[1]) / 3];
      const m = cubicPoint(p1, c1, c2, p2, 0.5);
      return { d: `M${p1[0]} ${p1[1]}C${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${p2[0]} ${p2[1]}`, mx: m[0], my: m[1] };
    }
    if (!curve) return { d: `M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}`, mx: (p1[0] + p2[0]) / 2, my: (p1[1] + p2[1]) / 2 };
    const dx = p2[0] - p1[0];
    const dy = p2[1] - p1[1];
    const len = Math.hypot(dx, dy) || 1;
    const cx = (p1[0] + p2[0]) / 2 - (dy / len) * 20;
    const cy = (p1[1] + p2[1]) / 2 + (dx / len) * 20;
    return { d: `M${p1[0]} ${p1[1]}Q${cx} ${cy} ${p2[0]} ${p2[1]}`, mx: (p1[0] + 2 * cx + p2[0]) / 4, my: (p1[1] + 2 * cy + p2[1]) / 4 };
  }

  tickEdges() {
    this.edgeSel?.each((d, i, els) => {
      const g = d3.select(els[i]);
      let p;
      if (d.internalArc) {
        const n = this.nodes.get(d.box);
        if (!n) { g.style("display", "none"); return; }
        const x = n.x + n.w / 2;
        const ya = n.y + rowCenterY(d.ra);
        const yb = n.y + rowCenterY(d.rb);
        const bulge = 16 + 4 * Math.abs(d.rb - d.ra);
        p = { d: `M${x} ${ya}C${x + bulge} ${ya} ${x + bulge} ${yb} ${x + 1} ${yb}`, mx: x + bulge * 0.75, my: (ya + yb) / 2 };
      } else p = this.edgePath(d.a, d.b, d.curve);
      if (!p) { g.style("display", "none"); return; }
      g.style("display", null);
      g.select("path.line").attr("d", p.d);
      g.select("path.hit").attr("d", p.d);
      if (d.flowing) g.select("path.flow").attr("d", p.d);
      // labels are placed by layoutLabels (clear of other text)
    });
  }

  tickFrontier() {
    this.frontSel?.each((d, i, els) => {
      const g = d3.select(els[i]);
      const p = this.edgePath(d.a, d.b, 1);
      if (!p) { g.style("display", "none"); return; }
      g.style("display", null);
      g.select("path.line").attr("d", p.d);
      g.select("path.hit").attr("d", p.d);
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

  updateContours() {
    this.contourDirty = false;
    const nodes = [...this.nodes.values()];
    const rects = new Map(nodes.map((n) => [n.id, rectOf(n)]));
    this.lastContourPos = new Map(nodes.map((n) => [n.id, [n.x, n.y, n.h]]));
    for (const g of this.openGroups ?? []) {
      const ids = new Set();
      for (const m of g.members) {
        const b = this.model.boxOfEntity(m);
        if (b) ids.add(b);
      }
      const members = [...ids].map((id) => rects.get(id)).filter(Boolean);
      const obstacles = nodes.filter((n) => !ids.has(n.id)).map((n) => rects.get(n.id));
      const c = hullContour(members, obstacles, PAD + NEST_PAD * g.level);
      this.contours.set(g.key, c);
    }
    this.hullSel?.each((g, i, els) => {
      d3.select(els[i]).select("path.shape").attr("d", this.contours.get(g.key)?.d ?? null);
    });
    this.drawLenses();
    this.netSel?.each((d, i, els) => {
      const ids = new Set(d.members.map((m) => this.model.boxOfEntity(m)).filter(Boolean));
      const members = [...ids].map((id) => rects.get(id)).filter(Boolean);
      const obstacles = nodes.filter((n) => !ids.has(n.id)).map((n) => rects.get(n.id));
      const c = hullContour(members, obstacles, PAD + 4 + 6 * i);
      const g = d3.select(els[i]);
      const path = g.select("path.shape").attr("d", c?.d ?? null);
      // a new network outline draws itself in, then settles into a dashed line
      if (d.fresh && c?.d && !this.opts.reducedMotion) {
        d.fresh = false;
        const L = path.node().getTotalLength();
        path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).attr("fill-opacity", 0)
          .transition().duration(750).ease(d3.easeCubicInOut).attr("stroke-dashoffset", 0).attr("fill-opacity", 0.08)
          .on("end", function () { d3.select(this).attr("stroke-dasharray", "5 3").attr("stroke-dashoffset", null); });
      } else if (d.fresh && c?.d) d.fresh = false;
      const b = c?.bbox;
      g.select("g.net-tab").style("display", b ? null : "none")
        .attr("transform", b ? `translate(${b.x1 - textWidth(d.label, TAB_FONT) - 18},${b.y1})` : null);
    });
    // tabs: each tab takes the free spot on its outline nearest the outline's top-left corner, clear of
    // other tabs and of every node (rival patterns share an outline and place their tabs one by one)
    const boxes = nodes.map((n) => rects.get(n.id));
    const placed = [];
    const free = (x0, x1, y) => !placed.some((p) => x0 < p.x1 + 4 && x1 > p.x0 - 4 && Math.abs(p.y - y) < 22)
      && !boxes.some((r) => x0 < r.x1 + 2 && x1 > r.x0 - 2 && y - 11 < r.y1 + 2 && y + 11 > r.y0 - 2);
    this.tabSel?.each((g, i, els) => {
      const c = this.contours.get(g.key);
      const sel = d3.select(els[i]);
      if (!c) { sel.style("display", "none"); return; }
      sel.style("display", null);
      // tabs sit on the outline's top edges, the topmost (then leftmost) free spot first
      const cands = c.topEdge?.length ? c.topEdge : (c.corners ?? [c.anchor]).map((k) => [k.x, k.y]);
      sel.selectAll("g.hull-tab").each((t, j, tels) => {
        let spot = null;
        for (const [px, py] of cands) {
          if (free(px + 2, px + 2 + t.w, py)) { spot = { x: px + 2, y: py }; break; }
        }
        if (!spot) spot = { x: c.anchor.x + 4 + j * (t.w + 4), y: c.anchor.y };
        placed.push({ x0: spot.x, x1: spot.x + t.w, y: spot.y });
        d3.select(tels[j]).attr("transform", `translate(${spot.x},${spot.y})`);
      });
    });
    this.tabRects = placed.map((p) => ({ x0: p.x0 - 2, x1: p.x1 + 2, y0: p.y - 12, y1: p.y + 12 }));
    this.labelsDirty = true;
  }

  // Where two open outlines share entities, the shared part is a lens striped in both colors.
  drawLenses() {
    const pal = this.view?.palettes ?? {};
    const safe = (k) => String(k).replace(/[^A-Za-z0-9_-]/g, "_");
    const data = (this.model?.lenses ?? []).map((l) => ({ ...l, ca: this.contours.get(l.a), cb: this.contours.get(l.b) }))
      .filter((l) => l.ca && l.cb);
    const sel = this.layers.lenses.selectAll("g.lens").data(data, (d) => d.key);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "lens");
    enter.append("clipPath").attr("id", (d) => `lc-${safe(d.key)}`).append("path");
    enter.append("path").attr("class", "lens-fill");
    enter.append("path").attr("class", "lens-edge");
    const all = enter.merge(sel);
    all.each((d) => {
      const pa = paletteOf(this.groupsInfo.byKey.get(d.a), pal);
      const pb = paletteOf(this.groupsInfo.byKey.get(d.b), pal);
      const id = `lp-${safe(d.a)}-${safe(d.b)}`;
      if (this.defs.select(`#${id}`).empty()) {
        const pat = this.defs.append("pattern").attr("id", id).attr("patternUnits", "userSpaceOnUse")
          .attr("width", 8).attr("height", 8).attr("patternTransform", "rotate(45)");
        pat.append("rect").attr("width", 4).attr("height", 8).attr("fill", pa.line).attr("fill-opacity", 0.2);
        pat.append("rect").attr("x", 4).attr("width", 4).attr("height", 8).attr("fill", pb.line).attr("fill-opacity", 0.2);
      }
      d.pattern = id;
      d.edge = pb.line;
    });
    all.select("clipPath path").attr("d", (d) => d.cb.d);
    all.select("path.lens-fill").attr("d", (d) => d.ca.d).attr("clip-path", (d) => `url(#lc-${safe(d.key)})`)
      .attr("fill", (d) => `url(#${d.pattern})`);
    all.select("path.lens-edge").attr("d", (d) => d.ca.d).attr("clip-path", (d) => `url(#lc-${safe(d.key)})`)
      .attr("stroke", (d) => d.edge);
    this.lensSel = all;
  }

  // -- highlight and selection ---------------------------------------------------------------------
  setHighlight(hl) {
    this.highlight = hl;
    this.applyHighlight();
  }

  applyHighlight() {
    const hl = this.highlight;
    const on = !!hl;
    const ents = hl?.entities ?? new Set();
    const links = hl?.links ?? new Set();
    const hot = hl?.hot ?? new Set();
    const hullKeys = new Set([...(hl?.hulls ?? [])].map((i) => this.groupsInfo.ofInstance.get(i)).filter(Boolean));
    this.pillSel?.classed("dim", (d) => on && !ents.has(d.id));
    this.cardSel?.classed("dim", (d) => on && !hullKeys.has(d.group.key) && ![...d.group.members].some((m) => ents.has(m)));
    this.hullSel?.classed("dim", (g) => on && !hullKeys.has(g.key));
    this.tabSel?.classed("dim", (g) => on && !hullKeys.has(g.key));
    this.edgeSel?.classed("dim", (d) => on && !d.ids.some((i) => links.has(i)))
      .classed("hl", (d) => d.ids.some((i) => hot.has(i)));
    this.edgeSel?.select("path.line").attr("marker-end", (d) => (d.ids.some((i) => hot.has(i)) ? "url(#arr-hl)"
      : d.super ? "url(#arr-super)" : d.learned ? "url(#arr-learned)" : "url(#arr)"));
  }

  select(sel) {
    this.selection = sel;
    this.pillSel?.classed("selected", (d) => sel?.kind === "entity" && sel.id === d.id);
    this.pillSel?.selectAll("g.row").classed("selected", (r) => sel?.kind === "subentity" && sel.id === r.sid);
    this.cardSel?.classed("selected", (d) => sel?.kind === "pattern" && d.group.patternIds.includes(sel.id));
    if (sel?.kind === "entity") this.selFocus = { box: this.model?.boxOfEntity(sel.id) };
    else if (sel?.kind === "subentity") {
      const a = this.model?.anchorOf(sel.id);
      this.selFocus = a ? { box: a.box, row: a.row >= 0 ? a.row : null } : null;
    } else if (sel?.kind === "pattern" && sel.group) this.selFocus = { group: sel.group };
    else this.selFocus = null;
    this.applyFocus();
  }

  focusNode(id) {
    this.reveal(id);
    const go = () => {
      const p = this.posOf(id);
      if (!p) return;
      this.zoom.centerOn(p.x, p.y, Math.max(this.zoom.transform().k, 1.05));
      const sub = this.subIndex.has(id);
      this.handlers.onSelect?.({ kind: sub ? "subentity" : "entity", id });
    };
    setTimeout(go, this.opts.reducedMotion ? 30 : 380);
  }

  bounds() {
    const ns = [...this.nodes.values()];
    if (!ns.length) return null;
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    for (const n of ns) {
      const r = rectOf(n);
      x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1);
    }
    for (const c of this.contours.values()) {
      if (!c) continue;
      x0 = Math.min(x0, c.bbox.x0); y0 = Math.min(y0, c.bbox.y0 - 12); x1 = Math.max(x1, c.bbox.x1); y1 = Math.max(y1, c.bbox.y1);
    }
    // tabs can sit past an outline's end
    for (const t of this.tabRects ?? []) {
      x0 = Math.min(x0, t.x0); y0 = Math.min(y0, t.y0); x1 = Math.max(x1, t.x1); y1 = Math.max(y1, t.y1);
    }
    return [[x0 - 16, y0 - 16], [x1 + 16, y1 + 16]];
  }

  fit(duration = 450) {
    this.zoom.fit(this.bounds(), duration);
  }

  // DECISION: the first view fits everything unless that would shrink names below about 9 px; on a
  // small screen it then shows the middle of the graph at a readable size, and F still fits everything.
  fitReadable(duration = 450) {
    this.zoom.fit(this.bounds(), duration, { minK: 0.68, pad: { top: 132, right: 24, bottom: 64, left: 24 } });
  }

  // Frame the boxes that hold these entities, subentities, or superentity instances in the part of the
  // canvas below `top` pixels (the walkthrough card). Uses where nodes are heading, not where they are
  // mid-animation, so a step that also opens entities frames the settled picture.
  frame(ids, { top = 0, left = 0, right = 0, duration = 550, maxK = 1.0 } = {}) {
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
      const settled = this.mode === "figure1" && n.hx != null ? { ...n, x: n.hx, y: n.hy } : n;
      const r = rectOf(settled);
      x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1);
    }
    // a margin wide enough to show the neighbors of what is framed
    this.zoom.fit([[x0 - 90, y0 - 70], [x1 + 90, y1 + 70]], this.opts.reducedMotion ? 0 : duration,
      { maxK, pad: { top: top + 12, right: right + 24, bottom: 64, left: left + 24 } });
    return true;
  }

  zoomBy(factor) {
    this.zoom.by(factor);
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
    const gk = this.groupsInfo.ofInstance.get(ref) ?? (this.groupsInfo.byKey.has(ref) ? ref : null);
    if (gk) {
      const card = this.nodes.get(`card:${gk}`);
      if (card) return { x: card.x, y: card.y };
      const c = this.contours.get(gk);
      if (c) return { x: (c.bbox.x0 + c.bbox.x1) / 2, y: (c.bbox.y0 + c.bbox.y1) / 2 };
    }
    // an entity id that is part of a subentity reference
    if (ref.includes(".")) return this.posOf(ref.split(".")[0]);
    return null;
  }

  // The drawn shape that stands for an id: a subentity's row when its entity is open, else the box
  // (pill or card) that holds it. Returns {key, box, row}.
  targetOf(id) {
    if (!this.model) return null;
    const ref = String(id ?? "").replace(/^new:/, "");
    if (this.subIndex.has(ref) || (ref.includes(".") && !this.model.boxOfEntity(ref))) {
      const a = this.model.anchorOf(ref);
      if (!a || !this.nodes.has(a.box)) return null;
      return { key: `${a.box}#${a.row}`, box: a.box, row: a.row };
    }
    const bid = this.model.boxOfEntity(ref)
      ?? (this.groupsInfo.ofInstance.has(ref) && this.nodes.has(`card:${this.groupsInfo.ofInstance.get(ref)}`)
        ? `card:${this.groupsInfo.ofInstance.get(ref)}` : null);
    return bid && this.nodes.has(bid) ? { key: `${bid}#-1`, box: bid, row: -1 } : null;
  }

  shapeOf(t, pad = 4) {
    const n = this.nodes.get(t.box);
    if (!n) return null;
    if (t.row >= 0) {
      const y = n.y + rowCenterY(t.row);
      return { x: n.x - n.w / 2 + 3 - pad / 2, y: y - GEOM.ROW_H / 2 + 1 - pad / 2, w: n.w - 6 + pad, h: GEOM.ROW_H - 2 + pad, rx: 5 + pad / 2 };
    }
    return { x: n.x - n.w / 2 - pad, y: n.y + n.oy - pad, w: n.w + 2 * pad, h: n.h + 2 * pad, rx: (n.kind === "card" ? 12 : 8) + pad };
  }

  // A ripple in the shape of what it marks: the outline grows a little and fades.
  pulse(ids, color = css("--real-line"), ms = 600) {
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : Math.max(ms, 420);
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
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : Math.max(ms, 520);
    const paths = this.edgeSel?.filter((d) => d.ids.some((i) => set.has(i))).select("path.line").nodes() ?? [];
    for (const el of paths) {
      const dAttr = el.getAttribute("d");
      if (!dAttr) continue;
      const L = el.getTotalLength();
      const head = Math.max(16, L * 0.22);
      this.layers.overlays.append("path").attr("class", "comet").attr("d", dAttr).attr("stroke", color)
        .attr("stroke-dasharray", `${head} ${L + head}`).attr("stroke-dashoffset", head)
        .transition().duration(dur).ease(d3.easeCubicInOut).attr("stroke-dashoffset", -L)
        .transition().duration(140).style("opacity", 0).remove();
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
    this.drawHalos(220);
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
    sel.exit().transition().duration(220).style("opacity", 0).remove();
    this.spotSel = sel.enter().append("rect").attr("class", "spot").style("opacity", 0).merge(sel);
    this.tickOverlays();
    this.spotSel.transition().duration(260).style("opacity", 1);
  }

  // Where an id is on screen (client coordinates), for the guide and other HTML overlays.
  screenOf(id) {
    const t = typeof id === "string" ? this.targetOf(id) : null;
    const r = t ? this.shapeOf(t, 0) : null;
    if (!r) return null;
    const tr = this.zoom.transform();
    const box = this.svg.node().getBoundingClientRect();
    const [x0, y0] = tr.apply([r.x, r.y]);
    const [x1, y1] = tr.apply([r.x + r.w, r.y + r.h]);
    return { left: box.left + x0, top: box.top + y0, right: box.left + x1, bottom: box.top + y1 };
  }

  flashHull(instanceId, ms = 800) {
    const dur = this.opts.reducedMotion ? 150 : ms;
    const key = this.groupsInfo.ofInstance.get(instanceId);
    const path = this.hullSel?.filter((g) => g.key === key).select("path.shape");
    const card = this.cardSel?.filter((d) => d.group.key === key).select("rect.body");
    const target = path && !path.empty() ? path : card && !card.empty() ? card : null;
    if (target) {
      target.interrupt().transition().duration(dur * 0.35).ease(d3.easeCubicOut).attr("stroke-width", 4.2)
        .transition().duration(dur * 0.65).ease(d3.easeCubicIn).attr("stroke-width", null);
    } else {
      const h = (this.view?.hulls ?? []).find((x) => x.id === instanceId);
      if (h) return this.pulse(h.members, css("--hyp-line"), dur);
    }
    return new Promise((r) => setTimeout(r, dur));
  }

  flashCandidates(candidates, ms = 700) {
    const dur = this.opts.reducedMotion ? 150 : Math.max(ms, 900);
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
    g.transition().duration(180).style("opacity", 1).transition().delay(dur).duration(300).style("opacity", 0).remove();
  }
}
