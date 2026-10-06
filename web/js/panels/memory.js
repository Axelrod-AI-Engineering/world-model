// Memory drawer (§13.6), laid out like Figure 1's long-term memory box: one tab per card and one for
// prior states.
//  - Object generalizations: the object taxonomy as a collapsible tree with supports; each configuration
//    node lists its superentities (support, status, track record). classify.path highlights the path.
//  - Interaction generalizations: the interaction taxonomy, in the same form.
//  - Entity memories: per entity, weekly entries as sparklines, learned level noise, decision profiles.
//  - Correlation frontier: co-movements with support, lag, sign, status, and next eligible verification.
//  - Prior states: daily episodes (non-routine ones highlighted), stored explanations, and versions
//    (clicking one opens a read-only view of that state).
import { api } from "../api.js";
import { sparkline } from "../charts/sparkline.js";
import { on, openVersion, store } from "../store.js";
import { esc, fmt, fmtTime } from "../util.js";

export function initMemory({ onSelect } = {}) {
  const drawer = document.getElementById("drawer");
  const body = document.getElementById("drawer-body");
  const btn = document.getElementById("btn-memory");
  let tab = "object";
  const lastPath = { object: [], interaction: [] };
  const toggled = new Set();
  let emSel = null;
  let frShown = 15;            // frontier rows shown; "+ more" adds 25
  let vShown = 20;             // version rows shown; "+ more" adds 30
  let timer = null;

  const isOpen = () => drawer.classList.contains("open");
  const subName = (sid) => store.view?.subentities.find((s) => s.id === sid)?.name ?? sid;

  function setOpen(open) {
    drawer.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
    if (open) render();
  }

  async function render() {
    if (!isOpen()) return;
    for (const b of drawer.querySelectorAll("[data-mtab]")) b.setAttribute("aria-selected", String(b.dataset.mtab === tab));
    try {
      if (tab === "object" || tab === "interaction") await renderTree(tab);
      else if (tab === "entity_memories") await renderEntityMemories();
      else if (tab === "frontier") await renderFrontier();
      else await renderPrior();
    } catch (err) {
      body.innerHTML = `<p class="error">${esc(err.message)}</p>`;
    }
  }

  async function renderTree(kind) {
    const [t, mem] = await Promise.all([api.taxonomy(kind), kind === "object" ? api.memory() : Promise.resolve(null)]);
    const nodes = new Map(t.nodes.map((n) => [n.id, n]));
    const onPath = new Set(lastPath[kind]);
    const pats = new Map();
    for (const p of [...(mem?.object_generalizations?.admitted ?? []).map((x) => ({ ...x, status: "admitted" })),
      ...(mem?.object_generalizations?.candidates ?? []).map((x) => ({ ...x, status: "candidate" }))]) {
      if (!p.generalization_id) continue;
      if (!pats.has(p.generalization_id)) pats.set(p.generalization_id, []);
      pats.get(p.generalization_id).push(p);
    }
    const li = (id, depth) => {
      const n = nodes.get(id);
      if (!n) return "";
      const kids = [...n.children].sort((a, b) => (nodes.get(b)?.support ?? 0) - (nodes.get(a)?.support ?? 0));
      const auto = depth >= 2 && !onPath.has(id);
      const closed = toggled.has(id) ? !auto : auto;
      const ps = pats.get(id) ?? [];
      return `<li><span class="toggle" data-tog="${esc(id)}">${kids.length ? (closed ? "▸" : "▾") : ""}</span>
        <span class="tnode ${onPath.has(id) ? "on-path" : ""}" title="${esc(id)}">${esc(n.name)}
          <span class="badge">${fmt(n.support, 0)}</span>${n.origin === "grown" ? `<span class="badge ltm">grown</span>` : ""}</span>
        ${ps.length ? `<span class="pats">${ps.map((p) => `<a href="#" class="badge ${p.status === "admitted" ? "ltm" : ""}" data-pat="${esc(p.id)}"
          title="support ${fmt(p.support)}${p.track_record != null ? `, track record ${fmt(p.track_record)}` : ""}">${esc(p.id)} · ${esc(p.name)}${p.status === "candidate" ? " (candidate)" : ""}</a>`).join("")}</span>` : ""}
        ${kids.length && !closed ? `<ul>${kids.map((k) => li(k, depth + 1)).join("")}</ul>` : ""}</li>`;
    };
    body.innerHTML = `<p class="small muted">${kind === "object"
      ? "Every entity and superentity is classified down this tree. Supports count what was classified; the latest classification path is highlighted. Superentities sit at the configuration they generalize to."
      : "Every interaction is classified down this tree, from general to specific relations. New links inherit priors from where they land."}</p>
      <div class="tree"><ul>${li(t.root_id, 0)}</ul></div>`;
    for (const tg of body.querySelectorAll("[data-tog]")) {
      tg.addEventListener("click", () => {
        const id = tg.dataset.tog;
        if (toggled.has(id)) toggled.delete(id); else toggled.add(id);
        render();
      });
    }
    for (const a of body.querySelectorAll("[data-pat]")) {
      a.addEventListener("click", (ev) => { ev.preventDefault(); onSelect?.({ kind: "pattern", id: a.dataset.pat }); });
    }
  }

  async function renderEntityMemories() {
    const m = await api.memory();
    const ids = m.entity_memories.entities;
    if (!emSel || !ids.includes(emSel)) emSel = ids.includes("federal_reserve") ? "federal_reserve" : ids[0];
    body.innerHTML = `<p class="small muted">Each entity keeps weekly entries. Their realized volatility sets how much its subentities
      drift day to day (learned level noise), and actors keep decision profiles by context.</p>
      <div class="two-col"><div class="chips">${ids.map((id) => `<button class="pick ${id === emSel ? "actor" : "ghosted"}" data-em="${esc(id)}">
        ${esc(store.view?.entities.find((e) => e.id === id)?.name ?? id)}</button>`).join("")}</div>
        <div id="em-detail"><p class="empty">Loading…</p></div></div>`;
    for (const tr of body.querySelectorAll("[data-em]")) tr.addEventListener("click", () => { emSel = tr.dataset.em; render(); });
    if (!emSel) return;
    const v = await api.entity(emSel);
    const mem = v.entity_memory;
    const det = body.querySelector("#em-detail");
    if (!mem) { det.innerHTML = `<p class="empty">No memory yet.</p>`; return; }
    det.innerHTML = `<h3 style="margin-bottom:6px">${esc(v.entity.name)}</h3><div class="small muted">${mem.entries} weekly entries</div>
      ${v.subentities.map((s) => `<div class="subrow"><span class="nm">${esc(s.name)}</span>
        <span class="val">level noise ${fmt(s.level_noise, 3)}</span><span class="sub2" data-ser="${esc(s.id)}"></span></div>`).join("")}
      ${Object.entries(mem.profiles ?? {}).map(([sid, prof]) => `<div class="section"><h4>Decisions of ${esc(subName(sid))}</h4>
        ${Object.entries(prof).map(([ctx, c]) => `<div class="small mono">${esc(ctx)}: raised ${c[0]}, cut ${c[1]}, held ${c[2]}</div>`).join("")}</div>`).join("")}`;
    for (const el of det.querySelectorAll("[data-ser]")) {
      el.appendChild(sparkline(mem.series?.[el.dataset.ser] ?? [], { value: (p) => p.z, width: 360, height: 30, zero: true,
        label: `${subName(el.dataset.ser)} weekly deviation` }));
    }
  }

  // the strongest first; the rest a click away (low friction without clutter)
  const RANK = { promotion_proposed: 0, holding: 1, promoted: 2, decayed: 3 };
  async function renderFrontier() {
    const all = (await api.frontier()).slice().sort((a, b) => (RANK[a.status] ?? 9) - (RANK[b.status] ?? 9)
      || b.support - a.support || String(a.id).localeCompare(String(b.id)));
    const fr = all.slice(0, frShown);
    body.innerHTML = `<p class="small muted">Co-movements the model has noticed but not yet made causal, strongest first. Each is verified at
      most once every 14 days; enough consistent support proposes a promotion to a learned edge. ${all.length} in all.</p>
      <table class="list"><thead><tr><th>Earlier → later</th><th>Lag</th><th>Sign</th><th>Support</th><th>Consistent</th><th>Status</th><th>Next check</th></tr></thead>
      <tbody>${fr.map((c) => `<tr class="clickable ${c.status === "promotion_proposed" ? "hl" : ""}" data-fr="${esc(c.id)}">
        <td>${esc(subName(c.earlier_id))} → ${esc(subName(c.later_id))}</td><td>${c.lag_days} d</td>
        <td>${c.sign > 0 ? "same" : "opposite"}</td><td>${fmt(c.support)}</td><td>${c.consistent} of ${c.consistent + c.inconsistent}</td>
        <td><span class="badge front">${esc(c.status.replace(/_/g, " "))}</span>${c.seeded ? " <span class='faint small'>seeded</span>" : ""}</td>
        <td class="mono">${esc(c.next_eligible ?? "now")}</td></tr>`).join("")}</tbody></table>
      ${all.length > fr.length ? `<button class="ghost small" id="fr-more">+ ${Math.min(25, all.length - fr.length)} more of ${all.length - fr.length}</button>` : ""}`;
    for (const tr of body.querySelectorAll("[data-fr]")) tr.addEventListener("click", () => onSelect?.({ kind: "frontier", id: tr.dataset.fr }));
    body.querySelector("#fr-more")?.addEventListener("click", () => { frShown += 25; renderFrontier(); });
  }

  async function renderPrior() {
    const [m, vs] = await Promise.all([api.memory(), api.versions()]);
    const p = m.prior_states;
    body.innerHTML = `<p class="small muted">${p.episodes} daily episodes (${p.non_routine_episodes} with news beyond routine data), ${p.explanations}
      stored explanations, and every state version. Recall draws analogs from the episodes.</p>
      <div class="two-col"><div>
        <h4>Recent episodes</h4>
        <table class="list"><thead><tr><th>Day</th><th>Event types</th><th>Tags</th><th>Active patterns</th></tr></thead>
        <tbody>${p.recent_episodes.map((e) => `<tr class="${e.routine ? "" : "hl"}"><td class="mono">${esc(e.day)}</td>
          <td>${e.event_types.map(esc).join(", ") || "<span class='faint'>routine data</span>"}</td>
          <td>${e.tags.map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}</td>
          <td class="small">${e.active_patterns.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table>
        <h4 style="margin-top:14px">Stored explanations</h4>
        ${p.explanations_recent.map((x) => `<div class="card"><div class="meta"><span class="badge ${x.kind === "forecast" ? "hyp" : "real"}">${esc(x.kind)}</span>
          <span class="mono">${esc(x.subject)}</span></div><div class="small">${esc(x.text)}</div></div>`).join("") || "<p class='empty'>none yet</p>"}
      </div><div>
        <h4>Versions</h4>
        <table class="list"><thead><tr><th>Version</th><th>Recorded</th><th>Change set</th><th></th></tr></thead>
        <tbody>${vs.slice().reverse().slice(0, vShown).map((v) => `<tr class="clickable" data-v="${v.version}">
          <td class="mono">v${v.version}</td><td>${fmtTime(v.recorded_at ?? v.created_at)}</td>
          <td class="mono small">${esc(v.changeset_id ?? v.cause ?? "")}</td>
          <td>${store.readOnlyVersion === v.version ? "<span class='badge ltm'>open</span>" : ""}</td></tr>`).join("")}</tbody></table>
        ${vs.length > vShown ? `<button class="ghost small" id="v-more">+ ${Math.min(30, vs.length - vShown)} more of ${vs.length - vShown}</button>` : ""}
      </div></div>`;
    for (const tr of body.querySelectorAll("[data-v]")) tr.addEventListener("click", () => openVersion(+tr.dataset.v));
    body.querySelector("#v-more")?.addEventListener("click", () => { vShown += 30; renderPrior(); });
  }

  btn.addEventListener("click", () => setOpen(!isOpen()));
  document.getElementById("drawer-close").addEventListener("click", () => setOpen(false));
  for (const b of drawer.querySelectorAll("[data-mtab]")) b.addEventListener("click", () => { tab = b.dataset.mtab; render(); });
  const later = (ms) => { clearTimeout(timer); timer = setTimeout(render, ms); };
  on("classify", (p) => {
    lastPath[p.taxonomy === "interaction" ? "interaction" : "object"] = p.path ?? [];
    if (isOpen() && (tab === "object" || tab === "interaction")) later(300);
  });
  on("memory", () => { if (isOpen()) later(400); });
  on("versions", () => { if (isOpen() && tab === "prior") later(800); });
  on("readonly", () => { if (isOpen() && tab === "prior") render(); });
  return { setOpen, isOpen, close: () => setOpen(false) };
}
