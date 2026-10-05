// Hypotheses board (§13.6): sorted by current VOI, with a decay sparkline, a kind badge, and the
// probability. Decision hypotheses have "Pose as thesis"; all have "Mark supported" and "Mark refuted".
import { api } from "../api.js";
import { sparkline } from "../charts/sparkline.js";
import { emit, on, store } from "../store.js";
import { errorText, esc, fmt } from "../util.js";

const SHOWN = 25;

export function initHypotheses({ toast }) {
  const el = document.getElementById("tab-hypotheses");
  let timer = null;
  let showAll = false;

  async function render() {
    let hs = [];
    let fcs = [];
    try { [hs, fcs] = await Promise.all([api.hypotheses(), api.forecasts()]); } catch { return; }
    const theses = [...new Map(fcs.map((f) => [f.thesis_id, f])).values()];
    const total = hs.length;
    if (!showAll) hs = hs.slice(0, SHOWN);
    el.innerHTML = `<h3>Hypotheses</h3><p class="small muted">Sorted by current value of information.
      ${total > SHOWN ? `Showing ${hs.length} of ${total}. <button class="small" id="hy-all">${showAll ? "Top " + SHOWN : "Show all"}</button>` : ""}</p>
      ${hs.length ? "" : "<p class='muted small'>No open hypotheses.</p>"}
      ${hs.map((v) => {
        const h = v.hypothesis;
        return `<div class="card" data-h="${esc(h.id)}">
          <div class="meta"><span class="badge ${h.kind === "entity_decision" ? "init" : "front"}">${esc(h.kind)}</span>
            <span class="mono">${esc(h.id)}</span><span class="badge">${esc(h.status)}</span><span class="spacer"></span>
            <span title="probability">p ${fmt(h.probability)}</span><span title="current value of information">VOI ${fmt(v.current_value, 3)}</span></div>
          <div class="title">${esc(h.statement)}</div>
          <div class="spark"></div>
          <div class="row">
            ${h.kind === "entity_decision" ? `<select data-base aria-label="Base thesis"><option value="">(no base thesis)</option>
              ${theses.filter((t) => !String(t.thesis_id).includes("+")).map((t) => `<option value="${esc(t.thesis_id)}">${esc(t.thesis_id)}</option>`).join("")}</select>
              <button class="hyp" data-act="pose">Pose as thesis</button>` : ""}
            <button data-act="supported">Mark supported</button><button data-act="refuted">Mark refuted</button>
          </div></div>`;
      }).join("")}`;
    el.querySelector("#hy-all")?.addEventListener("click", () => { showAll = !showAll; render(); });
    for (const v of hs) {
      const card = el.querySelector(`[data-h="${CSS.escape(v.hypothesis.id)}"]`);
      card.querySelector(".spark").appendChild(sparkline(v.decay_points, { value: (p) => p.value, width: 300, height: 34,
        label: "decay of the current value" }));
      card.querySelector("[data-act=pose]")?.addEventListener("click", async () => {
        const base = card.querySelector("[data-base]")?.value || null;
        try {
          const fv = await api.poseHypothesis(v.hypothesis.id, base);
          emit("show-forecast", fv);
          toast(`Posed ${fv.forecast.thesis_id}.`, "hyp");
        } catch (err) { toast(errorText(err), "err"); }
      });
      for (const st of ["supported", "refuted"]) {
        card.querySelector(`[data-act=${st}]`).addEventListener("click", async () => {
          try { await api.setHypothesisStatus(v.hypothesis.id, st); render(); } catch (err) { toast(errorText(err), "err"); }
        });
      }
    }
  }

  const later = () => { clearTimeout(timer); timer = setTimeout(render, 1200); };
  on("hypotheses", later);
  on("graph", later);
  return { render };
}
