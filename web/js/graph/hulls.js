// Hulls (§13.3). A superentity is drawn as a soft outline that hugs its members. DECISION: instead of a
// convex hull (which swallows non-members on Figure 1's grid), the outline is one level of a field that
// is high on member boxes and on bridges between neighboring members and low near non-members, traced
// with d3.contours (in the spirit of Bubble Sets). Blocks of neighbors read like Figure 1's rounded
// rectangles, far-apart members join through thin bands, and nearby non-members are carved out. A
// composite's outline wraps its parts' outlines with more padding, so nesting reads at a glance.
/* global d3 */

export const PAD = 12;          // a leaf hull's padding around its member boxes
export const NEST_PAD = 20;     // extra padding per level of nesting
const CELL = 5;                 // field resolution, in canvas px
const CLEAR = 8;                // clearance kept around non-members
const BAND = 8;                 // half-width of the band that joins far-apart members
const MAX_BRIDGE_GAP = 96;      // neighbors closer than this (and aligned) join with a full-height bridge

// read once a frame (reading computed style on every tick forced the page's styles to be recomputed)
const cssCache = new Map();
const cssVar = (name) => {
  if (!cssCache.size) requestAnimationFrame(() => cssCache.clear());
  let v = cssCache.get(name);
  if (v == null) { v = getComputedStyle(document.documentElement).getPropertyValue(name).trim(); cssCache.set(name, v); }
  return v;
};

// The extended pastel list leaves out violet and orchid, which mean real and hypothetical events.
const EXTENDED = [["#F6E7C1", "#B39443"], ["#DDE8C8", "#7E9B55"], ["#F2D6C2", "#B97E57"], ["#D3E4EC", "#5F8DA6"],
  ["#EBDDCB", "#9C8461"], ["#D5EAD4", "#62985F"], ["#F1D9DF", "#B07688"], ["#D9E7E4", "#5D958A"],
  ["#E9E3C9", "#A39A5B"], ["#E0E9D9", "#7C9A6C"], ["#F3DCC9", "#B88458"], ["#DCE3EE", "#6B84A8"]];

export function paletteOf(item, palettes) {
  const key = item?.palette;
  if (key && /^h[1-7]$/.test(key)) {
    return { fill: cssVar(`--${key}-fill`), line: cssVar(`--${key}-line`), ink: cssVar(`--${key}-ink`) };
  }
  let fill;
  let line;
  if (key && palettes?.[key]) ({ fill, line } = palettes[key]);
  else {
    let h = 0;
    for (const ch of String(item?.pattern_id ?? item?.key ?? "")) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    [fill, line] = EXTENDED[h % EXTENDED.length];
  }
  // generated palettes give a pale line; darken it so dashed outlines and tab text stay legible
  const l = d3.hcl(line);
  if (l.l > 58) l.l = 52;
  const lineColor = l.formatHex();
  const ink = d3.hcl(lineColor);
  ink.l = Math.max(22, ink.l - 18);
  return { fill, line: lineColor, ink: ink.formatHex() };
}

export function hullStyle(g, pal) {
  if (g.transient) return { fill: "none", stroke: cssVar("--hyp-line"), dash: "7 4", fillOpacity: 0 };
  if (g.status === "candidate") return { fill: "none", stroke: pal.line, dash: "1.5 4", fillOpacity: 0 };
  // DECISION: an outer (composite) hull is mostly outline and a rival pair is lighter, so the seven
  // Figure 1 hulls keep their tint and overlaps stay legible
  if (g.composite) return { fill: pal.fill, stroke: pal.line, dash: "12 4 2 4", fillOpacity: 0.16 };
  if (g.hulls.length > 1) return { fill: pal.fill, stroke: pal.line, dash: "6 4", fillOpacity: 0.3 };
  return { fill: pal.fill, stroke: pal.line, dash: "6 4", fillOpacity: 0.55 };
}

// -- grouping -------------------------------------------------------------------------------------
// One drawn group per pattern (DECISION: the instance the seeds bound, else the most active one; other
// instances of the same pattern show in the inspector), rival patterns that bind the same entities
// share a group with one tab each, and composites list their parts' groups as children.
export function buildGroups(view, { showCandidates = false, pendingPatterns = new Set() } = {}) {
  const all = view?.hulls ?? [];
  const patternOfInstance = new Map(all.map((h) => [h.id, h.pattern_id]));
  const pick = new Map();
  const better = (a, b) => {
    const sa = a.id === `inst-${a.pattern_id}` ? 1 : 0;
    const sb = b.id === `inst-${b.pattern_id}` ? 1 : 0;
    if (sa !== sb) return sa > sb;
    if (a.activation !== b.activation) return a.activation > b.activation;
    return a.id < b.id;
  };
  for (const h of all) {
    if (h.transient || h.status === "dissolved") continue;
    if (h.status === "candidate" && !showCandidates && !pendingPatterns.has(h.pattern_id)) continue;
    const cur = pick.get(h.pattern_id);
    if (!cur || better(h, cur)) pick.set(h.pattern_id, h);
  }
  const groups = [];
  const byKey = new Map();
  const groupOfPattern = new Map();
  for (const h of [...pick.values()].sort((a, b) => a.pattern_id.localeCompare(b.pattern_id, undefined, { numeric: true }))) {
    if (groupOfPattern.has(h.pattern_id)) continue;
    const memberKey = [...h.members].sort().join("|");
    // a rival that binds the same entities joins this group
    const rivals = (h.rival_ids ?? []).map((r) => pick.get(r)).filter((r) => r && [...r.members].sort().join("|") === memberKey);
    const hulls = [h, ...rivals];
    const g = {
      key: h.id, hulls, patternIds: hulls.map((x) => x.pattern_id), members: new Set(h.members),
      status: hulls.some((x) => x.status === "admitted") ? "admitted" : "candidate", transient: false,
      palette: h.palette, pattern_id: h.pattern_id, composite: (h.child_instance_ids ?? []).length > 0,
      children: [], parents: [], level: 0, description: h.description ?? "",
      label: hulls.map((x) => x.label).join("  |  "), support: Math.max(...hulls.map((x) => x.support ?? 0)),
    };
    for (const x of hulls) groupOfPattern.set(x.pattern_id, g);
    groups.push(g);
    byKey.set(g.key, g);
  }
  // composites: children are the drawn groups of the parts' patterns
  for (const g of groups) {
    if (!g.composite) continue;
    for (const c of g.hulls[0].child_instance_ids ?? []) {
      const child = groupOfPattern.get(patternOfInstance.get(c));
      if (child && child !== g && !g.children.includes(child.key)) {
        g.children.push(child.key);
        child.parents.push(g.key);
        for (const m of child.members) g.members.add(m);
      }
    }
  }
  const levelOf = (g, seen = new Set()) => {
    if (seen.has(g.key)) return 0;
    seen.add(g.key);
    g.level = g.children.length ? 1 + Math.max(...g.children.map((k) => levelOf(byKey.get(k), seen))) : 0;
    return g.level;
  };
  for (const g of groups) levelOf(g);
  // transient hulls (bound for one hypothetical) are outlines only
  for (const h of all) {
    if (!h.transient) continue;
    const g = { key: h.id, hulls: [h], patternIds: [h.pattern_id], members: new Set(h.members), status: h.status,
                transient: true, palette: h.palette, pattern_id: h.pattern_id, composite: false, children: [],
                parents: [], level: 0, description: h.description ?? "", label: `${h.label} (hypothetical)`, support: h.support };
    groups.push(g);
    byKey.set(g.key, g);
  }
  const ofEntity = new Map();
  for (const g of groups) {
    if (g.transient) continue;
    for (const m of g.members) {
      if (!ofEntity.has(m)) ofEntity.set(m, []);
      ofEntity.get(m).push(g.key);
    }
  }
  const ofInstance = new Map();
  for (const h of all) {
    const g = groupOfPattern.get(h.pattern_id);
    if (g) ofInstance.set(h.id, g.key);
  }
  for (const g of groups) if (g.transient) ofInstance.set(g.key, g.key);
  return { groups, byKey, ofEntity, ofInstance };
}

// Ancestors of a group (composites can share parts, so this walks a DAG).
export function ancestors(byKey, key) {
  const out = [];
  const stack = [...(byKey.get(key)?.parents ?? [])];
  const seen = new Set();
  while (stack.length) {
    const k = stack.pop();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(k);
    stack.push(...(byKey.get(k)?.parents ?? []));
  }
  return out;
}

// -- the field and its contour -------------------------------------------------------------------
function rectDist(px, py, r) {
  const dx = Math.max(r.x0 - px, 0, px - r.x1);
  const dy = Math.max(r.y0 - py, 0, py - r.y1);
  return Math.hypot(dx, dy);
}

function segDist(px, py, s) {
  const vx = s.bx - s.ax;
  const vy = s.by - s.ay;
  const len2 = vx * vx + vy * vy || 1;
  const t = Math.max(0, Math.min(1, ((px - s.ax) * vx + (py - s.ay) * vy) / len2));
  return Math.hypot(px - (s.ax + t * vx), py - (s.ay + t * vy));
}

const overlap = (a0, a1, b0, b1) => Math.min(a1, b1) - Math.max(a0, b0);

function rectGap(a, b) {
  const dx = Math.max(0, a.x0 - b.x1, b.x0 - a.x1);
  const dy = Math.max(0, a.y0 - b.y1, b.y0 - a.y1);
  return Math.hypot(dx, dy);
}

// Bridges along a minimum spanning tree of the member boxes: aligned neighbors join with a full-height
// (or full-width) bridge, as Figure 1's rectangles do; others with a thin band between nearest points.
function bridges(rects) {
  const out = { rects: [], segs: [] };
  const n = rects.length;
  if (n < 2) return out;
  const inTree = new Set([0]);
  const best = rects.map((r, i) => (i === 0 ? null : { d: rectGap(rects[0], r), from: 0 }));
  while (inTree.size < n) {
    let k = -1;
    for (let i = 0; i < n; i++) if (!inTree.has(i) && (k < 0 || best[i].d < best[k].d)) k = i;
    const a = rects[best[k].from];
    const b = rects[k];
    inTree.add(k);
    for (let i = 0; i < n; i++) {
      if (inTree.has(i)) continue;
      const d = rectGap(b, rects[i]);
      if (d < best[i].d) best[i] = { d, from: k };
    }
    const oy = overlap(a.y0, a.y1, b.y0, b.y1);
    const ox = overlap(a.x0, a.x1, b.x0, b.x1);
    const gx = Math.max(b.x0 - a.x1, a.x0 - b.x1);
    const gy = Math.max(b.y0 - a.y1, a.y0 - b.y1);
    if (oy > 8 && gx > 0 && gx <= MAX_BRIDGE_GAP) {
      out.rects.push({ x0: Math.min(a.x1, b.x1), x1: Math.max(a.x0, b.x0), y0: Math.max(a.y0, b.y0), y1: Math.min(a.y1, b.y1) });
    } else if (ox > 8 && gy > 0 && gy <= MAX_BRIDGE_GAP) {
      out.rects.push({ y0: Math.min(a.y1, b.y1), y1: Math.max(a.y0, b.y0), x0: Math.max(a.x0, b.x0), x1: Math.min(a.x1, b.x1) });
    } else if (gx > 0 || gy > 0) {
      const ax = Math.max(a.x0, Math.min((b.x0 + b.x1) / 2, a.x1));
      const ay = Math.max(a.y0, Math.min((b.y0 + b.y1) / 2, a.y1));
      const bx = Math.max(b.x0, Math.min(ax, b.x1));
      const by = Math.max(b.y0, Math.min(ay, b.y1));
      out.segs.push({ ax, ay, bx, by });
    }
  }
  return out;
}

const smooth = d3.line().curve(d3.curveBasisClosed);

// Thin a traced ring for drawing (Oct 11). Marching squares leaves a point on every cell along a box's side; a smoothed
// closed curve through a straight run of points is the same straight line through its two ends, so only the points
// within KEEP of a turn are kept. The curve near each turn is unchanged, and an outline has a tenth of the points to
// stroke and dash, which zoomed in had made every frame that moved an outline slow to draw.
const KEEP = 3;
function thin(ring) {
  const n = ring.length;
  if (n < 12) return ring;
  const turn = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const [ax, ay] = ring[(i - 1 + n) % n];
    const [bx, by] = ring[i];
    const [cx, cy] = ring[(i + 1) % n];
    if (Math.abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-3 * CELL * CELL) turn[i] = 1;
  }
  const keep = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    if (!turn[i]) continue;
    for (let k = -KEEP; k <= KEEP; k++) keep[(i + k + n) % n] = 1;
  }
  const out = ring.filter((_, i) => keep[i]);
  return out.length >= 3 ? out : ring;
}

// A remembered outline (Oct 11): tracing is the canvas's costliest step, and most ticks move nothing near a given
// outline, so each one is traced again only when its members, or the boxes in its reach, moved by a pixel or more.
const traced = new Map();
export function hullContourCached(key, members, obstacles, pad = PAD) {
  if (!members.length) { traced.delete(key); return null; }
  let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
  for (const r of members) { x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1); }
  const m = 2 * pad + 2 * CELL + CLEAR;
  const near = obstacles.filter((r) => r.x1 > x0 - m && r.x0 < x1 + m && r.y1 > y0 - m && r.y0 < y1 + m);
  const sig = `${pad}|${[members, near].map((rs) => rs.map((r) => `${Math.round(r.x0)},${Math.round(r.y0)},${Math.round(r.x1)},${Math.round(r.y1)}`).join(";")).join("|")}`;
  const hit = traced.get(key);
  if (hit && hit.sig === sig) return hit.c;
  const c = hullContour(members, near, pad);
  traced.set(key, { sig, c });
  return c;
}

// Trace a group's outline. `members` and `obstacles` are rects {x0, y0, x1, y1} in canvas coordinates.
// Returns {d, anchor, bbox} or null.
export function hullContour(members, obstacles, pad = PAD) {
  if (!members.length) return null;
  const br = bridges(members);
  const reach = 2 * pad;
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const r of members) {
    x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1);
  }
  x0 -= reach + 2 * CELL; y0 -= reach + 2 * CELL; x1 += reach + 2 * CELL; y1 += reach + 2 * CELL;
  const nx = Math.max(3, Math.ceil((x1 - x0) / CELL));
  const ny = Math.max(3, Math.ceil((y1 - y0) / CELL));
  const values = new Float64Array(nx * ny);
  const cellRange = (lo, hi, origin, n) => [Math.max(0, Math.floor((lo - origin) / CELL)), Math.min(n - 1, Math.ceil((hi - origin) / CELL))];
  const splatRect = (r, rad) => {
    const [i0, i1] = cellRange(r.x0 - rad, r.x1 + rad, x0, nx);
    const [j0, j1] = cellRange(r.y0 - rad, r.y1 + rad, y0, ny);
    for (let j = j0; j <= j1; j++) {
      const py = y0 + (j + 0.5) * CELL;
      for (let i = i0; i <= i1; i++) {
        const v = 1 - rectDist(x0 + (i + 0.5) * CELL, py, r) / rad;
        const k = j * nx + i;
        if (v > values[k]) values[k] = v;
      }
    }
  };
  for (const r of members) splatRect(r, reach);
  for (const r of br.rects) splatRect(r, reach);
  for (const s of br.segs) {
    const rad = 2 * BAND;
    const [i0, i1] = cellRange(Math.min(s.ax, s.bx) - rad, Math.max(s.ax, s.bx) + rad, x0, nx);
    const [j0, j1] = cellRange(Math.min(s.ay, s.by) - rad, Math.max(s.ay, s.by) + rad, y0, ny);
    for (let j = j0; j <= j1; j++) {
      const py = y0 + (j + 0.5) * CELL;
      for (let i = i0; i <= i1; i++) {
        const v = 1 - segDist(x0 + (i + 0.5) * CELL, py, s) / rad;
        const k = j * nx + i;
        if (v > values[k]) values[k] = v;
      }
    }
  }
  // carve out non-members that sit inside the region
  const rad = 2 * CLEAR;
  for (const o of obstacles) {
    if (o.x1 < x0 || o.x0 > x1 || o.y1 < y0 || o.y0 > y1) continue;
    const [i0, i1] = cellRange(o.x0 - rad, o.x1 + rad, x0, nx);
    const [j0, j1] = cellRange(o.y0 - rad, o.y1 + rad, y0, ny);
    for (let j = j0; j <= j1; j++) {
      const py = y0 + (j + 0.5) * CELL;
      for (let i = i0; i <= i1; i++) {
        const k = j * nx + i;
        if (values[k] <= 0) continue;
        const g = 1 - rectDist(x0 + (i + 0.5) * CELL, py, o) / rad;
        if (g > 0) values[k] -= g;
      }
    }
  }
  const [mp] = d3.contours().size([nx, ny]).thresholds([0.5])(values);
  if (!mp || !mp.coordinates.length) return null;
  let d = "";
  let best = null;
  let bx0 = Infinity;
  let by0 = Infinity;
  let bx1 = -Infinity;
  let by1 = -Infinity;
  for (const poly of mp.coordinates) {
    for (let r = 0; r < poly.length; r++) {
      const ring = poly[r].slice(0, -1).map(([gx, gy]) => [x0 + gx * CELL, y0 + gy * CELL]);
      if (ring.length < 3) continue;
      d += smooth(thin(ring));
      if (r === 0) {
        const area = Math.abs(d3.polygonArea(ring));
        if (!best || area > best.area) best = { area, ring };
        for (const [x, y] of ring) {
          bx0 = Math.min(bx0, x); by0 = Math.min(by0, y); bx1 = Math.max(bx1, x); by1 = Math.max(by1, y);
        }
      }
    }
  }
  if (!best) return null;
  // tab spots: the top-left corner of the largest piece first, then its other corners
  const ys = best.ring.map((p) => p[1]);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  const near = (y0) => best.ring.filter((p) => Math.abs(p[1] - y0) <= 4).map((p) => p[0]);
  const corners = [
    { x: Math.min(...near(top)) + 6, y: top + 1, align: "left" },
    { x: Math.min(...near(bottom)) + 6, y: bottom - 1, align: "left" },
    { x: Math.max(...near(top)) - 6, y: top + 1, align: "right" },
    { x: Math.max(...near(bottom)) - 6, y: bottom - 1, align: "right" },
  ];
  // points on the outline's top edges (inside just below, outside just above): where tabs may sit
  // (tested against the thinned ring: dropping points from straight runs leaves the polygon as it was)
  const topEdge = [];
  const poly = thin(best.ring);
  for (let k = 0; k < best.ring.length; k += 2) {
    const [x, y] = best.ring[k];
    if (d3.polygonContains(poly, [x, y + 6]) && !d3.polygonContains(poly, [x, y - 6])) topEdge.push([x, y]);
  }
  topEdge.sort((a, b) => (a[1] - b[1]) + 0.1 * (a[0] - b[0]));
  return { d, anchor: corners[0], corners, ring: best.ring, topEdge, bbox: { x0: bx0, y0: by0, x1: bx1, y1: by1 } };
}

// A block (Oct 11): a rounded rectangle around a superentity's home members, for the hierarchy's layout, where every
// superentity has a block of its own. It returns what hullContour returns, so tabs and lenses work the same.
const BLOCK_R = 14;
export function blockHull(members, pad = PAD) {
  if (!members.length) return null;
  let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
  for (const r of members) { x0 = Math.min(x0, r.x0); y0 = Math.min(y0, r.y0); x1 = Math.max(x1, r.x1); y1 = Math.max(y1, r.y1); }
  x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
  const rr = Math.min(BLOCK_R + pad / 3, (x1 - x0) / 2, (y1 - y0) / 2);
  const d = `M${x0 + rr},${y0}H${x1 - rr}A${rr},${rr} 0 0 1 ${x1},${y0 + rr}V${y1 - rr}A${rr},${rr} 0 0 1 ${x1 - rr},${y1}`
    + `H${x0 + rr}A${rr},${rr} 0 0 1 ${x0},${y1 - rr}V${y0 + rr}A${rr},${rr} 0 0 1 ${x0 + rr},${y0}Z`;
  // the outline as points, clockwise from the top-left, for tabs (top edge) and lenses
  const ring = [];
  const step = 6;
  for (let x = x0; x <= x1; x += step) ring.push([x, y0]);
  for (let y = y0; y <= y1; y += step) ring.push([x1, y]);
  for (let x = x1; x >= x0; x -= step) ring.push([x, y1]);
  for (let y = y1; y >= y0; y -= step) ring.push([x0, y]);
  const corners = [
    { x: x0 + 6, y: y0 + 1, align: "left" }, { x: x0 + 6, y: y1 - 1, align: "left" },
    { x: x1 - 6, y: y0 + 1, align: "right" }, { x: x1 - 6, y: y1 - 1, align: "right" },
  ];
  const topEdge = ring.filter(([, y], i) => y === y0 && i % 2 === 0);
  return { d, anchor: corners[0], corners, ring, topEdge, bbox: { x0, y0, x1, y1 } };
}

// A convex blob around some boxes (for the generalization end of a fuzzy ribbon).
export function hullPolygon(rects, pad = PAD) {
  const pts = [];
  for (const r of rects) pts.push([r.x0 - pad, r.y0 - pad], [r.x1 + pad, r.y0 - pad], [r.x1 + pad, r.y1 + pad], [r.x0 - pad, r.y1 + pad]);
  return pts.length >= 3 ? d3.polygonHull(pts) : null;
}
