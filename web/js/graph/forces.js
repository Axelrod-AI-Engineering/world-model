// Forces (§13.3). In the "Figure 1" layout every box is pulled back to its home and boxes only move to
// make room for one another (an opened entity pushes its neighbors aside, and they return when it
// closes). The "Gravity" layout adds the plan's bodies: charge, link springs, and each superentity as a
// gravity well, with loose entities drawn weakly to the center.
//
// DECISION (Oct 9): gravity places, it does not float. When the structure changes, `staticLayout` runs the gravity
// physics off-screen to convergence (charge, interaction springs, superentity wells, a pull to the center of mass,
// no overlaps), with boxes already placed anchored near where they were; each box then glides once to its new home
// and stays there. In the Gravity layout every box is placed this way; in the Figure 1 layout only the "free" boxes
// Figure 1 does not place (the tutorial's, and entities created during a run).
/* global d3 */
import { categoryAnchors } from "./layouts.js";

function forceHome(getMode) {
  let nodes = [];
  function force(alpha) {
    const fig = getMode() === "figure1";
    const s = 0.22;
    for (const n of nodes) {
      if (n.fx != null || n.hx == null) continue;
      if (fig && n.flow) {
        // a reflowed entity eases straight to its place (the reflow already keeps boxes apart)
        n.vx = (n.hx - n.x) * 0.5;
        n.vy = (n.hy - n.y) * 0.5;
        continue;
      }
      n.vx += (n.hx - n.x) * s * alpha;
      n.vy += (n.hy - n.y) * s * alpha;
    }
  }
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

// Each entity is pulled toward the centroid of its superentities' members; with "group by category",
// toward its category's anchor instead.
function forceCluster(getGroups, opts) {
  let nodes = [];
  function force(alpha) {
    if (opts.getMode && opts.getMode() !== "gravity") return;
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const anchors = opts.groupByCategory() ? categoryAnchors() : null;
    const centroids = new Map();
    for (const g of getGroups()) {
      let sx = 0;
      let sy = 0;
      let k = 0;
      for (const m of g.members) {
        const n = byId.get(m);
        if (n) { sx += n.x; sy += n.y; k += 1; }
      }
      if (k) centroids.set(g.key, { x: sx / k, y: sy / k });
    }
    for (const n of nodes) {
      if (n.kind !== "entity" || n.fx != null) continue;
      let tx;
      let ty;
      let s = 0.12;
      if (anchors) {
        const tags = (n.tags ?? []).filter((t) => anchors[t]);
        if (!tags.length) continue;
        tx = tags.reduce((a, t) => a + anchors[t].x, 0) / tags.length;
        ty = tags.reduce((a, t) => a + anchors[t].y, 0) / tags.length;
      } else if (n.groupKeys?.length) {
        const cs = n.groupKeys.map((k) => centroids.get(k)).filter(Boolean);
        if (!cs.length) continue;
        tx = cs.reduce((a, p) => a + p.x, 0) / cs.length;
        ty = cs.reduce((a, p) => a + p.y, 0) / cs.length;
      } else {
        tx = 600; ty = 440; s = 0.02;
      }
      n.vx += (tx - n.x) * s * alpha;
      n.vy += (ty - n.y) * s * alpha;
    }
  }
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

// how far apart two boxes' centers should sit when an interaction ties them: their half-widths, plus a gap that
// shrinks with the interaction's significance (strong ties sit closer)
const span = (l) => ((l.source.w ?? 160) + (l.target.w ?? 160)) / 2 + 80 + 110 * (1 - Math.min(1, l.significance ?? 0));

// The live simulation only carries boxes to their homes and keeps them apart; it holds the interaction list (the
// "link" force, at zero strength) for the static layout to read.
export function createSimulation({ getMode, onTick }) {
  const sim = d3.forceSimulation()
    .alphaDecay(0.045)
    .velocityDecay(0.45)
    .force("home", forceHome(getMode))
    .force("link", d3.forceLink().id((d) => d.id).strength(0))
    .on("tick", onTick);
  sim.stop();
  return sim;
}

// Gravity, solved off-screen. `nodes`: {id, kind, x, y, w, h, oy, tags, groupKeys, fixed, anchor: {x, y} | null}.
// Returns id -> {x, y}. Anchored boxes are held gently near their anchor, so a new entity finds its place among the
// others without reshuffling them; fixed boxes do not move.
export function staticLayout(nodes, links, { groups = [], groupByCategory = false, ticks = 300 } = {}) {
  if (!nodes.length) return new Map();
  const sim = d3.forceSimulation(nodes).stop()
    .alphaDecay(1 - Math.pow(0.001, 1 / ticks))
    .velocityDecay(0.45)
    .force("charge", d3.forceManyBody().strength((d) => -(d.kind === "card" ? 700 : 260 + 1.4 * (d.w ?? 160) + 2 * (d.h ?? 30)))
      .distanceMin(30).distanceMax(900))
    .force("link", d3.forceLink(links).id((d) => d.id).distance(span)
      .strength((l) => 0.18 + 0.32 * Math.min(1, l.significance ?? 0)))
    .force("cluster", forceCluster(() => groups, { groupByCategory: () => groupByCategory }));
  for (const n of nodes) if (n.fixed) { n.fx = n.x; n.fy = n.y; }
  const anchored = nodes.filter((n) => n.anchor);
  const free = nodes.filter((n) => !n.fixed);
  for (let i = 0; i < ticks; i++) {
    sim.tick();
    const alpha = sim.alpha();
    // gravity toward the center of mass, and the anchors that keep a placed box near its place
    const cx = nodes.reduce((t, n) => t + n.x, 0) / nodes.length;
    const cy = nodes.reduce((t, n) => t + n.y, 0) / nodes.length;
    for (const n of free) {
      n.x += (cx - n.x) * 0.018 * alpha;
      n.y += (cy - n.y) * 0.026 * alpha;
    }
    for (const n of anchored) {
      if (n.fixed) continue;
      n.x += (n.anchor.x - n.x) * 0.12;
      n.y += (n.anchor.y - n.y) * 0.12;
    }
    resolveCollisions(nodes, 2);
  }
  resolveCollisions(nodes, 8);
  return new Map(nodes.map((n) => [n.id, { x: n.x, y: n.y }]));
}

// Boxes never overlap: separate every overlapping pair along the axis that needs the smaller move.
// A pinned or dragged box (fx set) stays put and the other moves the whole way.
export function resolveCollisions(nodes, iterations = 3, gapX = 14, gapY = 10) {
  const n = nodes.length;
  for (let it = 0; it < iterations; it++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j++) {
        const b = nodes[j];
        const ax0 = a.x - a.w / 2;
        const ay0 = a.y + a.oy;
        const bx0 = b.x - b.w / 2;
        const by0 = b.y + b.oy;
        const px = Math.min(ax0 + a.w, bx0 + b.w) - Math.max(ax0, bx0) + gapX;
        if (px <= 0) continue;
        const py = Math.min(ay0 + a.h, by0 + b.h) - Math.max(ay0, by0) + gapY;
        if (py <= 0) continue;
        // two reflowed entities never collide (the reflow spaces them); a card yields to a reflowed entity
        if (a.flow && b.flow) continue;
        const fixedA = a.fx != null || (a.flow && !b.flow);
        const fixedB = b.fx != null || (b.flow && !a.flow);
        if (fixedA && fixedB) continue;
        const wa = fixedA ? 0 : fixedB ? 1 : 0.5;
        const wb = 1 - wa;
        if (px * 1.6 < py) {
          const dir = (a.x + 0.001 * i) < (b.x + 0.001 * j) ? -1 : 1;
          a.x += dir * px * wa;
          b.x -= dir * px * wb;
        } else {
          const ca = ay0 + a.h / 2;
          const cb = by0 + b.h / 2;
          const dir = (ca + 0.001 * i) < (cb + 0.001 * j) ? -1 : 1;
          a.y += dir * py * wa;
          b.y -= dir * py * wb;
        }
        moved = true;
      }
    }
    if (!moved) break;
  }
}
