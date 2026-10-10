// Levels (Oct 9): navigate the hierarchy of superentities, superentities within superentities. A path above the
// canvas names each level of what is selected: World › Oil and rates › Policy loop › Inflation. Each step is a link:
// the world closes everything into its outermost cards; a superentity opens with its parts closed and is framed; an
// entity is focused. After the last step, chips name the level below (a superentity's parts and loose members), so
// one click goes down a level. Keys: [ goes up a level, ] goes down into the first part.
import { ancestors } from "../graph/hulls.js";
import { on, store } from "../store.js";
import { esc } from "../util.js";

export function initLevels({ renderer, select }) {
  const bar = document.createElement("nav");
  bar.id = "levels";
  bar.className = "floating hidden";
  bar.setAttribute("aria-label", "Levels of superentities");
  document.getElementById("canvas").appendChild(bar);
  let path = [];        // [{kind: "world" | "group" | "entity", key, label}]
  let below = [];       // the level below the last step

  const info = () => renderer.groupsInfo;
  const label = (k) => info().byKey.get(k)?.label ?? k;
  const shown = (g) => g && !g.transient && (g.status === "admitted" || g.status === "candidate");

  // the chain of groups from the outermost down to `key` (composites can share parts: take the first parent each time)
  function chainTo(key) {
    const out = [key];
    let k = key;
    const seen = new Set([key]);
    for (;;) {
      const ps = (info().byKey.get(k)?.parents ?? []).filter((p) => !seen.has(p) && shown(info().byKey.get(p)));
      if (!ps.length) break;
      k = ps[0];
      seen.add(k);
      out.unshift(k);
    }
    return out;
  }

  // the innermost group that holds an entity
  function innermost(eid) {
    const ks = (info().ofEntity.get(eid) ?? []).filter((k) => shown(info().byKey.get(k)));
    if (!ks.length) return null;
    return ks.reduce((a, k) => ((info().byKey.get(k)?.level ?? 0) < (info().byKey.get(a)?.level ?? 0) ? k : a), ks[0]);
  }

  function compute() {
    const sel = store.selection;
    path = [{ kind: "world", key: null, label: "World" }];
    let groupKey = null;
    let eid = null;
    if (sel?.kind === "pattern") groupKey = sel.group ?? info().ofInstance.get(sel.instance) ?? null;
    else if (sel?.kind === "entity") eid = sel.id;
    else if (sel?.kind === "subentity") eid = store.view?.subentities.find((s) => s.id === sel.id)?.entity_id ?? null;
    if (eid) groupKey = innermost(eid);
    if (groupKey && info().byKey.has(groupKey)) {
      for (const k of chainTo(groupKey)) path.push({ kind: "group", key: k, label: label(k) });
    }
    if (eid) path.push({ kind: "entity", key: eid, label: store.view?.entities.find((e) => e.id === eid)?.name ?? eid });
    // the level below the last step
    const last = path[path.length - 1];
    below = [];
    if (last.kind === "world") {
      below = info().groups.filter((g) => shown(g) && !(g.parents ?? []).some((p) => shown(info().byKey.get(p))))
        .map((g) => ({ kind: "group", key: g.key, label: g.label, composite: g.composite }));
    } else if (last.kind === "group") {
      const g = info().byKey.get(last.key);
      const inParts = new Set((g.children ?? []).flatMap((c) => [...(info().byKey.get(c)?.members ?? [])]));
      below = [...(g.children ?? []).filter((c) => shown(info().byKey.get(c))).map((c) => ({ kind: "group", key: c, label: label(c), composite: info().byKey.get(c)?.composite })),
        ...[...g.members].filter((m) => !inParts.has(m)).map((m) => ({ kind: "entity", key: m, label: store.view?.entities.find((e) => e.id === m)?.name ?? m }))];
    }
  }

  function render() {
    compute();
    // only worth a line once there is a hierarchy to walk: a superentity, or something selected inside one
    const any = info().groups.some(shown);
    bar.classList.toggle("hidden", !any);
    if (!any) return;
    // a long path folds its middle into "…" (each folded step is still a link, in the "…" menu's title)
    const shownSteps = path.length > 3 ? [0, -1, path.length - 2, path.length - 1] : path.map((_, i) => i);
    bar.innerHTML = `<ol class="lv-path">${shownSteps.map((i, n) => `<li>${n ? `<span class="lv-sep" aria-hidden="true">›</span>` : ""}
        ${i < 0 ? `<button class="lv-step more" data-i="1" title="${esc(path.slice(1, -2).map((p) => p.label).join(" › "))}">…</button>` : `<button class="lv-step ${path[i].kind}${i === path.length - 1 ? " cur" : ""}" data-i="${i}" ${i === path.length - 1 ? 'aria-current="true"' : ""}
          title="${esc(path[i].label)}: ${path[i].kind === "world" ? "close every superentity into its card" : path[i].kind === "group" ? "open it, its parts closed, and frame it" : "go to it"}">${esc(path[i].label)}</button>`}</li>`).join("")}</ol>
      ${below.length ? `<span class="lv-below"><span class="lv-sep" aria-hidden="true">›</span>${below.slice(0, 6).map((b, j) => `<button class="lv-chip ${b.kind}${b.composite ? " composite" : ""}" data-j="${j}"
        title="${b.kind === "group" ? (b.composite ? "A superentity made of superentities: open it" : "Open this superentity") : "Go to this entity"}">${esc(b.label)}</button>`).join("")}${below.length > 6 ? `<span class="small muted">+${below.length - 6}</span>` : ""}</span>` : ""}
`;
    for (const b of bar.querySelectorAll(".lv-step")) b.addEventListener("click", () => goStep(path[+b.dataset.i]));
    for (const b of bar.querySelectorAll(".lv-chip")) b.addEventListener("click", () => goStep(below[+b.dataset.j]));
  }

  function goStep(p) {
    if (!p) return;
    if (p.kind === "world") {
      renderer.setDetail("super");
      select(null);
      setTimeout(() => renderer.fit(), 60);
    } else if (p.kind === "group") {
      const g = info().byKey.get(p.key);
      // open it and every level above it; its parts start closed, so one level shows at a time
      for (const a of ancestors(info().byKey, p.key)) renderer.ui.collapsed.delete(a);
      renderer.setGroupChildren(p.key, true);
      const h = g?.hulls?.[0];
      if (h) select({ kind: "pattern", id: h.pattern_id, instance: h.id, group: p.key }, false);
      setTimeout(() => renderer.frame([...(g?.members ?? [])], { maxK: 1.1 }), 80);
    } else if (p.kind === "entity") {
      renderer.focusNode(p.key);
    }
  }

  function up() { if (path.length > 1) goStep(path[path.length - 2]); }
  function down() { if (below.length) goStep(below[0]); }

  on("graph", () => requestAnimationFrame(render));
  return { render, up, down };
}
