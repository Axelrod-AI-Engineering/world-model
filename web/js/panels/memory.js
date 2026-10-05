// Memory drawer (§13.6): the object and interaction taxonomies (collapsible trees with supports, where
// classify.path highlights the path), episodes, the frontier, explanations, entity memories, and versions
// (clicking one opens a read-only view of that state).
import { api } from "../api.js";
import { on, openVersion, store } from "../store.js";
import { esc, fmt, fmtTime } from "../util.js";

export function initMemory() {
  const drawer = document.getElementById("drawer");
  const body = document.getElementById("drawer-body");
  const btn = document.getElementById("btn-memory");
  let tab = "object";
  let lastPath = { object: [], interaction: [] };
  let collapsed = new Set();
  let timer = null;

  const isOpen = () => drawer.classList.contains("open");

  function setOpen(open) {
    drawer.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.textContent = open ? "Memory ▾" : "Memory ▴";
    if (open) render();
  }

  async function render() {
    if (!isOpen()) return;
    for (const b of drawer.querySelectorAll("[data-mtab]")) b.setAttribute("aria-selected", String(b.dataset.mtab === tab));
    try {
      if (tab === "object" || tab === "interaction") await renderTree(tab);
      else if (tab === "versions") await renderVersions();
      else if (tab === "frontier") await renderFrontier();
      else await renderMemory(tab);
    } catch (err) {
      body.innerHTML = `<p class="error">${esc(err.message)}</p>`;
    }
  }

  async function renderTree(kind) {
    const t = await api.taxonomy(kind);
    const nodes = new Map(t.nodes.map((n) => [n.id, n]));
    const onPath = new Set(lastPath[kind]);
    const li = (id, depth) => {
      const n = nodes.get(id);
      if (!n) return "";
      const kids = [...n.children].sort((a, b) => (nodes.get(b)?.support ?? 0) - (nodes.get(a)?.support ?? 0));
      const closed = collapsed.has(id) || (depth >= 2 && !onPath.has(id) && !collapsed.has(`open:${id}`));
      return `<li><span class="toggle" data-tog="${esc(id)}">${kids.length ? (closed ? "▸" : "▾") : ""}</span>
        <span class="tnode ${onPath.has(id) ? "on-path" : ""}" data-node="${esc(id)}" title="${esc(id)}">${esc(n.name)}
          <span class="badge">${fmt(n.support, 0)}</span>${n.instance_ids?.length ? `<span class="muted small">${n.instance_ids.length} instances</span>` : ""}
          ${n.origin === "grown" ? `<span class="badge ltm">grown</span>` : ""}</span>
        ${kids.length && !closed ? `<ul>${kids.map((k) => li(k, depth + 1)).join("")}</ul>` : ""}</li>`;
    };
    body.innerHTML = `<div class="small muted">Supports count classified items; the last classification path is highlighted.</div>
      <div class="tree"><ul>${li(t.root_id, 0)}</ul></div>`;
    for (const tg of body.querySelectorAll("[data-tog]")) {
      tg.addEventListener("click", () => {
        const id = tg.dataset.tog;
        if (tg.textContent === "▸") { collapsed.delete(id); collapsed.add(`open:${id}`); } else { collapsed.add(id); collapsed.delete(`open:${id}`); }
        render();
      });
    }
  }

  async function renderVersions() {
    const vs = await api.versions();
    body.innerHTML = `<table class="list"><thead><tr><th>Version</th><th>Recorded</th><th>Change set</th><th>Hash</th><th></th></tr></thead>
      <tbody>${vs.slice().reverse().slice(0, 300).map((v) => `<tr class="clickable" data-v="${v.version}">
        <td class="mono">v${v.version}</td><td>${fmtTime(v.recorded_at ?? v.created_at)}</td>
        <td class="mono">${esc(v.changeset_id ?? v.cause ?? "")}</td><td class="mono muted">${esc(String(v.state_hash ?? "").slice(0, 10))}</td>
        <td>${store.readOnlyVersion === v.version ? "<span class='badge ltm'>open</span>" : ""}</td></tr>`).join("")}</tbody></table>`;
    for (const tr of body.querySelectorAll("[data-v]")) tr.addEventListener("click", () => openVersion(+tr.dataset.v));
  }

  async function renderFrontier() {
    const fr = await api.frontier();
    body.innerHTML = `<table class="list"><thead><tr><th>Id</th><th>Earlier → later</th><th>Lag</th><th>Sign</th><th>Support</th><th>Consistent</th><th>Status</th></tr></thead>
      <tbody>${fr.map((c) => `<tr><td class="mono">${esc(c.id)}</td><td>${esc(c.earlier_id)} → ${esc(c.later_id)}</td><td>${c.lag_steps}</td>
        <td>${c.sign > 0 ? "+" : "−"}</td><td>${fmt(c.support)}</td><td>${c.consistent}/${c.consistent + c.inconsistent}</td>
        <td><span class="badge front">${esc(c.status)}</span>${c.seeded ? " seeded" : ""}</td></tr>`).join("")}</tbody></table>`;
  }

  async function renderMemory(which) {
    const m = await api.memory();
    if (which === "episodes") {
      body.innerHTML = `<div class="small muted">${m.episodes} episodes, ${m.patterns} patterns, ${m.generalizations} generalizations.</div>
        <table class="list"><thead><tr><th>Id</th><th>Day</th><th>Event types</th><th>Tags</th><th>Active patterns</th><th>Signature</th></tr></thead>
        <tbody>${m.recent_episodes.map((e) => `<tr><td class="mono">${esc(e.id)}</td><td>${esc(String(e.end).slice(0, 10))}</td>
          <td>${e.event_types.map(esc).join(", ")}</td><td>${e.tags.map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}</td>
          <td>${e.active_patterns.map(esc).join(", ")}</td><td class="small muted">${e.signature.slice(0, 6).map(esc).join(", ")}</td></tr>`).join("")}</tbody></table>`;
    } else if (which === "explanations") {
      body.innerHTML = m.explanations_recent.map((x) => `<div class="card"><div class="meta"><span class="mono">${esc(x.id)}</span>
        <span class="badge ${x.kind === "forecast" ? "hyp" : "real"}">${esc(x.kind)}</span><span class="mono">${esc(x.subject)}</span></div>
        <div class="small">${esc(x.text)}</div></div>`).join("") || "<p class='muted'>none</p>";
    } else if (which === "entity_memories") {
      body.innerHTML = `<div class="small muted">Entities with a memory: click one to inspect its decision profiles.</div>
        <div>${m.entity_memory_ids.map((id) => `<button class="small" data-em="${esc(id)}" style="margin:2px">${esc(id)}</button>`).join("")}</div>
        <div id="em-detail"></div>`;
      for (const b of body.querySelectorAll("[data-em]")) {
        b.addEventListener("click", async () => {
          const v = await api.entity(b.dataset.em);
          const mem = v.entity_memory;
          body.querySelector("#em-detail").innerHTML = mem ? `<div class="card"><b>${esc(v.entity.name)}</b> · ${mem.entries} entries
            ${Object.entries(mem.profiles ?? {}).map(([sid, prof]) => `<div class="small"><b>${esc(sid)}</b>
              ${Object.entries(prof).map(([ctx, c]) => `<div class="mono">${esc(ctx)}: raised ${c[0]}, cut ${c[1]}, held ${c[2]}</div>`).join("")}</div>`).join("")}
            ${(mem.decisions ?? []).slice(-8).map((d) => `<div class="small mono">${esc(String(d.at).slice(0, 10))} ${esc(d.subentity_id)} ${fmt(d.change)}</div>`).join("")}
          </div>` : "<p class='muted'>no memory</p>";
        });
      }
    }
  }

  btn.addEventListener("click", () => setOpen(!isOpen()));
  document.getElementById("drawer-close").addEventListener("click", () => setOpen(false));
  for (const b of drawer.querySelectorAll("[data-mtab]")) b.addEventListener("click", () => { tab = b.dataset.mtab; render(); });
  on("classify", (p) => {
    lastPath[p.taxonomy === "interaction" ? "interaction" : "object"] = p.path ?? [];
    if (isOpen() && (tab === p.taxonomy || (tab === "object" && p.taxonomy !== "interaction"))) {
      clearTimeout(timer);
      timer = setTimeout(render, 250);
    }
  });
  on("memory", () => { if (isOpen()) { clearTimeout(timer); timer = setTimeout(render, 400); } });
  on("versions", () => { if (isOpen() && tab === "versions") { clearTimeout(timer); timer = setTimeout(render, 600); } });
  on("readonly", () => { if (isOpen() && tab === "versions") render(); });
  return { setOpen, isOpen, close: () => setOpen(false) };
}
