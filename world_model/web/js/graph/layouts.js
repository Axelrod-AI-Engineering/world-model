// Layout presets (§13.3). "Figure 1" (the default here) holds every pill near its Figure 1 position and
// only lets nodes move to make room; "Gravity" starts there and lets the forces run.

export const FIG_PILL = { width: 164, height: 30 };
export const GRID = { dx: 216, dy: 52, x0: 168, y0: 251 };

export function figurePosition(layout, entityId) {
  const p = layout?.entities?.[entityId];
  return p ? { x: p[0], y: p[1] } : null;
}

// A home for an entity that Figure 1 does not place (one created during a run): the free grid slot
// nearest its neighbors, outside the regions the seeded superentities cover.
// DECISION: new entities snap to Figure 1's grid, so the tidy first view stays tidy as the graph grows.
export function slotPosition(entityId, view, homes, regions) {
  const neighbors = [];
  for (const l of view?.entity_links ?? []) {
    if (l.source === entityId && homes.has(l.target)) neighbors.push(homes.get(l.target));
    if (l.target === entityId && homes.has(l.source)) neighbors.push(homes.get(l.source));
  }
  const target = neighbors.length
    ? { x: neighbors.reduce((s, p) => s + p.x, 0) / neighbors.length, y: neighbors.reduce((s, p) => s + p.y, 0) / neighbors.length }
    : { x: 1290, y: 520 };
  const taken = [...homes.values()];
  const free = (x, y) => taken.every((p) => Math.abs(p.x - x) > GRID.dx / 2 || Math.abs(p.y - y) > GRID.dy * 0.8)
    && regions.every((r) => x < r.x0 - 90 || x > r.x1 + 90 || y < r.y0 - 22 || y > r.y1 + 22);
  let best = null;
  for (let i = -3; i <= 7; i++) {
    for (let j = -3; j <= 12; j++) {
      const x = GRID.x0 + i * GRID.dx;
      const y = GRID.y0 + j * GRID.dy;
      if (!free(x, y)) continue;
      const d = Math.hypot((x - target.x) / 1.4, y - target.y);
      if (!best || d < best.d) best = { x, y, d };
    }
  }
  return best ? { x: best.x, y: best.y } : { x: target.x + 60, y: target.y + 60 };
}

export const CATEGORY_CODES = ["SD", "MF", "SC", "DI", "DF", "EN", "EX", "SH"];
export const CATEGORY_NAMES = {
  SD: "Spending and demand", MF: "Money and finance", SC: "Supply and capacity", DI: "Distribution",
  DF: "Deep foundations", EN: "Environment", EX: "Expectations", SH: "Shocks",
};
// One plain sentence per category, shown in the key and in tooltips.
export const CATEGORY_BLURBS = {
  SD: "Who buys what: households, firms, governments, and foreigners. Demand sets output in the short run.",
  MF: "The price and supply of money: interest rates, inflation, credit, debt, the dollar, and capital flows.",
  SC: "What the economy can produce: technology, workers, energy and commodities, supply chains, and competition.",
  DI: "Who gets the gains: inequality within countries and between them.",
  DF: "The slow rules of the game: institutions, law and regulation, geography, culture and trust.",
  EN: "The physical world: a changing climate and extreme weather.",
  EX: "What people believe about the future: confidence and policy uncertainty. Beliefs move spending today.",
  SH: "Sudden breaks: epidemics, wars, financial crises, and asset price swings.",
};

// "Group by category": eight fixed anchors on a circle, one per category tag. It shows that tags are
// labels, not structure.
export function categoryAnchors(cx = 600, cy = 440, r = 440) {
  const out = {};
  CATEGORY_CODES.forEach((c, i) => {
    const a = (i / CATEGORY_CODES.length) * Math.PI * 2 - Math.PI / 2;
    out[c] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  return out;
}
