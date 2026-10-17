// Levels (Oct 9): a path above the canvas that names each level of what is selected, each step a link. Oct 17: the
// levels are the static taxonomy's concepts (Actor › Firm › Bank › AIB Group), no longer superentities, which left the
// canvas. The world lists the top concepts; a concept frames its entities; an entity is focused. After the last step,
// chips name the level below (a concept's narrower concepts and its own entities), so one click goes down a level.
// Keys: [ goes up a level, ] goes down into the first chip.
import { on, store } from "../store.js";
import { esc } from "../util.js";

const titleOf = (id) => {
  const raw = String(id ?? "").split(":").pop().replaceAll("_", " ");
  return raw ? raw[0].toUpperCase() + raw.slice(1) : "";
};

export function initLevels({ renderer, select }) {
  const bar = document.createElement("nav");
  bar.id = "levels";
  bar.className = "floating hidden";
  bar.setAttribute("aria-label", "Levels of the taxonomy");
  document.getElementById("canvas").appendChild(bar);
  let path = [];        // [{kind: "world" | "concept" | "entity", key, label}]
  let below = [];       // the level below the last step
  let concept = null;   // a concept picked here (it is not a selection the inspector shows)

  const info = () => renderer.layoutGroups;
  const ents = () => store.view?.entities ?? [];
  // each concept's name: an entity's own concept is its kind's name, a top concept its branch's name
  function names() {
    const out = new Map();
    for (const e of ents()) {
      if (e.generalization_id && e.kind_name) out.set(e.generalization_id, e.kind_name);
      if (e.concept_branch && e.concept_branch_name) out.set(e.concept_branch, e.concept_branch_name);
    }
    return out;
  }
  const label = (key, nm) => { const id = info().byKey.get(key)?.concept ?? key; return nm.get(id) ?? titleOf(id); };
  const entName = (id) => ents().find((e) => e.id === id)?.name ?? id;

  // the chain of concepts from the top down to `key`
  function chainTo(key) {
    const out = [];
    for (let k = key; k; k = info().byKey.get(k)?.parents?.[0]) out.unshift(k);
    return out;
  }

  function compute() {
    const sel = store.selection;
    const nm = names();
    let eid = null;
    if (sel?.kind === "entity") eid = sel.id;
    else if (sel?.kind === "subentity") eid = store.view?.subentities.find((s) => s.id === sel.id)?.entity_id ?? null;
    if (eid) concept = null;
    const leaf = eid ? info().ofEntity.get(eid)?.at(-1) ?? null : concept;
    path = [{ kind: "world", key: null, label: "World" }];
    for (const k of leaf ? chainTo(leaf) : []) path.push({ kind: "concept", key: k, label: label(k, nm) });
    if (eid) path.push({ kind: "entity", key: eid, label: entName(eid) });
    // the level below the last step
    const last = path[path.length - 1];
    below = [];
    if (last.kind === "world") {
      below = info().groups.filter((g) => !g.parents.length).map((g) => ({ kind: "concept", key: g.key, label: label(g.key, nm) }));
    } else if (last.kind === "concept") {
      const g = info().byKey.get(last.key);
      const inParts = new Set(g.children.flatMap((c) => [...(info().byKey.get(c)?.members ?? [])]));
      below = [...g.children.map((c) => ({ kind: "concept", key: c, label: label(c, nm) })),
        ...[...g.members].filter((m) => !inParts.has(m)).map((m) => ({ kind: "entity", key: m, label: entName(m) }))];
    }
  }

  function render() {
    compute();
    // only worth a line once there is a taxonomy to walk
    const any = info().groups.length > 0;
    bar.classList.toggle("hidden", !any);
    if (!any) return;
    // a long path folds its middle into "…" (each folded step is still a link, in the "…" menu's title)
    const shownSteps = path.length > 3 ? [0, -1, path.length - 2, path.length - 1] : path.map((_, i) => i);
    const what = (p) => (p.kind === "world" ? "frame everything" : p.kind === "concept" ? "frame its entities" : "go to it");
    bar.innerHTML = `<ol class="lv-path">${shownSteps.map((i, n) => `<li>${n ? `<span class="lv-sep" aria-hidden="true">›</span>` : ""}
        ${i < 0 ? `<button class="lv-step more" data-i="1" title="${esc(path.slice(1, -2).map((p) => p.label).join(" › "))}">…</button>` : `<button class="lv-step ${path[i].kind}${i === path.length - 1 ? " cur" : ""}" data-i="${i}" ${i === path.length - 1 ? 'aria-current="true"' : ""}
          title="${esc(path[i].label)}: ${what(path[i])}">${esc(path[i].label)}</button>`}</li>`).join("")}</ol>
      ${below.length ? `<span class="lv-below"><span class="lv-sep" aria-hidden="true">›</span>${below.slice(0, 6).map((b, j) => `<button class="lv-chip ${b.kind}" data-j="${j}"
        title="${b.kind === "concept" ? "A concept in the taxonomy: frame its entities" : "Go to this entity"}">${esc(b.label)}</button>`).join("")}${below.length > 6 ? `<span class="small muted">+${below.length - 6}</span>` : ""}</span>` : ""}
`;
    for (const b of bar.querySelectorAll(".lv-step")) b.addEventListener("click", () => goStep(path[+b.dataset.i]));
    for (const b of bar.querySelectorAll(".lv-chip")) b.addEventListener("click", () => goStep(below[+b.dataset.j]));
  }

  function goStep(p) {
    if (!p) return;
    if (p.kind === "world") {
      concept = null;
      select(null);
      setTimeout(() => renderer.fit(), 60);
    } else if (p.kind === "concept") {
      concept = p.key;
      select(null, false);
      setTimeout(() => renderer.frame([...(info().byKey.get(p.key)?.members ?? [])], { maxK: 1.1 }), 60);
    } else if (p.kind === "entity") {
      renderer.focusNode(p.key);
    }
    render();
  }

  function up() { if (path.length > 1) goStep(path[path.length - 2]); }
  function down() { if (below.length) goStep(below[0]); }

  on("graph", () => requestAnimationFrame(render));
  return { render, up, down };
}
