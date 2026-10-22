// Level of detail that follows zoom gradually, like a map (Oct 11). It replaces Oct 9's three global levels, which
// switched everything at once after a zoom settled and re-laid out the graph each time.
//
// Each entity decides for itself, from the zoom and where it sits:
//   - an entity in view opens into its values once the scale passes the learned threshold (attention.kOpen), and
//     closes below 86% of it or once it leaves the view;
//   - changes wait until the view rests, then all of them apply at once (Oct 11, supersedes "a few per frame"), so a
//     zoom moves the canvas once.
// Oct 17: superentities no longer fold into cards as the view zooms out; they are not drawn on the canvas at all.
// An entity a person opened or closed by hand stays that way until the zoom passes back through its threshold.

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
  // Oct 14: the zoom at which detail was last chosen. Zooming in only ever opens things and zooming out only ever closes
  // them, so a zoom never closes what a person is zooming toward
  let kAt = null;

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

  // every change the current zoom asks for, nearest the middle of the view first
  function wanted() {
    if (!r.model || !r.view) return [];
    const t = r.zoom.transform();
    const v = viewBox(t);
    const near = viewBox(t, 0.1);
    const out = [];
    const dir = kAt == null ? 0 : t.k > kAt * 1.001 ? 1 : t.k < kAt / 1.001 ? -1 : 0;
    const dist = (x, y) => Math.hypot(x - v.cx, y - v.cy);
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
      // a pan (dir 0) may open and close values as entities enter and leave the middle; a zoom only moves one way
      if (!open && keep.has(n.id) && dir >= 0) out.push({ kind: "open", id: n.id, d: dist(n.x, n.y) });
      else if (open && !keep.has(n.id) && !stay && (dir <= 0 || !inView(n))) out.push({ kind: "close", id: n.id, d: -dist(n.x, n.y) });
    }
    return out.sort((a, b) => a.d - b.d);
  }

  function step() {
    timer = null;
    if (!r.autoDetail || r.peeked || document.body.classList.contains("staging")) return;
    // buffered (Oct 11): while a person is still panning or zooming, changes wait; each one moves the neighbors, which
    // made a zoomed-in view lag. They start as soon as the view rests.
    if (document.body.classList.contains("zooming")) { schedule(REST_MS); return; }
    const todo = wanted();
    kAt = r.zoom.transform().k;
    if (!todo.length) return;
    for (const c of todo) {
      if (c.kind === "open") r.ui.expanded.add(c.id);
      else r.ui.expanded.delete(c.id);
    }
    // nothing pops up under the still cursor while the boxes glide to their new homes
    document.body.classList.add("zooming");
    clearTimeout(r.zoomingTimer);
    r.zoomingTimer = setTimeout(() => document.body.classList.remove("zooming"), SETTLE_MS);
    r.handlers.onHover?.(null);
    r.recompute("lod");
    // DECISION: no follow-up pass. Opening moves boxes, which would change what sits in the middle of the view and
    // start another round; detail is chosen again only when a person moves the view.
  }

  function schedule(ms = 0) {
    if (!r.autoDetail || timer) return;
    timer = setTimeout(step, ms);
  }

  return {
    // called on every zoom or pan, and when detail-follows-zoom is switched on. Debounced (Oct 14): detail is chosen once
    // the view has stopped for STEP_MS, never partway through an animated zoom (the zoom buttons and the slider glide)
    update() { clearTimeout(timer); timer = null; schedule(STEP_MS); },
    now() { clearTimeout(timer); timer = null; step(); },
    // a person opened or closed an entity by hand
    hand(id, opened) {
      const k = r.zoom.transform().k;
      (opened ? handOpen : handClosed).add(id);
      (opened ? handClosed : handOpen).delete(id);
      attention.learnOpen(k, opened);
      attention.touch(id, k, 3);
    },
    reset() { handOpen.clear(); handClosed.clear(); pinned.clear(); kAt = null; },
    // the view was framed by the app (not by a person): its zoom is where the next zoom's direction is measured from
    mark() { kAt = r.zoom.transform().k; },
    // keep these entities open whatever the zoom (an isolated graph's), without teaching the threshold
    pin(ids) { for (const id of ids) { pinned.add(id); handClosed.delete(id); } },
    viewBox,
  };
}
