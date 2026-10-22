// Semantic zoom (Oct 22): a large model reads as groups first, and members appear as the view closes in.
//
// The server nests the entities into superentities (view.clusters, api/hierarchy.py). The layout places each group as a
// region, so a group has a box on the canvas: the box around its members' homes. Which groups are drawn as one box and
// which are opened into their members is the cut through that hierarchy, chosen from the zoom and the part of the model
// in view:
//   - a group opens when it is in view and big enough on screen for its parts to read (EXPAND_PX, measured as the square
//     root of its screen area), the nearest the middle of the view first, until MAX_SHOWN boxes are in view; an entity's pill does not open
//     below MIN_K, where its name could not be read;
//   - it closes below COLLAPSE of that size, or when it is well out of view. The gap between the two is the hysteresis
//     that stops a group opening and closing around one zoom value;
//   - the cut is chosen once the view rests (the same debounce as detail, graph/lod.js), never mid-gesture, and only the
//     groups whose state changes are redrawn. Nothing moves: boxes sit at the layout's homes, which do not depend on
//     the zoom.
// A group a person opened or closed by hand keeps that state until the zoom moves well past where it was chosen.

const EXPAND_PX = 230;          // a group opens at this screen size (sqrt of its area)
const COLLAPSE = 0.76;          // and closes below this share of it
const MAX_SHOWN = 26;           // boxes in view at once (groups and entities)
const GRACE = 1.25;             // a group already open may stay while the count is this far over
const MIN_K = 0.3;              // below this zoom an entity's name is unreadable: its group stays closed
const IN_VIEW = 0.08;           // a closed group opens only inside the view, grown by this share of it
const STAY_VIEW = 0.45;         // an open one stays until it is this far outside
const HAND_DROP = [0.55, 1.8];  // a hand-opened group closes below this share of its zoom; a hand-closed one frees above this
const PAD = 16;
const STEP_MS = 70;
const REST_MS = 120;
const HEAD = 30;

export const clusterBoxId = (id) => `cl:${id}`;

export function createSemantic(r, { pillWidth }) {
  let clusters = new Map();        // id -> cluster
  let roots = [];                  // top-level cluster ids
  let key = "";
  const open = new Set();          // groups opened into their parts (the cut)
  const hand = new Map();          // id -> {open, k}
  let timer = null;
  let geo = new Map();             // id -> {x0, y0, x1, y1, area} of the group's members at their homes
  let geoKey = "";

  function setView(view) {
    const cs = view?.clusters ?? [];
    const next = cs.map((c) => `${c.id}:${c.label}`).join("|");
    if (next === key) return;
    key = next;
    clusters = new Map(cs.map((c) => [c.id, c]));
    roots = cs.filter((c) => !c.parent).map((c) => c.id);
    for (const id of [...open]) if (!clusters.has(id)) open.delete(id);
    for (const id of [...hand.keys()]) if (!clusters.has(id)) hand.delete(id);
    geo = new Map();
    geoKey = "";
  }

  // Semantic zoom is on for a gravity layout of a model that has groups, and off while something else arranges the
  // canvas (a staged review, a transmission lane, an isolated graph, the walkthrough)
  function active() {
    if (!clusters.size || !r.view || r.isolated || r.lane || r.peeked || r.opts.groupByCategory || r.mode !== "gravity") return false;
    const b = document.body.classList;
    return !(b.contains("staging") || b.contains("txpath") || b.contains("gupdate") || document.querySelector("#walkthrough:not(.hidden)"));
  }

  // every entity has a home, so the groups' boxes can be placed
  function ready() {
    return r.view.entities.every((e) => r.gravHomes.has(e.id) || r.pinnedHomes.has(e.id));
  }

  function geometry() {
    const k = `${key}#${r.gravHomes.size}#${r.pinnedHomes.size}`;
    if (k === geoKey) return geo;
    geoKey = k;
    geo = new Map();
    const w = new Map(r.view.entities.map((e) => [e.id, pillWidth(e.name)]));
    for (const c of clusters.values()) {
      let x0 = Infinity; let y0 = Infinity; let x1 = -Infinity; let y1 = -Infinity;
      for (const m of c.members) {
        const h = r.fixedHome(m) ?? r.gravHomes.get(m);
        if (!h) continue;
        x0 = Math.min(x0, h.x - w.get(m) / 2); x1 = Math.max(x1, h.x + w.get(m) / 2);
        y0 = Math.min(y0, h.y - HEAD / 2); y1 = Math.max(y1, h.y + HEAD / 2);
      }
      if (x0 === Infinity) continue;
      x0 -= PAD; y0 -= PAD; x1 += PAD; y1 += PAD;
      geo.set(c.id, { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 });
    }
    return geo;
  }

  const screenSize = (g, k) => Math.sqrt(g.w * g.h) * k;

  function inView(g, vb, margin) {
    const mx = (vb.x1 - vb.x0) * margin;
    const my = (vb.y1 - vb.y0) * margin;
    return g.x1 >= vb.x0 - mx && g.x0 <= vb.x1 + mx && g.y1 >= vb.y0 - my && g.y0 <= vb.y1 + my;
  }

  // The cut the current zoom and view ask for, from the cut now (hysteresis). Deterministic: the nearest the middle of the
  // view first, ties by id; a group opens only after the one that holds it.
  function wanted() {
    const t = r.zoom.transform();
    const vb = r.lod.viewBox(t);
    const g = geometry();
    // hand states fade as the zoom moves well past where they were set
    for (const [id, h] of [...hand]) {
      if (h.open ? t.k < h.k * HAND_DROP[0] : t.k > h.k * HAND_DROP[1]) hand.delete(id);
    }
    const homeOfEntity = (id) => r.fixedHome(id) ?? r.gravHomes.get(id);
    const entIn = (id, margin) => {
      const h = homeOfEntity(id);
      return !!h && inView({ x0: h.x, x1: h.x, y0: h.y, y1: h.y }, vb, margin);
    };
    const dist = (c) => { const b = g.get(c.id); return b ? Math.hypot(b.cx - vb.cx, b.cy - vb.cy) : Infinity; };
    const next = new Set();
    const held = new Set(roots.flatMap((id) => clusters.get(id).members));
    // boxes in view count against the cap: the top level and loose entities to begin with; an opening takes its own box
    // away and adds the parts of it that are in view
    let shown = roots.filter((id) => g.has(id) && inView(g.get(id), vb, IN_VIEW)).length
      + r.view.entities.filter((e) => !held.has(e.id) && entIn(e.id, IN_VIEW)).length;
    const queue = roots.map((id) => clusters.get(id));
    const order = (a, b) => dist(a) - dist(b) || (a.id < b.id ? -1 : 1);
    queue.sort(order);
    while (queue.length) {
      const c = queue.shift();
      const box = g.get(c.id);
      if (!box) continue;
      const was = open.has(c.id);
      const h = hand.get(c.id);
      let go;
      if (h) go = h.open;
      else {
        const big = screenSize(box, t.k) >= EXPAND_PX * (was ? COLLAPSE : 1);
        const near = inView(box, vb, was ? STAY_VIEW : IN_VIEW);
        const readable = c.children.length > 0 || t.k >= MIN_K * (was ? 0.85 : 1);
        const parts = c.children.filter((id) => g.has(id) && inView(g.get(id), vb, IN_VIEW)).length
          + c.entity_ids.filter((id) => entIn(id, IN_VIEW)).length;
        const room = shown - 1 + parts <= MAX_SHOWN * (was ? GRACE : 1);
        go = big && near && readable && room;
        if (go) shown += parts - 1;
      }
      if (!go) continue;
      next.add(c.id);
      for (const id of c.children) queue.push(clusters.get(id));
      queue.sort(order);
    }
    return next;
  }

  // what the canvas draws now: group boxes, and the entities that are not inside one
  function shown() {
    const g = geometry();
    const boxes = [];
    const owner = new Map();
    const entities = new Set();
    const held = new Set(roots.flatMap((id) => clusters.get(id).members));
    for (const e of r.view.entities) if (!held.has(e.id)) entities.add(e.id);
    const visit = (id) => {
      const c = clusters.get(id);
      const box = g.get(id);
      if (!open.has(id) || !box) {
        const w = Math.max(box?.w ?? 160, 140);
        const h = Math.max(box?.h ?? 80, 70);
        boxes.push({ id: clusterBoxId(id), cluster: c, w, h, x: box?.cx ?? 600, y: box?.cy ?? 440 });
        for (const m of c.members) owner.set(m, clusterBoxId(id));
        return;
      }
      for (const m of c.entity_ids) entities.add(m);
      for (const kid of c.children) visit(kid);
    };
    for (const id of roots) visit(id);
    return { boxes, entities, owner };
  }

  // the home of a group's box
  function homeOf(boxId) {
    const g = geometry().get(boxId.slice(3));
    return g ? { x: g.cx, y: g.cy } : null;
  }

  function step() {
    timer = null;
    if (!r.model) return;
    // the layout or a review turned superentities off (or on): the drawing follows
    if (active() !== !!r.model.shown && (active() ? ready() : true)) { r.recompute("tier"); return; }
    if (!active() || !r.autoDetail || !ready()) return;
    if (document.body.classList.contains("zooming")) { schedule(REST_MS); return; }
    apply(wanted());
  }

  // adopt a cut; redraw only if it differs
  function apply(next) {
    const same = next.size === open.size && [...next].every((id) => open.has(id));
    if (same) return false;
    open.clear();
    for (const id of next) open.add(id);
    r.recompute("tier");
    return true;
  }

  function schedule(ms = 0) {
    if (timer) return;
    timer = setTimeout(step, ms);
  }

  // every group the entity sits in, outermost first
  function pathTo(entityId) {
    const out = [];
    for (const id of roots) {
      const c = clusters.get(id);
      if (c.members.includes(entityId)) {
        let cur = c;
        while (cur) {
          out.push(cur.id);
          cur = cur.children.map((k) => clusters.get(k)).find((k) => k.members.includes(entityId));
        }
        break;
      }
    }
    return out;
  }

  return {
    setView, active, ready, shown, homeOf, geometry, pathTo, wanted,
    clusters: () => clusters,
    roots: () => roots,
    isOpen: (id) => open.has(id),
    // a zoom or pan: choose again once the view has rested
    update() { clearTimeout(timer); timer = null; schedule(STEP_MS); },
    now() { clearTimeout(timer); timer = null; step(); },
    // a person opened or closed a group (click, double-click, the menu)
    toggle(id, to = !open.has(id)) {
      if (!clusters.has(id)) return false;
      hand.set(id, { open: to, k: r.zoom.transform().k });
      if (to) open.add(id);
      else {
        open.delete(id);
        // its parts close with it
        const drop = (c) => { for (const k of c.children) { open.delete(k); hand.delete(k); drop(clusters.get(k)); } };
        drop(clusters.get(id));
      }
      r.recompute("tier");
      return true;
    },
    // open every group on the way to these entities (the walkthrough, find, a framed node); true if the cut changed
    reveal(ids) {
      let changed = false;
      for (const e of ids) {
        for (const id of pathTo(e)) {
          if (!open.has(id)) { open.add(id); hand.set(id, { open: true, k: r.zoom.transform().k }); changed = true; }
        }
      }
      return changed;
    },
    // every group closed into the top level, or every one open
    setAll(opened, redraw = true) {
      hand.clear();
      open.clear();
      if (opened) for (const id of clusters.keys()) open.add(id);
      for (const id of clusters.keys()) hand.set(id, { open: !!opened, k: r.zoom.transform().k });
      if (redraw) r.recompute("tier");
    },
    reset() { open.clear(); hand.clear(); },
  };
}
