// Find (Oct 9): not just a find, a semantic filter over nodes and edges. Type words ("airline", "rates", "fuel
// costs") or filters ("moved", "up", "open>0.8", "learned", "hedged", "kind:company"); the server matches names,
// aliases, kinds and the kinds above them, categories, units, and interaction labels (api/find.py). The hits light up
// on the canvas, and the neighborhood control widens the light to what they touch: one hop (their neighbors through
// interactions), then two (the neighbors' neighbors). Everything else dims. Enter or a click goes to a hit; Esc clears.
import { api } from "../api.js";
import { on, store } from "../store.js";
import { esc } from "../util.js";

const KIND_WORD = { entity: "Entities", superentity: "Superentities", subentity: "Values", interaction: "Interactions" };
const KIND_MARK = { entity: "▭", superentity: "◌", subentity: "≡", interaction: "→" };
const HINTS = ["airline", "rates", "fuel costs", "moved", "open>0.8", "learned", "kind:company"];

export function initFind({ renderer, toast }) {
  const input = document.getElementById("search");
  input.removeAttribute("list");
  input.placeholder = "Find or filter…  /";
  input.setAttribute("aria-label", "Find or filter entities, values, interactions, and superentities");
  const box = document.createElement("div");
  box.id = "find-results";
  box.className = "floating hidden";
  box.setAttribute("role", "listbox");
  document.getElementById("canvas").appendChild(box);
  const st = { q: "", res: null, hops: 1, active: -1, ticket: 0, lit: false };

  // entity adjacency through interactions (both directions), from the graph on screen
  function adjacency() {
    const v = store.view;
    const ent = new Map((v?.subentities ?? []).map((s) => [s.id, s.entity_id]));
    const adj = new Map();
    const add = (a, b) => { if (!adj.has(a)) adj.set(a, new Set()); adj.get(a).add(b); };
    for (const l of v?.links ?? []) {
      const a = ent.get(l.source);
      const b = ent.get(l.target);
      if (a && b && a !== b) { add(a, b); add(b, a); }
    }
    return adj;
  }

  // the hits' entities, then the rings around them
  function rings() {
    const found = new Set();
    for (const h of st.res?.hits ?? []) {
      if (h.entity) found.add(h.entity);
      for (const e of h.entities ?? []) found.add(e);
    }
    const adj = adjacency();
    const ring1 = new Set();
    const ring2 = new Set();
    if (st.hops >= 1) for (const e of found) for (const n of adj.get(e) ?? []) if (!found.has(n)) ring1.add(n);
    if (st.hops >= 2) for (const e of ring1) for (const n of adj.get(e) ?? []) if (!found.has(n) && !ring1.has(n)) ring2.add(n);
    return { found, ring1, ring2 };
  }

  function light() {
    if (!st.res?.hits?.length) { unlight(); return; }
    const { found, ring1, ring2 } = rings();
    const all = new Set([...found, ...ring1, ...ring2]);
    const ent = new Map((store.view?.subentities ?? []).map((s) => [s.id, s.entity_id]));
    const hitLinks = new Set(st.res.hits.filter((h) => h.kind === "interaction").map((h) => h.id));
    const links = new Set((store.view?.links ?? []).filter((l) => hitLinks.has(l.id) || (all.has(ent.get(l.source)) && all.has(ent.get(l.target)))).map((l) => l.id));
    const hulls = new Set(st.res.hits.filter((h) => h.kind === "superentity").map((h) => h.id));
    renderer.setHighlight({ entities: all, links, hulls, hot: hitLinks, found, ring1, ring2 });
    st.lit = true;
  }
  function unlight() {
    if (!st.lit) return;
    st.lit = false;
    renderer.setHighlight(store.highlight);
  }

  // while find is in use, the story caption steps aside (the results and the wider box need its room)
  const finding = (on_) => document.body.classList.toggle("finding", on_);

  function render() {
    const r = st.res;
    if (!st.q) { box.classList.add("hidden"); finding(document.activeElement === input); return; }
    finding(true);
    box.classList.remove("hidden");
    if (!r) { box.innerHTML = `<div class="fr-empty small muted">Finding…</div>`; return; }
    const { ring1, ring2 } = rings();
    const groups = new Map();
    r.hits.forEach((h, i) => {
      if (!groups.has(h.kind)) groups.set(h.kind, []);
      groups.get(h.kind).push({ h, i });
    });
    const filt = Object.keys(r.filters ?? {});
    box.innerHTML = `
      <div class="fr-head"><span class="small"><b>${r.total}</b> match${r.total === 1 ? "" : "es"}${filt.length ? ` <span class="muted">· filters: ${filt.map(esc).join(", ")}</span>` : ""}</span>
        <span class="spacer"></span>
        <span class="seg fr-hops" role="group" aria-label="Neighborhood">${[0, 1, 2].map((k) => `<button data-hops="${k}" aria-pressed="${st.hops === k}"
          title="${["Only the matches", "And what they touch through interactions", "And what those touch"][k]}">${["matches", "+ 1 hop", "+ 2 hops"][k]}</button>`).join("")}</span></div>
      ${r.hits.length ? "" : `<div class="fr-empty small muted">Nothing matches. Try ${HINTS.map((x) => `<button class="linkish" data-try="${esc(x)}">${esc(x)}</button>`).join(", ")}.</div>`}
      ${[...groups.entries()].map(([k, xs]) => `<div class="fr-group"><div class="fr-gh">${esc(KIND_WORD[k] ?? k)} <span class="muted">${xs.length}</span></div>
        ${xs.map(({ h, i }) => `<div class="fr-hit${i === st.active ? " active" : ""}" role="option" data-i="${i}" aria-selected="${i === st.active}">
          <span class="fr-mk" aria-hidden="true">${KIND_MARK[h.kind] ?? "·"}</span>
          <span class="fr-name">${esc(h.name)}${h.label && h.kind === "interaction" ? ` <span class="muted">(${esc(h.label)})</span>` : ""}</span>
          <span class="fr-detail small muted">${esc(h.detail ?? "")}</span>
          ${(h.why ?? []).length ? `<span class="fr-why">${h.why.map((w) => `<span>${esc(w)}</span>`).join("")}</span>` : ""}</div>`).join("")}</div>`).join("")}
      ${st.hops && (ring1.size || ring2.size) ? `<div class="fr-foot small muted">Lit on the canvas: the matches${ring1.size ? `, ${ring1.size} neighbor${ring1.size === 1 ? "" : "s"}` : ""}${ring2.size ? `, and ${ring2.size} more at two hops` : ""}.</div>` : ""}`;
    for (const b of box.querySelectorAll("[data-hops]")) {
      b.addEventListener("mousedown", (ev) => ev.preventDefault());
      b.addEventListener("click", () => { st.hops = +b.dataset.hops; light(); render(); });
    }
    for (const b of box.querySelectorAll("[data-try]")) {
      b.addEventListener("mousedown", (ev) => ev.preventDefault());
      b.addEventListener("click", () => { input.value = b.dataset.try; query(); });
    }
    for (const el of box.querySelectorAll(".fr-hit")) {
      el.addEventListener("mousedown", (ev) => ev.preventDefault());
      el.addEventListener("click", () => go(+el.dataset.i));
    }
  }

  function go(i) {
    const h = st.res?.hits?.[i];
    if (!h) return;
    st.active = i;
    if (h.kind === "entity" || h.kind === "subentity") renderer.focusNode(h.id);
    else if (h.kind === "interaction") {
      renderer.frame?.(h.entities ?? []);
      renderer.handlers?.onSelect?.({ kind: "interaction", id: h.id, ids: [h.id] });
    } else if (h.kind === "superentity") {
      renderer.frame?.(h.entities ?? []);
      renderer.handlers?.onSelect?.({ kind: "pattern", id: h.pattern_id, instance: h.id });
    }
    render();
  }

  let timer = null;
  async function query() {
    st.q = input.value.trim();
    st.active = -1;
    if (!st.q) { st.res = null; render(); unlight(); return; }
    const ticket = ++st.ticket;
    render();
    try {
      const r = await api.find(st.q);
      if (ticket !== st.ticket) return;
      st.res = r;
      st.active = r.hits.length ? 0 : -1;
      light();
      render();
    } catch (err) { toast(String(err?.message ?? err), "err"); }
  }
  function clear() { input.value = ""; st.q = ""; st.res = null; render(); unlight(); }

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(query, 180); });
  input.addEventListener("focus", () => { finding(true); if (st.q) render(); });
  input.addEventListener("blur", () => { if (!st.q) finding(false); });
  input.addEventListener("keydown", (ev) => {
    const n = st.res?.hits?.length ?? 0;
    if (ev.key === "ArrowDown" && n) { ev.preventDefault(); st.active = (st.active + 1) % n; render(); }
    else if (ev.key === "ArrowUp" && n) { ev.preventDefault(); st.active = (st.active - 1 + n) % n; render(); }
    else if (ev.key === "Enter") { ev.preventDefault(); if (st.active >= 0) go(st.active); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); clear(); input.blur(); }
  });
  // the canvas keeps the filter's light until the query is cleared; a new graph re-lights it
  on("graph", () => { if (st.res) { clearTimeout(timer); timer = setTimeout(query, 300); } });
  return { clear, isActive: () => !!st.q };
}
