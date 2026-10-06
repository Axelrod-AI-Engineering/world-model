// Forces (§13.3). In the "Figure 1" layout every box is pulled back to its home and boxes only move to
// make room for one another (an opened entity pushes its neighbors aside, and they return when it
// closes). The "Gravity" layout adds the plan's bodies: charge, link springs, and each superentity as a
// gravity well, with loose entities drawn weakly to the center.
/* global d3 */
import { categoryAnchors } from "./layouts.js";

export function linkDistance(sig) {
  return 60 + 140 * (1 - Math.min(1, sig));
}

export function linkStrength(sig) {
  return 0.05 + 0.5 * Math.min(1, sig);
}

function forceHome(getMode) {
  let nodes = [];
  function force(alpha) {
    const fig = getMode() === "figure1";
    const s = fig ? 0.22 : 0.025;
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
    if (opts.getMode() !== "gravity") return;
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

export function createSimulation({ getMode, getGroups, groupByCategory, onTick }) {
  const gravity = () => getMode() === "gravity";
  const sim = d3.forceSimulation()
    .alphaDecay(0.03)
    .velocityDecay(0.42)
    .force("home", forceHome(getMode))
    .force("charge", d3.forceManyBody().strength((d) => (gravity() ? (d.kind === "card" ? -600 : -220) : 0)).distanceMax(700))
    .force("link", d3.forceLink().id((d) => d.id).distance((l) => linkDistance(l.significance ?? 0))
      .strength((l) => (gravity() ? linkStrength(l.significance ?? 0) * 0.5 : 0)))
    .force("cluster", forceCluster(getGroups, { getMode, groupByCategory }))
    .on("tick", onTick);
  sim.stop();
  return sim;
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
