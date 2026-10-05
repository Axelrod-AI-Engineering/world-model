// Gravity (§13.3): nodes behave like bodies; each superentity acts as a gravity well.
/* global d3 */
import { categoryAnchors } from "./layouts.js";

export function linkDistance(sig) {
  return 60 + 140 * (1 - Math.min(1, sig));
}

export function linkStrength(sig) {
  return 0.05 + 0.5 * Math.min(1, sig);
}

// Each entity is pulled toward the centroid of its hull (or the mean of its hulls' centroids);
// loose entities are pulled weakly toward the center.
function forceCluster(getHulls, getCenter, opts) {
  let nodes = [];
  function force(alpha) {
    const hulls = getHulls();
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const centroids = new Map();
    for (const h of hulls) {
      let sx = 0, sy = 0, k = 0;
      for (const m of h.members) {
        const n = byId.get(m);
        if (n) { sx += n.x; sy += n.y; k += 1; }
      }
      if (k) centroids.set(h.id, { x: sx / k, y: sy / k });
    }
    const anchors = opts.groupByCategory() ? categoryAnchors() : null;
    const c = getCenter();
    for (const n of nodes) {
      if (n.type !== "entity" || n.fx != null) continue;
      let tx, ty, s;
      if (anchors) {
        const tags = (n.tags ?? []).filter((t) => anchors[t]);
        if (!tags.length) continue;
        tx = tags.reduce((a, t) => a + anchors[t].x, 0) / tags.length;
        ty = tags.reduce((a, t) => a + anchors[t].y, 0) / tags.length;
        s = 0.12;
      } else if (n.instances?.length) {
        const cs = n.instances.map((i) => centroids.get(i)).filter(Boolean);
        if (!cs.length) continue;
        tx = cs.reduce((a, p) => a + p.x, 0) / cs.length;
        ty = cs.reduce((a, p) => a + p.y, 0) / cs.length;
        s = 0.12;
      } else {
        tx = c.x; ty = c.y; s = 0.02;
      }
      n.vx += (tx - n.x) * s * alpha;
      n.vy += (ty - n.y) * s * alpha;
    }
  }
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

// Subentities orbit their entity.
function forceOrbit(strength = 0.4) {
  let nodes = [];
  let parents = new Map();
  function force(alpha) {
    for (const n of nodes) {
      if (n.type !== "sub") continue;
      const p = parents.get(n.entity);
      if (!p) continue;
      n.vx += (p.x + (n.ox ?? 0) - n.x) * strength * alpha;
      n.vy += (p.y + (n.oy ?? 0) - n.y) * strength * alpha;
    }
  }
  force.initialize = (ns) => {
    nodes = ns;
    parents = new Map(ns.filter((n) => n.type === "entity").map((n) => [n.id, n]));
  };
  return force;
}

// Keep loose entities outside every hull they do not belong to.
function forceHullRepel(getHulls) {
  let nodes = [];
  function force(alpha) {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const circles = [];
    for (const h of getHulls()) {
      const ms = h.members.map((m) => byId.get(m)).filter(Boolean);
      if (ms.length < 2) continue;
      const cx = ms.reduce((a, n) => a + n.x, 0) / ms.length;
      const cy = ms.reduce((a, n) => a + n.y, 0) / ms.length;
      const r = Math.max(...ms.map((n) => Math.hypot(n.x - cx, n.y - cy) + n.w / 2)) + 14;
      circles.push({ cx, cy, r, members: new Set(h.members) });
    }
    for (const n of nodes) {
      if (n.type !== "entity" || !n.loose || n.fx != null) continue;
      for (const c of circles) {
        if (c.members.has(n.id)) continue;
        const dx = n.x - c.cx;
        const dy = n.y - c.cy;
        const d = Math.hypot(dx, dy) || 1;
        const need = c.r + n.w / 2;
        if (d < need) {
          const push = ((need - d) / d) * alpha * 0.6;
          n.vx += dx * push;
          n.vy += dy * push;
        }
      }
    }
  }
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

export function createSimulation({ getHulls, getCenter, groupByCategory, onTick }) {
  const sim = d3.forceSimulation()
    .alphaDecay(0.02)
    .velocityDecay(0.45)
    .force("charge", d3.forceManyBody().strength((d) => (d.type === "super" ? -600 : d.type === "entity" ? -220 : -60))
      .distanceMax(900))
    .force("link", d3.forceLink().id((d) => d.id).distance((l) => linkDistance(l.significance ?? 0))
      .strength((l) => linkStrength(l.significance ?? 0) * (l.weak ? 0.3 : 1)))
    .force("collide", d3.forceCollide().radius((d) => (d.type === "entity" ? d.w / 2 + 6 : (d.r ?? 8) + 4)).strength(0.7))
    .force("cluster", forceCluster(getHulls, getCenter, { groupByCategory }))
    .force("orbit", forceOrbit(0.4))
    .force("repel-hulls", forceHullRepel(getHulls))
    .force("x", d3.forceX(() => getCenter().x).strength(0.02))
    .force("y", d3.forceY(() => getCenter().y).strength(0.02))
    .on("tick", onTick);
  sim.stop();
  return sim;
}
