// Isolate (Oct 11): show only what matters to one node, laid out on its own. A node's upstream is what drives it (the
// values whose interactions reach it, up to `hops` interactions back); its downstream is what it moves (as far
// forward). The canvas keeps only those entities, their interactions, and the superentities among them, and lays them
// out fresh, so the structure around one idea reads cleanly. Leaving restores the full graph where it was.

// entity-level directed adjacency from the view's interactions (both ends' entities)
function adjacency(view) {
  const ent = new Map((view?.subentities ?? []).map((s) => [s.id, s.entity_id]));
  const fwd = new Map();
  const back = new Map();
  const add = (m, a, b) => { if (!m.has(a)) m.set(a, new Set()); m.get(a).add(b); };
  for (const l of view?.links ?? []) {
    const a = ent.get(l.source) ?? l.source.split(".")[0];
    const b = ent.get(l.target) ?? l.target.split(".")[0];
    if (!a || !b || a === b) continue;
    add(fwd, a, b);
    add(back, b, a);
    if (l.direction === "bidirectional" || l.direction === "both") { add(fwd, b, a); add(back, a, b); }
  }
  return { fwd, back };
}

// the entities within `hops` interactions of `ids`, upstream ("up"), downstream ("down"), or both
export function isolationSet(view, ids, way = "both", hops = 3) {
  const { fwd, back } = adjacency(view);
  const keep = new Set(ids);
  const walk = (m) => {
    let frontier = [...ids];
    for (let h = 0; h < hops && frontier.length; h++) {
      const next = [];
      for (const u of frontier) for (const v of m.get(u) ?? []) if (!keep.has(v)) { keep.add(v); next.push(v); }
      frontier = next;
    }
  };
  if (way !== "down") walk(back);
  if (way !== "up") walk(fwd);
  return keep;
}

// the view, cut down to a set of entities
// `opts` narrows further (Oct 15, a brief's transmission path on the canvas): `subs` keeps only those values, `links`
// only those interactions, and `hulls: false` drops the superentities
export function filterView(view, keep, opts = {}) {
  if (!view || !keep) return view;
  const subs = (view.subentities ?? []).filter((s) => keep.has(s.entity_id) && (!opts.subs || opts.subs.has(s.id)));
  const subIds = new Set(subs.map((s) => s.id));
  return {
    ...view,
    entities: (view.entities ?? []).filter((e) => keep.has(e.id)),
    subentities: subs,
    links: (view.links ?? []).filter((l) => subIds.has(l.source) && subIds.has(l.target) && (!opts.links || opts.links.has(l.id))),
    entity_links: (view.entity_links ?? []).filter((l) => keep.has(l.source) && keep.has(l.target)),
    // a superentity stays if at least two of its members do (one alone is just that entity)
    hulls: opts.hulls === false ? [] : (view.hulls ?? []).map((h) => ({ ...h, members: (h.members ?? []).filter((m) => keep.has(m)) }))
      .filter((h) => h.members.length >= 2),
    super_links: [],
    clusters: [],               // an isolated graph is small and laid out on its own: no nested superentities
    frontier: (view.frontier ?? []).filter((f) => subIds.has(f.earlier) && subIds.has(f.later)),
    fuzzy: (view.fuzzy ?? []).filter((f) => !f.subentity_id || subIds.has(f.subentity_id)),
  };
}
