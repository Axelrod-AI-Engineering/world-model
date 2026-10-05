// Forecast panel (§13.6): fan charts per target with a levels/effects toggle; a scenario weight bar;
// network small multiples; a decomposition bar per target; the explanation and top paths with a
// "Highlight" button; and "Compare with…" to overlay another forecast (T-01 against T-02).
import { api } from "../api.js";
import { fanChart } from "../charts/fan.js";
import { emit, on, store } from "../store.js";
import { esc, fmt, signed } from "../util.js";

const SCEN_COLORS = ["#E8CFEC", "#DCE6F0", "#F7E1D3", "#E1ECDF", "#F5E4E9", "#D6ECE7", "#E7E0F3", "#F3E1A6"];
const NET_COLORS = ["#B07CC0", "#6F93B8", "#C9825A", "#6E9E72", "#B86A84", "#5E9C8F", "#9A8C74", "#B08F2E"];

export function initForecast({ renderer, activateTab }) {
  const el = document.getElementById("tab-forecast");
  let mode = "effects";

  async function show(fv) {
    store.forecast = fv;
    render();
    activateTab("forecast");
  }

  async function openById(id) {
    try { show(await api.forecast(id)); } catch (err) { console.warn(err); }
  }

  async function render() {
    const fv = store.forecast;
    if (!fv) {
      el.innerHTML = `<p class="muted">Pose a thesis to see a forecast.</p>`;
      return;
    }
    let list = [];
    try { list = await api.forecasts(); } catch { /* offline */ }
    const fc = fv.forecast;
    const cmp = store.compare;
    const scen = fv.scenarios ?? [];
    const netNames = new Map((fv.networks ?? []).map((n, i) => [n.id, { name: n.name ?? n.id, color: NET_COLORS[i % NET_COLORS.length] }]));
    el.innerHTML = `
      <div class="row"><h3 style="flex:1">${esc(fc.thesis_id)}</h3><span class="badge hyp mono">${esc(fc.id)}</span></div>
      <div class="small muted">at version v${fc.based_on_version} · ${fc.horizon_steps} weekly steps · ${esc(fc.is_baseline ? "baseline" : "scenario forecast")}</div>
      <div class="row small" style="margin:6px 0">
        <div class="group" role="group" aria-label="Levels or effects">
          <button id="fc-lv" aria-pressed="${mode === "levels"}">Levels</button>
          <button id="fc-ef" aria-pressed="${mode === "effects"}">Effects</button></div>
        <label for="fc-cmp">Compare with…</label>
        <select id="fc-cmp"><option value="">(none)</option>${list.filter((x) => x.id !== fc.id).map((x) => `<option value="${esc(x.id)}" ${cmp?.forecast?.id === x.id ? "selected" : ""}>${esc(x.thesis_id)} · ${esc(x.id)}</option>`).join("")}</select>
      </div>
      <div class="section"><h4>Scenarios</h4>
        <div class="weightbar" role="img" aria-label="Scenario weights">${scen.map((s, i) => `<div style="width:${(s.weight * 100).toFixed(2)}%;background:${SCEN_COLORS[i % SCEN_COLORS.length]}" title="${esc(s.name)}: ${fmt(s.weight * 100, 1)}%">${s.weight > 0.12 ? `${esc(s.name.split(" · ")[0])} ${fmt(s.weight * 100, 0)}%` : ""}</div>`).join("")}</div>
        ${scen.map((s) => `<div class="small">${esc(s.name)} — weight ${fmt(s.weight, 3)}${Object.keys(s.forced_existence ?? {}).length ? ` · forced ${Object.entries(s.forced_existence).map(([k, v]) => `${esc(k)}=${v ? "on" : "off"}`).join(", ")}` : ""}</div>`).join("")}
      </div>
      <div class="section" id="fc-targets"></div>
      <div class="section"><h4>Networks</h4><div id="fc-nets"></div></div>
      <div class="section"><div class="row"><h4 style="flex:1">Explanation</h4><button id="fc-hl">Highlight</button></div><div id="fc-expl"></div></div>`;
    el.querySelector("#fc-lv").addEventListener("click", () => { mode = "levels"; render(); });
    el.querySelector("#fc-ef").addEventListener("click", () => { mode = "effects"; render(); });
    el.querySelector("#fc-cmp").addEventListener("change", async (ev) => {
      store.compare = ev.target.value ? await api.forecast(ev.target.value) : null;
      render();
    });
    const tg = el.querySelector("#fc-targets");
    const cmpTargets = new Map((cmp?.targets ?? []).map((t) => [t.id, t]));
    for (const t of fv.targets) {
      const series = mode === "levels" ? t.levels : t.effects;
      const c = cmpTargets.get(t.id);
      const box = document.createElement("div");
      box.className = "card fan";
      const last = series[series.length - 1];
      box.innerHTML = `<div class="row small"><b style="flex:1">${esc(t.name)}</b>
        <span class="mono">${mode === "levels" ? `${fmt(last?.q50)} ${esc(t.unit)}` : `${signed(last?.q50)} sd`}</span>
        ${c ? `<span class="mono muted" title="compare">vs ${mode === "levels" ? fmt(c.levels.at(-1)?.q50) : signed(c.effects.at(-1)?.q50)}</span>` : ""}</div>`;
      box.appendChild(fanChart({ dates: fv.dates, series, compare: c ? (mode === "levels" ? c.levels : c.effects) : null,
                                 unit: mode === "levels" ? t.unit : "effect (sd)", title: t.name, zeroLine: mode === "effects" }));
      // decomposition: each network's isolated effect plus the coupling term
      const dec = t.decomposition ?? {};
      const entries = Object.entries(dec);
      const tot = entries.reduce((a, [, v]) => a + Math.abs(v), 0) || 1;
      if (entries.length) {
        const bar = entries.map(([k, v]) => {
          const meta = netNames.get(k);
          const color = k === "coupling" ? "#CDBFA8" : meta?.color ?? "#999";
          return `<div style="width:${((Math.abs(v) / tot) * 100).toFixed(1)}%;background:${color}" title="${esc(meta?.name ?? k)}: ${signed(v)}"></div>`;
        }).join("");
        box.insertAdjacentHTML("beforeend", `<div class="small muted" style="margin-top:4px">Decomposition at the horizon</div>
          <div class="decomp" role="img" aria-label="decomposition">${bar}</div>
          <div class="small">${entries.map(([k, v]) => `<span class="mono">${esc(k === "coupling" ? "coupling" : (netNames.get(k)?.name ?? k).split(" · ")[0])} ${signed(v)}</span>`).join(" · ")}</div>`);
      }
      tg.appendChild(box);
    }
    // network small multiples from the isolated predictions
    const nets = el.querySelector("#fc-nets");
    const iso = fv.isolated ?? {};
    for (const n of fv.networks ?? []) {
      const sums = iso[n.id] ?? {};
      const meta = netNames.get(n.id);
      const items = Object.entries(sums).slice(0, 4).map(([t, d]) => `<span class="mono small">${esc(t.split(".")[1] ?? t)} ${signed(d.q50)}</span>`).join(" · ");
      nets.insertAdjacentHTML("beforeend", `<div class="card" style="border-left:4px solid ${meta?.color}">
        <div class="small"><b>${esc(n.name ?? n.id)}</b> <span class="muted">${esc(n.kind)} · relevance ${fmt(n.relevance)}</span></div>
        <div>${items || `<span class="muted small">no isolated effects at the horizon</span>`}</div></div>`);
    }
    const ex = fv.explanation;
    const expl = el.querySelector("#fc-expl");
    if (ex) {
      expl.innerHTML = `<div class="explanation">${esc(ex.text)}</div>
        ${(ex.top_paths ?? []).map((p) => `<div class="top-path">${esc(p.shock_id)} → ${p.interaction_ids.map(esc).join(" → ")} → ${esc(p.target_id)} <span class="muted">(${fmt(p.share * 100, 0)}%)</span></div>`).join("")}
        ${(ex.assumptions ?? []).length ? `<div class="small muted">Assumptions: ${ex.assumptions.map(esc).join("; ")}</div>` : ""}`;
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

  on("show-forecast", show);
  on("open-forecast", openById);
  on("forecast", (fv) => { if (fv === null) { store.forecast = null; render(); } });
  render();
  return { show, openById };
}
