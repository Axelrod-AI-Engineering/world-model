// What the canvas shows (§13.3), as a pure function of the GraphView and the user's choices.
// DECISION: detail is chosen per node, not by zoom (the user asked for zoom to be only zoom). An entity
// is a pill until it is opened into its subentities. Edges attach to the most specific thing on screen: a
// subentity row, else its entity's pill, and edges that land on the same pair of boxes are drawn once.
// DECISION (Oct 17): superentities are not drawn on the canvas (a meeting decision: "delete superentity artifacts
// from the world model diagram"); they stay in the model, in memory, in forecasts and in the panels. The canvas
// shows entities and their values, arranged by the static taxonomy's concepts (graph/concepts.js).

const ROW_H = 24;
const HEAD_H = 30;

let measureCtx = null;
export function textWidth(text, font = "600 13px Instrument Sans") {
  if (!measureCtx) measureCtx = document.createElement("canvas").getContext("2d");
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

// An open entity's rows read without the words they all start with ("Delta jet fuel cost" reads "Jet fuel
// cost"), so similar entities' rows line up word for word. Every row keeps at least one word.
export function rowLabels(subs) {
  const words = subs.map((s) => (s?.name ?? s?.id ?? "").split(" "));
  let n = 0;
  if (words.length > 1) {
    while (words.every((w) => w.length > n + 1 && w[n] === words[0][n])) n += 1;
  }
  return new Map(subs.map((s, i) => {
    const rest = words[i].slice(n).join(" ");
    return [s?.id, n ? rest.charAt(0).toUpperCase() + rest.slice(1) : words[i].join(" ")];
  }));
}

// Kin (addition): the same value in similar entities. Two subentities are kin when their kind gives both the
// same slot ("every airline has a jet fuel cost"), or when their ids end alike inside entities of the same kind
// (NVIDIA's and AMD's data-center revenue).
export function kinKey(s, entById) {
  if (!s) return null;
  if (s.slot) return `slot:${s.slot}`;
  const gen = entById.get(s.entity_id)?.generalization_id;
  const tail = String(s.id).split(".").slice(1).join(".");
  return gen && tail ? `${gen}:${tail}` : null;
}

export function truncate(text, maxW, font) {
  if (textWidth(text, font) <= maxW) return text;
  let s = text;
  while (s.length > 3 && textWidth(`${s}…`, font) > maxW) s = s.slice(0, -1);
  return `${s.trimEnd()}…`;
}

export const GEOM = { ROW_H, HEAD_H, PILL_MIN_W: 176, PILL_MAX_W: 248, OPEN_MIN_W: 268, CARD_H: 54 };

// A value in its own unit (Oct 17: the user asked for subentities' means and units, not standardized moves). Three
// significant figures for small numbers, one decimal from 100, thousands separators from 1,000; a currency sign leads
// ("$109.7bn/yr", "¥156.0 per $"), "pct" reads "%", and any other unit follows the number ("105.2 index").
export function fmtNumber(x) {
  if (x == null || !Number.isFinite(x)) return "–";
  const a = Math.abs(x);
  if (a >= 1000) return x.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 100) return x.toFixed(1);
  if (a === 0) return "0";
  if (a < 0.001) return x.toExponential(1);
  return String(Number(x.toPrecision(3)));
}

export function fmtValue(x, unit = "") {
  const u = String(unit ?? "").trim();
  const n = fmtNumber(x);
  if (!u) return n;
  const pct = /^pct\b/.exec(u);
  if (pct) return `${n}%${u.slice(3)}`;
  const cur = /^([$€¥£])\s*(.*)$/.exec(u);
  if (cur) {
    const rest = cur[2];
    const neg = n.startsWith("-") ? "-" : "";
    const body = neg ? n.slice(1) : n;
    return `${neg}${cur[1]}${body}${!rest ? "" : /^[a-z/]/i.test(rest) && !/^per\b/.test(rest) ? rest : ` ${rest}`}`;
  }
  return `${n} ${u}`;
}

// A forecast's move (in sd of the value's scale) in the value's own unit: a percent change for a value that moves in
// logs (lognormal), a change in its unit for one that moves in levels (gaussian; "pp" for a value already in percent).
// Values of other families, or without a scale, keep the move in sd.
export function fmtMove(z, s) {
  const arrow = z > 0.005 ? "▲" : z < -0.005 ? "▼" : "";
  const scale = s?.scale ?? 0;
  if (!(scale > 0) || !s) return `${arrow}${Math.abs(z).toFixed(1)} sd`;
  if (s.family === "lognormal") {
    const pct = 100 * (Math.exp(Math.abs(z) * scale) - 1);
    return `${arrow}${fmtNumber(pct)}%`;
  }
  if (s.family === "gaussian") {
    const d = Math.abs(z) * scale;
    if (/^pct\b/.test(s.unit ?? "")) return `${arrow}${fmtNumber(d)}pp`;
    return `${arrow}${fmtValue(d, s.unit)}`;
  }
  return `${arrow}${Math.abs(z).toFixed(1)} sd`;
}

// an open entity's width: its name, or its rows (name, distribution, value), whichever is wider
const ROW_FONT = "500 11.5px Instrument Sans";
const VAL_FONT = "500 10.5px IBM Plex Mono";
export const ROW_GEOM = { GLYPH_W: 32, LEFT: 21, GAP: 10, RIGHT: 9, NAME_MIN: 96, MAX_W: 380, ROW_FONT, VAL_FONT };
export function valueWidth(subs) {
  return Math.max(0, ...subs.map((s) => textWidth(fmtValue(s?.summary?.mean, s?.unit), VAL_FONT)));
}
function openWidth(e, subs) {
  const labels = rowLabels(subs);
  const nameW = Math.max(ROW_GEOM.NAME_MIN, ...subs.map((s) => textWidth(labels.get(s.id) ?? s.id, ROW_FONT)));
  const need = ROW_GEOM.LEFT + nameW + ROW_GEOM.GAP + ROW_GEOM.GLYPH_W + ROW_GEOM.GAP + valueWidth(subs) + ROW_GEOM.RIGHT + 8;
  return Math.max(pillWidth(e.name), GEOM.OPEN_MIN_W, Math.min(ROW_GEOM.MAX_W, Math.ceil(need)));
}

export function pillWidth(name) {
  return Math.max(GEOM.PILL_MIN_W, Math.min(GEOM.PILL_MAX_W, textWidth(name) + 64));
}

export function computeModel(view, ui) {
  const subsById = new Map((view?.subentities ?? []).map((s) => [s.id, s]));
  const entities = view?.entities ?? [];
  const visible = new Set(entities.map((e) => e.id));
  const boxOfEntity = (eid) => (visible.has(eid) ? eid : null);

  // boxes
  const boxes = [];
  const boxById = new Map();
  for (const e of entities) {
    const open = ui.expanded.has(e.id);
    const rows = open ? e.subentity_ids.filter((s) => subsById.has(s)) : [];
    const w = open ? openWidth(e, rows.map((sid) => subsById.get(sid))) : pillWidth(e.name);
    const h = open ? HEAD_H + 6 + rows.length * ROW_H + 4 : HEAD_H;
    const b = { id: e.id, kind: "entity", ref: e.id, entity: e, open, rows, w, h, oy: -HEAD_H / 2 };
    boxes.push(b);
    boxById.set(b.id, b);
  }
  const anchorOf = (sid) => {
    const s = subsById.get(sid);
    const eid = s?.entity_id ?? String(sid).split(".")[0];
    const bid = boxOfEntity(eid);
    if (!bid) return null;
    const b = boxById.get(bid);
    if (b?.open) return { box: bid, row: b.rows.indexOf(sid) };
    return { box: bid, row: -1 };
  };

  // edges, aggregated per pair of anchors
  const entityLinkLabel = new Map((view?.entity_links ?? []).map((l) => [`${l.source}>${l.target}`, l]));
  const agg = new Map();
  const internal = [];
  for (const l of view?.links ?? []) {
    const a = anchorOf(l.source);
    const b = anchorOf(l.target);
    if (!a || !b) continue;
    if (a.box === b.box) {
      if (a.row >= 0 && b.row >= 0 && a.row !== b.row) {
        internal.push({ id: l.id, box: a.box, ra: a.row, rb: b.row, label: l.label, ids: [l.id],
                        sig: l.significance, learned: l.edge_type === "learned_causal" });
      }
      continue;
    }
    const key = `${a.box}#${a.row}>${b.box}#${b.row}`;
    let e = agg.get(key);
    if (!e) {
      e = { key, a, b, ids: [], label: "", sig: -1, learned: true, demo: true, bidir: false, effect: 0, hedge: true, hedgeP: 0 };
      agg.set(key, e);
    }
    e.ids.push(l.id);
    if (l.significance > e.sig) { e.sig = l.significance; e.label = l.label; e.effect = l.effect; }
    e.learned = e.learned && l.edge_type === "learned_causal";
    e.demo = e.demo && (l.tags ?? []).includes("demo_addition");
    e.bidir = e.bidir || l.direction === "bidirectional";
    // a fuzzy end's soft interaction (Oct 8): the edge is hedged while every interaction in it is one
    e.hedge = e.hedge && !!l.hedge;
    if (l.hedge) e.hedgeP = Math.max(e.hedgeP, l.hedge_p ?? 0);
  }
  const edges = [...agg.values()];
  for (const e of edges) {
    if (e.a.row < 0 && e.b.row < 0) {
      const el = entityLinkLabel.get(`${e.a.box}>${e.b.box}`);
      if (el) { e.label = el.label; e.sig = Math.max(e.sig, el.significance); }
    }
    e.sig = Math.max(0, e.sig);
  }
  const keys = new Set(edges.map((e) => `${e.a.box}>${e.b.box}`));
  for (const e of edges) e.curve = keys.has(`${e.b.box}>${e.a.box}`) ? 1 : 0;

  // co-movements on the frontier: the seeded, the proposed, and the best supported
  const frontier = (view?.frontier ?? [])
    .filter((f) => f.status !== "promoted" && (f.seeded || f.status === "promotion_proposed" || f.support >= 2.5))
    .sort((x, y) => y.support - x.support).slice(0, 4)
    .map((f) => ({ ...f, a: anchorOf(f.earlier), b: anchorOf(f.later) }))
    .filter((f) => f.a && f.b && f.a.box !== f.b.box);

  return { visible, boxes, boxById, boxOfEntity, anchorOf, edges, internal, frontier };
}

// Where a row sits inside an open entity, relative to the box anchor (the header's center).
export function rowCenterY(i) {
  return HEAD_H / 2 + 6 + i * ROW_H + ROW_H / 2;
}
