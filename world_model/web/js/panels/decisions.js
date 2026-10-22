// Decisions panel (§13.6): recorded decisions with their agent, recommendation, cited forecasts, state
// version, review date, and outcome. "Trace" opens the cited forecasts and a read-only view of the state
// at the decision's version. "Resolve" scores a decision once its review date has passed.
import { api } from "../api.js";
import { names } from "../names.js";
import { emit, on, openVersion, store } from "../store.js";
import { errorText, esc, fmt, fmtDate } from "../util.js";

export function initDecisions({ toast }) {
  const el = document.getElementById("tab-decisions");

  async function render() {
    let ds = [];
    try { ds = await api.decisions(); } catch { return; }
    const now = new Date(store.status?.sim_time ?? Date.now());
    el.innerHTML = `<h3>Decisions</h3>
      ${ds.length ? "" : "<p class='muted small'>No decisions recorded yet. A decision records a recommendation made with forecasts in hand: it keeps the point-in-time world model state (its version) and the forecasts it cited, so it can be traced and scored once the outcome is known. The demo records one near its end.</p>"}
      ${ds.map((d) => `<div class="card" data-d="${esc(d.id)}">
        <div class="meta"><span class="mono">${esc(d.id)}</span><span>${esc(d.agent_id)}</span><span class="spacer"></span>
          <span class="badge ltm">v${d.state_version}</span></div>
        <div class="title">${names().proseHtml(d.recommendation)}</div>
        ${d.rationale ? `<div class="small muted">${names().proseHtml(d.rationale)}</div>` : ""}
        <div class="small">cites ${d.forecast_ids.map((f) => `<a href="#" data-fc="${esc(f)}">${esc(f)}</a>`).join(", ")}</div>
        <div class="small">review after ${fmtDate(d.review_after)}</div>
        ${d.outcome ? `<div class="small"><span class="badge eval">outcome</span> CRPS ${fmt(d.outcome.crps, 3)} · resolved ${fmtDate(d.outcome.resolved_at)}</div>` : ""}
        <div class="row"><button data-act="trace">Trace</button>
          <button data-act="resolve" ${d.outcome || new Date(d.review_after) > now ? "disabled" : ""}>Resolve</button></div>
        <div class="trace small"></div></div>`).join("")}`;
    for (const d of ds) {
      const card = el.querySelector(`[data-d="${CSS.escape(d.id)}"]`);
      for (const a of card.querySelectorAll("[data-fc]")) {
        a.addEventListener("click", (ev) => { ev.preventDefault(); emit("open-forecast", a.dataset.fc); });
      }
      card.querySelector("[data-act=trace]").addEventListener("click", async () => {
        try {
          const tr = await api.decisionTrace(d.id);
          card.querySelector(".trace").innerHTML = `<div>${tr.hash_verified ? "✓ the state hash at" : "✗ hash mismatch at"} v${d.state_version}
            <span class="mono muted">${esc(String(tr.state_hash_at_version).slice(0, 12))}</span></div>
            <div>${tr.forecasts.length} cited forecasts · ${tr.changes_since.length} change sets since</div>`;
          await openVersion(d.state_version);
        } catch (err) { toast(errorText(err), "err"); }
      });
      card.querySelector("[data-act=resolve]").addEventListener("click", async () => {
        try {
          const out = await api.resolveDecision(d.id);
          toast(`Resolved ${d.id}: CRPS ${fmt(out.crps, 3)}.`);
          render();
        } catch (err) { toast(errorText(err), "err"); }
      });
    }
  }

  on("decisions", render);
  on("status", () => { if (store.status?.state === "done") render(); });
  return { render };
}
