// Thesis composer (§13.6): a question; shocks (a subentity picker, the change, its mode, and persistence);
// optional interventions (a decision variable, hold or change, and a window); a horizon; and targets.
// "Run" poses the thesis and produces a forecast.
import { api } from "../api.js";
import { emit, on, store } from "../store.js";
import { errorText, esc } from "../util.js";

const DEFAULT_TARGETS = ["inflation.headline_cpi", "interest_rates.us_policy_rate", "credit_availability.credit_growth",
  "business_investment.capex_growth", "asset_prices.equity_index", "confidence.consumer_confidence"];

export function initThesis({ toast }) {
  const el = document.getElementById("tab-thesis");
  let shocks = [{ sid: "resources_energy.oil_price", delta: 1.0, mode: "relative", persistence: "step" }];
  let interventions = [];
  let targets = new Set(DEFAULT_TARGETS);
  let busy = false;
  let counter = 1;

  function subOptions() {
    return (store.graph?.subentities ?? []).map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  }

  function render() {
    const subs = store.graph?.subentities ?? [];
    const decisions = subs.filter((s) => s.decision_variable);
    el.innerHTML = `
      <h3>Pose a thesis</h3>
      <p class="small muted">A question becomes a hypothetical event. Shocks are applied, interventions hold a decision
        variable (do), and the engine forecasts the targets.</p>
      <div class="section"><label class="small" for="th-q">Question</label>
        <div class="row"><input id="th-q" type="text" style="flex:1" value="What if oil prices doubled next quarter?">
          <button id="th-ask" title="Translate the question with the template translator">Ask</button></div></div>
      <datalist id="sub-list">${subOptions()}</datalist>
      <div class="section"><h4>Shocks</h4>
        ${shocks.map((s, i) => `<div class="shock-row" data-i="${i}">
          <input type="text" list="sub-list" data-f="sid" value="${esc(s.sid)}" aria-label="Subentity">
          <input type="number" step="0.05" data-f="delta" value="${s.delta}" aria-label="Change">
          <select data-f="mode" aria-label="Mode">${["relative", "absolute", "standardized"].map((m) => `<option ${m === s.mode ? "selected" : ""}>${m}</option>`).join("")}</select>
          <select data-f="persistence" aria-label="Persistence">${["step", "pulse"].map((m) => `<option ${m === s.persistence ? "selected" : ""}>${m}</option>`).join("")}</select>
          <button data-del="${i}" aria-label="Remove shock">✕</button></div>`).join("")}
        <button id="th-add">+ shock</button>
        <label class="small" style="margin-left:8px">starts in <input id="th-start" type="number" value="12" style="width:52px"> weeks</label></div>
      <div class="section"><h4>Interventions</h4>
        ${interventions.map((v, i) => `<div class="shock-row" data-v="${i}" style="grid-template-columns: 1fr 70px 70px 64px 22px">
          <select data-f="sid" aria-label="Decision variable">${decisions.map((d) => `<option value="${esc(d.id)}" ${d.id === v.sid ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>
          <select data-f="kind" aria-label="Hold or change"><option ${v.kind === "hold" ? "selected" : ""}>hold</option><option ${v.kind === "change" ? "selected" : ""}>change</option></select>
          <input type="number" step="0.25" data-f="delta" value="${v.delta}" ${v.kind === "hold" ? "disabled" : ""} aria-label="Change">
          <input type="number" data-f="window" value="${v.window}" aria-label="Window (days)" title="window (days)">
          <button data-vdel="${i}" aria-label="Remove intervention">✕</button></div>`).join("")}
        <button id="th-addv" ${decisions.length ? "" : "disabled"}>+ intervention</button></div>
      <div class="section"><div class="form-grid"><label for="th-h">Horizon (days)</label><input id="th-h" type="number" value="270"></div></div>
      <div class="section"><h4>Targets</h4><div class="targets">${subs.map((s) => `<label><input type="checkbox" data-t="${esc(s.id)}" ${targets.has(s.id) ? "checked" : ""}> ${esc(s.name)}</label>`).join("")}</div></div>
      <div class="row"><button class="hyp" id="th-run">${busy ? "Running…" : "Run"}</button><span class="error" id="th-err"></span></div>`;
    for (const row of el.querySelectorAll("[data-i]")) {
      const i = +row.dataset.i;
      for (const inp of row.querySelectorAll("[data-f]")) {
        inp.addEventListener("change", () => { shocks[i][inp.dataset.f] = inp.type === "number" ? +inp.value : inp.value; });
      }
    }
    for (const row of el.querySelectorAll("[data-v]")) {
      const i = +row.dataset.v;
      for (const inp of row.querySelectorAll("[data-f]")) {
        inp.addEventListener("change", () => {
          interventions[i][inp.dataset.f] = inp.type === "number" ? +inp.value : inp.value;
          if (inp.dataset.f === "kind") render();
        });
      }
    }
    for (const b of el.querySelectorAll("[data-del]")) b.addEventListener("click", () => { shocks.splice(+b.dataset.del, 1); render(); });
    for (const b of el.querySelectorAll("[data-vdel]")) b.addEventListener("click", () => { interventions.splice(+b.dataset.vdel, 1); render(); });
    el.querySelector("#th-add").addEventListener("click", () => { shocks.push({ sid: "", delta: 1, mode: "standardized", persistence: "step" }); render(); });
    el.querySelector("#th-addv")?.addEventListener("click", () => {
      interventions.push({ sid: decisions[0]?.id, kind: "hold", delta: 0, window: 270 });
      render();
    });
    for (const c of el.querySelectorAll("[data-t]")) {
      c.addEventListener("change", () => { if (c.checked) targets.add(c.dataset.t); else targets.delete(c.dataset.t); });
    }
    el.querySelector("#th-run").addEventListener("click", run);
    el.querySelector("#th-ask").addEventListener("click", ask);
  }

  function nowIso() {
    return store.status?.sim_time ?? store.graph?.sim_time ?? new Date().toISOString();
  }

  async function run() {
    if (busy) return;
    const err = el.querySelector("#th-err");
    const now = new Date(nowIso());
    const start = new Date(now.getTime() + (+el.querySelector("#th-start").value || 0) * 7 * 86400000);
    const ops = shocks.filter((s) => s.sid).map((s) => ({
      op: "change_value", target: { kind: "concrete", subentity_id: s.sid }, delta: +s.delta, mode: s.mode,
      persistence: s.persistence, at: start.toISOString() }));
    for (const v of interventions) {
      if (!v.sid) continue;
      ops.push({ op: "change_value", target: { kind: "concrete", subentity_id: v.sid }, delta: v.kind === "hold" ? 0 : +v.delta,
                 mode: "absolute", persistence: "step", intervention: true, window_days: +v.window || 90, at: now.toISOString() });
    }
    const id = `T-UI${counter++}`;
    const thesis = {
      id, question: el.querySelector("#th-q").value || "Custom thesis", mode: "scaffolded",
      horizon_days: +el.querySelector("#th-h").value || 182, targets: [...targets],
      event: { id: `GUE-${id}`, kind: "hypothetical", event_type: ops.length ? "supply_shock" : null,
               occurred_at: start.toISOString(), recorded_at: now.toISOString(), produced_by: "human", ops },
    };
    busy = true;
    err.textContent = "";
    el.querySelector("#th-run").textContent = "Running…";
    try {
      const fv = await api.poseThesis(thesis);
      emit("show-forecast", fv);
      toast(`Forecast ${fv.forecast.id} ready.`, "hyp");
    } catch (e) {
      err.textContent = errorText(e);
    } finally {
      busy = false;
      const b = el.querySelector("#th-run");
      if (b) b.textContent = "Run";
    }
  }

  async function ask() {
    const err = el.querySelector("#th-err");
    err.textContent = "";
    try {
      const fv = await api.ask(el.querySelector("#th-q").value, +el.querySelector("#th-h").value || 182);
      emit("show-forecast", fv);
    } catch (e) {
      err.textContent = errorText(e);
    }
  }

  on("graph", () => { if (!el.querySelector("#th-q") || !document.activeElement?.closest?.("#tab-thesis")) render(); });
  render();
  return { render };
}
