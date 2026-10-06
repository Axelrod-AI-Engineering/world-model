// Draw tool (§13.5): drag from a subentity, entity, or hull to another to propose an edge.
// A subentity gives a concrete end; an entity an abstract end with its entity_id; a hull an abstract
// end whose candidate_entity_ids are the hull's members, so the refiner ranks them.
/* global d3 */
import { api } from "../api.js";
import { store } from "../store.js";

function endFromTarget(el, view) {
  const node = el?.closest?.("[data-kind]");
  if (node) {
    const kind = node.getAttribute("data-kind");
    const id = node.getAttribute("data-id");
    if (kind === "subentity") return { spec: { kind: "concrete", subentity_id: id }, label: id };
    if (kind === "entity") return { spec: { kind: "abstract", entity_id: id }, label: id };
  }
  const hull = el?.closest?.("g.hull");
  if (hull) {
    const iid = hull.getAttribute("data-instance");
    const h = view?.hulls?.find((x) => x.id === iid);
    if (h) return { spec: { kind: "abstract", candidate_entity_ids: [...h.members] }, label: h.label };
  }
  return null;
}

export function installDrawTool({ svgEl, rootSel, renderer, openModal, toast }) {
  let start = null;
  let line = null;
  let attach = null;      // set when the Update dialog asked for a drawn edge to attach to its request
  const pointer = (ev) => d3.pointer(ev, rootSel.node());

  svgEl.addEventListener("pointerdown", (ev) => {
    if (!store.settings.draw || ev.button !== 0) return;
    const end = endFromTarget(ev.target, store.view);
    if (!end) return;
    ev.preventDefault();
    ev.stopPropagation();
    const [x, y] = pointer(ev);
    start = { end, x, y };
    line = rootSel.append("line").attr("class", "draw-line").attr("x1", x).attr("y1", y).attr("x2", x).attr("y2", y);
  }, true);

  window.addEventListener("pointermove", (ev) => {
    if (!start || !line) return;
    const [x, y] = pointer(ev);
    line.attr("x2", x).attr("y2", y);
  });

  window.addEventListener("pointerup", (ev) => {
    if (!start) return;
    const from = start.end;
    start = null;
    line?.remove();
    line = null;
    const to = endFromTarget(document.elementFromPoint(ev.clientX, ev.clientY), store.view);
    if (!to) return;
    openForm(from, to);
  });

  function openForm(from, to) {
    openModal(`
      <h3>Propose an edge</h3>
      <p class="small muted">${from.label} → ${to.label}. The refiner ranks abstract ends; the proposal goes to review.</p>
      <div class="form-grid">
        <label for="dt-label">Label</label><input id="dt-label" type="text" value="drives" required>
        <label for="dt-pol">Polarity</label>
        <select id="dt-pol"><option value="1">+ raises</option><option value="-1">− lowers</option></select>
        <label for="dt-effect">Effect (optional)</label><input id="dt-effect" type="number" step="0.05" placeholder="from the generalization">
        <label for="dt-delay">Delay, lag, duration (days)</label>
        <div class="row"><input id="dt-delay" type="number" style="width:64px" placeholder="delay">
          <input id="dt-lag" type="number" style="width:64px" placeholder="lag">
          <input id="dt-dur" type="number" style="width:76px" placeholder="duration"></div>
      </div>
      <div class="error" id="dt-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="primary" id="dt-submit">Submit proposal</button></div>`,
    (root, close) => {
      root.querySelector("#dt-submit").addEventListener("click", async () => {
        const label = root.querySelector("#dt-label").value.trim() || "drives";
        const polarity = +root.querySelector("#dt-pol").value;
        const effect = root.querySelector("#dt-effect").value;
        const delay = root.querySelector("#dt-delay").value;
        const lag = root.querySelector("#dt-lag").value;
        const dur = root.querySelector("#dt-dur").value;
        const op = { op: "add_interaction", source: from.spec, target: to.spec, label, polarity };
        if (effect !== "" || delay !== "" || lag !== "") {
          op.dynamics = {
            effect: { family: "gaussian", mu: effect === "" ? 0.3 * polarity : +effect, sigma: 0.2 },
            kernel: { delay_days: delay === "" ? 14 : +delay, lag_days: lag === "" ? 30 : +lag,
                      duration_days: dur === "" ? null : +dur },
          };
        }
        const now = store.status?.sim_time ?? new Date().toISOString();
        const ev = { id: `GUE-DRAW-${Date.now()}`, kind: "real", event_type: "hand_drawn", occurred_at: now,
                     recorded_at: now, produced_by: "human", ops: [op] };
        if (attach) {
          const fn = attach;
          attach = null;
          close();
          toast("Drawn edge attached to the update.");
          fn(ev);
          return;
        }
        try {
          const pv = await api.submitGraphUpdate(ev);
          toast(`Proposal ${pv.proposal.id} submitted (${pv.proposal.status}).`);
          close();
        } catch (err) {
          root.querySelector("#dt-err").textContent = err.message + (err.body?.detail && typeof err.body.detail !== "string"
            ? `\n${JSON.stringify(err.body.detail, null, 1)}` : "");
        }
      });
    });
  }
  return {
    cancel: () => { start = null; line?.remove(); line = null; },
    // the next drawn edge goes to `fn` (the Update dialog) instead of straight to review
    armAttach: (fn) => { attach = fn; },
    disarm: () => { attach = null; },
  };
}
