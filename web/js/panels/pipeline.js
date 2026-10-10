// Pipeline strip (§13.6): phases light up as trace events arrive; clicking a phase filters the timeline.
// DECISION: the strip folds into one "now: <phase>" indicator in the bottom bar and opens on click, so the
// first view carries no row of nineteen chips.
import { api } from "../api.js";
import { emit, on, store } from "../store.js";
import { esc } from "../util.js";

// learning has two processes (restructure): working memory first, then long-term memory
const LEARN_WM = [["collect", "collect"], ["translate", "translate"], ["refine", "refine"], ["review", "review"],
  ["daily", "predict"], ["parse", "parse"], ["classify", "classify"], ["recall", "recall"], ["prefill", "prefill"],
  ["analyze", "analyze"], ["fold", "fold"]];
const LEARN_LTM = [["generalize", "generalize"], ["frontier", "frontier"], ["abduce", "abduce"],
  ["consolidate", "consolidate"]];
const LEARN = [...LEARN_WM, ...LEARN_LTM];
const PERF = [["isolate", "isolate"], ["predict", "predict"], ["couple", "couple"], ["unify", "unify"]];
const ALIAS = { ingest: "translate", update: "collect", explain: "unify", read_out: "unify", init: "consolidate" };
const PERF_SET = new Set(PERF.map(([p]) => p));

export function initPipeline({ onTask } = {}) {
  const el = document.getElementById("pipeline");
  const btn = document.getElementById("btn-activity");
  const now = document.getElementById("phase-now");
  const timers = new Map();
  let idleTimer = null;
  const chip = ([p, label], cls) => `<button class="phase ${cls}" data-phase="${p}" title="Filter the timeline to ${label}">${label}</button>`;
  el.innerHTML = `<span class="label" title="Learning of working memory: one vetted event into the current state">LEARNING · WORKING MEMORY</span>
    ${LEARN_WM.map((p) => chip(p, "learn")).join('<span class="arrow">→</span>')}
    <span class="divider"></span><span class="label" title="Learning of long-term memory: what generalizes across time and entities">LEARNING · LONG-TERM MEMORY</span>
    ${LEARN_LTM.map((p) => chip(p, "learn")).join('<span class="arrow">→</span>')}
    <span class="divider"></span><span class="label" title="Inference: a thesis on a branch of a committed version; nothing is learned">INFERENCE</span>
    ${PERF.map((p) => chip(p, "perf")).join('<span class="arrow">→</span>')}
    <div class="lt-box" aria-label="Learning tasks"></div>`;
  // the learning tasks at a glance (addition): what each has learned so far, with a way to see it
  const ltBox = el.querySelector(".lt-box");
  async function loadTasks() {
    let tasks = [];
    try { tasks = await api.learningTasks(); } catch { ltBox.innerHTML = ""; return; }
    ltBox.innerHTML = `<div class="label">LEARNING TASKS</div><div class="lt-list">${tasks.map((t, i) => `<div class="lt" data-phase-of="${esc(t.phase)}">
        <div class="lt-head"><b>${esc(t.name)}</b>${t.target ? `<button class="ghost small" data-lt="${i}" title="${esc(t.target_label ?? "")}">Show me ▸</button>` : ""}</div>
        <div class="small muted">${esc(t.what)}</div><div class="small">${esc(t.count)}</div></div>`).join("")}</div>`;
    for (const b of ltBox.querySelectorAll("[data-lt]")) b.addEventListener("click", () => onTask?.(tasks[+b.dataset.lt].target));
  }
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
    if (open) loadTasks();
  };
  btn.addEventListener("click", () => setOpen(el.classList.contains("hidden")));
  on("phase", (phase) => {
    if (!phase || phase === "scenario") return;
    const p = ALIAS[phase] ?? phase;
    now.textContent = (LEARN.find(([x]) => x === p) ?? PERF.find(([x]) => x === p))?.[1] ?? p;
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
