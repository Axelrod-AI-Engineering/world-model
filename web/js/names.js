// Names for ids. The server and the trace refer to values, links, and superentities by id
// ("change resources_energy.oil_price +35%", "note on e08"); the screen uses their names, so every panel reads
// the same way. Unknown words are left alone, so prose that happens to look like an id is not mangled.
import { prettyNode } from "./graph/fuzzy.js";
import { CATEGORY_NAMES } from "./graph/layouts.js";
import { store } from "./store.js";

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
// "cross_border_trade.chip_exports" → "Chip exports"
const ownName = (ref) => {
  const w = String(ref).split(".").pop().replace(/_/g, " ");
  return w.charAt(0).toUpperCase() + w.slice(1);
};

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
  const known = (m) => {
    const ref = m.replace(/^new:/, "");
    return /^(?:new|gen):/.test(m) || subs.has(ref) || ents.has(ref) || pats.has(ref) || hulls.has(ref);
  };
  // an interaction named on its own reads "source → target"
  const link = (id) => {
    const l = links.get(id);
    return l ? `${node(l.source)} → ${node(l.target)}` : null;
  };
  const text = (s) => String(s ?? "").replace(LINK_ID, (m) => link(m) ?? m).replace(NODE_ID, (m) => (known(m) ? node(m) : m));
  const entityOf = (id) => subs.get(id)?.entity_id ?? (ents.has(id) ? id : String(id).split(".")[0]);
  return { node, text, link, subs, ents, links, entityOf };
}
