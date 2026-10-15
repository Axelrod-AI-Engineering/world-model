// Names for ids. The server and the trace refer to values, links, and superentities by id
// ("change resources_energy.oil_price +35%", "note on e08"); the screen uses their names, so every panel reads
// the same way. Unknown words are left alone, so prose that happens to look like an id is not mangled.
import { prettyNode } from "./graph/fuzzy.js";
import { CATEGORY_NAMES } from "./graph/layouts.js";
import { store } from "./store.js";
import { esc } from "./util.js";

// the graph update event's operations, by name
export const OP_WORDS = {
  add_entity: "add entity", add_subentity: "add subentity", observe_value: "observe value", change_value: "change value",
  add_interaction: "add interaction", reweight_interaction: "reweight interaction", annotate_interaction: "annotate interaction",
  propose_hypothesis: "propose hypothesis", propose_superentity: "propose superentity", dissolve_superentity: "dissolve superentity",
};

// how specific an operation's end is: a generalization (fuzzy), an entity, or a subentity (real)
export const LEVEL_PLAIN = { generalization: "generalization", entity: "entity", subentity: "subentity" };

const LINK_ID = /\b(?:e\d{2,3}|int-\d+|d-[a-z0-9_]+(?:-[a-z0-9_]+)+)\b/g;
const NODE_ID = /\b(?:gen:(?:obj|int):[\w.]+|new:[\w.]+|[a-z][\w]*\.[a-z][\w.]*|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b/g;
const ANY_ID = new RegExp(`${LINK_ID.source}|${NODE_ID.source}`, "g");
const reEsc = (s) => String(s).replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
// "cross_border_trade.chip_exports" → "Chip exports"
const ownName = (ref) => {
  const w = String(ref).split(".").pop().replace(/_/g, " ");
  return w.charAt(0).toUpperCase() + w.slice(1);
};

// A subentity named on its own reads with its entity, "Tokio Marine · share price", and its own name drops the words
// that only repeat the entity ("Tokio Marine share price"; "BoJ policy rate" in Bank of Japan; "Citi share price" in
// Citigroup). Inside its entity (its open rows, an inspector headed by it) the bare name reads better.
// An idea's values are often terms that start with its name ("Credit growth" in Credit availability, "Dollar index" in
// Dollar, FX rates), so for an idea only its whole name ("Oil price" in Oil), the place it is the economy of ("Japan
// core CPI" in Japan economy), or its initials ("JGB 10Y yield") are dropped.
const STOP = new Set(["of", "the", "and", "&"]);
const KEEP = /^(?:Fed funds|Labor force)\b/i;   // terms of art that only look like they repeat their entity
const ACTOR_KINDS = new Set(["company", "agency", "person"]);
const initials = (ws, skip) => ws.filter((w) => !skip || !STOP.has(w.toLowerCase())).map((w) => w[0]).join("").toLowerCase();
export function ownPart(subName, entName, kind = null) {
  const sw = String(subName ?? "").split(" ");
  const ew = String(entName ?? "").replace(/\s*\(.*?\)\s*/g, " ").replace(/,/g, "").trim().split(/\s+/);
  if (sw.length < 2 || !ew[0] || KEEP.test(subName)) return String(subName ?? "");
  const lo = (w) => w.toLowerCase().replace(/[’']s$/, "");
  const actor = kind == null || ACTOR_KINDS.has(kind);
  let k = 0;
  // the entity's leading words ("Tokio Marine share price", "Japan core CPI" in Japan economy)
  while (k < ew.length && k < sw.length - 1 && lo(sw[k]) === lo(ew[k])) k += 1;
  if (!actor && k && k < ew.length && !(k === ew.length - 1 && /^econom/i.test(ew[k]))) k = 0;
  if (!k && !actor) {
    const w = lo(sw[0]);
    if (w.length >= 2 && ew.length >= 2 && (w === initials(ew, false) || w === initials(ew, true))) k = 1;
  } else if (!k) {
    const w = lo(sw[0]);
    const ews = ew.map(lo);
    // a short form ("Citi", "Fed"), its initials ("BoJ", "ECB", "JGB"), or a later proper name in it ("Aramco revenue"
    // in Saudi Aramco; not "Trade volume" in Cross-border trade)
    if ((w.length >= 3 && ews[0].startsWith(w)) || (w.length >= 2 && ew.length >= 2 && (w === initials(ew, false) || w === initials(ew, true)))
      || (w.length >= 4 && ew.slice(1).some((x) => /^[A-Z]/.test(x) && lo(x) === w))) k = 1;
  }
  if (!k) return sw.join(" ");
  // the rest keeps its case: it was mid-name ("share price", "Japan P&C profit", "10Y yield")
  return sw.slice(k).join(" ");
}
// the same from a payload that carries both names, not ids: "Entity · subentity", and as HTML (the entity's kind,
// actor or idea, from the graph on screen when it has an entity of that name)
const kindNamed = (entName) => (store.graph ?? store.view)?.entities?.find((e) => e.name === entName)?.kind ?? null;
export const ownOf = (subName, entName) => ownPart(subName, entName, kindNamed(entName));
export const qualified = (subName, entName) => (entName ? `${entName} · ${ownOf(subName, entName)}` : String(subName ?? ""));
export const qualifiedHtml = (subName, entName) => (entName
  ? `<span class="qn-ent">${esc(entName)} ·</span> ${esc(ownOf(subName, entName))}` : esc(subName));

export function names(v = store.view ?? store.graph) {
  const subs = new Map((v?.subentities ?? []).map((s) => [s.id, s]));
  const ents = new Map((v?.entities ?? []).map((e) => [e.id, e]));
  const links = new Map((v?.links ?? []).map((l) => [l.id, l]));
  const hulls = new Map((v?.hulls ?? []).map((h) => [h.id, h]));
  const pats = new Map((v?.hulls ?? []).map((h) => [h.pattern_id, h]));
  const node = (id) => {
    const ref = String(id ?? "").replace(/^new:/, "");
    if (subs.has(ref)) return subs.get(ref).name;
    if (ents.has(ref)) return ents.get(ref).name;
    if (links.has(ref)) return links.get(ref).label;
    if (pats.has(ref)) return `${ref} · ${pats.get(ref).label.replace(/^S\d+\s*·\s*/, "")}`;
    if (hulls.has(ref)) return hulls.get(ref).label;
    if (CATEGORY_NAMES[ref]) return CATEGORY_NAMES[ref];
    if (/^gen:/.test(ref)) return prettyNode(ref);
    return ref.includes(".") ? ownName(ref) : prettyNode(ref);
  };
  // a subentity (or a value id whose entity is known) as its entity's name and its own part; anything else null
  const parts = (id) => {
    const ref = String(id ?? "").replace(/^new:/, "");
    const s = subs.get(ref);
    if (s) {
      const e = ents.get(s.entity_id);
      return e ? { ent: e.name, own: ownPart(s.name, e.name, e.kind ?? null) } : null;
    }
    const head = ref.split(".")[0];
    if (ref.includes(".") && !/^gen:/.test(ref) && ents.has(head)) return { ent: ents.get(head).name, own: ownName(ref).toLowerCase() };
    return null;
  };
  // "Entity · subentity"; anything that is not a subentity reads as `node`
  const value = (id) => {
    const p = parts(id);
    return p ? `${p.ent} · ${p.own}` : node(id);
  };
  // the same as escaped HTML, the entity's part muted
  const valueHtml = (id) => {
    const p = parts(id);
    return p ? `<span class="qn-ent">${esc(p.ent)} ·</span> ${esc(p.own)}` : esc(node(id));   // as qualifiedHtml
  };
  // a subentity's name where its entity is already shown: without the words that repeat the entity
  const short = (id) => parts(id)?.own ?? node(id);
  const known = (m) => {
    const ref = m.replace(/^new:/, "");
    return /^(?:new|gen):/.test(m) || subs.has(ref) || ents.has(ref) || pats.has(ref) || hulls.has(ref);
  };
  // an interaction named on its own reads "source → target", each end with its entity
  const link = (id) => {
    const l = links.get(id);
    return l ? `${value(l.source)} → ${value(l.target)}` : null;
  };
  const linkHtml = (id) => {
    const l = links.get(id);
    return l ? `${valueHtml(l.source)} → ${valueHtml(l.target)}` : null;
  };
  // one pass over prose: each match `re` finds is replaced by `rep(match)` (null leaves it), the rest by `plain`
  const scan = (s, re, rep, plain) => {
    const src = String(s ?? "");
    let out = "";
    let at = 0;
    for (const m of src.matchAll(re)) {
      const r = rep(m);
      if (r == null) continue;
      out += plain(src.slice(at, m.index)) + r;
      at = m.index + m[0].length;
    }
    return out + plain(src.slice(at));
  };
  const same = (x) => x;
  // prose with ids → prose with names, each subentity as "Entity · subentity" (bare names with `bare`)
  const text = (s, { bare = false } = {}) => scan(s, ANY_ID, ([w]) => {
    const l = links.get(w);
    if (l) return bare ? `${node(l.source)} → ${node(l.target)}` : link(w);
    return known(w) ? (bare ? node(w) : value(w)) : null;
  }, same);
  // the same prose as escaped HTML, with each entity's part muted
  const html = (s) => scan(s, ANY_ID, ([w]) => (links.has(w) ? linkHtml(w) : known(w) ? valueHtml(w) : null), esc);
  // Prose the server wrote with names, not ids ("Move Fed policy rate +0.25"): each subentity's name, alone or after
  // its entity's ("Oil · Oil price (Brent)"), reads "Entity · subentity". A name two values share, or one that is
  // also an entity's name, is left alone.
  let byName = null;
  let nameRe = null;
  const nameIndex = () => {
    if (byName) return;
    byName = new Map();
    const entNames = new Set([...ents.values()].map((e) => e.name));
    for (const s of subs.values()) {
      if (!s.name || entNames.has(s.name) || !ents.has(s.entity_id)) continue;
      byName.set(s.name, byName.has(s.name) ? null : s.id);
    }
    const alts = [...byName.entries()].filter(([, id]) => id).sort((a, b) => b[0].length - a[0].length)
      .map(([n, id]) => `(?:${reEsc(ents.get(subs.get(id).entity_id).name)} · )?${reEsc(n)}`);
    nameRe = alts.length ? new RegExp(`(?<![\\w·])(?:${alts.join("|")})(?![\\w])`, "g") : null;
  };
  const idOfNamed = (w) => {
    if (byName.has(w)) return byName.get(w);
    const i = w.indexOf(" · ");
    return i >= 0 ? byName.get(w.slice(i + 3)) ?? null : null;
  };
  const named = (s) => {
    nameIndex();
    return nameRe ? scan(s, nameRe, ([w]) => { const id = idOfNamed(w); return id ? value(id) : null; }, same) : String(s ?? "");
  };
  const namedHtml = (s) => {
    nameIndex();
    return nameRe ? scan(s, nameRe, ([w]) => { const id = idOfNamed(w); return id ? valueHtml(id) : null; }, esc) : esc(s);
  };
  // free prose that may hold ids or names (an agent's recommendation): both, as HTML
  const proseHtml = (s) => namedHtml(text(s));
  const entityOf = (id) => subs.get(id)?.entity_id ?? (ents.has(id) ? id : String(id).split(".")[0]);
  return { node, value, valueHtml, short, text, html, named, namedHtml, proseHtml, link, linkHtml, subs, ents, links, entityOf };
}
