// The hierarchical layout (Oct 11): the gravity layout's first placement, which keeps the default view uncluttered.
//
// The graph is laid out the way its groups nest. Oct 17: the groups are the static taxonomy's concepts (graph/concepts.js:
// Actor > Firm > Bank, …), no longer superentities, and they are not drawn; related entities simply sit together. Every
// group is a region; its sub-concepts are regions inside it, and its own members sit beside them. Each region is laid
// out on its own, bottom-up:
//   - a flow toward causal order: an item goes in the column of its rank in the interactions between items, so causes
//     sit left of their effects and most arrows point the same way;
//   - each column ordered so items sit level with what they are joined to;
//   - no overlaps: boxes and regions are kept apart, with a wider gap between regions than between pills.
// A region's size is the box around what it holds, padded, so its parent places it as one body. An entity in several
// groups is placed in one of them (the most specific, with the most interactions inside).
// [x, y] gaps between items; regions stand apart (Oct 11). Oct 17: regions are no longer outlined, so they need less
// room around them (pad) and between them; the gap alone tells one concept from the next
const SPACING = { entity: [22, 14], region: [52, 40], pad: 10 };
const RANK_GAP = 34;                                     // added between causal columns at the root (Oct 14)
const ASPECT = 1.3;                                      // the width to height every arrangement aims for (Oct 11)

export function hierarchicalLayout(nodes, links, groups, { center = { x: 600, y: 440 }, spacing = SPACING } = {}) {
  const gap = (it) => (it.region ? spacing.region : spacing.entity);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const live = groups.filter((g) => !g.transient);
  const gByKey = new Map(live.map((g) => [g.key, g]));

  // the primary region of each entity: the most specific group holding it, with the most links inside
  const linksIn = (g, id) => links.filter((l) => (l.source === id && g.members.has(l.target)) || (l.target === id && g.members.has(l.source))).length;
  const primary = new Map();
  for (const n of nodes) {
    const holders = live.filter((g) => g.members.has(n.id));
    const leafmost = holders.filter((g) => !holders.some((h) => h !== g && g.children.includes(h.key)));
    leafmost.sort((a, b) => linksIn(b, n.id) - linksIn(a, n.id) || a.members.size - b.members.size || (a.key < b.key ? -1 : 1));
    if (leafmost.length) primary.set(n.id, leafmost[0].key);
  }
  // the region tree: each region's items are its parts that hold something, and its own entities
  const owns = new Map();               // region key (or "") -> item ids: "g:<key>" for a region, a box id otherwise
  const add = (k, id) => { if (!owns.has(k)) owns.set(k, []); if (!owns.get(k).includes(id)) owns.get(k).push(id); };
  const parentOf = (g) => g.parents.find((p) => gByKey.has(p)) ?? "";
  for (const [eid, k] of primary) add(k, eid);
  for (const n of nodes) if (!primary.has(n.id)) add("", n.id);
  // a region appears in its parent once it holds anything
  const holds = (k) => (owns.get(k)?.length ?? 0) > 0;
  let changed = true;
  while (changed) {
    changed = false;
    for (const g of live) {
      if (!holds(g.key)) continue;
      const p = parentOf(g);
      const id = `g:${g.key}`;
      if (!(owns.get(p) ?? []).includes(id)) { add(p, id); changed = true; }
    }
  }
  // the box (or region) in container k that holds a node id
  const itemIn = new Map();             // `${k}|${boxId}` -> item id
  const resolve = (k, box) => {
    const key = `${k}|${box}`;
    if (itemIn.has(key)) return itemIn.get(key);
    let found = null;
    for (const it of owns.get(k) ?? []) {
      if (it === box) { found = it; break; }
      if (it.startsWith("g:") && contains(it.slice(2), box)) { found = it; break; }
    }
    itemIn.set(key, found);
    return found;
  };
  const containsMemo = new Map();
  function contains(k, box) {
    const key = `${k}|${box}`;
    if (containsMemo.has(key)) return containsMemo.get(key);
    const r = (owns.get(k) ?? []).some((it) => it === box || (it.startsWith("g:") && contains(it.slice(2), box)));
    containsMemo.set(key, r);
    return r;
  }

  // lay out one region: returns its items' centers (relative) and its size
  const placed = new Map();             // region key -> {pos: Map(item -> {x, y}), w, h}
  function layoutRegion(k) {
    if (placed.has(k)) return placed.get(k);
    const items = (owns.get(k) ?? []).map((id) => {
      if (id.startsWith("g:")) {
        const sub = layoutRegion(id.slice(2));
        return { id, w: sub.w, h: sub.h, region: true };
      }
      const n = byId.get(id);
      return { id, w: n?.w ?? 180, h: n?.h ?? 30, region: false };
    });
    // interactions between this region's items, summed
    const agg = new Map();
    for (const l of links) {
      const a = resolve(k, l.source);
      const b = resolve(k, l.target);
      if (!a || !b || a === b) continue;
      const key = `${a}>${b}`;
      agg.set(key, (agg.get(key) ?? 0) + 0.4 + (l.significance ?? 0));
    }
    const pairs = [...agg.entries()].map(([key, w]) => { const [a, b] = key.split(">"); return { a, b, w }; });
    const rank = flowRanks(items.map((i) => i.id), pairs);
    const pos = solve(items, pairs, rank, gap, !k);
    // the region's box, padded for its outline (the root is not a region)
    let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
    for (const it of items) {
      const p = pos.get(it.id);
      x0 = Math.min(x0, p.x - it.w / 2); x1 = Math.max(x1, p.x + it.w / 2);
      y0 = Math.min(y0, p.y - it.h / 2); y1 = Math.max(y1, p.y + it.h / 2);
    }
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    for (const p of pos.values()) { p.x -= cx; p.y -= cy; }
    const pad = k ? spacing.pad : 0;
    const out = { pos, w: (x1 - x0) + 2 * pad, h: (y1 - y0) + 2 * pad };
    placed.set(k, out);
    return out;
  }

  // place every box: walk down from the root, adding each region's offset
  const result = new Map();
  function place(k, ox, oy) {
    const { pos } = layoutRegion(k);
    for (const [id, p] of pos) {
      if (id.startsWith("g:")) place(id.slice(2), ox + p.x, oy + p.y);
      else {
        const n = byId.get(id);
        // a box's y is its header's middle; the layout works with box centers
        result.set(id, { x: ox + p.x, y: oy + p.y - ((n?.oy ?? -15) + (n?.h ?? 30) / 2) });
      }
    }
  }
  layoutRegion("");
  place("", center.x, center.y);
  return result;
}

// causal order among a region's items: a longest-path rank on the net direction of the interactions between them
function flowRanks(ids, pairs) {
  const net = new Map();
  for (const { a, b, w } of pairs) {
    const k = a < b ? `${a}|${b}` : `${b}|${a}`;
    net.set(k, (net.get(k) ?? 0) + (a < b ? w : -w));
  }
  const out = new Map(ids.map((id) => [id, []]));
  const indeg = new Map(ids.map((id) => [id, 0]));
  for (const [k, w] of net) {
    if (Math.abs(w) < 1e-9) continue;
    const [x, y] = k.split("|");
    const [a, b] = w > 0 ? [x, y] : [y, x];
    out.get(a)?.push(b);
    indeg.set(b, (indeg.get(b) ?? 0) + 1);
  }
  // Kahn's order, breaking any cycle at the item with the fewest remaining inputs
  const rank = new Map(ids.map((id) => [id, 0]));
  const left = new Set(ids);
  while (left.size) {
    let pick = [...left].filter((id) => indeg.get(id) === 0);
    if (!pick.length) pick = [[...left].sort((a, b) => indeg.get(a) - indeg.get(b))[0]];
    for (const u of pick) {
      left.delete(u);
      for (const v of out.get(u) ?? []) {
        if (!left.has(v)) continue;
        rank.set(v, Math.max(rank.get(v), rank.get(u) + 1));
        indeg.set(v, indeg.get(v) - 1);
      }
    }
  }
  return rank;
}

// a region's physics: repulsion, attraction along interactions, a pull toward the flow's columns, and no overlaps
// A region's arrangement, without physics, so it is the same every time and nothing overlaps:
// - inside a region, layers: one column per causal rank (causes left, effects right), each column ordered so items sit
//   level with what they are joined to (a few barycenter sweeps); a column taller than the region should be wraps into
//   side-by-side sub-columns, so regions stay compact;
// - at the root, shelves: the regions, in causal order, packed row by row into a block about as wide as the screen.
function solve(items, pairs, rank, gap, root = false) {
  const pos = new Map();
  if (items.length === 1) { pos.set(items[0].id, { x: 0, y: 0 }); return pos; }
  // DECISION (Oct 14): a root that holds only entities (no concepts, as in the small demo's first steps) is laid out like a
  // region, causes left of effects; packed as shelves, a chain stacked into one column with its arrows squeezed between
  // the pills
  if (root && items.some((it) => it.region)) return shelves(items, rank, gap, pos);
  // layers by rank, then barycenter order within each
  const layers = [];
  for (const it of items) (layers[rank.get(it.id) ?? 0] ??= []).push(it);
  const L = layers.filter(Boolean);
  const nb = new Map(items.map((it) => [it.id, []]));
  for (const { a, b } of pairs) { nb.get(a)?.push(b); nb.get(b)?.push(a); }
  let order = new Map();
  L.forEach((layer) => layer.forEach((it, i) => order.set(it.id, i)));
  for (let sweep = 0; sweep < 4; sweep++) {
    for (const layer of L) {
      const bc = (it) => { const ns = nb.get(it.id).filter((n) => order.has(n)); return ns.length ? ns.reduce((t, n) => t + order.get(n), 0) / ns.length : order.get(it.id); };
      layer.sort((a, b) => bc(a) - bc(b) || a.id.localeCompare(b.id));
      layer.forEach((it, i) => order.set(it.id, i));
    }
  }
  // DECISION (Oct 11): a region is laid out a little wider than tall. Columns (one per causal rank) wrap into side-by-side
  // sub-columns at a height chosen from a range so the region's width to height is nearest ASPECT.
  const area = items.reduce((t, it) => t + (it.w + gap(it)[0]) * (it.h + gap(it)[1]), 0);
  let best = null;
  for (const f of [0.35, 0.45, 0.55, 0.65, 0.8, 0.95, 1.15, 1.4, 1.8, 2.5]) {
    const out = layered(L, Math.max(90, Math.sqrt(area) * f), gap, root ? RANK_GAP : 0);
    const score = Math.abs(Math.log(out.w / Math.max(out.h, 1) / ASPECT));
    if (!best || score < best.score - 1e-9) best = { ...out, score };
  }
  for (const [id, p] of best.pos) pos.set(id, p);
  return pos;
}

// columns of a region's layers, each wrapping into sub-columns no taller than maxH; returns positions and the size
function layered(L, maxH, gap, rankGap = 0) {
  const pos = new Map();
  let x = 0;
  let hMax = 0;
  L.forEach((layer, li) => {
    // DECISION (Oct 14): at the root (entities in no group), causal columns stand further apart than the
    // sub-columns of one rank, so the arrows between causes and effects have room to curve and to show their heads;
    // inside a group the columns keep their tight spacing, so the regions keep their size
    if (li > 0) x += rankGap;
    const cols = [[]];
    let h = 0;
    for (const it of layer) {
      const ih = it.h + gap(it)[1];
      if (h + ih > maxH && cols.at(-1).length) { cols.push([]); h = 0; }
      cols.at(-1).push(it);
      h += ih;
    }
    for (const col of cols) {
      const w = Math.max(...col.map((it) => it.w + gap(it)[0]));
      const total = col.reduce((t, it) => t + it.h + gap(it)[1], 0);
      hMax = Math.max(hMax, total);
      let y = -total / 2;
      for (const it of col) {
        const ih = it.h + gap(it)[1];
        pos.set(it.id, { x: x + w / 2, y: y + ih / 2 });
        y += ih;
      }
      x += w;
    }
  });
  return { pos, w: x, h: hMax };
}

// the root: regions in causal order, packed row by row at the width whose result is nearest ASPECT (wider than tall)
function shelves(items, rank, gap, pos) {
  const sorted = [...items].sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0) || b.w * b.h - a.w * a.h);
  const widest = Math.max(...sorted.map((it) => it.w + gap(it)[0]));
  const total = sorted.reduce((t, it) => t + it.w + gap(it)[0], 0);
  const pack = (width) => {
    let rowsW = 0; let h = 0; let w = 0; let rh = 0;
    for (const it of sorted) {
      const iw = it.w + gap(it)[0];
      if (w + iw > width && w > 0) { rowsW = Math.max(rowsW, w); h += rh; w = 0; rh = 0; }
      w += iw; rh = Math.max(rh, it.h + gap(it)[1]);
    }
    return { w: Math.max(rowsW, w), h: h + rh };
  };
  let width = widest;
  let bestScore = Infinity;
  for (let k = 0; k <= 30; k++) {
    const cand = widest + (total - widest) * (k / 30);
    const { w, h } = pack(cand);
    const score = Math.abs(Math.log(w / Math.max(h, 1) / ASPECT));
    if (score < bestScore - 1e-9) { bestScore = score; width = cand; }
  }
  const rows = [[]];
  let w = 0;
  for (const it of sorted) {
    const iw = it.w + gap(it)[0];
    if (w + iw > width && rows.at(-1).length) { rows.push([]); w = 0; }
    rows.at(-1).push(it);
    w += iw;
  }
  let y = 0;
  for (const row of rows) {
    const rh = Math.max(...row.map((it) => it.h + gap(it)[1]));
    const rw = row.reduce((t, it) => t + it.w + gap(it)[0], 0);
    let x = -rw / 2;
    for (const it of row) {
      const iw = it.w + gap(it)[0];
      pos.set(it.id, { x: x + iw / 2, y: y + rh / 2 });
      x += iw;
    }
    y += rh;
  }
  return pos;
}
