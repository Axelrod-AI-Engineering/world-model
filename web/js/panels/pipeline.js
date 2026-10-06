// Pipeline strip (§13.6): phases light up as trace events arrive; clicking a phase filters the timeline.
// DECISION: the strip folds into one "now: <phase>" indicator in the bottom bar and opens on click, so the
// first view carries no row of nineteen chips.
import { emit, on, store } from "../store.js";

const LEARN = [["collect", "collect"], ["translate", "translate"], ["refine", "refine"], ["review", "review"],
  ["daily", "predict"], ["parse", "parse"], ["classify", "classify"], ["recall", "recall"], ["prefill", "prefill"],
  ["analyze", "analyze"], ["fold", "fold"], ["generalize", "generalize"], ["frontier", "frontier"], ["abduce", "abduce"],
  ["consolidate", "consolidate"]];
const PERF = [["isolate", "isolate"], ["predict", "predict"], ["couple", "couple"], ["unify", "unify"]];
const ALIAS = { ingest: "translate", update: "collect", explain: "unify", read_out: "unify", init: "consolidate" };
const PERF_SET = new Set(PERF.map(([p]) => p));

export function initPipeline() {
  const el = document.getElementById("pipeline");
  const btn = document.getElementById("btn-activity");
  const now = document.getElementById("phase-now");
  const timers = new Map();
  let idleTimer = null;
  const chip = ([p, label], cls) => `<button class="phase ${cls}" data-phase="${p}" title="Filter the timeline to ${label}">${label}</button>`;
  el.innerHTML = `<span class="label">LEARNING</span>
    ${LEARN.map((p) => chip(p, "learn")).join('<span class="arrow">→</span>')}
    <span class="divider"></span><span class="label">PERFORMANCE</span>
    ${PERF.map((p) => chip(p, "perf")).join('<span class="arrow">→</span>')}`;
  for (const b of el.querySelectorAll("[data-phase]")) {
    b.addEventListener("click", () => {
      store.phaseFilter = store.phaseFilter === b.dataset.phase ? null : b.dataset.phase;
      for (const x of el.querySelectorAll("[data-phase]")) x.classList.toggle("filter", x.dataset.phase === store.phaseFilter);
      emit("phase-filter", store.phaseFilter);
    });
  }
  const setOpen = (open) => {
    el.classList.toggle("hidden", !open);
    btn.setAttribute("aria-expanded", String(open));
  };
  btn.addEventListener("click", () => setOpen(el.classList.contains("hidden")));
  on("phase", (phase) => {
    if (!phase || phase === "scenario") return;
    const p = ALIAS[phase] ?? phase;
    const label = (LEARN.find(([x]) => x === p) ?? PERF.find(([x]) => x === p))?.[1] ?? p;
    now.textContent = label;
    btn.classList.add("busy");
    btn.classList.toggle("perf", PERF_SET.has(p));
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { btn.classList.remove("busy", "perf"); now.textContent = "idle"; }, 1600);
    const b = el.querySelector(`[data-phase="${p}"]`);
    if (!b) return;
    b.classList.add("active");
    clearTimeout(timers.get(p));
    timers.set(p, setTimeout(() => b.classList.remove("active"), store.settings.reducedMotion ? 300 : 900));
  });
  return { setOpen };
}
