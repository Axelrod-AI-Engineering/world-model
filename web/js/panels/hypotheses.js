// Hypotheses board (§13.6): sorted by current VOI, with a decay sparkline, a kind badge, and the
// probability. Decision hypotheses have "Pose as thesis"; all have "Mark supported" and "Mark refuted".
import { api } from "../api.js";
import { sparkline } from "../charts/sparkline.js";
import { emit, on } from "../store.js";
import { errorText, esc, fmt } from "../util.js";

// DECISION (low friction without clutter): each hypothesis is one line (statement, p, VOI) that opens in
// place to its decay and actions; the board shows the top 10 by value and grows 15 at a time.
const FIRST = 10;
const MORE = 15;

export function initHypotheses({ toast }) {
  const el = document.getElementById("tab-hypotheses");
  let timer = null;
  let shown = FIRST;
  const opened = new Set();

  async function render() {
    let hs = [];
    let fcs = [];
    try { [hs, fcs] = await Promise.all([api.hypotheses(), api.forecasts()]); } catch { return; }
    const theses = [...new Map(fcs.map((f) => [f.thesis_id, f])).values()];
    const total = hs.length;
    const list = hs.slice(0, shown);
    el.innerHTML = `<div class="group-label">Hypotheses</div><h3>What the model is unsure of</h3>
      <p class="small muted">Links it suspects and decisions actors might take, sorted by value of information: how much the
        forecasts you care about would move if it held, times how unsure the model is.</p>
      ${list.length ? "" : "<p class='muted small'>No open hypotheses.</p>"}
      ${list.map((v) => {
        const h = v.hypothesis;
        return `<details class="hrow" data-h="${esc(h.id)}" ${opened.has(h.id) ? "open" : ""}>
          <summary><span class="badge ${h.kind === "entity_decision" ? "init" : "front"}" title="${esc(h.kind)}">${h.kind === "entity_decision" ? "decision" : h.comovement_id ? "co-movement" : "link"}</span>
            <span class="st">${esc(h.statement)}</span>
            <span class="mono small" title="probability · current value of information">p ${fmt(h.probability)} · ${fmt(v.current_value, 2)}</span></summary>
          <div class="hbody"><div class="small faint mono">${esc(h.id)} · ${esc(h.status)}</div>
            <div class="spark"></div>
            <div class="row">
              ${h.kind === "entity_decision" ? `<select data-base aria-label="Base thesis"><option value="">(no base thesis)</option>
                ${theses.filter((t) => !String(t.thesis_id).includes("+")).map((t) => `<option value="${esc(t.thesis_id)}">${esc(t.thesis_id)}</option>`).join("")}</select>
                <button class="hyp" data-act="pose">Pose as thesis</button>` : ""}
              <button data-act="supported">Mark supported</button><button data-act="refuted">Mark refuted</button>
            </div></div></details>`;
      }).join("")}
      ${total > shown ? `<button class="ghost small" id="hy-more">+ ${Math.min(MORE, total - shown)} more of ${total - shown}</button>` : ""}`;
    el.querySelector("#hy-more")?.addEventListener("click", () => { shown += MORE; render(); });
    for (const v of list) {
      const row = el.querySelector(`[data-h="${CSS.escape(v.hypothesis.id)}"]`);
      const fill = () => {
        const sp = row.querySelector(".spark");
        if (sp.childElementCount) return;
        sp.appendChild(sparkline(v.decay_points, { value: (p) => p.value, width: 300, height: 34, label: "decay of the current value" }));
      };
      if (row.open) fill();
      row.addEventListener("toggle", () => {
        if (row.open) { opened.add(v.hypothesis.id); fill(); } else opened.delete(v.hypothesis.id);
      });
      row.querySelector("[data-act=pose]")?.addEventListener("click", async () => {
        const base = row.querySelector("[data-base]")?.value || null;
        try {
          const fv = await api.poseHypothesis(v.hypothesis.id, base);
          emit("show-forecast", fv);
          toast(`Posed ${fv.forecast.thesis_id}.`, "hyp");
        } catch (err) { toast(errorText(err), "err"); }
      });
      for (const st of ["supported", "refuted"]) {
        row.querySelector(`[data-act=${st}]`).addEventListener("click", async () => {
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
