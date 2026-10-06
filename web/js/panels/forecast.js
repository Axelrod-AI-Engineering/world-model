// Forecast panel (§13.6): fan charts per target with a levels/effects toggle; a scenario weight bar;
// network small multiples; a decomposition bar per target; the explanation and top paths with a
// "Highlight" button; and "Compare with…" to overlay another forecast (T-01 against T-02).
// Additions: forecasts for coarser targets (an actor, a sector, a superentity, an idea) come first; each
// target shows a small picture of its effect's distribution at the horizon; targets sit in a wrapping grid
// of small cards that open into a full chart; and "Walk through" steps through how the forecast was made.
import { api } from "../api.js";
import { densitySvg } from "../charts/density.js";
import { fanChart } from "../charts/fan.js";
import { emit, on, store } from "../store.js";
import { esc, fmt, signed } from "../util.js";
/* global d3 */

const SCEN_COLORS = ["#E8CFEC", "#DCE6F0", "#F7E1D3", "#E1ECDF", "#F5E4E9", "#D6ECE7", "#E7E0F3", "#F3E1A6"];
const NET_COLORS = ["#B07CC0", "#6F93B8", "#C9825A", "#6E9E72", "#B86A84", "#5E9C8F", "#9A8C74", "#B08F2E"];
const GROUP_KIND = { entity: "actor or idea", superentity: "superentity", sector: "sector", category: "category" };
const EFFECT_FMT = d3.format("+.2~f");
const flat = (series) => series.every((p) => Math.abs(p.q05 ?? 0) < 0.01 && Math.abs(p.q95 ?? 0) < 0.01);

// -- forecasting progress (addition): the sidebar shows what the model is doing while a forecast runs.
// It reads the raw trace stream (before the animation queue), so it is never behind the server.
const PHASES = [["posed", "Question"], ["recall", "Recall"], ["isolate", "Isolate"], ["predict", "Predict"],
                ["unify", "Scenarios"], ["couple", "Couple"], ["explain", "Explain"], ["ready", "Forecast"]];
const PHASE_TEXT = { posed: "Reading the question as a hypothetical event", recall: "Recalling superentities and analogs",
                     isolate: "Isolating the networks it touches", predict: "Simulating each network", unify: "Weighing rival scenarios",
                     couple: "Coupling the networks", explain: "Finding the paths that explain it", ready: "Done" };
export const progress = { run: null };

export function trackForecast(ev) {
  if (!/^T-/.test(ev.scope ?? "")) return;
  const p = ev.payload ?? {};
  let r = progress.run;
  if (ev.kind === "thesis.posed") {
    r = progress.run = { scope: ev.scope, question: p.question, phase: "posed", nets: 0, total: 0, current: "" };
  } else if (!r || r.scope !== ev.scope) return;
  else if (ev.kind === "recall.result") r.phase = "recall";
  else if (ev.kind === "isolate.networks") { r.phase = "isolate"; r.total = (p.networks ?? []).length; }
  else if (ev.kind === "predict.network") { r.phase = "predict"; r.nets += 1; r.current = p.name ?? ""; }
  else if (ev.kind === "unify.scenarios") { r.phase = "unify"; r.scenarios = (p.scenarios ?? []).map((x) => [x.name, x.weight]); }
  else if (ev.kind === "couple.done") r.phase = "couple";
  else if (ev.kind === "explain.stored") r.phase = "explain";
  else if (ev.kind === "forecast.ready") {
    r.phase = "ready";
    r.forecast_id = p.forecast_id;
    setTimeout(() => { if (progress.run === r) { progress.run = null; emit("forecasting", null); } }, 900);
  } else return;
  emit("forecasting", r);
}

export function progressCard(r) {
  const at = PHASES.findIndex(([k]) => k === r.phase);
  const pct = r.phase === "predict" && r.total ? Math.round((r.nets / r.total) * 100) : Math.round(((at + 1) / PHASES.length) * 100);
  return `<div class="card progress-card" role="status" aria-live="polite">
    <div class="meta"><span class="spinner" aria-hidden="true"></span><span>Forecasting</span><span class="spacer"></span>
      <span class="mono faint">${esc(r.scope)}</span></div>
    <div class="title">${esc(r.question ?? "")}</div>
    <div class="phases">${PHASES.map(([k, label], i) => `<span class="ph ${i < at ? "done" : i === at ? "cur" : ""}">${label}</span>`).join("")}</div>
    <div class="bar"><i style="width:${pct}%"></i></div>
    <div class="small muted">${esc(PHASE_TEXT[r.phase] ?? "")}${r.phase === "predict" && r.total ? `: ${r.nets} of ${r.total}${r.current ? ` · ${esc(r.current.split(" · ")[0])}` : ""}` : ""}</div>
  </div>`;
}

// server text names links and values by id ("mostly through e08 → e43"); show their names
function readable(text) {
  const v = store.view;
  const subs = new Map((v?.subentities ?? []).map((x) => [x.id, x.name]));
  const links = new Map((v?.links ?? []).map((x) => [x.id, x.label]));
  return String(text ?? "").replace(/\b([a-z][\w]*\.[a-z][\w.]*|e\d{2,3})\b/g, (m) => subs.get(m) ?? links.get(m) ?? m);
}

export function initForecast({ renderer, activateTab, onWalk }) {
  const el = document.getElementById("tab-forecast");
  let mode = "effects";
  let open = null;            // the target card shown as a full chart

  async function show(fv) {
    store.forecast = fv;
    open = null;
    render();
    activateTab("forecast");
  }

  async function openById(id) {
    try { show(await api.forecast(id)); } catch (err) { console.warn(err); }
  }

  const arrow = (v) => (v > 0.05 ? `<span class="z-up">▲ ${fmt(Math.abs(v))}</span>` : v < -0.05 ? `<span class="z-down">▼ ${fmt(Math.abs(v))}</span>` : `<span class="faint">≈ 0</span>`);

  async function render() {
    const fv = store.forecast;
    const r = progress.run;
    if (r && r.phase !== "ready" && fv?.forecast?.thesis_id !== r.scope) {
      el.innerHTML = `${progressCard(r)}${fv ? `<p class="small faint">The previous forecast (${esc(fv.forecast.thesis_id)}) returns when this one is ready.</p>` : ""}`;
      return;
    }
    if (!fv) {
      el.innerHTML = `<p class="empty">No forecast yet. Ask a what-if question (the Ask tab) and the forecast appears here:
        a fan of outcomes for each target, the scenarios behind it, and the paths that explain it.</p>`;
      return;
    }
    let list = [];
    try { list = await api.forecasts(); } catch { /* offline */ }
    const fc = fv.forecast;
    const cmp = store.compare;
    const scen = fv.scenarios ?? [];
    const netNames = new Map((fv.networks ?? []).map((n, i) => [n.id, { name: n.name ?? n.id, color: NET_COLORS[i % NET_COLORS.length] }]));
    el.innerHTML = `
      <div class="group-label">Forecast · ${esc(fc.thesis_id)} · ${esc(fc.id)}</div>
      ${fc.question ? `<h3>${esc(fc.question)}</h3>` : ""}
      <div class="small muted">at version v${fc.based_on_version} · ${fc.horizon_days ?? fc.horizon_steps} days ahead · ${esc(fc.is_baseline ? "baseline" : "scenario forecast")}</div>
      <div class="ask-row small" style="margin:8px 0">
        <button class="hyp" id="fc-walk" title="Step through how the model made this forecast (W)">Walk through ▸</button>
        <div class="seg" role="group" aria-label="Levels or effects">
          <button id="fc-ef" aria-pressed="${mode === "effects"}">Effects</button>
          <button id="fc-lv" aria-pressed="${mode === "levels"}">Levels</button></div>
        <select id="fc-cmp" aria-label="Compare with another forecast"><option value="">Compare with…</option>${list.filter((x) => x.id !== fc.id).map((x) => `<option value="${esc(x.id)}" ${cmp?.forecast?.id === x.id ? "selected" : ""}>${esc(x.thesis_id)} · ${esc(x.id)}</option>`).join("")}</select>
      </div>
      ${scen.length > 1 ? `<div class="section"><h4>Scenarios</h4>
        <div class="weightbar" role="img" aria-label="Scenario weights">${scen.map((s, i) => `<div style="width:${(s.weight * 100).toFixed(2)}%;background:${SCEN_COLORS[i % SCEN_COLORS.length]}" title="${esc(s.name)}: ${fmt(s.weight * 100, 1)}%">${s.weight > 0.12 ? `${esc(s.name.split(" · ")[0])} ${fmt(s.weight * 100, 0)}%` : ""}</div>`).join("")}</div></div>` : ""}
      ${(fv.groups ?? []).length ? `<div class="section"><h4>Actors, sectors, and ideas</h4><div class="fc-grid groups" id="fc-groups"></div></div>` : ""}
      <div class="section"><h4>Values</h4><div class="fc-grid" id="fc-targets"></div></div>
      <div class="section"><h4>Networks</h4><div class="chips">${(fv.networks ?? []).map((n) => {
        const meta = netNames.get(n.id);
        return `<span class="pick" style="border-color:${meta?.color}" title="relevance ${fmt(n.relevance)}"><span class="k">${esc(n.kind)}</span>${esc((n.name ?? n.id).split(" · ")[0])}</span>`;
      }).join("")}</div></div>
      <div class="section"><div class="ask-row"><h4 style="flex:1;margin:0">Why</h4><button id="fc-hl">Highlight the paths</button></div><div id="fc-expl"></div></div>`;
    el.querySelector("#fc-walk").addEventListener("click", () => onWalk?.(fc.thesis_id));
    el.querySelector("#fc-lv").addEventListener("click", () => { mode = "levels"; render(); });
    el.querySelector("#fc-ef").addEventListener("click", () => { mode = "effects"; render(); });
    el.querySelector("#fc-cmp").addEventListener("change", async (ev) => {
      store.compare = ev.target.value ? await api.forecast(ev.target.value) : null;
      render();
    });
    // coarser targets: the average standardized effect of their members
    const gbox = el.querySelector("#fc-groups");
    for (const g of fv.groups ?? []) {
      const last = g.effects[g.effects.length - 1];
      const card = document.createElement("div");
      card.className = "card fan fc-card";
      card.innerHTML = `<div class="fc-head"><span class="k">${esc(GROUP_KIND[g.kind] ?? g.kind)}</span><b>${esc(g.name)}</b>
          <span class="mono small" title="median average effect at the horizon">${arrow(last?.q50 ?? 0)} sd</span></div>
        <div class="fc-viz"></div>
        <div class="small muted">${g.members} values averaged${flat(g.effects) ? "" : ` · most moved: ${g.top.filter((t) => Math.abs(t.effect) >= 0.05).slice(0, 3).map((t) => `${esc(t.name)} ${arrow(t.effect)}`).join(", ") || "none by much"}`}</div>`;
      const viz = card.querySelector(".fc-viz");
      if (flat(g.effects)) {
        viz.innerHTML = `<span class="small faint">No visible effect within ${fv.dates.length - 1} days: the shock does not reach it through the graph.</span>`;
      } else {
        viz.appendChild(fanChart({ dates: fv.dates, series: g.effects, unit: "sd", title: g.name, zeroLine: true, compact: true, width: 220, height: 84 }));
        if (g.effect_density?.length) {
          const d = densitySvg(g.effect_density, { width: 104, height: 30, zero: true, labels: true, fmt: EFFECT_FMT, fill: "#E8CFEC", stroke: "#7A3F8C" });
          d.setAttribute("title", "the distribution of the effect at the horizon");
          viz.appendChild(d);
        }
      }
      gbox.appendChild(card);
    }
    // values: small cards in a wrapping grid; one opens into the full chart
    const tg = el.querySelector("#fc-targets");
    const cmpTargets = new Map((cmp?.targets ?? []).map((t) => [t.id, t]));
    for (const t of fv.targets) {
      const series = mode === "levels" ? t.levels : t.effects;
      const c = cmpTargets.get(t.id);
      const last = series[series.length - 1];
      const card = document.createElement("div");
      const isOpen = open === t.id;
      card.className = `card fan fc-card selectable ${isOpen ? "wide" : ""}`;
      card.tabIndex = 0;
      card.innerHTML = `<div class="fc-head"><b>${esc(t.name)}</b>
          <span class="mono small">${mode === "levels" ? `${fmt(last?.q50)} ${esc(t.unit)}` : `${arrow(last?.q50 ?? 0)} sd`}</span>
          ${c ? `<span class="mono faint small" title="compare">vs ${mode === "levels" ? fmt(c.levels.at(-1)?.q50) : signed(c.effects.at(-1)?.q50)}</span>` : ""}</div>
        ${t.entity ? `<div class="small faint">${esc(t.entity)}</div>` : ""}<div class="fc-viz"></div>`;
      const viz = card.querySelector(".fc-viz");
      viz.appendChild(fanChart({ dates: fv.dates, series, compare: c ? (mode === "levels" ? c.levels : c.effects) : null,
                                 unit: mode === "levels" ? t.unit : "effect (sd)", title: t.name, zeroLine: mode === "effects",
                                 compact: !isOpen, axes: isOpen, width: isOpen ? 340 : 150, height: isOpen ? 140 : 56 }));
      if (mode === "effects" && t.effect_density?.length) {
        viz.appendChild(densitySvg(t.effect_density, { width: isOpen ? 120 : 60, height: isOpen ? 30 : 18, zero: true,
                                                       labels: isOpen, fmt: EFFECT_FMT, fill: "#E8CFEC", stroke: "#7A3F8C" }));
      }
      if (isOpen) {
        const dec = Object.entries(t.decomposition ?? {}).filter(([, v]) => Math.abs(v) >= 0.005)
          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
        const tot = dec.reduce((a, [, v]) => a + Math.abs(v), 0) || 1;
        if (dec.length) {
          card.insertAdjacentHTML("beforeend", `<div class="small muted" style="margin-top:6px">How much each network contributes at the horizon</div>
            <div class="decomp" role="img" aria-label="decomposition">${dec.map(([k, v]) => `<div style="width:${((Math.abs(v) / tot) * 100).toFixed(1)}%;background:${k === "coupling" ? "#CDBFA8" : netNames.get(k)?.color ?? "#999"}" title="${esc(netNames.get(k)?.name ?? k)}: ${signed(v)}"></div>`).join("")}</div>
            <div class="chips small">${dec.map(([k, v]) => `<span class="pick"><span class="k">${esc(k === "coupling" ? "coupling" : (netNames.get(k)?.name ?? k).split(" · ")[0])}</span><span class="mono">${signed(v)}</span></span>`).join("")}</div>`);
        }
      }
      const toggle = () => { open = isOpen ? null : t.id; render(); };
      card.addEventListener("click", toggle);
      card.addEventListener("keydown", (ev) => { if (ev.key === "Enter") toggle(); });
      tg.appendChild(card);
    }
    const ex = fv.explanation;
    const expl = el.querySelector("#fc-expl");
    if (ex) {
      const paths = ex.top_paths ?? [];
      expl.innerHTML = `<div class="explanation">${esc(readable(ex.text))}</div>
        ${paths.slice(0, 3).map((p) => `<div class="top-path">${esc(p.shock_id)} → ${p.interaction_ids.map(esc).join(" → ")} → ${esc(p.target_id)} <span class="muted">(${fmt(p.share * 100, 0)}%)</span></div>`).join("")}
        ${paths.length > 3 ? `<details><summary class="small faint">${paths.length - 3} more paths</summary>${paths.slice(3).map((p) => `<div class="top-path">${esc(p.shock_id)} → ${p.interaction_ids.map(esc).join(" → ")} → ${esc(p.target_id)} <span class="muted">(${fmt(p.share * 100, 0)}%)</span></div>`).join("")}</details>` : ""}
        ${(ex.assumptions ?? []).length ? `<details><summary class="small faint">Assumptions</summary><div class="small muted">${ex.assumptions.map(esc).join("; ")}</div></details>` : ""}`;
    } else {
      expl.innerHTML = `<span class="muted small">no explanation</span>`;
    }
    el.querySelector("#fc-hl").addEventListener("click", () => highlight(fv));
  }

  function highlight(fv) {
    const ex = fv.explanation;
    const hot = new Set((ex?.top_paths ?? []).flatMap((p) => p.interaction_ids));
    const ents = new Set();
    const links = new Set(hot);
    const hulls = new Set();
    for (const n of fv.networks ?? []) {
      for (const s of n.subentity_ids ?? []) ents.add(s.split(".")[0]);
      for (const c of n.channels ?? []) links.add(String(c.interaction_id ?? c.channel_key ?? "").split(":")[0]);
      if (n.instance_id) hulls.add(n.instance_id);
    }
    const linkIndex = new Map((store.view?.links ?? []).map((l) => [l.id, l]));
    for (const i of hot) {
      const l = linkIndex.get(i);
      if (l) { ents.add(l.source.split(".")[0]); ents.add(l.target.split(".")[0]); }
    }
    store.highlight = { entities: ents, links, hulls, hot };
    renderer.setHighlight(store.highlight);
    emit("highlight", store.highlight);
  }

  on("forecasting", (run) => {
    document.querySelector('#right-tabs [data-tab="forecast"]')?.classList.toggle("busy", !!run && run.phase !== "ready");
    if (run && run.phase !== "ready") render();
  });
  on("show-forecast", show);
  on("open-forecast", openById);
  on("forecast", (fv) => { if (fv === null) { store.forecast = null; render(); } });
  render();
  return { show, openById };
}
