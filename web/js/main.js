// Boot, layout, and shortcuts (§13). The demo renders what the server sends; it never computes model results.
import { api, Stream } from "./api.js";
import { Player } from "./animator/player.js";
import { installDrawTool } from "./graph/draw-tool.js";
import { ribbonItems } from "./graph/fuzzy.js";
import { renderLegend } from "./graph/legend.js";
import { SvgRenderer } from "./graph/renderer.js";
import { initCaption } from "./panels/caption.js";
import { initDecisions } from "./panels/decisions.js";
import { initForecast } from "./panels/forecast.js";
import { initHypotheses } from "./panels/hypotheses.js";
import { initInbox } from "./panels/inbox.js";
import { initInspector } from "./panels/inspector.js";
import { initMemory } from "./panels/memory.js";
import { initPipeline } from "./panels/pipeline.js";
import { initReview } from "./panels/review.js";
import { initThesis } from "./panels/thesis.js";
import { initTimeline } from "./panels/timeline.js";
import { applyTrace, backToLive, emit, on, refreshGraph, scheduleRefresh, setStatus, store } from "./store.js";
import { errorText, esc, fmt, fmtTime, signed } from "./util.js";

const $ = (sel) => document.querySelector(sel);

// -- modal and toast ------------------------------------------------------------------------------
function openModal(markup, setup) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true">${markup}</div></div>`;
  const prevFocus = document.activeElement;
  const close = () => { root.innerHTML = ""; prevFocus?.focus?.(); };
  root.querySelector(".modal-backdrop").addEventListener("click", (ev) => { if (ev.target.classList.contains("modal-backdrop")) close(); });
  for (const b of root.querySelectorAll("[data-close]")) b.addEventListener("click", close);
  setup?.(root.querySelector(".modal"), close);
  root.querySelector(".modal input, .modal textarea, .modal select, .modal button:not([data-close])")?.focus();
  return close;
}

function toast(text, kind = "real") {
  const box = $("#toast");
  const t = document.createElement("div");
  t.className = `t ${kind}`;
  t.textContent = text;
  box.prepend(t);
  while (box.children.length > 4) box.lastChild.remove();
  setTimeout(() => t.remove(), kind === "err" ? 9000 : 4200);
}

// -- tabs -----------------------------------------------------------------------------------------
function activateTab(name) {
  for (const b of document.querySelectorAll("#right-tabs [data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const p of document.querySelectorAll("#right-body .tabpanel")) p.classList.toggle("active", p.id === `tab-${name}`);
  emit("tab", name);
}

// -- boot -----------------------------------------------------------------------------------------
async function boot() {
  renderLegend($("#legend"));
  const tooltip = $("#tooltip");

  const renderer = new SvgRenderer($("#canvas"), {
    onSelect: (sel) => select(sel),
    onHover: (ev, info) => hover(ev, info),
    onLevel: (lv) => setLevelButtons(lv),
    isDrawMode: () => store.settings.draw,
  });
  window.axelrod = { store, renderer, api };     // handy for debugging in the console

  const inspector = initInspector({ onSelect: (sel) => select(sel), focusNode: (id) => renderer.focusNode(id) });
  const review = initReview({ openModal, toast });
  initInbox();
  initCaption();
  initPipeline();
  const timeline = initTimeline();
  const memory = initMemory();
  initThesis({ toast });
  initForecast({ renderer, activateTab });
  const hyps = initHypotheses({ toast });
  const decisions = initDecisions({ toast });
  installDrawTool({ svgEl: $("#graph-svg"), rootSel: renderer.root, renderer, openModal, toast });

  function select(sel) {
    store.selection = sel;
    renderer.select(sel);
    inspector.show(sel);
    if (sel) activateTab("inspector");
  }

  function hover(ev, info) {
    if (!ev || !info) { tooltip.classList.add("hidden"); return; }
    const v = store.view;
    let html = "";
    if (info.kind === "entity") {
      const e = v?.entities.find((x) => x.id === info.id);
      if (e) html = `<b>${esc(e.name)}</b> <span class="muted">${esc(e.category_tags.join(" "))}</span><br>
        ${esc(e.kind)} · ${e.loose ? "in no superentity" : `in ${e.instance_ids.map(esc).join(", ")}`}<br>
        largest deviation z ${signed(e.deviation.z)}`;
    } else if (info.kind === "subentity") {
      const s = v?.subentities.find((x) => x.id === info.id);
      if (s) html = `<b>${esc(s.name)}</b><br><span class="mono">${esc(s.id)}</span><br>median ${fmt(s.summary.q50)} ${esc(s.unit)}
        (90%: ${fmt(s.summary.q05)} to ${fmt(s.summary.q95)})<br>z ${signed(s.z)}`;
    } else if (info.kind === "link") {
      const ls = (v?.links ?? []).filter((l) => info.ids.includes(l.id)).sort((a, b) => b.significance - a.significance);
      html = ls.slice(0, 4).map((l) => `<b>${esc(l.label)}</b> <span class="mono">${esc(l.id)}</span>${l.edge_type === "learned_causal" ? " <b>L</b>" : ""}<br>
        effect ${signed(l.effect)} · existence ${fmt(l.existence)} · significance ${fmt(l.significance)} · confidence ${fmt(l.confidence)}`).join("<hr>");
    } else if (info.kind === "hull") {
      html = info.hulls.map((h) => `<b>${esc(h.label)}</b><br>${esc(h.status)}${h.transient ? " (transient)" : ""} · support ${fmt(h.support)}
        · activation ${fmt(h.activation)}`).join("<hr>");
    } else if (info.kind === "frontier") {
      const f = info.entry;
      html = `<b>Co-movement</b> ${esc(f.id)}<br>${esc(f.earlier)} → ${esc(f.later)}<br>lag ${f.lag_steps} · sign ${f.sign > 0 ? "+" : "−"}
        · support ${fmt(f.support)} · ${esc(f.status)}`;
    }
    if (!html) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = html;
    tooltip.classList.remove("hidden");
    tooltip.style.left = `${Math.min(ev.clientX + 14, window.innerWidth - 330)}px`;
    tooltip.style.top = `${ev.clientY + 12}px`;
  }

  // -- graph, ribbons, ghosts ----------------------------------------------------------------------
  function extras() {
    const live = store.readOnlyVersion == null ? store.liveOps : new Map();
    const ghostEdges = [];
    const ghostSubs = [];
    if (store.readOnlyVersion == null) {
      for (const pv of store.proposals ?? []) {
        pv.proposal.event.ops.forEach((op, i) => {
          if (op.op === "add_interaction") {
            const s = op.source?.kind === "concrete" ? op.source.subentity_id : null;
            const t = op.target?.kind === "concrete" ? op.target.subentity_id : null;
            if (s && t) ghostEdges.push({ key: `${pv.proposal.id}:${i}`, a: s, b: t, hyp: pv.proposal.event.kind === "hypothetical" });
          } else if (op.op === "add_subentity") {
            ghostSubs.push({ id: String(op.temp_id).replace(/^new:/, "") });
          }
        });
      }
      for (const id of store.recentlyCreated) if (!ghostSubs.some((g) => g.id === id)) ghostSubs.push({ id });
    }
    return { ribbons: ribbonItems(store.view, live), ghostEdges, ghostSubs };
  }

  let lastLayoutView = null;
  on("graph", (g) => {
    if (!g) return;
    renderer.setData(g, extras());
    if (lastLayoutView == null) lastLayoutView = g.version;
    const dl = $("#search-list");
    dl.innerHTML = [...g.entities.map((e) => `<option value="${esc(e.name)}">${esc(e.id)}</option>`),
      ...g.subentities.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`)].join("");
    $("#sim-version").textContent = `v${g.version}${store.readOnlyVersion != null ? " (read-only)" : ""}`;
    if (store.selection) renderer.select(store.selection);
  });
  const refreshRibbons = () => renderer.setExtras(extras());
  on("proposals", refreshRibbons);
  on("fuzzy", refreshRibbons);
  on("highlight", (hl) => $("#btn-clear").classList.toggle("hidden", !hl));

  // -- status and toolbar ----------------------------------------------------------------------------
  on("status", (st) => {
    if (!st) return;
    $("#sim-time").textContent = fmtTime(st.sim_time);
    if (store.readOnlyVersion == null) $("#sim-version").textContent = `v${st.version}`;
    $("#step-label").textContent = `step ${st.step_index}/${st.total_steps}`;
    const chip = $("#sim-state");
    chip.dataset.state = st.state;
    chip.textContent = st.state.replace("_", " ");
    const playing = st.state === "running";
    const play = $("#btn-play");
    play.textContent = playing ? "❚❚ Pause" : "▶ Play";
    play.setAttribute("aria-pressed", String(playing));
    $("#btn-step").disabled = st.state === "done" || playing;
    if (st.error) toast(`Scenario error: ${st.error}`, "err");
  });

  async function guarded(fn) {
    try { return await fn(); } catch (err) { toast(errorText(err), "err"); return null; }
  }

  const doStep = () => guarded(async () => { const r = await api.step(); scheduleRefresh(100); return r; });
  const doPlay = () => guarded(async () => {
    if (store.status?.state === "running") setStatus(await api.pause());
    else setStatus(await api.play());
  });

  $("#btn-step").addEventListener("click", doStep);
  $("#btn-play").addEventListener("click", doPlay);
  $("#btn-back").addEventListener("click", () => timeline.stepBack());
  $("#btn-load").addEventListener("click", () => guarded(async () => {
    const st = await api.load($("#scenario-select").value, true);
    setStatus(st);
    backToLive();
    await refreshGraph();
    renderer.fit();
  }));
  $("#speed").addEventListener("change", (ev) => { store.settings.speed = +ev.target.value; player.setSpeed(store.settings.speed); });
  $("#review-policy").addEventListener("change", (ev) => guarded(async () => {
    const cfg = await api.setReviewPolicy(ev.target.value);
    toast(`Review policy: ${cfg.review_policy}`);
  }));
  $("#btn-motion").addEventListener("click", () => setReducedMotion(!store.settings.reducedMotion));
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setReducedMotion(true);

  function setReducedMotion(on_) {
    store.settings.reducedMotion = on_;
    document.body.classList.toggle("reduced-motion", on_);
    $("#btn-motion").setAttribute("aria-pressed", String(on_));
    renderer.setOptions({ reducedMotion: on_ });
  }

  // canvas toolbar
  const levelButtons = { super: $("#lvl-super"), entity: $("#lvl-entity"), sub: $("#lvl-sub") };
  function setLevelButtons(lv) {
    store.settings.level = lv;
    for (const [k, b] of Object.entries(levelButtons)) b.setAttribute("aria-pressed", String(k === lv));
  }
  for (const [k, b] of Object.entries(levelButtons)) b.addEventListener("click", () => renderer.setLevel(k, true));
  $("#btn-fit").addEventListener("click", () => renderer.fit());
  const setDraw = (on_) => {
    store.settings.draw = on_;
    $("#btn-draw").setAttribute("aria-pressed", String(on_));
    $("#canvas").classList.toggle("draw-mode", on_);
    if (on_) toast("Draw mode: drag from a subentity, entity, or hull to another.");
  };
  $("#btn-draw").addEventListener("click", () => setDraw(!store.settings.draw));
  const setLayout = (mode) => {
    store.settings.layout = mode;
    $("#layout-gravity").setAttribute("aria-pressed", String(mode === "gravity"));
    $("#layout-figure1").setAttribute("aria-pressed", String(mode === "figure1"));
    renderer.setLayoutMode(mode);
    setTimeout(() => renderer.fit(), 60);
  };
  $("#layout-gravity").addEventListener("click", () => setLayout("gravity"));
  $("#layout-figure1").addEventListener("click", () => setLayout("figure1"));
  $("#btn-category").addEventListener("click", () => {
    store.settings.groupByCategory = !store.settings.groupByCategory;
    $("#btn-category").setAttribute("aria-pressed", String(store.settings.groupByCategory));
    renderer.setOptions({ groupByCategory: store.settings.groupByCategory });
  });
  $("#btn-fig1links").addEventListener("click", () => {
    store.settings.figure1LinksOnly = !store.settings.figure1LinksOnly;
    $("#btn-fig1links").setAttribute("aria-pressed", String(store.settings.figure1LinksOnly));
    renderer.setOptions({ figure1LinksOnly: store.settings.figure1LinksOnly });
  });
  $("#btn-clear").addEventListener("click", () => {
    store.highlight = null;
    renderer.setHighlight(null);
    renderer.clearHalos();
    emit("highlight", null);
  });
  $("#search").addEventListener("change", (ev) => {
    const q = ev.target.value.trim().toLowerCase();
    if (!q) return;
    const v = store.view;
    const hit = v.entities.find((e) => e.id === q || e.name.toLowerCase() === q)
      ?? v.subentities.find((s) => s.id === q || s.name.toLowerCase() === q)
      ?? v.entities.find((e) => e.name.toLowerCase().includes(q))
      ?? v.subentities.find((s) => s.name.toLowerCase().includes(q) || s.id.includes(q));
    if (hit) {
      if (hit.entity_id) renderer.setLevel("sub", true);
      setTimeout(() => renderer.focusNode(hit.id), hit.entity_id ? 500 : 0);
    } else toast(`No entity or subentity matches “${q}”.`, "err");
  });
  for (const b of document.querySelectorAll("#right-tabs [data-tab]")) b.addEventListener("click", () => activateTab(b.dataset.tab));
  on("tab", (name) => {
    if (name === "hypotheses") hyps.render();
    if (name === "decisions") decisions.render();
  });

  // -- keyboard (§13.8) -------------------------------------------------------------------------------
  document.addEventListener("keydown", (ev) => {
    const typing = ev.target.closest?.("input, textarea, select, [contenteditable]");
    if (ev.key === "Escape") {
      if ($("#modal-root").innerHTML) { $("#modal-root").innerHTML = ""; return; }
      if (memory.isOpen()) { memory.close(); return; }
      if (store.settings.draw) { setDraw(false); return; }
      if (store.readOnlyVersion != null) { backToLive(); return; }
      select(null);
      return;
    }
    if (typing || $("#modal-root").innerHTML) return;
    if (ev.key === " ") { ev.preventDefault(); doPlay(); }
    else if (ev.key === "ArrowRight" && ev.shiftKey) { ev.preventDefault(); timeline.stepForward(); }
    else if (ev.key === "ArrowLeft" && ev.shiftKey) { ev.preventDefault(); timeline.stepBack(); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); doStep(); }
    else if (ev.key === "1") renderer.setLevel("super", true);
    else if (ev.key === "2") renderer.setLevel("entity", true);
    else if (ev.key === "3") renderer.setLevel("sub", true);
    else if (ev.key === "f" || ev.key === "F") renderer.fit();
    else if (ev.key === "d" || ev.key === "D") setDraw(!store.settings.draw);
    else if (ev.key === "/") { ev.preventDefault(); $("#search").focus(); }
    else if (ev.key === "a" || ev.key === "A") review.approveFocused();
    else if (ev.key === "r" || ev.key === "R") review.rejectFocused();
  });

  // -- data ---------------------------------------------------------------------------------------------
  const player = new Player({ renderer, toast, refresh: () => scheduleRefresh(150), refreshRibbons });
  window.axelrod.player = player;

  const [layout, scenarios, cfg] = await Promise.all([
    api.layout().catch(() => null), api.scenarios().catch(() => []), api.config().catch(() => null)]);
  store.layout = layout;
  renderer.setLayout(layout);
  store.scenarios = scenarios;
  $("#scenario-select").innerHTML = scenarios.map((s) => `<option value="${esc(s.id)}">${esc(s.title)}</option>`).join("");
  if (cfg) $("#review-policy").value = cfg.review_policy;

  // the trace so far fills the inbox, timeline, and caption without animating
  try {
    const evs = await api.trace(0);
    for (const ev of evs) applyTrace(ev);
  } catch (err) { console.warn("no trace backfill", err); }
  timeline.backfill();
  setStatus(await api.status().catch(() => null));
  await refreshGraph();

  const stream = new Stream({
    sinceSeq: () => store.lastSeq,
    onTrace: (ev) => player.push(ev),
    onStatus: (st) => setStatus(st),
    onOpen: () => document.body.classList.remove("offline"),
    onClose: () => document.body.classList.add("offline"),
  });
  stream.connect();
  setTimeout(() => renderer.fit(0), 400);
}

boot().catch((err) => {
  console.error(err);
  const c = document.querySelector("#caption .text");
  if (c) c.textContent = `Could not start the demo: ${err.message}`;
});
