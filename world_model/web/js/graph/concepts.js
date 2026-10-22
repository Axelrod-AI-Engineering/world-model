// Concept outlines (Oct 15): each entity's outline says which concept in long-term memory it belongs to (its object
// generalization: a central bank, a bank, an insurer, a yield curve), so actors of different types read apart at a
// glance. Each concept has a hue of its own, actors' concepts first and with a heavier line. The hues stay clear of the
// ones that already mean something on the canvas: green and red (movement), violet (learning), orchid (what-ifs), and
// amber (blind spots); dashes keep meaning "not committed yet".
const PALETTE = ["hsl(186 58% 31%)", "hsl(224 52% 42%)", "hsl(22 58% 38%)", "hsl(62 45% 31%)", "hsl(203 64% 44%)",
                 "hsl(242 26% 40%)", "hsl(172 38% 42%)", "hsl(30 26% 46%)", "hsl(200 14% 44%)", "hsl(214 24% 60%)"];

const titleOf = (id) => {
  const raw = String(id ?? "").split(":").pop().replaceAll("_", " ");
  return raw ? raw[0].toUpperCase() + raw.slice(1) : "";
};

// {generalization id -> {color, width, name, branch, branchName}} for the concepts the view's entities belong to
export function conceptStyles(view) {
  const ents = (view?.entities ?? []).filter((e) => e.generalization_id && e.concept_branch);
  // actors: the institutions branch (central banks and companies), or an older world's "actor" branch
  const actor = (b) => /actor|institution/.test(b ?? "");
  const gens = [...new Map(ents.map((e) => [e.generalization_id, e])).values()]
    .sort((a, b) => Number(actor(b.concept_branch)) - Number(actor(a.concept_branch))
      || String(a.concept_branch).localeCompare(String(b.concept_branch)) || String(a.generalization_id).localeCompare(String(b.generalization_id)));
  const out = new Map();
  gens.forEach((e, k) => {
    out.set(e.generalization_id, { color: PALETTE[k % PALETTE.length], width: actor(e.concept_branch) ? 2.2 : 1.4,
                                   name: e.kind_name ?? titleOf(e.generalization_id), branch: e.concept_branch,
                                   branchName: e.concept_branch_name ?? titleOf(e.concept_branch) });
  });
  return out;
}

// The canvas's arrangement (Oct 17): superentities are no longer drawn, so entities are placed by the static,
// expert-provided taxonomy instead. Each concept on an entity's path (Actor > Firm > Bank) is a group for the layout
// (graph/layout-hier.js), never drawn: related entities sit together, and each top-level branch keeps a block of its
// own. Groups look like buildGroups' (key, members, children, parents), so the layout and the gravity force read both.
export function conceptGroups(view) {
  const byKey = new Map();
  const get = (id, parent) => {
    const key = `concept:${id}`;
    let g = byKey.get(key);
    if (!g) {
      g = { key, concept: id, members: new Set(), children: [], parents: parent ? [parent] : [], transient: false, level: 0 };
      byKey.set(key, g);
      if (parent) byKey.get(parent).children.push(key);
    }
    return g;
  };
  const ofEntity = new Map();
  for (const e of [...(view?.entities ?? [])].sort((a, b) => String(a.id).localeCompare(String(b.id)))) {
    let parent = null;
    const keys = [];
    for (const c of e.concept_path ?? []) {
      const g = get(c, parent);
      g.members.add(e.id);
      keys.push(g.key);
      parent = g.key;
    }
    if (keys.length) ofEntity.set(e.id, keys);
  }
  return { groups: [...byKey.values()], byKey, ofEntity };
}

// The same shape from the nested superentities the server computes (view.clusters, api/hierarchy.py): groups of groups,
// each a region of the layout. Their members sit together, so a collapsed group can stand for its region, and the
// arrangement stays the same whatever the zoom. Falls back to the taxonomy's concepts when the view has none.
export function clusterGroups(view) {
  const byKey = new Map();
  const groups = [];
  const cs = view?.clusters ?? [];
  const keyOf = (id) => `cluster:${id}`;
  for (const c of cs) {
    const g = { key: keyOf(c.id), cluster: c.id, members: new Set(c.members), children: c.children.map(keyOf),
                parents: c.parent ? [keyOf(c.parent)] : [], transient: false, level: c.depth };
    byKey.set(g.key, g);
    groups.push(g);
  }
  // an entity belongs to its group and every group above it, deepest last
  const ofEntity = new Map();
  for (const g of [...groups].sort((a, b) => a.level - b.level)) {
    for (const m of g.members) {
      if (!ofEntity.has(m)) ofEntity.set(m, []);
      ofEntity.get(m).push(g.key);
    }
  }
  return { groups, byKey, ofEntity };
}
