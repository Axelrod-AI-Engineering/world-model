// Edge routing (Oct 14): where each interaction's curve leaves and enters its boxes, and how it bends.
//
// DECISION (Oct 14): edges are cubic curves between ports on the boxes' borders, not lines from center to center:
//   - sides: an edge leaves and enters through the facing sides, preferring left and right (the layout runs causes left
//     of effects), so a curve starts and ends square to its box;
//   - ports: the edges that share a side are spread along it, ordered by where their other end is, so they do not
//     cross at the box and two edges between the same pair (A→B and B→A, or two interactions) run side by side;
//   - clipping: a curve ends exactly at the border; the arrowhead (drawn from the curve's end) fills the last few
//     pixels, so its tip touches the box and never sits inside it or short of it;
//   - detours: a curve that would pass through another box (a pill, an open entity, a card, a superentity's tab) has
//     its control points pushed away from that box, a few times at most;
//   - parallel edges between the same pair bow apart a little more.
// It is cheap (a spatial grid, a handful of samples per edge) and runs while the layout moves and once at rest, never
// per zoom frame: zooming slides the drawing already made.

const CELL = 140;             // spatial grid cell (world units)
const CLEAR = 7;              // how far a curve keeps from a box it detours around
const PASSES = 6;
const MAX_BEND = 240;      // the most a curve's control points move for detours, in all

export function rectOf(n) {
  return { x0: n.x - n.w / 2, y0: n.y + n.oy, x1: n.x + n.w / 2, y1: n.y + n.oy + n.h };
}

export function cubicAt(r, t) {
  const u = 1 - t;
  const a = u * u * u; const b = 3 * u * u * t; const c = 3 * u * t * t; const d = t * t * t;
  return [a * r.p0[0] + b * r.c1[0] + c * r.c2[0] + d * r.p3[0], a * r.p0[1] + b * r.c1[1] + c * r.c2[1] + d * r.p3[1]];
}

const NORMAL = { L: [-1, 0], R: [1, 0], T: [0, -1], B: [0, 1] };

// which sides two rects connect through: [side of a, side of b]
function sidesFor(ra, rb, preferH = 1.6) {
  const hgap = Math.max(rb.x0 - ra.x1, ra.x0 - rb.x1);
  const vgap = Math.max(rb.y0 - ra.y1, ra.y0 - rb.y1);
  const right = rb.x0 + rb.x1 >= ra.x0 + ra.x1;
  const below = rb.y0 + rb.y1 >= ra.y0 + ra.y1;
  let horiz;
  if (hgap > 0 && vgap <= 0) horiz = true;
  else if (vgap > 0 && hgap <= 0) horiz = false;
  else if (hgap <= 0 && vgap <= 0) horiz = Math.abs((rb.x0 + rb.x1) - (ra.x0 + ra.x1)) >= Math.abs((rb.y0 + rb.y1) - (ra.y0 + ra.y1));
  else horiz = hgap * preferH >= vgap;
  if (horiz) return right ? ["R", "L"] : ["L", "R"];
  return below ? ["B", "T"] : ["T", "B"];
}

/**
 * Route every edge at once (ports are shared, so they are spread together).
 * specs: [{key, a: {box, row}, b: {box, row}, gapA, gapB}] — gapA/gapB: how far the curve stops short of the border
 *   at each end, for an arrowhead drawn from there (0 for none).
 * nodes: Map box id -> {x, y, w, h, oy, kind, box}
 * opts: {rowY(row) -> y offset of a row's center from n.y, headH, obstacles: [{x0, y0, x1, y1}]}
 * Returns Map key -> {p0, c1, c2, p3, d}.
 */
export function routeEdges(specs, nodes, { rowY, headH = 30, obstacles = [] } = {}) {
  const rects = new Map();
  const rect = (id) => {
    let r = rects.get(id);
    if (!r) { const n = nodes.get(id); if (!n) return null; r = rectOf(n); rects.set(id, r); }
    return r;
  };
  // 1. each end's side, and the point its port would ideally sit at
  const ends = [];            // {spec, which, box, row, side, group, lo, hi, ideal, tie}
  const live = [];
  for (const s of specs) {
    const na = nodes.get(s.a.box);
    const nb = nodes.get(s.b.box);
    if (!na || !nb) continue;
    const ra = rect(s.a.box);
    const rb = rect(s.b.box);
    const rowPt = (n, row) => ({ x: n.x, y: n.y + rowY(row) });
    // a value's row is a port in itself: it leaves through the side facing the other end
    const pa = s.a.row >= 0 ? rowPt(na, s.a.row) : null;
    const pb = s.b.row >= 0 ? rowPt(nb, s.b.row) : null;
    const ca = pa ?? { x: (ra.x0 + ra.x1) / 2, y: (ra.y0 + ra.y1) / 2 };
    const cb = pb ?? { x: (rb.x0 + rb.x1) / 2, y: (rb.y0 + rb.y1) / 2 };
    const ptRect = (p) => ({ x0: p.x, x1: p.x, y0: p.y, y1: p.y });
    const rowSide = (n, r, other) => (other.x < (r.x0 + r.x1) / 2 ? "L" : "R");
    let sa; let sb;
    if (pa && pb) {
      // two values in boxes side by side face each other; in boxes one above the other, they loop out of the same
      // side (the one where the boxes' ends line up best), never out of one side and back into the far side
      if (ra.x1 < rb.x0) { sa = "R"; sb = "L"; } else if (rb.x1 < ra.x0) { sa = "L"; sb = "R"; } else {
        sa = sb = Math.abs(ra.x1 - rb.x1) < Math.abs(ra.x0 - rb.x0) ? "R" : "L";
      }
    } else if (pa) {
      sa = rowSide(na, ra, cb);
      sb = sidesFor(ptRect({ x: sa === "R" ? ra.x1 : ra.x0, y: pa.y }), rb)[1];
    } else if (pb) {
      sb = rowSide(nb, rb, ca);
      sa = sidesFor(ra, ptRect({ x: sb === "R" ? rb.x1 : rb.x0, y: pb.y }))[0];
    } else {
      [sa, sb] = sidesFor(ra, rb);
    }
    const rec = { s, sa, sb, ra, rb, ca, cb, pa, pb, na, nb };
    live.push(rec);
    ends.push(endOf(rec, "a"), endOf(rec, "b"));
  }

  function endOf(rec, which) {
    const n = which === "a" ? rec.na : rec.nb;
    const r = which === "a" ? rec.ra : rec.rb;
    const side = which === "a" ? rec.sa : rec.sb;
    const row = which === "a" ? rec.s.a.row : rec.s.b.row;
    const other = which === "a" ? rec.cb : rec.ca;
    const horizSide = side === "L" || side === "R";
    const open = n.kind === "entity" && n.h > headH + 4;
    let lo; let hi; let fixed = null; let hole = null;
    if (row >= 0) {
      // a row's port: within its own height
      const y = which === "a" ? rec.pa.y : rec.pb.y;
      lo = y - 9; hi = y + 9; fixed = y;
      // a value's open node sits on the middle of its right end: ports go above and below it
      if (side === "R") hole = y;
    } else if (horizSide) {
      // an open entity's own interactions meet its header, not its values
      const y0 = r.y0; const y1 = open ? r.y0 + headH : r.y1;
      const inset = Math.min(8, (y1 - y0) * 0.22);
      lo = y0 + inset; hi = y1 - inset;
      // a closed entity's open node sits on the middle of its right end
      if (side === "R" && n.kind === "entity" && !open) hole = (y0 + y1) / 2;
    } else {
      const inset = Math.min(16, (r.x1 - r.x0) * 0.15);
      lo = r.x0 + inset; hi = r.x1 - inset;
    }
    const mid = fixed ?? (lo + hi) / 2;
    const want = horizSide ? other.y : other.x;
    // left and right ports stay near the middle of the side; top and bottom ones lean toward the other end
    const lean = horizSide ? 0.25 : 0.55;
    const ideal = mid + Math.max(lo - mid, Math.min(hi - mid, (want - mid) * lean));
    return { rec, which, side, lo, hi, ideal, want, hole,
             group: `${which === "a" ? rec.s.a.box : rec.s.b.box}|${side}|${row >= 0 ? row : ""}` };
  }

  // 2. spread the ports that share a side: in order of where their other ends are, at least `sp` apart
  const groups = new Map();
  for (const e of ends) { if (!groups.has(e.group)) groups.set(e.group, []); groups.get(e.group).push(e); }
  // edges between the same pair of boxes, in one fixed order (so both of their ends list them the same way)
  const pairs = new Map();
  for (const rec of live) {
    const k = rec.s.a.box < rec.s.b.box ? `${rec.s.a.box}|${rec.s.b.box}` : `${rec.s.b.box}|${rec.s.a.box}`;
    if (!pairs.has(k)) pairs.set(k, []);
    pairs.get(k).push(rec);
  }
  for (const list of pairs.values()) {
    list.sort((x, y) => (x.s.key < y.s.key ? -1 : 1));
    list.forEach((rec, i) => { rec.tie = i; rec.pairN = list.length; });
  }
  const spread = (list, lo, hi, maxSp) => {
    if (!list.length) return;
    if (list.length === 1) { list[0].pos = Math.max(lo, Math.min(hi, list[0].ideal)); return; }
    const room = hi - lo;
    const sp = Math.min(maxSp, room / (list.length - 1));
    // centered on the ideals' mean, inside [lo, hi]
    const mean = list.reduce((t, e) => t + e.ideal, 0) / list.length;
    const span = sp * (list.length - 1);
    const start = span >= room ? lo : Math.max(lo, Math.min(hi - span, mean - span / 2));
    list.forEach((e, i) => { e.pos = start + i * sp; });
  };
  const HOLE = 7.5;          // half the band an open node takes on a right side
  for (const list of groups.values()) {
    list.sort((x, y) => x.want - y.want || x.rec.tie - y.rec.tie);
    const { lo, hi, hole, side } = list[0];
    const maxSp = side === "L" || side === "R" ? 9 : 14;
    if (hole == null) { spread(list, lo, hi, maxSp); continue; }
    // the ports keep clear of the open node: those whose other end is higher go above it, the rest below
    const up = list.filter((e) => e.want < hole || (e.want === hole && e.rec.tie === 0));
    const down = list.filter((e) => !up.includes(e));
    for (const e of up) e.ideal = Math.min(e.ideal, hole - HOLE);
    for (const e of down) e.ideal = Math.max(e.ideal, hole + HOLE);
    spread(up, lo, hole - HOLE, maxSp);
    spread(down, hole + HOLE, hi, maxSp);
  }

  // 3. the curves
  const grid = new Map();
  const put = (r, ref) => {
    for (let gx = Math.floor(r.x0 / CELL); gx <= Math.floor(r.x1 / CELL); gx++) {
      for (let gy = Math.floor(r.y0 / CELL); gy <= Math.floor(r.y1 / CELL); gy++) {
        const k = gx * 100003 + gy;
        let c = grid.get(k);
        if (!c) { c = []; grid.set(k, c); }
        c.push(ref);
      }
    }
  };
  for (const [id, n] of nodes) put(rect(id) ?? rectOf(n), { id, r: rect(id) });
  for (const o of obstacles) put(o, { id: null, r: o });
  const near = (x, y) => grid.get(Math.floor(x / CELL) * 100003 + Math.floor(y / CELL)) ?? [];

  const out = new Map();
  const byKey = new Map();
  for (const e of ends) { if (!byKey.has(e.rec.s.key)) byKey.set(e.rec.s.key, {}); byKey.get(e.rec.s.key)[e.which] = e; }
  for (const rec of live) {
    const { a: ea, b: eb } = byKey.get(rec.s.key);
    const port = (e, r, gap) => {
      const nrm = NORMAL[e.side];
      const x = e.side === "L" ? r.x0 : e.side === "R" ? r.x1 : e.pos;
      const y = e.side === "T" ? r.y0 : e.side === "B" ? r.y1 : e.pos;
      return { pt: [x + nrm[0] * gap, y + nrm[1] * gap], nrm };
    };
    const A = port(ea, rec.ra, rec.s.gapA ?? 1);
    const B = port(eb, rec.rb, rec.s.gapB ?? 1);
    const p0 = A.pt; const p3 = B.pt;
    const dx = p3[0] - p0[0]; const dy = p3[1] - p0[1];
    const dist = Math.hypot(dx, dy) || 1;
    const same = A.nrm[0] * B.nrm[0] + A.nrm[1] * B.nrm[1] > 0.5;
    let kA; let kB;
    if (same) {
      // a loop out and back (two values on one side): each end reaches past the other's, so the loop clears both boxes
      const out = dx * A.nrm[0] + dy * A.nrm[1];        // how much further out the far end sits
      const base = Math.min(90, 22 + 0.15 * dist);
      kA = base + Math.max(0, out); kB = base + Math.max(0, -out);
    } else {
      const along = Math.abs(dx * A.nrm[0] + dy * A.nrm[1]);
      kA = kB = Math.max(6, Math.min(220, 0.5 * along + 0.12 * dist));
    }
    const c1 = [p0[0] + A.nrm[0] * kA, p0[1] + A.nrm[1] * kA];
    const c2 = [p3[0] + B.nrm[0] * kB, p3[1] + B.nrm[1] * kB];
    // parallel edges between one pair bow apart (their ports are already apart)
    const ux = -dy / dist; const uy = dx / dist;
    if (rec.pairN > 1) {
      // along the ports' own axis, in the order the ports were spread, so the bows never cross the ports
      const ax = ea.side === "L" || ea.side === "R" ? [0, 1] : [1, 0];
      const o = (rec.tie - (rec.pairN - 1) / 2) * 12;
      c1[0] += ax[0] * o; c1[1] += ax[1] * o; c2[0] += ax[0] * o; c2[1] += ax[1] * o;
    }
    const r = { p0, c1, c2, p3 };
    // detours: push the control points away from any other box a sample falls in
    const skip = new Set([rec.s.a.box, rec.s.b.box]);
    // samples about every 22 units along the curve (its control polygon bounds its length), so no box slips between two
    const poly = Math.hypot(c1[0] - p0[0], c1[1] - p0[1]) + Math.hypot(c2[0] - c1[0], c2[1] - c1[1]) + Math.hypot(p3[0] - c2[0], p3[1] - c2[1]);
    const ns = Math.max(6, Math.min(48, Math.ceil(poly / 22)));
    const ts = [];
    for (let i = 1; i < ns; i++) { const t = i / ns; if (t >= 0.06 && t <= 0.94) ts.push(t); }
    let bent = 0;
    for (let pass = 0; pass < PASSES; pass++) {
      let worst = null;
      for (const t of ts) {
        const P = cubicAt(r, t);
        for (const ob of near(P[0], P[1])) {
          if (ob.id && skip.has(ob.id)) continue;
          const o = ob.r;
          if (P[0] < o.x0 - CLEAR || P[0] > o.x1 + CLEAR || P[1] < o.y0 - CLEAR || P[1] > o.y1 + CLEAR) continue;
          const cx = (o.x0 + o.x1) / 2; const cy = (o.y0 + o.y1) / 2;
          // push across the chord, away from the box's center
          const side = (P[0] - cx) * ux + (P[1] - cy) * uy;
          const s = side >= 0 ? 1 : -1;
          const ex = Math.abs(ux) * ((o.x1 - o.x0) / 2) + Math.abs(uy) * ((o.y1 - o.y0) / 2) + CLEAR + 2;
          const need = ex - Math.abs(side);
          if (need > 0 && (!worst || need > worst.need)) worst = { need, s, t };
        }
      }
      if (!worst) break;
      const { t } = worst;
      const w1 = 1 - t; const w2 = t;
      const gain = 3 * t * (1 - t) * (w1 * w1 + w2 * w2);
      // a detour bends the curve, never flings it: each push and the sum of them are capped
      const amt = Math.min(160, worst.need / gain, MAX_BEND - bent) * worst.s;
      if (Math.abs(amt) < 0.5) break;
      bent += Math.abs(amt);
      r.c1[0] += ux * amt * w1; r.c1[1] += uy * amt * w1;
      r.c2[0] += ux * amt * w2; r.c2[1] += uy * amt * w2;
    }
    const f = (v) => Math.round(v * 10) / 10;
    r.d = `M${f(p0[0])} ${f(p0[1])}C${f(r.c1[0])} ${f(r.c1[1])} ${f(r.c2[0])} ${f(r.c2[1])} ${f(p3[0])} ${f(p3[1])}`;
    out.set(rec.s.key, r);
  }
  return out;
}
