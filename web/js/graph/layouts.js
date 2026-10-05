// Layout presets (§13.3): "gravity" starts from Figure 1's positions and lets the forces run;
// "figure1" pins every pill at its Figure 1 position and draws the seed hulls with the figure's shapes.

export const FIG_PILL = { width: 164, height: 30 };
export const DEMO_COLUMN_X = 1290;

export function figurePosition(layout, entityId) {
  const p = layout?.entities?.[entityId];
  return p ? { x: p[0], y: p[1] } : null;
}

// A start position for an entity with no Figure 1 position: next to its first neighbor, or in the
// demo-additions column.
export function fallbackPosition(entityId, view, positions, index = 0) {
  const neighbors = [];
  for (const l of view?.entity_links ?? []) {
    if (l.source === entityId && positions.has(l.target)) neighbors.push(positions.get(l.target));
    if (l.target === entityId && positions.has(l.source)) neighbors.push(positions.get(l.source));
  }
  if (neighbors.length) {
    const x = neighbors.reduce((s, p) => s + p.x, 0) / neighbors.length;
    const y = neighbors.reduce((s, p) => s + p.y, 0) / neighbors.length;
    return { x: x + 40 + 13 * (index % 5), y: y + 46 };
  }
  return { x: DEMO_COLUMN_X, y: 470 + 52 * (index % 8) };
}

// Figure 1's own hull shapes, as SVG path strings in the figure's frame.
export function figureHullPath(layout, patternId) {
  const h = layout?.hulls?.[patternId];
  if (!h) return null;
  if (h.path) return h.path;
  if (h.rect) {
    const [x, y, w, hh] = h.rect;
    return `M${x} ${y}H${x + w}V${y + hh}H${x}Z`;
  }
  return null;
}

export function figureHullAnchor(layout, patternId) {
  const h = layout?.hulls?.[patternId];
  if (!h) return null;
  if (h.rect) return { x: h.rect[0] + 8, y: h.rect[1] - 6 };
  const m = /^M\s*([\d.]+)[ ,]([\d.]+)/.exec(h.path ?? "");
  return m ? { x: +m[1] + 8, y: +m[2] - 6 } : null;
}

export const CATEGORY_CODES = ["SD", "MF", "SC", "DI", "DF", "EN", "EX", "SH"];
export const CATEGORY_NAMES = {
  SD: "spending and demand", MF: "money and finance", SC: "supply and capacity", DI: "distribution",
  DF: "deep foundations", EN: "environment", EX: "expectations", SH: "shocks",
};

// "Group by category": eight fixed anchors on a circle, one per category tag.
export function categoryAnchors(cx = 640, cy = 440, r = 420) {
  const out = {};
  CATEGORY_CODES.forEach((c, i) => {
    const a = (i / CATEGORY_CODES.length) * Math.PI * 2 - Math.PI / 2;
    out[c] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  return out;
}
