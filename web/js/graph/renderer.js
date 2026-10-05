// The canvas (§13.3). Drawing sits behind the GraphRenderer interface, so a canvas or WebGL renderer
// can replace SVG if the node count passes about 2,000.
/* global d3 */
import { densityGlyph } from "../charts/density.js";
import { createSimulation } from "./forces.js";
import { COMPOSITE_PAD, expandPolygon, groupHulls, hullPolygon, hullStyle, paletteOf, polygonPath } from "./hulls.js";
import { FIG_PILL, fallbackPosition, figureHullAnchor, figureHullPath, figurePosition } from "./layouts.js";
import { drawRibbons, flashCandidates, prettyNode } from "./fuzzy.js";
import { createZoom } from "./zoom.js";

/** The interface every renderer implements. */
export class GraphRenderer {
  setLayout(_layout) {}
  setData(_view, _extras) {}
  setLevel(_level, _jump) {}
  setLayoutMode(_mode) {}
  setOptions(_opts) {}
  fit() {}
  focusNode(_id) {}
  setHighlight(_hl) {}
  pulse(_ids, _color, _ms) {}
  pulseLinks(_ids, _color, _ms) {}
  halos(_zById, _ms) {}
  flashHull(_instanceId, _ms) {}
  flashCandidates(_candidates, _ms) {}
  select(_sel) {}
}

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function pillWidth(name, figure) {
  if (figure) return FIG_PILL.width;
  return Math.max(76, Math.min(170, name.length * 6.4 + 30));
}

// Where a segment from the center of a box toward (tx, ty) leaves the box.
function boxExit(n, tx, ty, pad = 2) {
  const dx = tx - n.x;
  const dy = ty - n.y;
  if (n.type !== "entity") {
    const d = Math.hypot(dx, dy) || 1;
    const r = (n.r ?? 8) + pad;
    return [n.x + (dx / d) * r, n.y + (dy / d) * r];
  }
  const hw = n.w / 2 + pad;
  const hh = n.h / 2 + pad;
  const s = Math.min(hw / Math.abs(dx || 1e-9), hh / Math.abs(dy || 1e-9));
  return [n.x + dx * Math.min(s, 1), n.y + dy * Math.min(s, 1)];
}

export class SvgRenderer extends GraphRenderer {
  constructor(container, handlers = {}) {
    super();
    this.container = container;
    this.handlers = handlers;
    this.svg = d3.select(container).select("svg");
    this.defs = this.svg.append("defs");
    this.makeMarkers();
    this.root = this.svg.append("g").attr("class", "root");
    this.layers = {};
    for (const name of ["hulls", "superLinks", "links", "ghosts", "fuzzy", "frontier", "nodes", "labels", "overlays"]) {
      this.layers[name] = this.root.append("g").attr("class", `layer-${name}`);
    }
    this.layout = null;
    this.view = null;
    this.extras = { ghostEdges: [], ghostSubs: [], liveOps: new Map() };
    this.entities = new Map();
    this.subs = new Map();
    this.level = "entity";
    this.mode = "gravity";
    this.opts = { figure1LinksOnly: false, groupByCategory: false, reducedMotion: false };
    this.highlight = null;
    this.selection = null;
    this.haloData = new Map();
    this.sim = createSimulation({
      getHulls: () => (this.view?.hulls ?? []).filter((h) => !h.transient && !h.child_instance_ids?.length),
      getCenter: () => ({ x: 640, y: 440 }),
      groupByCategory: () => this.opts.groupByCategory,
      onTick: () => this.ticked(),
    });
    this.zoom = createZoom(this.svg, this.root, {
      onLevel: (lv) => {
        this.level = lv;
        this.rebuild(true);
        this.handlers.onLevel?.(lv);
      },
    });
    this.svg.on("click", (ev) => {
      if (ev.target === this.svg.node()) this.handlers.onSelect?.(null);
    });
  }

  makeMarkers() {
    const mk = (id, color, size = 7, start = false) => {
      this.defs.append("marker").attr("id", id).attr("viewBox", "0 -5 10 10").attr("refX", start ? 1 : 9).attr("refY", 0)
        .attr("markerWidth", size).attr("markerHeight", size).attr("orient", start ? "auto-start-reverse" : "auto")
        .append("path").attr("d", "M0,-4L10,0L0,4Z").attr("fill", color);
    };
    mk("arr", "#6F665B");
    mk("arr-s", "#6F665B", 7, true);
    mk("arr-learned", "#7C64C4");
    mk("arr-hl", "#874B2B");
    mk("arr-hl-s", "#874B2B", 7, true);
    mk("arr-super", "#5B534A", 5);
    mk("arr-ghost", "#7C64C4");
  }

  // -- data ---------------------------------------------------------------------------------------
  setLayout(layout) {
    this.layout = layout;
  }

  setOptions(opts) {
    Object.assign(this.opts, opts);
    if ("groupByCategory" in opts) this.sim.alpha(0.5).restart();
    this.rebuild(false);
  }

  setLayoutMode(mode) {
    this.mode = mode;
    const fig = mode === "figure1";
    for (const n of this.entities.values()) {
      n.w = pillWidth(n.name, fig);
      n.h = fig ? FIG_PILL.height : 26;
      const p = figurePosition(this.layout, n.id);
      if (fig && p) { n.fx = p.x; n.fy = p.y; n.x = p.x; n.y = p.y; } else if (!n.pinnedByUser) { n.fx = null; n.fy = null; }
    }
    this.sim.alpha(fig ? 0.05 : 0.6).restart();
    this.rebuild(false);
  }

  setData(view, extras = {}) {
    const first = !this.view;
    this.view = view;
    Object.assign(this.extras, extras);
    const fig = this.mode === "figure1";
    const seen = new Set();
    const positions = new Map([...this.entities.values()].map((n) => [n.id, { x: n.x, y: n.y }]));
    let newIdx = 0;
    for (const e of view.entities) {
      seen.add(e.id);
      let n = this.entities.get(e.id);
      if (!n) {
        const p = figurePosition(this.layout, e.id) ?? fallbackPosition(e.id, view, positions, newIdx++);
        n = { id: e.id, type: "entity", x: p.x, y: p.y, vx: 0, vy: 0 };
        if (!first) n.fresh = true;
        this.entities.set(e.id, n);
        positions.set(e.id, p);
      }
      Object.assign(n, { name: e.name, tags: e.category_tags, loose: e.loose, instances: e.instance_ids,
                         origin: e.origin, deviation: e.deviation, demo: e.demo_addition, kind: e.kind,
                         subIds: e.subentity_ids });
      n.w = pillWidth(e.name, fig);
      n.h = fig ? FIG_PILL.height : 26;
      if (fig) {
        const p = figurePosition(this.layout, e.id);
        if (p) { n.fx = p.x; n.fy = p.y; }
      }
    }
    for (const id of [...this.entities.keys()]) if (!seen.has(id)) this.entities.delete(id);
    const subSeen = new Set();
    const perEntity = new Map();
    for (const s of view.subentities) {
      subSeen.add(s.id);
      const k = perEntity.get(s.entity_id) ?? 0;
      perEntity.set(s.entity_id, k + 1);
      let n = this.subs.get(s.id);
      const parent = this.entities.get(s.entity_id);
      if (!n) {
        n = { id: s.id, type: "sub", x: parent?.x ?? 0, y: parent?.y ?? 0, vx: 0, vy: 0 };
        this.subs.set(s.id, n);
      }
      const count = (parent?.subIds?.length ?? 1);
      const a = (k / Math.max(1, count)) * Math.PI * 2 + Math.PI / 2;
      const ring = 34 + 7 * count;
      Object.assign(n, { entity: s.entity_id, name: s.name, summary: s.summary, z: s.z, family: s.family, unit: s.unit,
                         origin: s.origin, decision: s.decision_variable, r: 7, ox: Math.cos(a) * ring, oy: Math.sin(a) * ring });
    }
    for (const id of [...this.subs.keys()]) if (!subSeen.has(id)) this.subs.delete(id);
    this.rebuild(!first);
    if (first) {
      this.sim.alpha(0.6).restart();
      setTimeout(() => this.fit(0), 30);
    }
  }

  setExtras(extras) {
    Object.assign(this.extras, extras);
    this.drawGhosts();
    this.drawFuzzy(true);
  }

  // -- levels -------------------------------------------------------------------------------------
  setLevel(level, jump = true) {
    if (jump) this.zoom.jumpTo(level);
    else { this.level = level; this.rebuild(true); }
  }

  simNodes() {
    const nodes = [...this.entities.values()];
    if (this.level === "sub") {
      for (const s of this.subs.values()) {
        if (!Number.isFinite(s.x) || s.parked) {
          const p = this.entities.get(s.entity);
          s.x = (p?.x ?? 0) + (s.ox ?? 0) * 0.3;
          s.y = (p?.y ?? 0) + (s.oy ?? 0) * 0.3;
        }
        s.parked = false;
        nodes.push(s);
      }
    } else {
      for (const s of this.subs.values()) s.parked = true;
    }
    return nodes;
  }

  simLinks() {
    const ids = new Set(this.entities.keys());
    const links = (this.view?.entity_links ?? []).filter((l) => ids.has(l.source) && ids.has(l.target) && l.source !== l.target)
      .map((l) => ({ source: l.source, target: l.target, significance: l.significance }));
    if (this.level === "sub") {
      for (const l of this.view?.links ?? []) {
        if (this.subs.has(l.source) && this.subs.has(l.target)) {
          links.push({ source: l.source, target: l.target, significance: l.significance, weak: true });
        }
      }
    }
    return links;
  }

  rebuild(reheat) {
    if (!this.view) return;
    this.sim.nodes(this.simNodes());
    this.sim.force("link").links(this.simLinks());
    if (reheat) this.sim.alpha(Math.max(this.sim.alpha(), this.mode === "figure1" ? 0.05 : 0.3)).restart();
    this.draw();
  }

  // -- drawing ------------------------------------------------------------------------------------
  draw() {
    this.drawHulls();
    this.drawSuper();
    this.drawLinks();
    this.drawFrontier();
    this.drawGhosts();
    this.drawFuzzy(false);
    this.drawNodes();
    this.applyHighlight();
    this.ticked();
  }

  hullGroups() {
    const hulls = (this.view?.hulls ?? []);
    return groupHulls(hulls);
  }

  drawHulls() {
    const show = this.level !== "super";
    const groups = show ? this.hullGroups() : [];
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.hulls.selectAll("g.hull").data(groups, (d) => d.key);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "hull");
    enter.append("path").attr("class", "shape");
    const all = enter.merge(sel);
    // tabs sit in the label layer, above links and nodes, so they stay readable and clickable
    const tsel = this.layers.labels.selectAll("g.hull-tabs").data(groups, (d) => d.key);
    tsel.exit().remove();
    const tenter = tsel.enter().append("g").attr("class", "hull-tabs hull");
    this.tabSel = tenter.merge(tsel).attr("data-instance", (d) => d.hulls[0].id);
    all.attr("data-instance", (d) => d.hulls[0].id)
      .on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "pattern", id: d.hulls[0].pattern_id, instance: d.hulls[0].id }); })
      .on("mouseenter", (ev, d) => this.handlers.onHover?.(ev, { kind: "hull", hulls: d.hulls }))
      .on("mouseleave", () => this.handlers.onHover?.(null));
    all.each((d, i, nodes) => {
      const g = d3.select(nodes[i]);
      const h = d.hulls[0];
      const p = paletteOf(h, pal);
      const st = hullStyle(h, p);
      d.style = st;
      d.palette = p;
      g.select("path.shape").attr("fill", st.fill).attr("fill-opacity", st.fillOpacity).attr("stroke", st.stroke)
        .attr("stroke-dasharray", st.dash);
    });
    this.tabSel.each((d, i, nodes) => {
      const g = d3.select(nodes[i]);
      const tabs = g.selectAll("g.tab").data(d.hulls, (x) => x.id);
      tabs.exit().remove();
      const te = tabs.enter().append("g").attr("class", "tab");
      te.append("rect").attr("class", "tab-bg").attr("rx", 4).attr("height", 17);
      te.append("text").attr("class", "tab").attr("dy", 12.5).attr("dx", 6);
      const ta = te.merge(tabs);
      ta.select("text").text((x) => `${x.label}${x.status === "candidate" ? " (candidate)" : ""}`);
      ta.select("rect").attr("fill", (x) => (x.transient ? css("--hyp-fill") : paletteOf(x, pal).fill))
        .attr("stroke", (x) => (x.transient ? css("--hyp-line") : paletteOf(x, pal).line))
        .attr("width", (x) => 12 + 6.3 * (`${x.label}${x.status === "candidate" ? " (candidate)" : ""}`).length);
      ta.on("click", (ev, x) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "pattern", id: x.pattern_id, instance: x.id }); });
    });
    this.hullSel = all;
  }

  superGroups() {
    // one node per instance; rivals binding the same entities share a node
    const groups = this.hullGroups().filter((g) => !g.hulls[0].transient);
    return groups.map((g) => ({
      id: g.key, hulls: g.hulls, members: g.composite ? g.hulls[0].members : g.hulls[0].members,
      label: g.hulls.map((h) => h.pattern_id).join(" | "),
      name: g.hulls.length > 1 ? "rival pair" : g.hulls[0].label.split(" · ").slice(1).join(" · "),
      composite: g.composite,
    }));
  }

  drawSuper() {
    const show = this.level === "super";
    const groups = show ? this.superGroups() : [];
    this.superData = groups;
    const pal = this.view?.palettes ?? {};
    const sel = this.layers.nodes.selectAll("g.node-super").data(groups, (d) => d.id);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "node-super").attr("tabindex", 0);
    enter.append("circle").attr("class", "body");
    enter.append("text").attr("class", "lbl").attr("dy", -2);
    enter.append("text").attr("class", "sub-lbl").attr("dy", 13).attr("font-size", 10).attr("font-weight", 500)
      .attr("font-family", "var(--font-ui)");
    const all = enter.merge(sel);
    all.select("circle").attr("r", (d) => 20 + 5 * d.members.length)
      .attr("fill", (d) => paletteOf(d.hulls[0], pal).fill).attr("stroke", (d) => paletteOf(d.hulls[0], pal).line)
      .attr("stroke-dasharray", (d) => (d.composite ? "2 4" : "6 4"));
    all.select("text.lbl").text((d) => d.label);
    all.select("text.sub-lbl").text((d) => d.name.slice(0, 26));
    all.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "pattern", id: d.hulls[0].pattern_id, instance: d.hulls[0].id }); })
      .on("dblclick", (ev, d) => { ev.stopPropagation(); const c = this.centroid(d.members); this.zoom.zoomToPoint(c.x, c.y, 1.1); });
    // super-links: thick labeled arrows (Figure 4)
    const byInstance = new Map();
    for (const g of groups) for (const h of g.hulls) byInstance.set(h.id, g);
    const sl = show ? (this.view?.super_links ?? []).map((s) => ({ ...s, a: byInstance.get(s.source), b: byInstance.get(s.target) }))
      .filter((s) => s.a && s.b && s.a !== s.b) : [];
    const ls = this.layers.superLinks.selectAll("g.super-link-g").data(sl, (d) => d.id);
    ls.exit().remove();
    const le = ls.enter().append("g").attr("class", "super-link-g");
    le.append("path").attr("class", "super-link");
    le.append("text").attr("class", "super-link-label");
    this.superLinkSel = le.merge(ls);
    this.superLinkSel.select("path").attr("stroke-width", (d) => (d.kind === "causal" ? 3 + 4 * Math.min(1, d.significance) : 1.5))
      .attr("stroke-dasharray", (d) => (d.kind === "causal" ? null : "4 4"))
      .attr("marker-end", (d) => (d.kind === "causal" ? "url(#arr-super)" : null));
    this.superLinkSel.select("text").text((d) => (d.kind === "causal" ? d.label : "shares members"));
  }

  centroid(members) {
    let sx = 0, sy = 0, k = 0;
    for (const m of members) {
      const n = this.entities.get(m);
      if (n) { sx += n.x; sy += n.y; k += 1; }
    }
    return k ? { x: sx / k, y: sy / k } : { x: 0, y: 0 };
  }

  linkData() {
    const v = this.view;
    if (!v) return [];
    const demo = (ids) => ids.length && ids.every((i) => this.linkById.get(i)?.tags?.includes("demo_addition"));
    this.linkById = new Map(v.links.map((l) => [l.id, l]));
    if (this.level === "super") return [];
    if (this.level === "entity") {
      const out = [];
      const pairs = new Set(v.entity_links.map((l) => `${l.source}>${l.target}`));
      for (const l of v.entity_links) {
        if (l.source === l.target) continue;
        const ints = l.interaction_ids.map((i) => this.linkById.get(i)).filter(Boolean);
        const learned = ints.length > 0 && ints.every((i) => i.edge_type === "learned_causal");
        const bidir = ints.some((i) => i.direction === "bidirectional");
        out.push({ id: `${l.source}>${l.target}`, a: l.source, b: l.target, label: l.label, sig: l.significance,
                   learned, bidir, demo: demo(l.interaction_ids), ids: l.interaction_ids,
                   curve: pairs.has(`${l.target}>${l.source}`) ? 1 : 0 });
      }
      return out;
    }
    const out = [];
    const pairs = new Set(v.links.map((l) => `${l.source}>${l.target}`));
    for (const l of v.links) {
      if (!this.subs.has(l.source) || !this.subs.has(l.target)) continue;
      out.push({ id: l.id, a: l.source, b: l.target, label: l.label, sig: l.significance,
                 learned: l.edge_type === "learned_causal", bidir: l.direction === "bidirectional",
                 demo: (l.tags ?? []).includes("demo_addition"), ids: [l.id], internal: l.internal,
                 curve: pairs.has(`${l.target}>${l.source}`) ? 1 : 0 });
    }
    return out;
  }

  drawLinks() {
    let data = this.linkData();
    if (this.opts.figure1LinksOnly) data = data.filter((d) => !d.demo);
    const sel = this.layers.links.selectAll("g.link-g").data(data, (d) => d.id);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "link-g");
    enter.append("path").attr("class", "link-hit").attr("stroke", "transparent").attr("stroke-width", 12).attr("fill", "none");
    enter.append("path").attr("class", "link");
    enter.append("text").attr("class", "link-label").attr("dy", -4);
    enter.append("text").attr("class", "l-badge").text("L");
    const all = enter.merge(sel);
    all.select("path.link")
      .classed("learned", (d) => d.learned).classed("demo", (d) => d.demo)
      .attr("stroke-width", (d) => (d.learned ? 0.9 + 1.8 * Math.min(1, d.sig) : 1 + 3.5 * Math.min(1, d.sig)))
      .attr("marker-end", (d) => (d.learned ? "url(#arr-learned)" : "url(#arr)"))
      .attr("marker-start", (d) => (d.bidir ? "url(#arr-s)" : null));
    all.select("text.link-label").text((d) => d.label ?? "");
    all.select("text.l-badge").style("display", (d) => (d.learned ? null : "none"));
    all.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "interaction", id: d.ids[0], ids: d.ids }); })
      .on("mouseenter", (ev, d) => this.handlers.onHover?.(ev, { kind: "link", ids: d.ids, label: d.label }))
      .on("mouseleave", () => this.handlers.onHover?.(null));
    this.linkSel = all;
  }

  drawFrontier() {
    const show = this.level !== "super";
    // the frontier logs many weak co-movements; draw the seeded, the proposed, and the well supported
    const data = show ? (this.view?.frontier ?? [])
      .filter((f) => f.status !== "promoted" && (f.seeded || f.status === "promotion_proposed" || f.support >= 2.5))
      .sort((a, b) => b.support - a.support).slice(0, 8) : [];
    const sel = this.layers.frontier.selectAll("g.front-g").data(data, (d) => d.id);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "front-g");
    enter.append("path").attr("class", "frontier-line");
    enter.append("text").attr("class", "link-label").attr("dy", -5).attr("fill", "#93465F");
    const all = enter.merge(sel);
    all.select("path").classed("proposed", (d) => d.status === "promotion_proposed");
    all.select("text").text((d) => (d.seeded || d.status === "promotion_proposed"
      ? `co-moves (support ${d.support.toFixed(1)})` : ""));
    all.on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind: "frontier", id: d.id }); })
      .on("mouseenter", (ev, d) => this.handlers.onHover?.(ev, { kind: "frontier", entry: d }))
      .on("mouseleave", () => this.handlers.onHover?.(null));
    this.frontSel = all;
  }

  drawGhosts() {
    const show = this.level !== "super";
    const edges = show ? (this.extras.ghostEdges ?? []) : [];
    const sel = this.layers.ghosts.selectAll("path.ghost-edge").data(edges, (d) => d.key);
    sel.exit().transition().duration(300).style("opacity", 0).remove();
    this.ghostSel = sel.enter().append("path").attr("class", "ghost-edge").attr("marker-end", "url(#arr-ghost)").merge(sel)
      .attr("stroke", (d) => (d.hyp ? css("--hyp-line") : css("--real-line")));
    const subs = show ? (this.extras.ghostSubs ?? []).filter((g) => !this.subs.has(g.id)) : [];
    const gs = this.layers.ghosts.selectAll("g.ghost-sub").data(subs, (d) => d.id);
    gs.exit().remove();
    const ge = gs.enter().append("g").attr("class", "ghost-sub");
    ge.append("circle").attr("r", 9).attr("fill", "none").attr("stroke", css("--real-line")).attr("stroke-dasharray", "3 2");
    ge.append("text").attr("x", 12).attr("dy", 4).attr("font-size", 10).attr("fill", css("--real-ink"));
    this.ghostSubSel = ge.merge(gs);
    this.ghostSubSel.select("text").text((d) => prettyNode(d.id.split(".").slice(1).join(".")));
  }

  anchorFor(end) {
    if (!end) return null;
    const ref = String(end.ref ?? "").replace(/^new:/, "");
    if (end.level === "subentity") {
      const s = this.subs.get(ref);
      if (s && this.level === "sub") return { x: s.x, y: s.y };
      const e = this.entities.get(ref.split(".")[0]);
      return e ? { x: e.x, y: e.y + (s ? 0 : 14) } : null;
    }
    if (end.level === "entity") {
      const e = this.entities.get(ref);
      return e ? { x: e.x, y: e.y } : null;
    }
    // a generalization: a soft blob around its candidate entities
    const cands = (end.candidates ?? []).map(([id]) => this.entities.get(id)).filter(Boolean);
    if (cands.length) {
      const poly = hullPolygon(cands, 18);
      const c = this.centroid(cands.map((n) => n.id));
      return { x: c.x, y: c.y, blob: poly };
    }
    return { x: 120, y: 150, blob: [[90, 128], [150, 128], [160, 150], [150, 172], [90, 172], [80, 150]] };
  }

  drawFuzzy(animate) {
    const show = this.level !== "super";
    const items = show ? this.ribbonItems() : [];
    this.fuzzySel = drawRibbons(this.layers.fuzzy, items, (end) => this.anchorFor(end), {
      real: css("--real-line"), hyp: css("--hyp-line"), realFill: css("--real-fill"), hypFill: css("--hyp-fill"),
      realInk: css("--real-ink"), hypInk: css("--hyp-ink"),
    }, { animate: animate && !this.opts.reducedMotion, duration: this.opts.reducedMotion ? 150 : 700 });
  }

  ribbonItems() {
    return this.extras.ribbons ?? [];
  }

  drawNodes() {
    const entities = [...this.entities.values()];
    const superLevel = this.level === "super";
    const sel = this.layers.nodes.selectAll("g.node-pill").data(entities, (d) => d.id);
    sel.exit().remove();
    const enter = sel.enter().append("g").attr("class", "node-pill").attr("tabindex", 0).attr("role", "button");
    enter.append("rect").attr("class", "halo-ring").attr("fill", "none").attr("stroke-width", 3).attr("rx", 15);
    enter.append("rect").attr("class", "body").attr("rx", 13);
    enter.append("text").attr("class", "code");
    enter.append("text").attr("class", "label");
    enter.append("text").attr("class", "halo-glyph");
    const all = enter.merge(sel);
    all.classed("loose", (d) => d.loose).classed("demo", (d) => d.demo)
      .classed("mini", superLevel).attr("aria-label", (d) => `${d.name} (${(d.tags ?? []).join(", ")})`)
      .attr("data-id", (d) => d.id).attr("data-kind", "entity");
    all.style("display", (d) => (superLevel && !d.loose ? "none" : null))
      .style("opacity", this.level === "sub" ? 0.55 : null);
    all.select("rect.body").attr("x", (d) => (superLevel ? -d.w / 4 : -d.w / 2)).attr("y", (d) => -d.h / 2)
      .attr("width", (d) => (superLevel ? d.w / 2 : d.w)).attr("height", (d) => d.h)
      .attr("fill", (d) => (superLevel ? "#EEE8DD" : null));
    all.select("text.code").attr("x", (d) => -d.w / 2 + 7).style("display", superLevel ? "none" : null)
      .text((d) => (d.tags ?? []).join(" "));
    const codeW = (d) => ((d.tags ?? []).join(" ").length * 5.4 + 4);
    all.select("text.label").attr("x", (d) => (superLevel ? 0 : codeW(d) / 2))
      .text((d) => (superLevel ? d.name.slice(0, 14) : d.name.length > 22 && d.w < 150 ? `${d.name.slice(0, 21)}…` : d.name));
    all.select("rect.halo-ring")
      .attr("x", (d) => -d.w / 2 - 4).attr("y", (d) => -d.h / 2 - 4).attr("width", (d) => d.w + 8).attr("height", (d) => d.h + 8)
      .attr("stroke", (d) => (d.deviation?.direction === "up" ? css("--up") : d.deviation?.direction === "down" ? css("--down") : "none"))
      .attr("stroke-opacity", (d) => Math.min(0.85, 0.25 + 0.25 * Math.abs(d.deviation?.z ?? 0)))
      .style("display", superLevel ? "none" : null);
    all.select("text.halo-glyph").attr("x", (d) => d.w / 2 - 9)
      .attr("fill", (d) => (d.deviation?.direction === "up" ? css("--up") : css("--down")))
      .text((d) => (superLevel ? "" : d.deviation?.direction === "up" ? "▲" : d.deviation?.direction === "down" ? "▼" : ""));
    this.bindNodeEvents(all, "entity");
    this.pillSel = all;
    // subentities
    const subs = this.level === "sub" ? [...this.subs.values()] : [];
    const ss = this.layers.nodes.selectAll("g.node-sub").data(subs, (d) => d.id);
    ss.exit().remove();
    const se = ss.enter().append("g").attr("class", "node-sub").attr("tabindex", 0).attr("role", "button");
    se.append("circle").attr("class", "body");
    se.append("g").attr("class", "glyph").attr("transform", "translate(0,15)");
    se.append("text").attr("class", "slabel").attr("dy", 30).attr("text-anchor", "middle");
    const sa = se.merge(ss);
    sa.attr("data-id", (d) => d.id).attr("data-kind", "subentity")
      .classed("created", (d) => d.origin === "event" || d.origin === "learned");
    sa.select("circle.body").attr("r", (d) => d.r)
      .attr("fill", (d) => (d.z > 0.25 ? "#F3D9D1" : d.z < -0.25 ? "#D3E0EC" : "#FFFDF8"))
      .attr("stroke", (d) => (d.decision ? css("--init-ink") : null));
    sa.select("text.slabel").text((d) => (d.name.length > 26 ? `${d.name.slice(0, 25)}…` : d.name));
    sa.each((d, i, nodes) => densityGlyph(d3.select(nodes[i]).select("g.glyph"), d.summary, { width: 30, height: 7 }));
    this.bindNodeEvents(sa, "subentity");
    this.subSel = sa;
  }

  bindNodeEvents(sel, kind) {
    const drag = d3.drag()
      .filter((ev) => !this.handlers.isDrawMode?.() && !ev.button)
      .on("start", (ev, d) => { if (!ev.active) this.sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on("end", (ev, d) => { if (!ev.active) this.sim.alphaTarget(0); d.pinnedByUser = true; });
    sel.call(drag)
      .on("click", (ev, d) => { ev.stopPropagation(); this.handlers.onSelect?.({ kind, id: d.id }); })
      .on("dblclick", (ev, d) => {
        ev.stopPropagation();
        if (d.pinnedByUser) { d.pinnedByUser = false; if (this.mode !== "figure1") { d.fx = null; d.fy = null; } this.sim.alpha(0.2).restart(); }
        else this.zoom.zoomToPoint(d.x, d.y, kind === "entity" ? 2.3 : 3);
      })
      .on("keydown", (ev, d) => { if (ev.key === "Enter") this.handlers.onSelect?.({ kind, id: d.id }); })
      .on("mouseenter", (ev, d) => this.handlers.onHover?.(ev, { kind, id: d.id }))
      .on("mouseleave", () => this.handlers.onHover?.(null));
  }

  // -- tick ---------------------------------------------------------------------------------------
  nodeFor(id) {
    const ref = String(id ?? "").replace(/^new:/, "");
    if (this.level === "sub" && this.subs.has(ref)) return this.subs.get(ref);
    return this.entities.get(ref) ?? this.entities.get(this.subs.get(ref)?.entity ?? ref.split(".")[0]) ?? null;
  }

  linkPath(a, b, curve) {
    const [x1, y1] = boxExit(a, b.x, b.y, 3);
    const [x2, y2] = boxExit(b, a.x, a.y, 5);
    if (!curve) return { d: `M${x1} ${y1}L${x2} ${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    const off = 22;
    const cx = (x1 + x2) / 2 - (dy / len) * off;
    const cy = (y1 + y2) / 2 + (dx / len) * off;
    return { d: `M${x1} ${y1}Q${cx} ${cy} ${x2} ${y2}`, mx: (x1 + 2 * cx + x2) / 4, my: (y1 + 2 * cy + y2) / 4 };
  }

  ticked() {
    if (!this.view) return;
    this.pillSel?.attr("transform", (d) => `translate(${d.x},${d.y})`);
    this.subSel?.attr("transform", (d) => `translate(${d.x},${d.y})`);
    if (this.linkSel) {
      this.linkSel.each((d, i, nodes) => {
        const a = this.nodeFor(d.a);
        const b = this.nodeFor(d.b);
        const g = d3.select(nodes[i]);
        if (!a || !b) { g.style("display", "none"); return; }
        g.style("display", null);
        const p = this.linkPath(a, b, d.curve);
        g.select("path.link").attr("d", p.d);
        g.select("path.link-hit").attr("d", p.d);
        g.select("text.link-label").attr("x", p.mx).attr("y", p.my);
        g.select("text.l-badge").attr("x", p.mx + 6).attr("y", p.my + 11);
      });
    }
    if (this.frontSel) {
      this.frontSel.each((d, i, nodes) => {
        const a = this.nodeFor(d.earlier);
        const b = this.nodeFor(d.later);
        const g = d3.select(nodes[i]);
        if (!a || !b || a === b) { g.style("display", "none"); return; }
        g.style("display", null);
        const p = this.linkPath(a, b, 0);
        g.select("path").attr("d", p.d);
        g.select("text").attr("x", p.mx).attr("y", p.my);
      });
    }
    if (this.ghostSel) {
      this.ghostSel.attr("d", (d) => {
        const a = this.nodeFor(d.a);
        const b = this.nodeFor(d.b);
        return a && b ? this.linkPath(a, b, 1).d : null;
      });
    }
    this.ghostSubSel?.attr("transform", (d) => {
      const e = this.entities.get(d.id.split(".")[0]);
      return e ? `translate(${e.x + e.w / 2 + 14},${e.y + 16})` : "translate(-9999,-9999)";
    });
    this.tickHulls();
    if (this.level === "super") this.tickSuper();
    if (this.fuzzySel && (this.sim.alpha() > 0.02)) this.drawFuzzy(false);
    this.tickOverlays();
  }

  tickHulls() {
    if (!this.hullSel) return;
    const fig = this.mode === "figure1";
    const polys = new Map();
    const anchors = new Map();
    this.hullSel.each((d, i, nodes) => {
      if (d.composite) return;
      const h = d.hulls[0];
      const g = d3.select(nodes[i]);
      let path = null;
      let anchor = null;
      if (fig && !h.transient) {
        path = figureHullPath(this.layout, h.pattern_id);
        anchor = path ? figureHullAnchor(this.layout, h.pattern_id) : null;
      }
      if (!path) {
        const ns = h.members.map((m) => this.entities.get(m)).filter(Boolean);
        const poly = hullPolygon(ns, 14 + (d.hulls.length > 1 ? 4 : 0));
        if (poly) {
          polys.set(h.id, poly);
          path = polygonPath(poly);
          const top = poly.reduce((best, p) => (p[1] < best[1] ? p : best), poly[0]);
          const left = Math.min(...poly.map((p) => p[0]));
          anchor = { x: Math.max(left, top[0] - 60), y: top[1] - 10 };
        }
      }
      g.select("path.shape").attr("d", path);
      anchors.set(d.key, anchor);
    });
    // composites: an outer hull around the children's hulls
    this.hullSel.filter((d) => d.composite).each((d, i, nodes) => {
      const h = d.hulls[0];
      const kids = h.child_instance_ids.map((k) => polys.get(k)).filter(Boolean);
      const pts = kids.length ? kids.flat() : null;
      const poly = pts ? expandPolygon(d3.polygonHull(pts), COMPOSITE_PAD - 14)
        : hullPolygon(h.members.map((m) => this.entities.get(m)).filter(Boolean), COMPOSITE_PAD);
      const g = d3.select(nodes[i]);
      g.select("path.shape").attr("d", polygonPath(poly)).attr("fill-opacity", 0.12);
      if (poly) {
        const top = poly.reduce((best, p) => (p[1] < best[1] ? p : best), poly[0]);
        anchors.set(d.key, { x: top[0] - 40, y: top[1] - 14 });
      }
    });
    this.tabSel?.each((d, i, nodes) => {
      const anchor = anchors.get(d.key);
      let dx = 0;
      d3.select(nodes[i]).style("display", anchor ? null : "none").selectAll("g.tab").attr("transform", (x) => {
        const t = `translate(${(anchor?.x ?? 0) + dx},${(anchor?.y ?? 0) - 8})`;
        dx += 16 + 6.3 * x.label.length;
        return t;
      });
    });
  }

  tickSuper() {
    const sel = this.layers.nodes.selectAll("g.node-super");
    const ds = sel.data();
    for (const d of ds) { const c = this.centroid(d.members); d.x = c.x + (d.dx ?? 0); d.y = c.y + (d.dy ?? 0); }
    // nodes sit at their members' centroid; a few relaxation passes keep overlapping wells apart
    for (let it = 0; it < 6; it++) {
      for (let i = 0; i < ds.length; i++) {
        for (let j = i + 1; j < ds.length; j++) {
          const a = ds[i];
          const b = ds[j];
          const ra = 20 + 5 * a.members.length;
          const rb = 20 + 5 * b.members.length;
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let d = Math.hypot(dx, dy);
          if (d < 1e-3) { dx = 1; dy = 0.5; d = Math.hypot(dx, dy); }
          const overlap = ra + rb + 12 - d;
          if (overlap > 0) {
            const ux = dx / d;
            const uy = dy / d;
            a.dx = (a.dx ?? 0) - (ux * overlap) / 2; a.dy = (a.dy ?? 0) - (uy * overlap) / 2;
            b.dx = (b.dx ?? 0) + (ux * overlap) / 2; b.dy = (b.dy ?? 0) + (uy * overlap) / 2;
            a.x -= (ux * overlap) / 2; a.y -= (uy * overlap) / 2;
            b.x += (ux * overlap) / 2; b.y += (uy * overlap) / 2;
          }
        }
      }
    }
    sel.attr("transform", (d) => `translate(${d.x},${d.y})`);
    this.superLinkSel?.each((d, i, nodes) => {
      const ra = 20 + 5 * d.a.members.length;
      const rb = 20 + 5 * d.b.members.length;
      const dx = d.b.x - d.a.x;
      const dy = d.b.y - d.a.y;
      const len = Math.hypot(dx, dy) || 1;
      const x1 = d.a.x + (dx / len) * ra;
      const y1 = d.a.y + (dy / len) * ra;
      const x2 = d.b.x - (dx / len) * (rb + 6);
      const y2 = d.b.y - (dy / len) * (rb + 6);
      const g = d3.select(nodes[i]);
      g.select("path").attr("d", `M${x1} ${y1}L${x2} ${y2}`);
      g.select("text").attr("x", (x1 + x2) / 2).attr("y", (y1 + y2) / 2 - 6);
    });
  }

  // -- highlight and selection --------------------------------------------------------------------
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
    this.pillSel?.classed("dim", (d) => on && !ents.has(d.id));
    this.subSel?.classed("dim", (d) => on && !ents.has(d.entity));
    this.hullSel?.classed("dim", (d) => on && !d.hulls.some((h) => (hl.hulls ?? new Set()).has(h.id)));
    this.tabSel?.classed("dim", (d) => on && !d.hulls.some((h) => (hl.hulls ?? new Set()).has(h.id)));
    this.linkSel?.select("path.link").classed("dim", (d) => on && !d.ids.some((i) => links.has(i)))
      .classed("hl", (d) => d.ids.some((i) => hot.has(i)))
      .attr("marker-end", (d) => (d.ids.some((i) => hot.has(i)) ? "url(#arr-hl)" : d.learned ? "url(#arr-learned)" : "url(#arr)"));
  }

  select(sel) {
    this.selection = sel;
    this.pillSel?.classed("selected", (d) => sel?.kind === "entity" && sel.id === d.id);
    this.subSel?.classed("selected", (d) => sel?.kind === "subentity" && sel.id === d.id);
  }

  focusNode(id) {
    const n = this.subs.get(id) ?? this.entities.get(id);
    if (!n) return;
    const e = n.type === "sub" ? this.entities.get(n.entity) : n;
    this.zoom.zoomToPoint(e.x, e.y, n.type === "sub" ? 2.4 : 1.4);
    this.handlers.onSelect?.({ kind: n.type === "sub" ? "subentity" : "entity", id });
  }

  bounds() {
    const ns = [...this.entities.values()];
    if (!ns.length) return null;
    const x0 = Math.min(...ns.map((n) => n.x - n.w / 2)) - 30;
    const x1 = Math.max(...ns.map((n) => n.x + n.w / 2)) + 30;
    const y0 = Math.min(...ns.map((n) => n.y - n.h / 2)) - 50;
    const y1 = Math.max(...ns.map((n) => n.y + n.h / 2)) + 30;
    return [[x0, y0], [x1, y1]];
  }

  // Fit everything at the current level: the entity and subentity levels never zoom out past the
  // superentity threshold (k = 0.7), so "Fit" on a small screen keeps the Figure 1 view.
  fit(duration = 450) {
    if (this.level === "super") this.zoom.fit(this.bounds(), duration, 0.65);
    else this.zoom.fit(this.bounds(), duration, this.level === "sub" ? 2.2 : 1.6, this.level === "sub" ? 1.8 : 0.72);
  }

  // -- animation overlays (the animator calls these; it never computes model results) -----------
  posOf(id) {
    const n = this.nodeFor(id) ?? this.entities.get(String(id).split(".")[0]);
    return n ? { x: n.x, y: n.y } : null;
  }

  pulse(ids, color = css("--real-line"), ms = 600) {
    const pts = [...new Set(ids)].map((id) => this.posOf(id)).filter(Boolean);
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : ms;
    const g = this.layers.overlays.append("g");
    g.selectAll("circle").data(pts).join("circle").attr("class", "pulse").attr("cx", (d) => d.x).attr("cy", (d) => d.y)
      .attr("r", 14).attr("stroke", color).style("opacity", 0.9)
      .transition().duration(dur).attr("r", this.opts.reducedMotion ? 16 : 42).style("opacity", 0);
    g.transition().delay(dur).remove();
    return new Promise((r) => setTimeout(r, dur));
  }

  pulseLinks(ids, color = css("--real-line"), ms = 400) {
    const set = new Set(ids);
    const dur = this.opts.reducedMotion ? Math.min(ms, 150) : ms;
    const sel = this.linkSel?.filter((d) => d.ids.some((i) => set.has(i))).select("path.link");
    if (sel && !sel.empty()) {
      sel.each((d, i, nodes) => {
        const p = d3.select(nodes[i]);
        const w = +p.attr("stroke-width");
        p.interrupt().attr("stroke", color).attr("stroke-width", w + 3)
          .transition().duration(dur).attr("stroke-width", w).attr("stroke", null);
      });
    }
    return new Promise((r) => setTimeout(r, dur));
  }

  halos(zById, ms = 120) {
    for (const [id, z] of Object.entries(zById ?? {})) this.haloData.set(id, z);
    this.drawHalos();
    return new Promise((r) => setTimeout(r, this.opts.reducedMotion ? Math.min(ms, 60) : ms));
  }

  clearHalos() {
    this.haloData.clear();
    this.drawHalos();
  }

  drawHalos() {
    const data = [...this.haloData.entries()].filter(([, z]) => Math.abs(z) >= 0.05).map(([id, z]) => ({ id, z }));
    const sel = this.layers.overlays.selectAll("circle.halo").data(data, (d) => d.id);
    sel.exit().remove();
    this.haloSel = sel.enter().append("circle").attr("class", "halo").merge(sel)
      .attr("stroke", (d) => (d.z > 0 ? css("--up") : css("--down")))
      .attr("r", (d) => 10 + 9 * Math.min(3, Math.abs(d.z)));
    this.tickOverlays();
  }

  tickOverlays() {
    this.haloSel?.each((d, i, nodes) => {
      const p = this.posOf(d.id);
      if (p) d3.select(nodes[i]).attr("cx", p.x).attr("cy", p.y);
    });
  }

  flashHull(instanceId, ms = 800) {
    const dur = this.opts.reducedMotion ? 150 : ms;
    const sel = this.hullSel?.filter((d) => d.hulls.some((h) => h.id === instanceId)).select("path.shape");
    if (sel && !sel.empty()) {
      sel.interrupt().attr("stroke-width", 5).transition().duration(dur).attr("stroke-width", 1.6);
    } else {
      // not drawn (e.g. at the superentity level, or a transient hull): pulse the members
      const h = (this.view?.hulls ?? []).find((x) => x.id === instanceId);
      if (h) return this.pulse(h.members, css("--hyp-line"), dur);
    }
    return new Promise((r) => setTimeout(r, dur));
  }

  flashCandidates(candidates, ms = 700) {
    flashCandidates(this.layers.overlays, candidates, (id) => this.posOf(id), this.opts.reducedMotion ? 150 : ms);
  }
}
