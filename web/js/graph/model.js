// What the canvas shows (§13.3), as a pure function of the GraphView and the user's choices.
// DECISION: detail is chosen per node, not by zoom (the user asked for zoom to be only zoom). An entity
// is a pill until it is opened into its subentities; a superentity is an outline around its members
// until it is closed into one card. Edges attach to the most specific thing on screen: a subentity row,
// else its entity's pill, else the card that holds it, and edges that land on the same pair of boxes
// are drawn once.
import { ancestors } from "./hulls.js";

const ROW_H = 24;
const HEAD_H = 30;

let measureCtx = null;
export function textWidth(text, font = "600 13px Instrument Sans") {
  if (!measureCtx) measureCtx = document.createElement("canvas").getContext("2d");
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

export function truncate(text, maxW, font) {
  if (textWidth(text, font) <= maxW) return text;
  let s = text;
  while (s.length > 3 && textWidth(`${s}…`, font) > maxW) s = s.slice(0, -1);
  return `${s.trimEnd()}…`;
}

export const GEOM = { ROW_H, HEAD_H, PILL_MIN_W: 176, PILL_MAX_W: 248, OPEN_MIN_W: 268, CARD_H: 54 };

// A closed card lists its members as chips that wrap: the members it holds (solid) and the members it
// shares with an outline or card drawn elsewhere (dashed, with a tether to where they are drawn).
export const CHIP = { H: 19, GAP: 4, PADX: 7, FONT: "600 11px Instrument Sans", MAX_W: 132, TOP: 44, MAX: 8 };

function layoutChips(items, width) {
  const chips = [];
  let x = 0;
  let row = 0;
  const shown = items.length > CHIP.MAX ? items.slice(0, CHIP.MAX - 1) : items;
  const rest = items.length - shown.length;
  const all = rest > 0 ? [...shown, { more: rest }] : shown;
  for (const it of all) {
    const label = it.more ? `+${it.more} more` : truncate(it.name, CHIP.MAX_W - 2 * CHIP.PADX, CHIP.FONT);
    const w = Math.min(CHIP.MAX_W, textWidth(label, CHIP.FONT) + 2 * CHIP.PADX + (it.hosted === false ? 10 : 0));
    if (x > 0 && x + w > width) { x = 0; row += 1; }
    chips.push({ ...it, label, x, y: row * (CHIP.H + CHIP.GAP), w });
    x += w + CHIP.GAP;
  }
  return { chips, rows: chips.length ? row + 1 : 0 };
}

export function pillWidth(name) {
  return Math.max(GEOM.PILL_MIN_W, Math.min(GEOM.PILL_MAX_W, textWidth(name) + 64));
}

// Group states: "open" (an outline), "card" (closed into one card), or "hidden" (inside a closed parent).
export function groupStates(groupsInfo, collapsed) {
  const { groups, byKey } = groupsInfo;
  const state = new Map();
  for (const g of groups) {
    if (g.transient) { state.set(g.key, "open"); continue; }
    const anc = ancestors(byKey, g.key);
    if (anc.some((k) => collapsed.has(k))) state.set(g.key, "hidden");
    else state.set(g.key, collapsed.has(g.key) ? "card" : "open");
  }
  return state;
}

// The card a closed group shows inside: itself, or its outermost closed ancestor.
function cardOf(byKey, state, key) {
  if (state.get(key) === "card") return key;
  for (const a of ancestors(byKey, key)) if (state.get(a) === "card") return a;
  return null;
}

export function computeModel(view, groupsInfo, ui) {
  const { groups, byKey, ofEntity } = groupsInfo;
  const state = groupStates(groupsInfo, ui.collapsed);
  const subsById = new Map((view?.subentities ?? []).map((s) => [s.id, s]));
  const entities = view?.entities ?? [];

  // which entities are visible, and which card holds each hidden one
  const visible = new Set();
  const host = new Map();
  for (const e of entities) {
    const gs = (ofEntity.get(e.id) ?? []).filter((k) => !byKey.get(k).transient);
    if (!gs.length || gs.some((k) => state.get(k) === "open")) { visible.add(e.id); continue; }
    const cards = [...new Set(gs.map((k) => cardOf(byKey, state, k)).filter(Boolean))]
      .sort((a, b) => (byKey.get(b).level - byKey.get(a).level) || (byKey.get(b).members.size - byKey.get(a).members.size)
        || a.localeCompare(b));
    if (cards.length) host.set(e.id, cards[0]);
    else visible.add(e.id);
  }

  const boxOfEntity = (eid) => (visible.has(eid) ? eid : host.has(eid) ? `card:${host.get(eid)}` : null);
  const nameOf = new Map(entities.map((e) => [e.id, e.name]));
  // each closed card's members: those it holds first, then those drawn elsewhere
  const cardMembers = new Map();
  for (const g of groups) {
    if (state.get(g.key) !== "card") continue;
    const list = [];
    for (const m of g.members) {
      const where = boxOfEntity(m);
      if (!where) continue;
      list.push({ eid: m, name: nameOf.get(m) ?? m, hosted: where === `card:${g.key}`, where });
    }
    list.sort((a, b) => (Number(b.hosted) - Number(a.hosted)) || a.name.localeCompare(b.name));
    cardMembers.set(g.key, list);
  }

  // boxes
  const boxes = [];
  const boxById = new Map();
  for (const e of entities) {
    if (!visible.has(e.id)) continue;
    const open = ui.expanded.has(e.id);
    const rows = open ? e.subentity_ids.filter((s) => subsById.has(s)) : [];
    const w = open ? Math.max(pillWidth(e.name), GEOM.OPEN_MIN_W) : pillWidth(e.name);
    const h = open ? HEAD_H + 6 + rows.length * ROW_H + 4 : HEAD_H;
    const b = { id: e.id, kind: "entity", ref: e.id, entity: e, open, rows, w, h, oy: -HEAD_H / 2 };
    boxes.push(b);
    boxById.set(b.id, b);
  }
  for (const g of groups) {
    if (state.get(g.key) !== "card") continue;
    const title = g.label;
    const w = Math.max(228, Math.min(340, textWidth(title, "700 13px Instrument Sans") + 34));
    const { chips, rows } = layoutChips(cardMembers.get(g.key) ?? [], w - 24);
    const h = rows ? CHIP.TOP + rows * (CHIP.H + CHIP.GAP) + 6 : GEOM.CARD_H;
    const b = { id: `card:${g.key}`, kind: "card", ref: g.key, group: g, w, h, oy: -h / 2, chips };
    boxes.push(b);
    boxById.set(b.id, b);
  }
  const anchorOf = (sid) => {
    const s = subsById.get(sid);
    const eid = s?.entity_id ?? String(sid).split(".")[0];
    const bid = boxOfEntity(eid);
    if (!bid) return null;
    const b = boxById.get(bid);
    if (b?.kind === "entity" && b.open) {
      const row = b.rows.indexOf(sid);
      return { box: bid, row };
    }
    return { box: bid, row: -1 };
  };

  // edges, aggregated per pair of anchors
  const entityLinkLabel = new Map((view?.entity_links ?? []).map((l) => [`${l.source}>${l.target}`, l]));
  const superByPair = new Map();
  for (const s of view?.super_links ?? []) {
    if (s.kind !== "causal") continue;
    const a = groupsInfo.ofInstance.get(s.source);
    const b = groupsInfo.ofInstance.get(s.target);
    if (a && b && a !== b) {
      const k = `card:${a}>card:${b}`;
      const cur = superByPair.get(k);
      if (!cur || s.significance > cur.significance) superByPair.set(k, s);
    }
  }
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
      e = { key, a, b, ids: [], label: "", sig: -1, learned: true, demo: true, bidir: false, effect: 0 };
      agg.set(key, e);
    }
    e.ids.push(l.id);
    if (l.significance > e.sig) { e.sig = l.significance; e.label = l.label; e.effect = l.effect; }
    e.learned = e.learned && l.edge_type === "learned_causal";
    e.demo = e.demo && (l.tags ?? []).includes("demo_addition");
    e.bidir = e.bidir || l.direction === "bidirectional";
  }
  const edges = [...agg.values()];
  for (const e of edges) {
    const ba = boxById.get(e.a.box);
    const bb = boxById.get(e.b.box);
    if (ba?.kind === "entity" && bb?.kind === "entity" && e.a.row < 0 && e.b.row < 0) {
      const el = entityLinkLabel.get(`${ba.ref}>${bb.ref}`);
      if (el) { e.label = el.label; e.sig = Math.max(e.sig, el.significance); }
    }
    if (ba?.kind === "card" && bb?.kind === "card") {
      const s = superByPair.get(`${ba.id}>${bb.id}`);
      if (s) { e.super = true; e.label = s.label; }
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

  // membership dots: closed groups that also hold a visible entity
  const dots = new Map();
  for (const eid of visible) {
    const ks = new Set();
    for (const k of ofEntity.get(eid) ?? []) {
      if (byKey.get(k).transient || state.get(k) === "open") continue;
      const c = cardOf(byKey, state, k);
      if (c) ks.add(c);
    }
    if (ks.size) dots.set(eid, [...ks]);
  }

  // Shared ownership (addition: the user asked for overlaps between superentities to be tangible).
  // An entity's direct owners are the most specific groups that hold it (a composite that holds it only
  // through a part is left out: nesting already shows that). Each owner is drawn as an outline ("open")
  // or inside a card; an entity with two owners, or with an owner closed into a card, wears a stripe per
  // owner, and a closed card lists its members as chips, tethered to wherever a shared one is drawn.
  const directOwners = (eid) => {
    const ks = (ofEntity.get(eid) ?? []).filter((k) => !byKey.get(k).transient);
    return ks.filter((k) => !ks.some((o) => o !== k && ancestors(byKey, o).includes(k)));
  };
  const owners = new Map();
  for (const e of entities) {
    const list = directOwners(e.id).map((k) => {
      const card = state.get(k) === "open" ? null : cardOf(byKey, state, k);
      return { key: k, drawn: card ? "card" : "open", card };
    });
    if (list.length) owners.set(e.id, list);
  }
  // open outlines that share entities overlap: the shared part is drawn as a lens with both colors
  const lenses = [];
  const openKeys = groups.filter((g) => !g.transient && state.get(g.key) === "open").map((g) => g.key);
  for (let i = 0; i < openKeys.length; i++) {
    for (let j = i + 1; j < openKeys.length; j++) {
      const a = byKey.get(openKeys[i]);
      const b = byKey.get(openKeys[j]);
      if (ancestors(byKey, a.key).includes(b.key) || ancestors(byKey, b.key).includes(a.key)) continue;
      const shared = [...a.members].filter((m) => b.members.has(m) && visible.has(m));
      if (shared.length) lenses.push({ key: `${a.key}&${b.key}`, a: a.key, b: b.key, shared });
    }
  }

  // superentities of subentities: which drawn groups' relations run through each subentity
  // (a composite marks only the edges it adds, its boundary edges)
  const linkById = new Map((view?.links ?? []).map((l) => [l.id, l]));
  const marks = new Map();
  for (const g of groups) {
    if (g.transient || state.get(g.key) === "hidden") continue;
    let ids = new Set(g.hulls.flatMap((h) => h.interaction_ids ?? []));
    if (g.composite) {
      const own = new Set(g.children.flatMap((k) => byKey.get(k).hulls.flatMap((h) => h.interaction_ids ?? [])));
      ids = new Set([...ids].filter((i) => !own.has(i)));
    }
    for (const iid of ids) {
      const l = linkById.get(iid);
      if (!l) continue;
      for (const sid of [l.source, l.target]) {
        if (!marks.has(sid)) marks.set(sid, []);
        const arr = marks.get(sid);
        if (!arr.includes(g.key)) arr.push(g.key);
      }
    }
  }

  return { state, visible, host, boxes, boxById, boxOfEntity, anchorOf, edges, internal, frontier, dots, marks,
           owners, cardMembers, lenses };
}

// Where a row sits inside an open entity, relative to the box anchor (the header's center).
export function rowCenterY(i) {
  return HEAD_H / 2 + 6 + i * ROW_H + ROW_H / 2;
}
