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
