// Hulls (§13.3): convex hulls of the member boxes, padded by 14 px and smoothed with
// curveCatmullRomClosed.alpha(0.5), with a tab label. Styles follow Figure 1's key.
/* global d3 */

const PAD = 14;
const COMPOSITE_PAD = 30;
const EXTENDED = ["#F6E7C1", "#DDE8C8", "#F2D6C2", "#D3E4EC", "#EBDDCB", "#D5EAD4", "#F1D9DF", "#D9E7E4",
                  "#E9E3C9", "#E0E9D9", "#F3DCC9", "#DCE3EE"];
const EXTENDED_LINE = ["#B39443", "#7E9B55", "#B97E57", "#5F8DA6", "#9C8461", "#62985F", "#B07688", "#5D958A",
                       "#A39A5B", "#7C9A6C", "#B88458", "#6B84A8"];

const smooth = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.5));

export function paletteOf(hull, palettes) {
  const key = hull.palette;
  const css = getComputedStyle(document.documentElement);
  if (key && /^h[1-7]$/.test(key)) {
    return { fill: css.getPropertyValue(`--${key}-fill`).trim(), line: css.getPropertyValue(`--${key}-line`).trim() };
  }
  if (key && palettes?.[key]) return { fill: palettes[key].fill, line: palettes[key].line };
  if (key === "h8") return { fill: "#F0E2C8", line: "#A8854A" };
  if (key === "h9") return { fill: "#D8E2EF", line: "#5C7EA6" };
  // the extended pastel list leaves out violet and orchid (reserved for real and hypothetical events)
  let h = 0;
  for (const ch of hull.pattern_id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return { fill: EXTENDED[h % EXTENDED.length], line: EXTENDED_LINE[h % EXTENDED_LINE.length] };
}

function boxPoints(n, pad) {
  const w = n.w / 2 + pad;
  const h = n.h / 2 + pad;
  return [[n.x - w, n.y - h], [n.x + w, n.y - h], [n.x + w, n.y + h], [n.x - w, n.y + h]];
}

export function hullPolygon(nodes, pad = PAD) {
  const pts = [];
  for (const n of nodes) if (Number.isFinite(n.x)) pts.push(...boxPoints(n, pad));
  if (pts.length < 3) return null;
  return d3.polygonHull(pts);
}

export function polygonPath(poly) {
  return poly ? smooth(poly) : null;
}

export function expandPolygon(poly, by) {
  if (!poly) return null;
  const c = d3.polygonCentroid(poly);
  return poly.map(([x, y]) => {
    const dx = x - c[0];
    const dy = y - c[1];
    const d = Math.hypot(dx, dy) || 1;
    return [x + (dx / d) * by, y + (dy / d) * by];
  });
}

// Group hulls for drawing: rival instances binding the same entities share one shape with a tab
// per rival; composites become outer hulls around their children.
export function groupHulls(hulls) {
  const groups = [];
  const byKey = new Map();
  for (const h of hulls) {
    if (h.child_instance_ids?.length) {
      groups.push({ key: h.id, hulls: [h], composite: true });
      continue;
    }
    const memberKey = [...h.members].sort().join("|");
    const rivalKey = h.rival_ids?.length ? [h.pattern_id, ...h.rival_ids].sort().join("+") : null;
    const key = rivalKey ? `${rivalKey}@${memberKey}@${h.transient}` : h.id;
    if (rivalKey && byKey.has(key)) {
      byKey.get(key).hulls.push(h);
      continue;
    }
    const g = { key, hulls: [h], composite: false };
    if (rivalKey) byKey.set(key, g);
    groups.push(g);
  }
  return groups;
}

export function hullStyle(h, pal) {
  const css = getComputedStyle(document.documentElement);
  if (h.transient) {
    return { fill: "none", stroke: css.getPropertyValue("--hyp-line").trim(), dash: "7 4", fillOpacity: 0 };
  }
  if (h.status === "candidate") return { fill: "none", stroke: pal.line, dash: "1.5 4", fillOpacity: 0 };
  if (h.status === "dissolved") return { fill: "none", stroke: "#B9B0A2", dash: "2 6", fillOpacity: 0 };
  return { fill: pal.fill, stroke: pal.line, dash: "7 4", fillOpacity: 0.55 };
}

export { PAD, COMPOSITE_PAD };
