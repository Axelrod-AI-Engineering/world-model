// Inspector (§13.6): entities, interactions (the Figure 2 record), superentities, subentities, and
// frontier entries.
import { api } from "../api.js";
import { densitySvg } from "../charts/density.js";
import { scatter } from "../charts/fan.js";
import { sparkline } from "../charts/sparkline.js";
import { store } from "../store.js";
import { esc, fmt, fmtDate, fmtTime, signed } from "../util.js";

const kernelText = (k) => (k ? `${fmt(k.delay_days, 0)} d delay · ${fmt(k.lag_days, 0)} d lag · ${k.duration_days == null ? "permanent" : `${fmt(k.duration_days, 0)} d duration`}` : "—");
const summ = (s) => (s ? `${fmt(s.q50)} (${fmt(s.q05)} to ${fmt(s.q95)})` : "—");

export function initInspector({ onSelect, focusNode }) {
  const el = document.getElementById("tab-inspector");
  let seq = 0;

  async function show(sel) {
    const my = ++seq;
    if (!sel) {
      el.innerHTML = `<p class="muted">Click an entity, edge, or hull to inspect it.</p>`;
      return;
    }
    el.innerHTML = `<p class="muted">Loading ${esc(sel.id)}…</p>`;
    try {
      let node;
      if (sel.kind === "entity") node = await entity(sel.id);
      else if (sel.kind === "subentity") node = await subentity(sel.id);
      else if (sel.kind === "interaction") node = await interaction(sel.id, sel.ids);
      else if (sel.kind === "pattern") node = await pattern(sel.id, sel.instance);
      else if (sel.kind === "frontier") node = await frontier(sel.id);
      if (my !== seq) return;
      el.innerHTML = "";
      if (node) el.appendChild(node);
    } catch (err) {
      if (my === seq) el.innerHTML = `<p class="error">${esc(err.message)}</p>`;
    }
  }

  function wrap(markup) {
    const d = document.createElement("div");
    d.innerHTML = markup;
    for (const a of d.querySelectorAll("[data-goto]")) {
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        const [kind, id] = a.dataset.goto.split("|");
        onSelect({ kind, id });
        if (kind === "entity" || kind === "subentity") focusNode?.(id);
      });
    }
    return d;
  }

  const link = (kind, id, text) => `<a href="#" data-goto="${esc(kind)}|${esc(id)}">${esc(text ?? id)}</a>`;

  async function entity(id) {
    const v = await api.entity(id);
    const e = v.entity;
    const subs = v.subentities.map((s) => `
      <div class="card" data-sub="${esc(s.id)}">
        <div class="row"><b>${link("subentity", s.id, s.name)}</b><span class="spacer"></span>
          <span class="badge ${s.z > 0.25 ? "front" : s.z < -0.25 ? "ltm" : ""}">${s.z > 0.25 ? "▲" : s.z < -0.25 ? "▼" : "·"} z ${signed(s.z)}</span></div>
        <div class="small muted">${esc(s.family)} · ${esc(s.unit)} · ${esc(s.attribute_kind)}${s.decision_variable ? " · decision variable" : ""} · from ${esc(s.prior_source_id ?? s.origin)}</div>
        <div class="row small"><span class="glyph"></span><span>${summ(s.summary)} ${esc(s.unit)}</span></div>
        <div class="spark"></div>
      </div>`).join("");
    const memory = v.entity_memory ? `<div class="section"><h4>Entity memory</h4>
      <div class="small">${v.entity_memory.entries} entries</div>
      ${Object.entries(v.entity_memory.profiles ?? {}).map(([sid, prof]) => `<div class="small"><b>${esc(sid)}</b> decision profile:
        ${Object.entries(prof).map(([ctx, c]) => `<div class="mono">${esc(ctx)}: raised ${c[0]}, cut ${c[1]}, held ${c[2]}</div>`).join("")}</div>`).join("")}
    </div>` : "";
    const d = wrap(`
      <h3>${esc(e.name)}</h3>
      <div class="meta small muted">${esc(e.kind)} · <span class="mono">${esc(e.id)}</span> · ${esc(e.origin)}
        ${(e.category_tags ?? []).map((t) => `<span class="badge">${esc(t)}</span>`).join(" ")}</div>
      <div class="section"><h4>Generalization path</h4><div class="path-list">${v.generalization_path.map((g) => `<span class="node">${esc(g.name)}</span>`).join("") || "<span class='muted'>unclassified</span>"}</div></div>
      <div class="section"><h4>Superentities</h4>${v.instance_ids.map((i) => `<span class="badge ltm">${esc(i)}</span>`).join(" ") || "<span class='muted small'>none (a loose entity)</span>"}</div>
      <div class="section"><h4>Subentities</h4>${subs}</div>
      ${memory}
      <div class="section small"><h4>Edges</h4>in: ${v.in_links.map((i) => link("interaction", i)).join(", ") || "—"}<br>out: ${v.out_links.map((i) => link("interaction", i)).join(", ") || "—"}</div>`);
    for (const s of v.subentities) {
      const card = d.querySelector(`[data-sub="${CSS.escape(s.id)}"]`);
      card.querySelector(".glyph").appendChild(densitySvg(s.summary, { width: 70, height: 9 }));
      card.querySelector(".spark").appendChild(sparkline(s.history, { value: (p) => p.mean, lo: (p) => p.mean - p.sd,
        hi: (p) => p.mean + p.sd, width: 300, height: 38, label: `${s.name} history` }));
    }
    return d;
  }

  async function subentity(id) {
    const eid = id.split(".")[0];
    const node = await entity(eid);
    node.querySelector(`[data-sub="${CSS.escape(id)}"]`)?.classList.add("selected");
    return node;
  }

  async function interaction(id, ids) {
    const r = await api.interaction(id);
    const others = (ids ?? []).filter((x) => x !== id);
    const w = r.weight.history;
    const d = wrap(`
      <h3>${esc(r.label)}</h3>
      <div class="small muted"><span class="mono">${esc(r.id)}</span> · ${esc(r.direction)} · ${esc(r.edge_type)} · origin ${esc(r.origin)}
        ${r.internal ? " · internal" : ""}</div>
      <div class="small">${link("subentity", r.source)} → ${link("subentity", r.target)}</div>
      ${others.length ? `<div class="small muted">Also in this entity link: ${others.map((x) => link("interaction", x)).join(", ")}</div>` : ""}
      <div class="section"><h4>Weight p(w, t)</h4><div class="small">significance now ${summ(r.weight.now)}</div><div class="wspark"></div></div>
      <dl class="kv">
        <dt>Effect</dt><dd>${summ(r.effect)}${r.reverse_effect ? ` · reverse ${summ(r.reverse_effect)}` : ""}</dd>
        <dt>Existence</dt><dd>${fmt(r.existence.mean)} (α ${fmt(r.existence_params.alpha, 1)}, β ${fmt(r.existence_params.beta, 1)})</dd>
        <dt>Confidence</dt><dd>${fmt(r.confidence)}</dd>
        <dt>Kernel</dt><dd>${kernelText(r.kernel_means)}</dd>
        <dt>Delay</dt><dd>${summ(r.delay)} d</dd>
        <dt>Lag</dt><dd>${summ(r.lag)} d</dd>
        <dt>Duration</dt><dd>${r.duration ? `${summ(r.duration)} d` : "permanent"}</dd>
        <dt>Prior from</dt><dd>${esc(r.prior_source_id ?? "—")}</dd>
        <dt>Created</dt><dd>${fmtDate(r.created_at)}</dd>
      </dl>
      <div class="section"><h4>Generalization path</h4><div class="path-list">${r.generalization_path.map((g) => `<span class="node">${esc(g.name)}</span>`).join("") || "—"}</div></div>
      ${r.parameters.length ? `<div class="section"><h4>Parameters</h4>${r.parameters.map((p) => `<div class="small mono">${esc(p.form)} by ${esc(p.moderator_id)}</div>`).join("")}</div>` : ""}
      <div class="section"><h4>Evidence (${r.evidence_count})</h4>${r.evidence.slice(-8).reverse().map((e) => `
        <div class="small"><span class="badge">${esc(e.source_type)}</span> ${fmtDate(e.observed_at)} · strength ${fmt(e.strength)}<br>
        <span class="muted">${esc(e.excerpt)}</span></div>`).join("") || "<span class='muted small'>none</span>"}</div>
      <div class="section"><h4>Time states</h4>${r.time_states.slice(-6).reverse().map((t) => `<div class="small mono">${fmtTime(t.at.valid_at)} ${Object.entries(t.values).map(([k, v]) => `${k}=${typeof v === "number" ? fmt(v, 3) : v}`).join(" ")}</div>`).join("")}</div>`);
    d.querySelector(".wspark").appendChild(sparkline(w, { value: (p) => p.significance, width: 320, height: 46,
      lo: (p) => (p.effect_mean != null && p.effect_sd != null ? Math.abs(p.effect_mean) * p.existence_mean - p.effect_sd : p.significance),
      hi: (p) => (p.effect_mean != null && p.effect_sd != null ? Math.abs(p.effect_mean) * p.existence_mean + p.effect_sd : p.significance),
      label: "weight over time" }));
    return d;
  }

  async function pattern(id, instance) {
    const r = await api.pattern(id);
    const p = r.pattern;
    const d = wrap(`
      <h3>${esc(p.id)} · ${esc(p.name)}</h3>
      <div class="small muted">${esc(p.status)} · origin ${esc(p.origin)} · support ${fmt(p.support)}${p.rival_ids?.length ? ` · rivals ${p.rival_ids.map((x) => link("pattern", x)).join(", ")}` : ""}</div>
      <div class="section"><h4>Roles</h4>${p.roles.map((x) => `<div class="small"><b>${esc(x.name)}</b> <span class="mono muted">${esc(x.generalization_id)}</span></div>`).join("")}</div>
      <div class="section"><h4>Relations</h4>${p.relations.map((x) => `<div class="small">${esc(x.source_role)} → ${esc(x.target_role)}
        <span class="mono muted">${esc(x.interaction_generalization_id ?? "")}</span> ${x.present === false ? `<span class="badge front">absent</span>` : ""}</div>`).join("")}</div>
      <div class="section"><h4>Instances</h4>${r.instances.map((i) => `<div class="card ${i.id === instance ? "selected" : ""}"><div class="mono small">${esc(i.id)}${i.transient ? " (transient)" : ""} · activation ${fmt(i.activation)}</div>
        <div class="small">${Object.entries(i.bindings).map(([role, e]) => `${esc(role)}: ${link("entity", e)}`).join(" · ")}</div>
        <div class="small">edges: ${(i.interaction_ids ?? []).map((x) => link("interaction", x)).join(", ")}${i.absent_interaction_ids?.length ? ` · absent: ${i.absent_interaction_ids.map((x) => link("interaction", x)).join(", ")}` : ""}</div></div>`).join("")}</div>
      <div class="section"><h4>Super-interactions</h4>${r.super_interactions.map((s) => `<div class="small">${esc(s.source_instance_id)} → ${esc(s.target_instance_id)} · ${esc(s.kind)} · ${esc(s.label)}</div>`).join("") || "<span class='muted small'>none</span>"}</div>
      <div class="section"><h4>Support history</h4><div class="sspark"></div></div>`);
    d.querySelector(".sspark").appendChild(sparkline(r.support_history, { value: (x) => x.support, width: 320, height: 40, label: "support" }));
    return d;
  }

  async function frontier(id) {
    const entry = store.view?.frontier?.find((f) => f.id === id);
    const s = await api.frontierSeries(id);
    const d = wrap(`
      <h3>Co-movement ${esc(id)}</h3>
      <div class="small">${link("subentity", s.earlier)} moves first; ${link("subentity", s.later)} follows ${s.lag_steps} steps later
        (${s.sign > 0 ? "same direction" : "opposite direction"}).</div>
      ${entry ? `<dl class="kv"><dt>Support</dt><dd>${fmt(entry.support)}</dd><dt>Consistent</dt><dd>${entry.consistent} / ${entry.consistent + entry.inconsistent}</dd>
        <dt>Correlation</dt><dd>${fmt(entry.corr)}</dd><dt>Status</dt><dd>${esc(entry.status)}${entry.seeded ? " (seeded)" : ""}</dd>
        <dt>Hypothesis</dt><dd>${esc(entry.hypothesis_id ?? "—")}</dd></dl>` : ""}
      <div class="section"><h4>Earlier move against later innovation</h4><div class="sc"></div></div>`);
    d.querySelector(".sc").appendChild(scatter(s.pairs));
    return d;
  }

  return { show };
}
