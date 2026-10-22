// Inspector (§13.6): entities, interactions (the Figure 2 record), superentities, subentities, frontier
// entries, and update reports. Each view opens with a plain sentence about what the thing is, then the
// model's current numbers, then the structure around it.
// DECISION (low friction without clutter): no nested scroll boxes. Each value is one line with a small
// picture of its distribution that opens in place; long lists show their first few items and fold the rest
// behind "+ n more"; the less-used sections fold behind one line that says what they hold.
import { api } from "../api.js";
import { densitySvg } from "../charts/density.js";
import { scatter } from "../charts/fan.js";
import { sparkline } from "../charts/sparkline.js";
import { paletteOf } from "../graph/hulls.js";
import { CATEGORY_BLURBS, CATEGORY_NAMES } from "../graph/layouts.js";
import { rowLabels } from "../graph/model.js";
import { names } from "../names.js";
import { store } from "../store.js";
import { esc, fmt, fmtDate, fmtTime, signed } from "../util.js";
import { reportView } from "./update.js";

const IS_MAC_HINT = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "") ? "<kbd>⌘Z</kbd>" : "<kbd>Ctrl-Z</kbd>";
const kernelText = (k) => (k ? `${fmt(k.delay_days, 0)} d delay · ${fmt(k.lag_days, 0)} d lag · ${k.duration_days == null ? "permanent" : `${fmt(k.duration_days, 0)} d duration`}` : "—");
const summ = (s) => (s ? `${fmt(s.q50)} (${fmt(s.q05)} to ${fmt(s.q95)})` : "—");
// the first `n` items, then the rest behind a native disclosure (no script, no scroll box)
const more = (items, n = 4, empty = "") => {
  const list = items.filter(Boolean);
  if (!list.length) return empty;
  if (list.length <= n + 1) return list.join("");
  return list.slice(0, n).join("") + `<details class="more"><summary>+ ${list.length - n} more</summary>${list.slice(n).join("")}</details>`;
};
const fold = (title, body, open = false) => `<details class="section fold" ${open ? "open" : ""}><summary><h4>${title}</h4></summary>${body}</details>`;
const zText = (z) => (z > 0.25 ? `<span class="z-up">▲ ${Math.abs(z).toFixed(2)} sd</span>`
  : z < -0.25 ? `<span class="z-down">▼ ${Math.abs(z).toFixed(2)} sd</span>` : `<span class="faint">steady (${signed(z)} sd)</span>`);

export function initInspector({ onSelect, focusNode, renderer, onAction, scopeFor }) {
  const el = document.getElementById("tab-inspector");
  let seq = 0;

  // a value inside the entity the inspector is headed by reads bare; any other reads "Entity · subentity"
  const subName = (sid) => names().short(sid);
  const subHtml = (sid) => names().valueHtml(sid);
  const subLink = (sid) => `<a href="#" data-goto="subentity|${esc(sid)}">${subHtml(sid)}</a>`;
  const entName = (eid) => store.view?.entities.find((e) => e.id === eid)?.name ?? eid;
  const linkOf = (iid) => store.view?.links.find((l) => l.id === iid);

  function welcome() {
    const v = store.view;
    const n = v?.entities.length ?? 0;
    const groups = renderer.groupsInfo.groups.filter((g) => !g.transient && g.status === "admitted");
    el.innerHTML = `
      <div class="group-label">How to read the graph</div>
      <h3>The economy as a causal graph</h3>
      <p class="lede">Each pill is one of ${n} <b>entities</b>: actors such as companies, cartels, and agencies, and the economic ideas
        they act in, such as oil, inflation, or credit. Each pill's outline says its kind, and pills of a kind sit together.
        <b>Superentities</b>, groups that move together such as a supply chain, a rivalry, or a sector (${groups.length} so far),
        are listed in the panels rather than drawn. Arrows are causal links.</p>
      <div class="section small">
        <div>Hover anything to see what it is. Click to inspect it here.</div>
        <div>Double-click an entity to open it into its <b>subentities</b>, the values the model tracks (a firm's revenue, share price…).</div>
        <div>Right-click for every option: show values, forecast, ask a what-if.</div>
        <div>Press <b>Update</b> to read news and data up to a date, or <b>Step</b> to follow the scripted demo; then press
          <kbd>W</kbd> to walk through what the model did, one step at a time.</div>
        <div class="faint">${IS_MAC_HINT} undoes a view change · <kbd>?</kbd> lists every shortcut · all news and data in the demo are synthetic.</div>
      </div>`;
  }

  async function show(sel) {
    const my = ++seq;
    if (!sel) { welcome(); return; }
    el.innerHTML = `<p class="empty">Loading…</p>`;
    try {
      let node;
      if (sel.kind === "entity") node = await entity(sel.id);
      else if (sel.kind === "subentity") node = await entity(sel.id.split(".")[0], sel.id);
      else if (sel.kind === "interaction") node = await interaction(sel.id, sel.ids);
      else if (sel.kind === "pattern") node = await pattern(sel.id, sel.instance);
      else if (sel.kind === "frontier") node = await frontier(sel.id);
      else if (sel.kind === "report") node = wrap(reportView(sel.run));
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
        const [kind, id, instance] = a.dataset.goto.split("|");
        onSelect({ kind, id, instance: instance || undefined });
        if (kind === "entity" || kind === "subentity") focusNode?.(id);
      });
    }
    for (const b of d.querySelectorAll("[data-act]")) {
      b.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopPropagation(); onAction?.(b.dataset.act, b.dataset.arg); });
    }
    return d;
  }

  const link = (kind, id, text, extra = "") => `<a href="#" data-goto="${esc(kind)}|${esc(id)}${extra ? `|${esc(extra)}` : ""}">${esc(text ?? id)}</a>`;

  function edgeLine(iid, dir) {
    const l = linkOf(iid);
    if (!l) return "";
    const other = dir === "in" ? l.source : l.target;
    const mine = dir === "in" ? l.target : l.source;
    const arrow = `<span class="faint">${dir === "in" ? "→" : "→"}</span>`;
    const text = dir === "in"
      ? `${subLink(other)} ${arrow} ${esc(subName(mine))}`
      : `${esc(subName(mine))} ${arrow} ${subLink(other)}`;
    return `<div class="small" style="padding:2px 0">${text} <span class="faint">· ${link("interaction", iid, l.label)}${l.edge_type === "learned_causal" ? " · learned" : ""}</span></div>`;
  }

  function groupChip(key, label) {
    const g = renderer.groupsInfo.byKey.get(key);
    if (!g) return "";
    const p = paletteOf(g, store.view?.palettes);
    const h = g.hulls[0];
    return `<a href="#" class="badge" style="background:${p.fill};border-color:${p.line};color:${p.ink}" data-goto="pattern|${esc(h.pattern_id)}|${esc(h.id)}">${esc(label ?? g.label)}</a>`;
  }

  async function entity(id, focusSub = null) {
    const v = await api.entity(id);
    const e = v.entity;
    const node = store.view?.entities.find((x) => x.id === id);
    const tags = (e.category_tags ?? []).slice().sort();
    const groupKeys = renderer.groupsInfo.ofEntity.get(id) ?? [];
    const marks = renderer.marks ?? new Map();
    // one line per value (name, a small picture of its distribution, how far from normal); a click opens it.
    // Names read as on the canvas, without the entity's name they all start with.
    const labels = rowLabels(v.subentities);
    const subOpen = (sid) => store.view?.subentities.find((x) => x.id === sid)?.open;
    const rowHtml = (s) => {
      const usedBy = (marks.get(s.id) ?? []).map((k) => groupChip(k, renderer.groupsInfo.byKey.get(k)?.hulls[0]?.pattern_id)).join(" ");
      const open = s.id === focusSub || v.subentities.length === 1;
      return `<details class="subrow ${s.id === focusSub ? "selected" : ""}" data-sub="${esc(s.id)}" ${open ? "open" : ""}>
        <summary><span class="nm" title="${esc(s.name)}">${esc(labels.get(s.id) ?? s.name)}${s.decision_variable ? ` <span class="badge init">decision</span>` : ""}</span>
          <span class="mini"></span><span class="val">${zText(s.z)}</span></summary>
        <div class="subbody">
          <div class="dens"><span class="big"></span><span class="small muted">median <b class="mono">${fmt(s.summary.q50)}</b> ${esc(s.unit)}<br>
            90%: ${fmt(s.summary.q05)} to ${fmt(s.summary.q95)}<br><span class="faint">dashed: its normal range</span></span></div>
          <div class="small muted">${s.observed_today ? "● observed today" : s.observed === false ? "◌ never observed; moved by the graph" : "◌ carried forward by daily propagation"}</div>
          ${subOpen(s.id) != null ? `<div class="small tt-open"><span class="on-dot" aria-hidden="true"></span><span>Open node ${Math.round(100 * subOpen(s.id))}% <span class="muted">of its movement is not explained by the graph yet</span></span></div>` : ""}
          <div class="spark"></div>
          ${usedBy ? `<div class="small">used by ${usedBy}</div>` : ""}
          <div class="row"><button class="ghost small" data-act="forecast" data-arg="subentity|${esc(s.id)}">Forecast it</button>
            ${scopeFor?.(s.id) ? `<button class="ghost small" data-act="walk" data-arg="${esc(scopeFor(s.id))}" title="Step through what the model did with the latest news about it">How it learned ▸</button>` : ""}</div>
        </div></details>`;
    };
    // the values its kinds give every member come first, under the kind that gives them, then its own: similar
    // objects have similar subentities, and the line names the entities that share them
    const kindName = new Map((v.generalization_path ?? []).map((g) => [g.id, g.name]));
    const order = [...new Set(v.subentities.map((s) => s.slot_of ?? ""))];
    const kinOf = (k) => {
      const slots = new Set(v.subentities.filter((s) => s.slot_of === k).map((s) => s.slot));
      const subs = store.view?.subentities ?? [];
      return (store.view?.entities ?? []).filter((x) => x.id !== id && subs.some((s) => s.entity_id === x.id && slots.has(s.slot)))
        .map((x) => x.name);
    };
    const subRows = order.length === 1 && !order[0] ? v.subentities.map(rowHtml).join("") : order.map((k) => {
      const kin = k ? kinOf(k) : [];
      const head = k ? `Like every ${esc((kindName.get(k) ?? k).toLowerCase())}` : "Its own";
      const also = kin.length ? ` <span class="faint">· also ${esc(kin.length <= 3 ? kin.join(", ") : `${kin.slice(0, 2).join(", ")} and ${kin.length - 2} more`)}</span>` : "";
      return `<div class="kin-h">${head}${also}</div>${v.subentities.filter((s) => (s.slot_of ?? "") === k).map(rowHtml).join("")}`;
    }).join("");
    const memory = v.entity_memory ? fold(`Entity memory <span class="faint small">${v.entity_memory.entries} weekly entries</span>`,
      Object.entries(v.entity_memory.profiles ?? {}).map(([sid, prof]) => `<div class="small"><b>${esc(subName(sid))}</b> decisions by context:
        ${Object.entries(prof).map(([ctx, c]) => `<div class="mono">${esc(ctx)}: raised ${c[0]}, cut ${c[1]}, held ${c[2]}</div>`).join("")}</div>`).join("")
      || `<div class="small muted">Weekly summaries of how its values moved; no decision profiles.</div>`) : "";
    const walkScope = scopeFor?.(id);
    const d = wrap(`
      <div class="group-label">Entity · ${esc(e.kind.replace(/_/g, " "))}${node?.loose ? " · in no superentity" : ""}</div>
      <h3>${esc(e.name)}</h3>
      <div class="row" style="margin:6px 0">${tags.map((t) => `<span class="badge" title="${esc(CATEGORY_BLURBS[t] ?? "")}"><code>${esc(t)}</code> ${esc(CATEGORY_NAMES[t] ?? t)}</span>`).join("")}
        ${e.origin !== "construction" ? `<span class="badge real">learned from ${esc(e.origin)}</span>` : ""}
        ${node?.user_confidence != null && node.user_confidence < 1 ? `<span class="badge" title="The reviewer's confidence when it was added">added at ${Math.round(100 * node.user_confidence)}% confidence</span>` : ""}</div>
      ${e.description ? `<p class="lede">${esc(e.description)}</p>` : ""}
      ${tags.length ? `<p class="small muted">${tags.map((t) => esc(CATEGORY_BLURBS[t] ?? "")).join(" ")}</p>` : ""}
      <div class="row" style="margin:8px 0 4px">
        <button data-act="toggle-entity" data-arg="${esc(id)}">${renderer.ui.expanded.has(id) ? "Close its subentities" : "Show its subentities"}</button>
        <button data-act="ask-entity" data-arg="${esc(id)}">What if it moves?</button>
        <button data-act="forecast" data-arg="entity|${esc(id)}">Forecast it</button>
        ${walkScope ? `<button data-act="walk" data-arg="${esc(walkScope)}" title="Step through what the model did with the latest news that touched it">How it learned ▸</button>` : ""}</div>
      <div class="section"><h4>Its values now</h4>${subRows}</div>
      <div class="section"><h4>Part of</h4>${groupKeys.map((k) => groupChip(k)).join(" ") || "<span class='muted small'>no superentity yet: a loose entity</span>"}</div>
      <div class="section"><h4>Pushed by <span class="faint small">${v.in_links.length}</span></h4>${more(v.in_links.map((i) => edgeLine(i, "in")), 4, "<span class='muted small'>nothing in the graph</span>")}
        ${node?.open != null ? `<div class="small tt-open" title="Its open node: the share of its values' movement over the last weeks that no interaction in the graph explains (a cause outside the model, so far)"><span class="on-dot" aria-hidden="true"></span>
          <span><b>Something not in the graph: ${Math.round(100 * node.open)}%</b> <span class="muted">of its values' movement</span></span></div>` : ""}</div>
      <div class="section"><h4>Pushes <span class="faint small">${v.out_links.length}</span></h4>${more(v.out_links.map((i) => edgeLine(i, "out")), 4, "<span class='muted small'>nothing in the graph</span>")}</div>
      ${fold(`Classified as <span class="faint small">${esc(v.generalization_path.at(-1)?.name ?? "unclassified")}</span>`,
        `<div class="path-list">${v.generalization_path.map((g) => `<span class="node">${esc(g.name)}</span>`).join("") || "<span class='muted'>unclassified</span>"}</div>`)}
      ${memory}`);
    for (const s of v.subentities) {
      const row = d.querySelector(`[data-sub="${CSS.escape(s.id)}"]`);
      row.querySelector(".mini").appendChild(densitySvg(s.density, { width: 56, height: 14, prior: s.prior_density, marker: s.summary?.q50 }));
      row.querySelector(".big").appendChild(densitySvg(s.density, { width: 150, height: 34, labels: true, unit: s.unit, prior: s.prior_density, marker: s.summary?.q50 }));
      row.querySelector(".spark").appendChild(sparkline(s.daily ?? [], { value: (p) => p.z, width: 340, height: 34, zero: true,
        dot: (p) => p.observed, label: `${s.name}: deviation over the last ${(s.daily ?? []).length} days` }));
    }
    return d;
  }

  async function interaction(id, ids) {
    const r = await api.interaction(id);
    const others = (ids ?? []).filter((x) => x !== id);
    const w = r.weight.history;
    const sign = (r.effect?.q50 ?? 0) >= 0 ? "raises" : "lowers";
    const d = wrap(`
      <div class="group-label">Interaction · ${esc(r.edge_type.replace(/_/g, " "))}${r.internal ? " · inside one entity" : ""}</div>
      <h3>${esc(r.label)}</h3>
      <p class="lede">${subLink(r.source)} ${sign} ${subLink(r.target)},
        after about ${fmt(r.kernel_means?.delay_days, 0)} days, building over ${fmt(r.kernel_means?.lag_days, 0)} more.</p>
      ${linkOf(id)?.hedge ? `<p class="small hedge-note">A candidate of a fuzzy end: ${Math.round(100 * (linkOf(id).hedge_p ?? 0))}% likely to be the one the
        article meant. It stays soft until later evidence carries one candidate past the bound and a reviewer approves.</p>` : ""}
      ${linkOf(id)?.user_confidence != null && linkOf(id).user_confidence < 1 ? `<p class="small muted">Its latest evidence came at the reviewer's ${Math.round(100 * linkOf(id).user_confidence)}% confidence.</p>` : ""}
      ${others.length ? `<div class="small muted">The same arrow on the canvas also carries ${others.map((x) => link("interaction", x, linkOf(x)?.label ?? x)).join(", ")}.</div>` : ""}
      <div class="section"><h4>Weight over time</h4><div class="small">significance now ${summ(r.weight.now)}</div><div class="wspark"></div></div>
      <details class="section fold"><summary><h4>The full record <span class="faint small">effect ${summ(r.effect)} sd per sd · exists ${fmt(r.existence.mean)}</span></h4></summary>
      <dl class="kv">
        <dt>Effect</dt><dd>${summ(r.effect)} sd per sd${r.reverse_effect ? ` · reverse ${summ(r.reverse_effect)} sd per sd` : ""}</dd>
        <dt>Exists</dt><dd>${fmt(r.existence.mean)} (α ${fmt(r.existence_params.alpha, 1)}, β ${fmt(r.existence_params.beta, 1)})</dd>
        <dt>Confidence</dt><dd>${fmt(r.confidence)}</dd>
        <dt>Timing</dt><dd>${kernelText(r.kernel_means)}</dd>
        <dt>Delay</dt><dd>${summ(r.delay)} d</dd>
        <dt>Lag</dt><dd>${summ(r.lag)} d</dd>
        <dt>Duration</dt><dd>${r.duration ? `${summ(r.duration)} d` : "permanent"}</dd>
        <dt>Direction</dt><dd>${esc(r.direction)}</dd>
        <dt>Origin</dt><dd>${esc(r.origin)}</dd>
        <dt>Prior from</dt><dd>${esc(r.prior_source_id ?? "—")}</dd>
        <dt>Created</dt><dd>${fmtDate(r.created_at)}</dd>
      </dl></details>
      <div class="section"><h4>Classified as</h4><div class="path-list">${r.generalization_path.map((g) => `<span class="node">${esc(g.name)}</span>`).join("") || "—"}</div></div>
      ${r.parameters.length ? `<div class="section"><h4>Moderated by</h4>${r.parameters.map((p) => `<div class="small">${esc(p.name ?? p.moderator_id)} <span class="mono faint">${esc(p.form)}</span></div>`).join("")}</div>` : ""}
      <div class="section"><h4>Evidence <span class="faint small">${r.evidence_count}</span></h4>${more(r.evidence.slice(-12).reverse().map((e) => `
        <div class="small" style="margin-bottom:4px"><span class="badge">${esc(e.source_type)}</span> ${fmtDate(e.observed_at)} · strength ${fmt(e.strength)}<br>
        <span class="muted">${esc(e.excerpt ?? "")}</span></div>`), 2, "<span class='muted small'>none yet</span>")}</div>
      ${fold("Recent time states", r.time_states.slice(-5).reverse().map((t) => `<div class="small mono">${fmtTime(t.at.valid_at)} ${Object.entries(t.values).map(([k, v]) => `${k}=${typeof v === "number" ? fmt(v, 3) : v}`).join(" ")}</div>`).join("") || "<span class='muted small'>none</span>")}`);
    d.querySelector(".wspark").appendChild(sparkline(w, { value: (p) => p.significance, width: 360, height: 46,
      lo: (p) => (p.effect_mean != null && p.effect_sd != null ? Math.abs(p.effect_mean) * p.existence_mean - p.effect_sd : p.significance),
      hi: (p) => (p.effect_mean != null && p.effect_sd != null ? Math.abs(p.effect_mean) * p.existence_mean + p.effect_sd : p.significance),
      label: "weight over time" }));
    return d;
  }

  async function pattern(id, instance) {
    const r = await api.pattern(id);
    const p = r.pattern;
    const key = renderer.groupsInfo.ofInstance.get(instance ?? `inst-${id}`) ?? renderer.groupsInfo.ofInstance.get(r.instances[0]?.id);
    const g = key ? renderer.groupsInfo.byKey.get(key) : null;
    const inst = r.instances.find((i) => i.id === instance) ?? r.instances.find((i) => i.id === g?.key) ?? r.instances[0];
    const ids = inst?.interaction_ids ?? [];
    const subs = [...new Set(ids.flatMap((i) => { const l = linkOf(i); return l ? [l.source, l.target] : []; }))];
    const members = [...new Set(Object.values(inst?.bindings ?? {}))];
    const parts = (p.sub_pattern_ids ?? []).map((pid) => {
      const ck = renderer.groupsInfo.ofInstance.get(`inst-${pid}`) ?? [...renderer.groupsInfo.byKey.values()].find((x) => x.patternIds.includes(pid))?.key;
      return ck ? groupChip(ck) : `<span class="badge">${esc(pid)}</span>`;
    });
    const inParts = new Set((g?.children ?? []).flatMap((k) => [...(renderer.groupsInfo.byKey.get(k)?.members ?? [])]));
    const extra = members.filter((m) => !inParts.has(m));
    const parents = (g?.parents ?? []).map((k) => groupChip(k));
    const d = wrap(`
      <div class="group-label">Superentity · ${esc(p.status)} · ${esc(p.origin)}${p.sub_pattern_ids?.length ? " · made of superentities" : ""}</div>
      <h3>${esc(p.id)} · ${esc(p.name)}</h3>
      ${p.description ? `<p class="lede">${esc(p.description)}</p>` : `<p class="lede">A pattern the model inferred: these entities moved together through the interactions below often enough to count as one recurring configuration.</p>`}
      ${g && p.status === "admitted" ? `<div class="row" style="margin:8px 0 4px"><button data-act="forecast" data-arg="superentity|${esc(p.id)}">Forecast it</button>
        <button class="ghost" data-act="dissolve" data-arg="${esc(p.id)}" title="Break it back into its constituents (waits for review)">Dissolve…</button></div>` : ""}
      ${parts.length ? `<div class="section"><h4>Made of</h4><div class="row">${parts.join(" ")}${extra.length ? ` <span class="faint">plus</span> ${extra.map((m) => link("entity", m, entName(m))).join(", ")}` : ""}</div></div>` : ""}
      ${parents.length ? `<div class="section"><h4>Part of</h4><div class="row">${parents.join(" ")}</div></div>` : ""}
      <div class="section"><h4>Entities</h4><div class="small">${members.map((m) => link("entity", m, entName(m))).join(", ") || "—"}</div></div>
      <div class="section"><h4>How it works</h4>${more(ids.map((i) => { const l = linkOf(i); return l ? `<div class="small" style="padding:1px 0">${subHtml(l.source)} <span class="faint">→</span> ${subHtml(l.target)} <span class="faint">· ${link("interaction", i, l.label)}</span></div>` : ""; }), 5, "<span class='muted small'>no interactions bound</span>")}
        ${inst?.absent_interaction_ids?.length ? `<div class="small muted" style="margin-top:4px">and, by this pattern, no interaction ${inst.absent_interaction_ids.map((i) => esc(linkOf(i)?.label ?? i)).join(", ")}</div>` : ""}</div>
      ${fold(`Subentities it runs through <span class="faint small">${subs.length}</span>`, `<div class="small">${subs.map(subLink).join(", ") || "—"}</div>`)}
      ${p.rival_ids?.length ? `<div class="section"><h4>Rivals</h4><div class="small">${p.rival_ids.map((x) => link("pattern", x)).join(", ")}: they explain the same moves with a different structure, and forecasts weigh both.</div></div>` : ""}
      ${fold(`Connections to other superentities <span class="faint small">${r.super_interactions.filter((s) => s.kind === "causal").length}</span>`, more(r.super_interactions.filter((s) => s.kind === "causal").slice(0, 24).map((s) => `<div class="small">${esc(s.source_instance_id)} → ${esc(s.target_instance_id)} · <b>${esc(s.label)}</b></div>`), 6, "<span class='muted small'>none</span>"))}
      <div class="section"><h4>Support</h4><div class="small">${fmt(p.support)} (track record ${fmt(r.track_record.mean)}: ${r.track_record.hits} hits, ${r.track_record.misses} misses)</div><div class="sspark"></div></div>
      ${r.instances.length > 1 ? fold(`Other bindings <span class="faint small">${r.instances.length - 1}</span>`, r.instances.filter((i) => i.id !== inst?.id).slice(0, 12).map((i) => `<div class="small mono">${esc(i.id)}: ${Object.values(i.bindings).map((m) => esc(entName(m))).join(", ")}</div>`).join("")) : ""}`);
    d.querySelector(".sspark").appendChild(sparkline(r.support_history, { value: (x) => x.support, width: 340, height: 40, label: "support over time" }));
    return d;
  }

  async function frontier(id) {
    const entry = store.view?.frontier?.find((f) => f.id === id);
    const s = await api.frontierSeries(id);
    const d = wrap(`
      <div class="group-label">Co-movement on the correlation frontier</div>
      <h3>${subHtml(s.earlier)} → ${subHtml(s.later)}</h3>
      <p class="lede">${subLink(s.earlier)} tends to move first, and ${subLink(s.later)}
        follows about ${s.lag_days ?? s.lag_steps} days later, in the ${s.sign > 0 ? "same" : "opposite"} direction. It is not yet a causal link:
        it becomes one only if it keeps holding and you approve its promotion.</p>
      ${entry ? `<dl class="kv"><dt>Support</dt><dd>${fmt(entry.support)}</dd><dt>Consistent</dt><dd>${entry.consistent} of ${entry.consistent + entry.inconsistent}</dd>
        <dt>Correlation</dt><dd>${fmt(entry.corr)}</dd><dt>Status</dt><dd>${esc(entry.status)}${entry.seeded ? " (seeded)" : ""}</dd>
        <dt>Hypothesis</dt><dd>${esc(entry.hypothesis_id ?? "—")}</dd></dl>` : ""}
      <div class="section"><h4>Earlier move against later surprise</h4><div class="sc"></div></div>`);
    d.querySelector(".sc").appendChild(scatter(s.pairs));
    return d;
  }

  return { show, welcome };
}
