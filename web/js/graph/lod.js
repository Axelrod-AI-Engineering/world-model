// Level of detail that follows zoom gradually, like a map (Oct 11). It replaces Oct 9's three global levels, which
// switched everything at once after a zoom settled and re-laid out the graph each time.
//
// Each superentity and each entity decides for itself, from its own size on screen:
//   - a superentity closes into a card once its drawn outline is narrower than CARD_CLOSE pixels on screen, and opens
//     again once it would be wider than CARD_OPEN (the gap between them keeps it from flickering); a closed one's width
//     is the width its outline had when last drawn, at today's zoom;
//   - an entity in view opens into its values once the scale passes the learned threshold (attention.kOpen), and
//     closes below 86% of it or once it leaves the view;
//   - changes wait until the view rests, then all of them apply at once (Oct 11, supersedes "a few per frame"): with
//     superentities drawn as blocks every change re-packs the hierarchy, so a drip of small changes moved the whole
//     canvas again and again after a zoom. One pass means one re-pack and one glide.
// Boxes then glide once to their new homes. An entity a person opened or closed by hand stays that way until the zoom passes back
// through its threshold.

const CARD_CLOSE = 170;
const CARD_OPEN = 230;
const READABLE_K = 0.6;          // below this scale names start to get small: only then do superentities fold
const LEVEL_STEP = 0.72;         // each level up the hierarchy folds this much further out than the level below it
const OPEN_HYST = 0.86;
const MAX_OPEN = 6;                // values open only for the few entities nearest the middle of the view
const STEP_MS = 70;
const SETTLE_MS = 650;             // hover pop-ups wait this long after a change of detail, while the boxes glide
const REST_MS = 120;               // how often a buffered change checks whether the view has rested

export function createLOD(r, attention) {
  let timer = null;
  const handOpen = new Set();      // opened by hand: stays open while zoomed in
  const handClosed = new Set();    // closed by hand: stays closed while zoomed in
  const pinned = new Set();        // kept open whatever the zoom (an isolated graph's entities)

  function viewBox(t, margin = 0) {
    const rect = r.zoom.rect();
    const i = r.insets?.() ?? { left: 0, right: 0 };
    const x0 = (i.left - t.x) / t.k;
    const x1 = (rect.width - i.right - t.x) / t.k;
    const y0 = (Math.max(56, i.top ?? 0) - t.y) / t.k;
    const y1 = (rect.height - 64 - t.y) / t.k;
    const mx = (x1 - x0) * margin;
    const my = (y1 - y0) * margin;
    return { x0: x0 - mx, x1: x1 + mx, y0: y0 - my, y1: y1 + my, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 };
  }

  // a superentity's width on screen: measured from its drawn outline when open (and remembered in world units for when
  // it is closed); estimated from its members' homes when it has never been drawn
  const worldWidth = new Map();
  function screenWidth(g, k) {
    if (!r.ui.collapsed.has(g.key)) {
      const el = r.layers?.hulls?.node()?.querySelector(`g.hull[data-instance="${CSS.escape(g.key)}"]`);
      const w = el?.getBoundingClientRect().width;
      if (w) { worldWidth.set(g.key, w / k); return w; }
    }
    const ww = worldWidth.get(g.key) ?? groupSpan(g)?.w;
    return ww ? ww * k : null;
  }

  // the outline of a superentity, from its members' homes (stable whether it is open or closed)
  function groupSpan(g) {
    const pts = [...g.members].map((m) => r.entityHome(m)).filter(Boolean);
    if (!pts.length) return null;
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    return { w: Math.max(...xs) - Math.min(...xs) + 220, cx: (Math.min(...xs) + Math.max(...xs)) / 2,
             cy: (Math.min(...ys) + Math.max(...ys)) / 2 };
  }

  // how many levels of superentities a superentity holds below it (0 for one with no parts)
  function height(g, seen = new Set()) {
    if (!g.children?.length || seen.has(g.key)) return 0;
    seen.add(g.key);
    return 1 + Math.max(...g.children.map((c) => { const cg = r.groupsInfo.byKey.get(c); return cg ? height(cg, seen) : 0; }));
  }

  // every change the current zoom asks for, nearest the middle of the view first
  function wanted() {
    if (!r.model || !r.view) return [];
    const t = r.zoom.transform();
    const v = viewBox(t);
    const near = viewBox(t, 0.1);
    const out = [];
    const dist = (x, y) => Math.hypot(x - v.cx, y - v.cy);
    // superentities, outermost first: an inner one only matters once its parent is open
    const groups = r.groupsInfo.groups.filter((g) => !g.transient);
    // an isolated graph is small by construction: everything in it stays open
    for (const g of r.isolated ? [] : groups) {
      if (g.parents.some((p) => r.ui.collapsed.has(p))) continue;
      const sp = groupSpan(g);
      const sw = screenWidth(g, t.k);
      if (!sp || sw == null) continue;
      const closed = r.ui.collapsed.has(g.key);
      // the hierarchy folds from the inside out (Oct 11): a superentity with no parts folds once names get small, one
      // holding parts further out, and one holding those further out still, so zooming out climbs the hierarchy a
      // level at a time. Within a level, the narrowest fold first. A one-member superentity never folds.
      // size only nudges the order within a level: a small region folds a little sooner, a large one a little later
      const h = height(g);
      const nudge = Math.max(0.85, Math.min(1.2, (CARD_OPEN * (1 + h)) / Math.max(1, sw / Math.max(t.k, 0.05) * READABLE_K)));
      const kFold = READABLE_K * LEVEL_STEP ** h * nudge;
      if (!closed && g.members.size > 1 && t.k < kFold) out.push({ kind: "close-group", key: g.key, d: -sw });
      else if (closed && t.k >= kFold * 1.12) out.push({ kind: "open-group", key: g.key, d: dist(sp.cx, sp.cy) });
    }
    // entities' values
    const kOpen = attention.kOpen;
    if (t.k < kOpen * OPEN_HYST) { handOpen.clear(); handClosed.clear(); }
    const ents = [...r.nodes.values()].filter((n) => n.kind === "entity");
    const inView = (n) => n.x >= near.x0 && n.x <= near.x1 && n.y >= near.y0 && n.y <= near.y1;
    const inner = viewBox(t, -0.22);
    const inMiddle = (n) => n.x >= inner.x0 && n.x <= inner.x1 && n.y >= inner.y0 && n.y <= inner.y1;
    const candidates = t.k >= kOpen
      ? ents.filter((n) => inMiddle(n) && !handClosed.has(n.id)).sort((a, b) => dist(a.x, a.y) - dist(b.x, b.y)).slice(0, MAX_OPEN)
      : [];
    const keep = new Set(candidates.map((n) => n.id));
    for (const n of ents) {
      const open = r.ui.expanded.has(n.id);
      if (handOpen.has(n.id) || pinned.has(n.id)) continue;
      const stay = open && t.k >= kOpen * OPEN_HYST && inView(n);
      if (!open && keep.has(n.id)) out.push({ kind: "open", id: n.id, d: dist(n.x, n.y) });
      else if (open && !keep.has(n.id) && !stay) out.push({ kind: "close", id: n.id, d: -dist(n.x, n.y) });
    }
    return out.sort((a, b) => a.d - b.d);
  }

  function step() {
    timer = null;
    if (!r.autoDetail || r.peeked || document.body.classList.contains("staging")) return;
    // buffered (Oct 11): while a person is still panning or zooming, changes wait; each one re-lays out the
    // neighbors and retraces outlines, which made a zoomed-in view lag. They start as soon as the view rests.
    if (document.body.classList.contains("zooming")) { schedule(REST_MS); return; }
    const todo = wanted();
    if (!todo.length) return;
    for (const c of todo) {
      if (c.kind === "close-group") r.ui.collapsed.add(c.key);
      else if (c.kind === "open-group") r.ui.collapsed.delete(c.key);
      else if (c.kind === "open") r.ui.expanded.add(c.id);
      else r.ui.expanded.delete(c.id);
    }
    // nothing pops up under the still cursor while the boxes glide to their new homes
    document.body.classList.add("zooming");
    clearTimeout(r.zoomingTimer);
    r.zoomingTimer = setTimeout(() => document.body.classList.remove("zooming"), SETTLE_MS);
    r.handlers.onHover?.(null);
    r.recompute("lod");
    // DECISION: no follow-up pass. The re-pack moves boxes, which would change what sits in the middle of the view and
    // start another round; detail is chosen again only when a person moves the view.
  }

  function schedule(ms = 0) {
    if (!r.autoDetail || timer) return;
    timer = setTimeout(step, ms);
  }

  return {
    // called on every zoom or pan, and when detail-follows-zoom is switched on
    update() { schedule(STEP_MS); },
    now() { clearTimeout(timer); timer = null; step(); },
    // a person opened or closed an entity by hand
    hand(id, opened) {
      const k = r.zoom.transform().k;
      (opened ? handOpen : handClosed).add(id);
      (opened ? handClosed : handOpen).delete(id);
      attention.learnOpen(k, opened);
      attention.touch(id, k, 3);
    },
    reset() { handOpen.clear(); handClosed.clear(); pinned.clear(); },
    // keep these entities open whatever the zoom (an isolated graph's), without teaching the threshold
    pin(ids) { for (const id of ids) { pinned.add(id); handClosed.delete(id); } },
    viewBox,
  };
}
