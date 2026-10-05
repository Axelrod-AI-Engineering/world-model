// Pipeline strip (§13.6): phases light up as trace events arrive. Clicking a phase filters the timeline.
import { emit, on, store } from "../store.js";

const LEARN = ["translate", "refine", "review", "parse", "classify", "recall", "prefill", "analyze", "fold", "generalize", "frontier"];
const PERF = ["isolate", "predict", "couple", "unify"];

export function initPipeline() {
  const el = document.getElementById("pipeline");
  const timers = new Map();
  const phaseHtml = (p, cls) => `<button class="phase ${cls}" data-phase="${p}" title="Filter the timeline to ${p}">${p}</button>`;
  el.innerHTML = `<span class="label">PIPELINE</span>
    ${LEARN.map((p) => phaseHtml(p, "learn")).join('<span class="arrow">→</span>')}
    <span class="divider"></span>
    ${PERF.map((p) => phaseHtml(p, "perf")).join('<span class="arrow">→</span>')}`;
  for (const b of el.querySelectorAll("[data-phase]")) {
    b.addEventListener("click", () => {
      store.phaseFilter = store.phaseFilter === b.dataset.phase ? null : b.dataset.phase;
      for (const x of el.querySelectorAll("[data-phase]")) x.classList.toggle("filter", x.dataset.phase === store.phaseFilter);
      emit("phase-filter", store.phaseFilter);
    });
  }
  const alias = { ingest: "translate", abduce: "frontier", explain: "analyze", consolidate: "generalize", read_out: "unify" };
  on("phase", (phase) => {
    const p = alias[phase] ?? phase;
    const b = el.querySelector(`[data-phase="${p}"]`);
    if (!b) return;
    b.classList.add("active");
    clearTimeout(timers.get(p));
    timers.set(p, setTimeout(() => b.classList.remove("active"), store.settings.reducedMotion ? 300 : 900));
  });
}
