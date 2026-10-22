// Attention (Oct 11): what a person looks at, and at what zoom, learned as they use the canvas. The zoom slider reads
// it in three ways:
//   - detents: the zoom levels a person keeps settling at, as ticks on the slider that the thumb snaps to; each
//     remembers what was looked at there, so clicking it returns to that view;
//   - the focus: the slider and +/− zoom toward the attention-weighted middle of what is in view, not the bare center;
//   - when values open: opening an entity by hand while zoomed further out than the threshold lowers it; closing one
//     while zoomed in past it raises it.
// DECISION: dwell is counted only while the view is still (a person reading), decays with a half-life of a few minutes
// of use, and stays in this browser (localStorage). Nothing here reaches the server or the model.

export const K_MIN = 0.2;
export const K_MAX = 3.5;
const BINS = 40;
const DECAY = 0.9985;            // per observation (about every half second of stillness): half-life near 4 minutes
const NODE_CAP = 12;             // nodes remembered per zoom bin
const OPEN_DEFAULT = 0.95;       // values open at or above this scale until a person teaches otherwise (was 1.25: too far in)
const OPEN_RANGE = [0.7, 2.4];

const lk = (k) => Math.log(k);
export const toUnit = (k) => (lk(Math.max(K_MIN, Math.min(K_MAX, k))) - lk(K_MIN)) / (lk(K_MAX) - lk(K_MIN));
export const fromUnit = (u) => Math.exp(lk(K_MIN) + Math.max(0, Math.min(1, u)) * (lk(K_MAX) - lk(K_MIN)));
const binOf = (k) => Math.min(BINS - 1, Math.floor(toUnit(k) * BINS));

function blank() {
  return { v: 1, hist: new Array(BINS).fill(0), nodes: Array.from({ length: BINS }, () => ({})), kOpen: OPEN_DEFAULT };
}

export function createAttention(key = "default", storage = globalThis.localStorage) {
  const storeKey = `axelrod.attention.${key}`;
  let s = blank();
  try {
    const raw = storage?.getItem(storeKey);
    const got = raw ? JSON.parse(raw) : null;
    if (got?.v === 1 && got.hist?.length === BINS) {
      s = got;
      if (Math.abs(s.kOpen - 1.25) < 1e-9) s.kOpen = OPEN_DEFAULT;   // the old default, never taught: take the new one
    }
  } catch { /* private window or bad data: start fresh */ }
  let dirty = 0;
  const save = (force = false) => {
    dirty += 1;
    if (!force && dirty < 10) return;
    dirty = 0;
    try { storage?.setItem(storeKey, JSON.stringify(s)); } catch { /* full or blocked */ }
  };

  return {
    // `seen`: [{id, w}] for the nodes in the middle of the view, weighted by how central they are; `dt` in seconds
    observe(k, seen, dt = 0.5) {
      for (let i = 0; i < BINS; i++) s.hist[i] *= DECAY;
      const b = binOf(k);
      s.hist[b] += dt;
      const m = s.nodes[b];
      for (const id of Object.keys(m)) m[id] *= DECAY;
      for (const { id, w } of seen) m[id] = (m[id] ?? 0) + w * dt;
      const ids = Object.keys(m);
      if (ids.length > NODE_CAP) {
        ids.sort((a, c) => m[c] - m[a]);
        for (const id of ids.slice(NODE_CAP)) delete m[id];
      }
      save();
    },
    // a hover, click, or open counts as a moment of looking at one node
    touch(id, k, w = 1) {
      const m = s.nodes[binOf(k)];
      m[id] = (m[id] ?? 0) + w;
      save();
    },
    // the zoom levels a person keeps settling at: peaks of the smoothed dwell histogram, at most three
    detents() {
      const total = s.hist.reduce((a, v) => a + v, 0);
      if (total < 12) return [];
      const kern = [1, 2, 3, 2, 1];
      const sm = s.hist.map((_, i) => kern.reduce((a, w, j) => a + w * (s.hist[i + j - 2] ?? 0), 0) / 9);
      const peaks = [];
      for (let i = 0; i < BINS; i++) {
        if (sm[i] >= (sm[i - 1] ?? 0) && sm[i] > (sm[i + 1] ?? 0) && sm[i] * 9 / 3 >= 0.12 * total) peaks.push({ i, mass: sm[i] });
      }
      peaks.sort((a, c) => c.mass - a.mass);
      return peaks.slice(0, 3).map(({ i, mass }) => {
        // the nodes looked at near this zoom, strongest first
        const near = {};
        for (const j of [i - 1, i, i + 1]) for (const [id, w] of Object.entries(s.nodes[j] ?? {})) near[id] = (near[id] ?? 0) + w;
        const top = Object.entries(near).sort((a, c) => c[1] - a[1]).slice(0, 6).map(([id, w]) => ({ id, w }));
        return { k: fromUnit((i + 0.5) / BINS), share: mass * 3 / total, nodes: top };
      }).sort((a, c) => a.k - c.k);
    },
    // how much a node has been looked at, at any zoom near k
    weight(id, k) {
      const b = binOf(k);
      let w = 0;
      for (const j of [b - 2, b - 1, b, b + 1, b + 2]) w += s.nodes[j]?.[id] ?? 0;
      return w;
    },
    get kOpen() { return s.kOpen; },
    // a person opened (true) or closed (false) an entity's values by hand at scale k
    learnOpen(k, opened) {
      if (opened && k < s.kOpen) s.kOpen += 0.3 * (k - s.kOpen);
      else if (!opened && k >= s.kOpen) s.kOpen += 0.3 * (k * 1.15 - s.kOpen);
      else return;
      s.kOpen = Math.max(OPEN_RANGE[0], Math.min(OPEN_RANGE[1], s.kOpen));
      save(true);
    },
    reset() { s = blank(); save(true); },
    flush() { save(true); },
  };
}
