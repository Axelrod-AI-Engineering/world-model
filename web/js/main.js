// Boot, layout, and shortcuts (§13). The demo renders what the server sends; it never computes model results.
// DECISION: the first screen is the graph, a caption, and one row of controls; every panel opens on demand
// (selecting something opens the inspector, an update that needs you opens the review queue), and every
// per-node choice lives in the right-click menu.
import { api, Stream } from "./api.js";
import { Guide } from "./animator/guide.js";
import { Player } from "./animator/player.js";
import { installDrawTool } from "./graph/draw-tool.js";
import { ribbonItems } from "./graph/fuzzy.js";
import { paletteOf } from "./graph/hulls.js";
import { CATEGORY_NAMES } from "./graph/layouts.js";
import { closeMenu, menuOpen, openMenu } from "./graph/menu.js";
import { kinKey } from "./graph/model.js";
import { SvgRenderer } from "./graph/renderer.js";
import { initZoomSlider } from "./graph/zoom-slider.js";
import { isolationSet } from "./graph/isolate.js";
import { initAdmin } from "./panels/admin.js";
import { initBriefs } from "./panels/briefs.js";
import { initCaption } from "./panels/caption.js";
import { initChat } from "./panels/chat.js";
import { initConsole } from "./panels/console.js";
import { initDecisions } from "./panels/decisions.js";
import { initExamples } from "./panels/examples.js";
import { initImport } from "./panels/import.js";
import { initChecks } from "./panels/checks.js";
import { initPaths } from "./panels/paths.js";
import { initFind } from "./panels/find.js";
import { initLevels } from "./panels/levels.js";
import { entityLens, groupLens, linkLens } from "./graph/lens.js";
import { initColorKey } from "./panels/colorkey.js";
import { initManual } from "./panels/manual.js";
import { initForecast, progress, trackForecast } from "./panels/forecast.js";
import { initHypotheses } from "./panels/hypotheses.js";
import { initInbox } from "./panels/inbox.js";
import { initInspector } from "./panels/inspector.js";
import { initMemory } from "./panels/memory.js";
import { initMethods } from "./panels/methods.js";
import { initPipeline } from "./panels/pipeline.js";
import { initReview } from "./panels/review.js";
import { initThesis } from "./panels/thesis.js";
import { initTimeline } from "./panels/timeline.js";
import { initUpdate } from "./panels/update.js";
import { initWalkthrough } from "./panels/walkthrough.js";
import { applyTrace, backToLive, clearStaged, emit, on, openVersion, refreshGraph, scheduleRefresh, setStatus, stepShown, store } from "./store.js";
import { errorText, esc, fmt, signed } from "./util.js";

const $ = (sel) => document.querySelector(sel);
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = IS_MAC ? "⌘" : "Ctrl-";
const REDO_KEY = IS_MAC ? "⇧⌘Z" : "Ctrl-Y";

// the keyboard sheet (?): every shortcut in one place, so none needs a button on screen
const SHORTCUTS = [
  ["Canvas", [[`${MOD}Z`, "Undo a view change (open, close, move, layout)"], [`${REDO_KEY}`, "Redo"],
              ["1 · 2 · 3", "Superentities · entities · subentities"], ["0", "Auto: detail follows zoom"], ["K", "Color: what pills are colored by, and the key"], ["[ · ]", "Up a level · down into the first part (superentities within superentities)"], ["+ · − · F", "Zoom in · zoom out · fit"],
              [`/ · ${MOD}K`, "Find or filter: words, kinds, “moved”, “open>0.8”, “learned”; widen to neighborhoods"], ["D", "Draw a proposed edge"], ["Esc", "Close the top thing"]]],
  ["Demo", [["E", "Tutorial"], ["I", "Import research (imported models)"], ["→", "Next scripted step"], ["Space", "Play or pause"],
            ["⇧← · ⇧→", "Step through the timeline"], ["U", "Request an update"]]],
  ["Walkthrough", [["W", "How it learned (the latest news) or how it inferred (the latest question)"], ["← · →", "Previous · next step (while open)"]]],
  ["Panels", [["I", "Console: the commit log (Learn)"], ["N", "News"], ["B", "Forecast briefs"], ["Q", "Ask a question"], ["M", "Long-term memory"], ["C", "Checks: what the model is testing"], ["G", "Transmission grid: input, each order, output"], ["X", "Isolate the selection: what drives it and what it moves"],
              ["H", "How it works, the literature, the implementation"], [",", "Admin: story, map, view, settings"], ["A · R", "Approve · reject the focused proposal"], ["?", "This sheet"]]],
];

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

// A toast; with `action` ({label, run}) it carries one button, e.g. "Report" after an update.
// DECISION (Oct 11): toasts are for errors, for work that finished out of sight, and for results nothing else on screen
// shows; a toast repeating one still on screen is dropped, and at most two show at once.
function toast(text, kind = "real", action = null) {
  const box = $("#toast");
  if ([...box.children].some((t) => t.firstChild?.textContent === text)) return;
  const t = document.createElement("div");
  t.className = `t ${kind}`;
  t.textContent = text;
  if (action) {
    const b = document.createElement("button");
    b.textContent = action.label;
    b.addEventListener("click", () => { t.remove(); action.run(); });
    t.appendChild(b);
    t.classList.add("act");
  }
  box.prepend(t);
  while (box.children.length > 2) box.lastChild.remove();
  setTimeout(() => t.remove(), kind === "err" ? 9000 : action ? 7000 : 3600);
}

// a toast that explains something the first time only (per browser)
function once(key, text) {
  try { if (localStorage.getItem(`axelrod.told.${key}`)) return; localStorage.setItem(`axelrod.told.${key}`, "1"); } catch { /* say it */ }
  toast(text);
}

// counts read "0" most of the time; a zero count hides itself so only news that needs you shows
function hideZeroCounts() {
  const sync = (el) => el.classList.toggle("zero", el.textContent.trim() === "0" || !el.textContent.trim());
  for (const el of document.querySelectorAll(".count")) {
    sync(el);
    new MutationObserver(() => sync(el)).observe(el, { childList: true, characterData: true, subtree: true });
  }
}

const fmtDay = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
};

// -- boot -----------------------------------------------------------------------------------------
async function boot() {
  const tooltip = $("#tooltip");
  hideZeroCounts();
  const renderer = new SvgRenderer($("#canvas"), {
    onSelect: (sel) => select(sel),
    onHover: (ev, info) => hover(ev, info),
    onHoverMove: (ev) => moveTooltip(ev),
    onContext: (ev, target) => contextMenu(ev, target),
    onDetail: (lv) => setDetailButtons(lv),
    onHistory: (nUndo, nRedo) => setHistoryState(nUndo, nRedo),
    onLayoutMode: (mode) => { store.settings.layout = mode; },
    isDrawMode: () => store.settings.draw,
  });
  window.axelrod = { store, renderer, api };     // handy for debugging in the console

  // -- side panels -------------------------------------------------------------------------------
  const right = $("#right-panel");
  const left = $("#left-panel");
  // what the side panels cover: the floating controls (CSS reads --inset-l and --inset-r) and the camera use
  // the part of the canvas they leave visible, so nothing useful hides under an open panel
  const stage = $("#stage");
  let insets = { left: 0, right: 0 };
  // an open transmission grid that isolates the canvas covers its top: fits frame what is kept below it
  renderer.insets = () => {
    const pane = renderer.isolated?.way === "grid" ? document.getElementById("paths") : null;
    if (!pane || pane.classList.contains("hidden") || pane.classList.contains("win-max")) return insets;
    const c = $("#canvas").getBoundingClientRect();
    return { ...insets, top: Math.max(0, Math.min(pane.getBoundingClientRect().bottom - c.top + 8, c.height - 260)) };
  };
  function syncInsets() {
    const c = $("#canvas").getBoundingClientRect();
    const l = left.hidden ? 0 : Math.max(0, Math.round(left.getBoundingClientRect().right - c.left));
    const r = right.hidden ? 0 : Math.max(0, Math.round(c.right - right.getBoundingClientRect().left));
    insets = { left: l, right: r };
    stage.style.setProperty("--inset-l", `${l}px`);
    stage.style.setProperty("--inset-r", `${r}px`);
    stage.classList.toggle("left-open", l > 0);
    stage.classList.toggle("right-open", r > 0);
    stage.classList.toggle("cramped", c.width - l - r < 760);
  }
  for (const p of [left, right]) new ResizeObserver(syncInsets).observe(p);
  window.addEventListener("resize", syncInsets);
  function activateTab(name) {
    if (right.dataset.tab === "forecast" && name !== "forecast") clearForecastCanvas();
    for (const b of document.querySelectorAll("#right-tabs [data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
    for (const p of document.querySelectorAll("#right-body .tabpanel")) p.classList.toggle("active", p.id === `tab-${name}`);
    right.dataset.tab = name;
    $("#btn-ask").setAttribute("aria-expanded", String(!right.hidden && name === "thesis"));
    emit("tab", name);
  }
  function openRight(name) {
    right.hidden = false;
    activateTab(name);
    syncInsets();
  }
  // leaving a forecast or its brief (Oct 11): the paths it lit stop dimming the rest of the canvas
  // (the forecast's animation and the guide stop drawing on it too, even if they are still running)
  function clearForecastCanvas() {
    if (store.walkthrough) return;
    store.forecastDismissed = true;
    if (window.axelrod?.guide?.run) window.axelrod.guide.stop();
    renderer.setOverlayGroups([]);
    renderer.focusOverlay?.(null);
    renderer.setFlows({});
    renderer.clearHalos();
    if (!store.highlight) return;
    store.highlight = null;
    renderer.setHighlight(store.isolatedHighlight ?? null);
    emit("highlight", null);
  }
  function closeRight() {
    if (right.dataset.tab === "forecast") clearForecastCanvas();
    right.hidden = true;
    $("#btn-ask").setAttribute("aria-expanded", "false");
    syncInsets();
  }
  function openLeft(name) {
    left.hidden = false;
    left.classList.toggle("wide", name === "review");
    for (const b of left.querySelectorAll("[data-ltab]")) b.setAttribute("aria-selected", String(b.dataset.ltab === name));
    for (const p of left.querySelectorAll(".ltab")) p.classList.toggle("active", p.id === `ltab-${name}`);
    left.dataset.tab = name;
    $("#btn-inbox").setAttribute("aria-expanded", String(name === "inbox"));
    $("#btn-review").setAttribute("aria-expanded", String(name === "review"));
    $("#btn-briefs").setAttribute("aria-expanded", String(name === "briefs"));
    syncInsets();
    emit("tab-left", name);
  }
  function closeLeft() {
    if (left.dataset.tab === "briefs") clearForecastCanvas();
    left.hidden = true;
    left.classList.remove("wide");
    $("#btn-inbox").setAttribute("aria-expanded", "false");
    $("#btn-review").setAttribute("aria-expanded", "false");
    $("#btn-briefs").setAttribute("aria-expanded", "false");
    syncInsets();
    emit("tab-left", null);
  }
  const toggleLeft = (name) => (!left.hidden && left.dataset.tab === name ? closeLeft() : openLeft(name));
  let reviewOpenedForYou = false;     // the review queue opened itself (a run waits on you)
  for (const b of left.querySelectorAll("[data-ltab]")) b.addEventListener("click", () => openLeft(b.dataset.ltab));
  for (const b of document.querySelectorAll("#right-tabs [data-tab]")) b.addEventListener("click", () => activateTab(b.dataset.tab));
  $('[data-close-panel="right"]').addEventListener("click", () => { closeRight(); select(null, false); });
  $('[data-close-panel="left"]').addEventListener("click", closeLeft);

  // -- panels ------------------------------------------------------------------------------------
  const inspector = initInspector({
    onSelect: (sel) => select(sel), focusNode: (id) => renderer.focusNode(id), renderer,
    onAction: (act, arg) => {
      if (act === "toggle-entity") { renderer.toggleEntityByHand(arg); select(store.selection); }
      else if (act === "ask-entity") { thesis.prefill(arg); openRight("thesis"); }
      else if (act === "toggle-group") { renderer.toggleGroup(arg); select(store.selection); }
      else if (act === "close-parts") renderer.setGroupChildren(arg, true);
      else if (act === "forecast") {
        const [kind, ref] = String(arg).split("|");
        thesis.forecastFor(kind, ref);
        openRight("thesis");
        toast("Added to “Forecast for”. Ask a question to forecast it.");
      } else if (act === "walk") walk.open(arg);
    },
    scopeFor: (id) => latestScopeFor(id),
  });
  const review = initReview({ openModal, toast, onFocusGraph: (r) => showStagedItems(r) });
  initInbox({
    onWalk: (scope) => walk.open(scope),
    onReport: (id) => api.update(id).then((run) => select({ kind: "report", id: run.id, run })).catch(() => toast("No report for that update.", "err")),
  });
  initCaption({ onWalk: (scope) => walk.open(scope) });
  const pipeline = initPipeline({
    onTask: (t) => {
      if (!t) return;
      pipeline.setOpen(false);
      if (t.kind === "walk") walk.open(t.id);
      else if (t.kind === "memory") memory.openTab(t.id);
      else {
        select({ kind: t.kind, id: t.id });
        if (t.kind === "subentity") renderer.focusNode(String(t.id).split(".")[0]);
      }
    },
  });
  const timeline = initTimeline();
  const memory = initMemory({ onSelect: (sel) => select(sel) });
  const thesis = initThesis({ toast });
  initForecast({ renderer, activateTab: (name) => openRight(name), onWalk: (scope) => walk.open(scope) });
  const walk = initWalkthrough({ renderer, toast, openForecast: (id) => emit("open-forecast", id) });
  const guide = new Guide({ renderer, stage: $("#stage"), onModeChange: () => admin?.refresh() });
  const chat = initChat();
  const methods = initMethods();
  const consolePane = initConsole({ toast });
  const manual = initManual({
    toast,
    onProposal: async (pid) => { await refreshGraph(); openLeft("review"); review.focus(pid); },
  });
  const checks = initChecks({ toast, onSelect: (sel) => select(sel) });
  // the grid's part of the graph, isolated on the canvas (Oct 11): only its entities, laid out causes-left like the
  // grid's columns, its interactions lit, framed in the room the grid window leaves; closing the grid brings it all back
  const paths = initPaths({ toast, onSelect: (sel) => select(sel),
    onShow: (g, lay) => isolateGrid(g, lay), onIsolate: (g, lay) => (g ? isolateGrid(g, lay) : unisolate()),
    onHide: () => { if (renderer.isolated?.way === "grid") unisolate(); } });
  const examples = initExamples({
    toast,
    onManual: (spec, id) => { setMode("learn", false); manual.open(spec, { example: id }); },
    onProposal: async (pid) => { await refreshGraph(); openLeft("review"); review.focus(pid); },
    onQuestion: (q) => { setMode("predict", false); thesis.setQuestion(q); openRight("thesis"); },
    onReset: () => loadScenario(store.status?.scenario_id ?? "small_demo"),
  });
  // DECISION (Oct 11): an imported model's Tutorial is the small demo: it loads in place of the model, and Back
  // (top bar) loads the model again. The scenario to return to is kept for this tab only.
  const RETURN = "axelrod.tutorialReturn";
  const returnTo = () => { try { return sessionStorage.getItem(RETURN); } catch { return null; } };
  async function openTutorial() {
    if (!store.status?.imports) { examples.toggle(); return; }
    try { sessionStorage.setItem(RETURN, store.status.scenario_id); } catch { /* the tutorial still opens */ }
    await loadScenario("small_demo");
    examples.open();
  }
  const importer = initImport({
    toast,
    onProposal: async (pid) => { await refreshGraph(); openLeft("review"); review.focus(pid); },
  });
  on("open-examples", () => examples.open());
  on("run-example", (id) => { setMode("learn", false); examples.run(id); });
  // after a review, the tutorial's small graph is framed again
  on("reviewed", () => { if (store.status?.examples) setTimeout(() => renderer.fit(), 700); });
  const briefs = initBriefs({
    openLeft, onWalk: (scope) => walk.open(scope), onChat: (x) => chat.open(x), focusNode: (id) => renderer.focusNode(id),
    openForecast: (id) => emit("open-forecast", id),
  });
  const hyps = initHypotheses({ toast });
  const decisions = initDecisions({ toast });
  const draw = installDrawTool({ svgEl: $("#graph-svg"), rootSel: renderer.root, renderer, openModal, toast });
  const update = initUpdate({
    openModal, toast,
    startDraw: (fn) => { draw.armAttach((ev) => { setDraw(false); fn(ev); }); setDraw(true); },
    openReview: () => openLeft("review"),
    showReport: (run) => { select({ kind: "report", id: run.id, run }); },
  });
  // the categories, now in the Admin window's Map tab: hover lights up their entities, click frames them
  const categoryIds = (code) => (store.view?.entities ?? []).filter((e) => e.category_tags.includes(code)).map((e) => e.id);
  function highlightCategory(code) {
    if (!code) { renderer.setHighlight(store.highlight); hover(null); return; }
    renderer.setHighlight({ entities: new Set(categoryIds(code)), links: new Set(), hulls: new Set(), hot: new Set() });
  }
  const admin = initAdmin({
    renderer,
    actions: {
      step: () => doStep(), play: () => doPlay(), fit: () => renderer.fit(), zoom: (f) => renderer.zoomBy(f),
      undo: () => undo(), redo: () => redo(), hypotheses: () => openRight("hypotheses"), decisions: () => openRight("decisions"),
      methods: () => methods.open(), shortcuts: () => showShortcuts(), walk: (sc) => walk.open(sc),
      highlightCategory, frameCategory: (code) => renderer.frame(categoryIds(code), { maxK: 0.9 }),
      frameGroup: (key) => renderer.frame([key, ...(renderer.groupsInfo.byKey.get(key)?.members ?? [])], { maxK: 1 }),
      focusNode: (id) => renderer.focusNode(id), setLayout: (m) => setLayout(m), setCandidates: (v) => setCandidates(v),
      setFigure1Links: (v) => { store.settings.figure1LinksOnly = v; renderer.setOptions({ figure1LinksOnly: v }); },
      setReducedMotion: (v) => setReducedMotion(v), setSpeed: (x) => { store.settings.speed = x; player.setSpeed(x); },
      setCaptions: (v) => {
        store.settings.captions = v;
        try { localStorage.setItem("axelrod.captions", v ? "on" : "off"); } catch { /* fine */ }
        emit("captions-setting", v);
      },
      setPolicy: (pol) => setPolicy(pol), loadScenario: (id) => loadScenario(id),
      guideMode: () => guide.mode, setGuideMode: (m) => guide.setMode(m),
      guideAgain: () => { guide.seen = {}; try { localStorage.removeItem("axelrod.guide.seen"); } catch { /* none */ } toast("The guide will show the next forecast."); },
      toast,
    },
  });
  inspector.welcome();
  gestureHint();

  // A first visit says, once, how to explore the canvas; it goes after the first click on the graph.
  function gestureHint() {
    try { if (localStorage.getItem("axelrod.hinted")) return; } catch { /* show it */ }
    const hint = document.createElement("div");
    hint.id = "gesture-hint";
    hint.className = "floating";
    hint.setAttribute("role", "note");
    hint.innerHTML = `<span><b>Hover</b> anything to see what it is · <b>click</b> to inspect · <b>double-click</b> to open ·
      <b>right-click</b> for options · <kbd>?</kbd> for keys</span><button class="x" aria-label="Got it">✕</button>`;
    $("#canvas").appendChild(hint);
    const svg = $("#graph-svg");
    const done = () => {
      hint.classList.add("gone");
      setTimeout(() => hint.remove(), 300);
      try { localStorage.setItem("axelrod.hinted", "1"); } catch { /* fine */ }
      for (const t of ["click", "dblclick", "contextmenu"]) svg.removeEventListener(t, onGraph, true);
    };
    const onGraph = (ev) => { if (ev.target.closest?.("g.pill, g.card-super, g.hull, g.edge, g.row, g.frontier")) done(); };
    for (const t of ["click", "dblclick", "contextmenu"]) svg.addEventListener(t, onGraph, true);
    hint.querySelector(".x").addEventListener("click", done);
    // it has said its piece once the canvas has been zoomed or panned, or after a while
    svg.addEventListener("wheel", done, { once: true, passive: true });
    setTimeout(() => { if (hint.isConnected) done(); }, 20000);
  }

  let levels = null;
  function select(sel, open = true) {
    store.selection = sel;
    renderer.select(sel);
    inspector.show(sel);
    levels?.render();
    if (sel && open) {
      openRight("inspector");
      // the inspector may now cover what was clicked: slide the canvas so it shows
      if (sel.kind === "entity" || sel.kind === "subentity") requestAnimationFrame(() => renderer.keepVisible(sel.id));
    }
    if (!sel && !right.hidden && right.dataset.tab === "inspector") closeRight();
  }

  // -- tooltips ------------------------------------------------------------------------------------
  const listNames = (ns) => (ns.length <= 3 ? ns.join(", ") : `${ns.slice(0, 2).join(", ")} and ${ns.length - 2} more`);
  const groupLabel = (k) => renderer.groupsInfo.byKey.get(k)?.label ?? k;
  // the open node (Oct 9): the share the graph does not account for yet
  function openLine(share, what) {
    if (share == null) return "";
    return `<div class="small tt-open"><span class="on-dot" aria-hidden="true"></span><span><b>Open node ${Math.round(100 * share)}%</b>
      <span class="muted">of ${esc(what)} is not explained by the graph yet</span></span></div>`;
  }

  function hover(ev, info) {
    if (!ev || !info || menuOpen()) { tooltip.classList.add("hidden"); return; }
    const v = store.view;
    let html = "";
    if (info.kind === "entity") {
      const e = v?.entities.find((x) => x.id === info.id);
      if (e) {
        const subs = v.subentities.filter((s) => s.entity_id === e.id);
        const top = subs.reduce((a, s) => (!a || Math.abs(s.z) > Math.abs(a.z) ? s : a), null);
        const gs = (renderer.groupsInfo.ofEntity.get(e.id) ?? []).map(groupLabel);
        // its kind, and the entities of the same kind: similar objects, similar subentities
        // an actor's kind and the actors like it (similar objects, similar subentities); ideas leave it out
        const actor = ["company", "agency", "person"].includes(e.kind);
        const sibs = actor && e.kind_name ? v.entities.filter((x) => x.id !== e.id && x.generalization_id === e.generalization_id).map((x) => x.name) : [];
        html = `<div class="tt-h">${esc(e.name)}</div>
          <div class="tt-s">${e.category_tags.map((t) => esc(CATEGORY_NAMES[t] ?? t)).join(", ")} · ${subs.length} subentities</div>
          ${actor && e.kind_name ? `<div class="small">${esc(e.kind_name)}${sibs.length ? ` <span class="muted">· like ${esc(listNames(sibs))}</span>` : ""}</div>` : ""}
          ${e.description ? `<div class="tt-d">${esc(e.description)}</div>` : ""}
          ${top && Math.abs(top.z) >= 0.25 ? `<div>${top.z > 0 ? "<span class='z-up'>▲</span>" : "<span class='z-down'>▼</span>"} ${esc(top.name)}: ${signed(top.z)} sd
            ${top.observed_today ? "(observed today)" : "(propagated)"}</div>` : ""}
          ${(() => {
            const os = renderer.model?.owners.get(e.id) ?? [];
            if (os.length > 1) {
              return `<div class="small"><b>Shared</b> by ${os.map((o) => `${esc(groupLabel(o.key))}${o.drawn === "card" ? " (closed)" : ""}`).join(" and ")}</div>`;
            }
            return gs.length ? `<div class="small muted">In ${gs.map(esc).join("; ")}</div>` : `<div class="small muted">In no superentity yet</div>`;
          })()}
          ${openLine(e.open, "its values' movement")}
          ${renderer.ui.expanded.has(e.id) ? "" : entityLens(subs)}
          <div class="tt-f">double-click: subentities · right-click: options</div>`;
      }
    } else if (info.kind === "subentity") {
      const s = v?.subentities.find((x) => x.id === info.id);
      if (s) {
        const used = (renderer.model?.marks.get(s.id) ?? []).map(groupLabel);
        html = `<div class="tt-h">${esc(s.name)}</div>
          <div class="tt-s">${esc(v.entities.find((e) => e.id === s.entity_id)?.name ?? s.entity_id)} · ${esc(s.unit)}</div>
          <div>median ${fmt(s.summary.q50)} ${esc(s.unit)} <span class="muted">(90%: ${fmt(s.summary.q05)} to ${fmt(s.summary.q95)})</span></div>
          <div>${s.z > 0.25 ? "<span class='z-up'>▲</span>" : s.z < -0.25 ? "<span class='z-down'>▼</span>" : "·"} ${signed(s.z)} sd from normal ·
            ${s.observed_today ? "observed today" : s.observed ? "carried forward by the graph" : "never observed; moved by the graph"}</div>
          ${used.length ? `<div class="small muted">Used by ${used.map(esc).join("; ")}</div>` : ""}
          ${(() => {
            // its kin: the same value in similar entities (lit on the canvas while hovered)
            const byId = new Map(v.entities.map((x) => [x.id, x]));
            const key = kinKey(s, byId);
            const kin = key ? [...new Set(v.subentities.filter((x) => x.entity_id !== s.entity_id && kinKey(x, byId) === key)
              .map((x) => byId.get(x.entity_id)?.name ?? x.entity_id))] : [];
            if (s.slot) {
              return `<div class="small"><b>Every ${esc((s.slot_kind ?? "").toLowerCase())} has one</b>${kin.length ? ` <span class="muted">· also ${esc(listNames(kin))}</span>` : ""}</div>`;
            }
            return kin.length ? `<div class="small">Also in ${esc(listNames(kin))}</div>` : "";
          })()}
          ${openLine(s.open, "its movement")}`;
      }
    } else if (info.kind === "group") {
      const g = renderer.groupsInfo.byKey.get(info.key);
      const h = info.hull;
      if (g) {
        const closed = renderer.ui.collapsed.has(g.key);
        html = `<div class="tt-h">${esc(h?.label ?? g.label)}</div>
          <div class="tt-s">${g.transient ? "bound for one hypothetical" : `${esc(g.status)} superentity`}${g.composite ? " · made of superentities" : ""} · ${g.members.size} entities · support ${fmt(g.support, 1)}</div>
          ${(h?.description || g.description) ? `<div class="tt-d">${esc(h?.description || g.description)}</div>` : ""}
          ${g.composite ? `<div class="small muted">Parts: ${g.children.map(groupLabel).map(esc).join("; ")}</div>` : ""}
          ${openLine(h?.open, "its members' movement")}
          ${groupLens([...g.members], v)}
          <div class="tt-f">double-click: ${closed ? "open" : "close into one card"} · right-click: options</div>`;
      }
    } else if (info.kind === "link") {
      const ls = (v?.links ?? []).filter((l) => info.ids.includes(l.id)).sort((a, b) => b.significance - a.significance);
      const name = (sid) => v.subentities.find((s) => s.id === sid)?.name ?? sid;
      html = ls.slice(0, 3).map((l) => `<div class="tt-h">${esc(l.label)}${l.edge_type === "learned_causal" ? " <span class='badge real'>learned</span>" : ""}</div>
        <div class="tt-s">${esc(name(l.source))} → ${esc(name(l.target))}</div>
        <div class="small">effect ${signed(l.effect)} · exists ${fmt(l.existence)} · confidence ${fmt(l.confidence)}</div>
        ${ls.length === 1 ? linkLens(l) : ""}`).join("<hr>")
        + (ls.length > 3 ? `<div class="tt-f">+ ${ls.length - 3} more on this arrow</div>` : "");
    } else if (info.kind === "frontier") {
      const f = info.entry;
      const name = (sid) => v.subentities.find((s) => s.id === sid)?.name ?? sid;
      html = `<div class="tt-h">Co-movement</div><div>${esc(name(f.earlier))} → ${esc(name(f.later))}</div>
        <div class="small muted">${f.lag_days} days later · ${f.sign > 0 ? "same" : "opposite"} direction · support ${fmt(f.support)} · ${esc(f.status.replace(/_/g, " "))}</div>
        <div class="tt-f">not causal until promoted</div>`;
    }
    if (!html) { tooltip.classList.add("hidden"); return; }
    tooltip.innerHTML = html;
    tooltip.classList.remove("hidden");
    moveTooltip(ev);
  }
  function moveTooltip(ev) {
    if (tooltip.classList.contains("hidden") || !ev) return;
    const w = tooltip.offsetWidth || 300;
    const h = tooltip.offsetHeight || 120;
    const x = ev.clientX + 16 + w > window.innerWidth ? ev.clientX - w - 12 : ev.clientX + 16;
    const y = ev.clientY + 14 + h > window.innerHeight ? ev.clientY - h - 10 : ev.clientY + 14;
    tooltip.style.left = `${Math.max(6, x)}px`;
    tooltip.style.top = `${Math.max(6, y)}px`;
  }

  // -- right-click menus ---------------------------------------------------------------------------
  function swatch(key) {
    const g = renderer.groupsInfo.byKey.get(key);
    return g ? paletteOf(g, store.view?.palettes) : null;
  }
  function contextMenu(ev, target) {
    hover(null);
    const at = { x: ev.clientX, y: ev.clientY, keyboard: !!ev.keyboard };
    const v = store.view;
    if (!v) return;
    if (target.kind === "entity") {
      const e = v.entities.find((x) => x.id === target.id);
      const open = renderer.ui.expanded.has(target.id);
      const gs = (renderer.groupsInfo.ofEntity.get(target.id) ?? []).filter((k) => !renderer.groupsInfo.byKey.get(k).transient);
      const n = renderer.nodes.get(target.id);
      openMenu(at, {
        title: e?.name ?? target.id, subtitle: (e?.category_tags ?? []).map((t) => CATEGORY_NAMES[t] ?? t).join(", "),
        items: [
          { label: open ? "Hide its subentities" : "Show its subentities", kbd: "dbl-click", action: () => renderer.toggleEntityByHand(target.id) },
          { label: "Inspect", kbd: "click", action: () => select({ kind: "entity", id: target.id }) },
          { label: "What if it moves?", action: () => { thesis.prefill(target.id); openRight("thesis"); } },
          { label: "Forecast it", action: () => forecastIt("entity", target.id) },
          ...walkItem(target.id),
          { sep: true }, { group: "Isolate" },
          { label: "What drives it and what it moves", kbd: "X", action: () => isolate([target.id], "both") },
          { label: "Only what drives it", action: () => isolate([target.id], "up") },
          { label: "Only what it moves", action: () => isolate([target.id], "down") },
          ...(gs.length ? [{ sep: true }, { group: "Its superentities" }] : []),
          ...gs.map((k) => {
            const closed = renderer.ui.collapsed.has(k);
            return { label: `${closed ? "Open" : "Close"} ${groupLabel(k)}`, swatch: swatch(k), action: () => renderer.toggleGroup(k) };
          }),
          { sep: true },
          ...(learning() ? [{ label: "Draw an edge from here", kbd: "D", action: () => setDraw(true) }] : []),
          ...(n?.pinned ? [{ label: "Return to its place", action: () => renderer.unpin(target.id) }] : []),
          ...(learning() ? [{ sep: true }, { group: "Structure (proposed, then vetted)" },
            { label: "Group into a superentity…", action: () => groupDialog([target.id]) },
            { label: "Retire this entity…", action: () => retireDialog({ entity_id: target.id }, e?.name ?? target.id) }] : []),
        ],
      });
    } else if (target.kind === "subentity") {
      const s = v.subentities.find((x) => x.id === target.id);
      const used = renderer.model?.marks.get(target.id) ?? [];
      openMenu(at, {
        title: s?.name ?? target.id, subtitle: v.entities.find((e) => e.id === s?.entity_id)?.name,
        items: [
          { label: "Inspect", kbd: "click", action: () => select({ kind: "subentity", id: target.id }) },
          { label: "What if it moves?", action: () => { thesis.prefill(target.id); openRight("thesis"); } },
          { label: "Forecast it", action: () => forecastIt("subentity", target.id) },
          ...walkItem(target.id),
          { label: "Hide this entity's subentities", action: () => renderer.toggleEntityByHand(s.entity_id, false) },
          { label: "Isolate what drives it and what it moves", kbd: "X", action: () => isolate([s.entity_id], "both") },
          ...(used.length ? [{ sep: true }, { group: "Superentities that use it" }] : []),
          ...used.map((k) => {
            const h = renderer.groupsInfo.byKey.get(k).hulls[0];
            return { label: groupLabel(k), swatch: swatch(k), action: () => select({ kind: "pattern", id: h.pattern_id, instance: h.id, group: k }) };
          }),
        ],
      });
    } else if (target.kind === "group") {
      const g = renderer.groupsInfo.byKey.get(target.key);
      if (!g) return;
      const closed = renderer.ui.collapsed.has(g.key);
      const membersOpen = [...g.members].some((m) => renderer.ui.expanded.has(m));
      const h = g.hulls[0];
      openMenu(at, {
        title: g.label, subtitle: g.composite ? "a superentity of superentities" : `${g.members.size} entities`,
        items: [
          { label: closed ? "Open it" : "Close it into one card", kbd: "dbl-click", action: () => renderer.toggleGroup(g.key) },
          ...(g.children.length ? [
            { label: "Open it with its parts closed", action: () => renderer.setGroupChildren(g.key, true) },
            { label: "Open it and all its parts", action: () => renderer.setGroupChildren(g.key, false) }] : []),
          ...(!closed ? [{ label: membersOpen ? "Hide its members' subentities" : "Show its members' subentities",
                           action: () => renderer.setMembersOpen(g.key, !membersOpen) }] : []),
          { label: "Inspect", kbd: "click", action: () => select({ kind: "pattern", id: h.pattern_id, instance: h.id, group: g.key }) },
          ...(g.transient ? [] : [{ label: "Forecast it", action: () => forecastIt("superentity", h.pattern_id) }]),
          ...(g.parents.length ? [{ sep: true }, { group: "Part of" }] : []),
          ...g.parents.map((k) => ({ label: `Close ${groupLabel(k)}`, swatch: swatch(k), action: () => renderer.toggleGroup(k, true) })),
          ...(learning() && !g.transient && g.status === "admitted" ? [{ sep: true }, { group: "Structure (proposed, then vetted)" },
            { label: "Dissolve it into its constituents…", action: () => dissolveDialog(h.pattern_id, g.label) }] : []),
        ],
      });
    } else if (target.kind === "edge") {
      const ls = v.links.filter((l) => target.ids.includes(l.id));
      openMenu(at, {
        title: ls[0]?.label ?? "Interaction", subtitle: ls.length > 1 ? `${ls.length} interactions on this arrow` : null,
        items: [
          ...ls.slice(0, 6).map((l) => ({ label: `Inspect ${l.label} (${l.id})`, action: () => select({ kind: "interaction", id: l.id, ids: target.ids }) })),
          ...(learning() ? [{ sep: true }, { group: "Structure (proposed, then vetted)" },
            ...ls.slice(0, 6).map((l) => ({ label: `Retire ${l.label} (${l.id})…`, action: () => retireDialog({ interaction_id: l.id }, `${l.label} (${l.id})`) }))] : []),
        ],
      });
    } else {
      openMenu(at, {
        title: "Canvas",
        items: [
          ...(renderer.undoStack.length ? [{ label: `Undo ${renderer.undoStack.at(-1).label}`, kbd: `${MOD}Z`, action: undo }] : []),
          ...(renderer.redoStack.length ? [{ label: `Redo ${renderer.redoStack.at(-1).label}`, kbd: REDO_KEY, action: redo }] : []),
          ...(renderer.undoStack.length || renderer.redoStack.length ? [{ sep: true }] : []),
          { label: "Close every superentity", kbd: "1", action: () => renderer.setDetail("super") },
          { label: "Open every superentity", kbd: "2", action: () => renderer.setDetail("entity") },
          { label: "Show every entity's subentities", kbd: "3", action: () => renderer.setDetail("sub") },
          { sep: true },
          { label: store.settings.showCandidates ? "Hide candidate superentities" : "Show candidate superentities",
            action: () => setCandidates(!store.settings.showCandidates) },
          { label: document.body.classList.contains("labels") ? "Hide interaction labels" : "Show every interaction label",
            action: () => document.body.classList.toggle("labels") },
          { sep: true },
          { label: "Fit everything", kbd: "F", action: () => renderer.fit() },
          { label: "Return every node to its place", action: () => renderer.resetLayout() },
          { sep: true },
          ...(walk.latestScope() ? [{ label: /^T-|^FC-/.test(walk.latestScope()) ? "How it inferred: the latest question" : "How it learned: the latest news", kbd: "W", action: () => walk.open(walk.latestScope()) }] : []),
          { label: "Keyboard shortcuts", kbd: "?", action: showShortcuts },
        ],
      });
    }
  }

  // -- structure edits (restructure): collapse, expand, delete. Each is a proposal that waits for review in the
  // Console and the Review queue (unless the review policy approves everything), then commits once.
  const learning = () => store.settings.mode !== "predict";
  function proposed(pv) {
    const p = pv?.proposal ?? pv;
    if (!p) return;
    const pending = p.status === "pending";
    toast(pending ? `Proposed ${p.id}: it waits for review.` : `${p.id}: ${String(p.status).replace(/_/g, " ")}.`, "real",
          pending ? { label: "Review", run: () => { openLeft("review"); review.focus(p.id); } } : null);
    scheduleRefresh(200);
  }
  function groupDialog(seed) {
    const ents = [...(store.view?.entities ?? [])].sort((a, b) => a.name.localeCompare(b.name));
    openModal(`<h3>Group into a superentity</h3>
      <p class="small">Collapse: the members become one superentity (one card on the graph), with one relation for each interaction among them. It waits for review.</p>
      <label class="field">Name <input data-name placeholder="e.g. Airline fuel squeeze"></label>
      <div class="field">Members <span class="small muted">(at least two)</span>
        <div class="memberpick">${ents.map((x) => `<label><input type="checkbox" value="${esc(x.id)}" ${seed.includes(x.id) ? "checked" : ""}> ${esc(x.name)}</label>`).join("")}</div></div>
      <label class="field">Why <input data-desc placeholder="One sentence for the log"></label>
      <div class="actions"><button data-close>Cancel</button><button class="primary" data-ok>Propose</button></div>`, (m, close) => {
      m.querySelector("[data-ok]").addEventListener("click", () => guarded(async () => {
        const members = [...m.querySelectorAll(".memberpick input:checked")].map((x) => x.value);
        const name = m.querySelector("[data-name]").value.trim();
        if (!name || members.length < 2) { toast("Name it and pick at least two members.", "err"); return; }
        const pv = await api.group({ name, members, description: m.querySelector("[data-desc]").value.trim(), by: "backend user" });
        close();
        proposed(pv);
      }));
    });
  }
  function retireDialog(target, label) {
    openModal(`<h3>Retire ${esc(label)}</h3>
      <p class="small">Delete: ${target.entity_id ? "the entity, its subentities, and every interaction that touches them leave" : "the interaction leaves"} the graph and every forecast. The log keeps the whole history. It waits for review.</p>
      <label class="field">Why <input data-reason placeholder="e.g. the agreement expired"></label>
      <div class="actions"><button data-close>Cancel</button><button class="primary" data-ok>Propose</button></div>`, (m, close) => {
      m.querySelector("[data-ok]").addEventListener("click", () => guarded(async () => {
        const reason = m.querySelector("[data-reason]").value.trim();
        if (!reason) { toast("Say why, for the log.", "err"); return; }
        const pv = await api.retire({ ...target, reason, by: "backend user" });
        close();
        proposed(pv);
      }));
    });
  }
  function dissolveDialog(patternId, label) {
    openModal(`<h3>Dissolve ${esc(label)}</h3>
      <p class="small">Expand: the superentity breaks back into its constituents. Its pattern stays in long-term memory, dissolved, with its history. It waits for review.</p>
      <label class="field">Why <input data-reason placeholder="e.g. show the members' own interactions"></label>
      <div class="actions"><button data-close>Cancel</button><button class="primary" data-ok>Propose</button></div>`, (m, close) => {
      m.querySelector("[data-ok]").addEventListener("click", () => guarded(async () => {
        const reason = m.querySelector("[data-reason]").value.trim();
        if (!reason) { toast("Say why, for the log.", "err"); return; }
        const pv = await api.dissolve(patternId, reason, "backend user");
        close();
        proposed(pv);
      }));
    });
  }

  function forecastIt(kind, ref) {
    thesis.forecastFor(kind, ref);
    openRight("thesis");
    toast("Added to “Forecast for”. Ask a question to forecast it.");
  }

  // "How it learned": the latest news (or question) that touched this node, replayed step by step
  // (news first; a routine daily data release only when no news touched it)
  function latestScopeFor(id) {
    const ent = String(id).split(".")[0];
    const touches = (r) => typeof r === "string" && (r === id || r === ent || r.startsWith(`${ent}.`));
    let routine = null;
    for (let k = store.traces.length - 1; k >= 0; k--) {
      const e = store.traces[k];
      if (!e.scope || e.scope.startsWith("day:") || /^T-/.test(e.scope)) continue;
      if (e.kind !== "refine.step" && e.kind !== "fold.posterior" && e.kind !== "parse.op") continue;
      if (!(e.refs ?? []).some(touches)) continue;
      if (!/^ME-D-/.test(e.scope)) return e.scope;
      routine ??= e.scope;
    }
    return routine;
  }
  function walkItem(id) {
    const sc = latestScopeFor(id);
    return sc ? [{ label: "How it learned: its latest news", action: () => walk.open(sc) }] : [];
  }

  async function guarded(fn) {
    try { return await fn(); } catch (err) { toast(errorText(err), "err"); return null; }
  }
  const setPolicy = (p) => guarded(async () => {
    store.config = { ...(store.config ?? {}), ...(await api.setReviewPolicy(p)) };
    toast(p === "default" ? "Structural changes now wait for your review." : "Everything is approved automatically.");
  });
  const setLayout = (mode) => {
    store.settings.layout = mode;
    renderer.setLayoutMode(mode);
    setTimeout(() => renderer.fit(), 420);
  };
  const setCandidates = (on_) => {
    store.settings.showCandidates = on_;
    renderer.setShowCandidates(on_);
  };
  function setReducedMotion(on_) {
    store.settings.reducedMotion = on_;
    document.body.classList.toggle("reduced-motion", on_);
    renderer.setOptions({ reducedMotion: on_ });
  }
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setReducedMotion(true);

  async function loadScenario(id) {
    clearStaged();
    // another world: what was open about this one (a forecast, its grid, the side panels) does not carry over
    if (paths.isOpen()) paths.close();
    if (importer.isOpen()) importer.close();
    clearForecastCanvas();
    closeRight();
    predict.keep = new Set();
    predict.all = false;
    await guarded(async () => {
      const st = await api.load(id, true);
      setStatus(st);
      backToLive();
      await refreshGraph();
      renderer.fit();
    });
  }

  // -- graph, ribbons, ghosts ------------------------------------------------------------------------
  function extras() {
    const live = store.readOnlyVersion == null ? store.liveOps : new Map();
    const ghostEdges = [];
    const ghostSubs = [];
    const pendingPatterns = new Set();
    const staged = stagedMarks();
    if (staged) return { ribbons: [], ghostEdges, ghostSubs, pendingPatterns, staged };
    if (store.readOnlyVersion == null) {
      for (const pv of store.proposals ?? []) {
        if (pv.proposal.kind === "superentity_admission" && pv.proposal.subject_id) pendingPatterns.add(pv.proposal.subject_id);
        pv.proposal.event.ops.forEach((op, i) => {
          if (op.op === "add_interaction") {
            const s = op.source?.kind === "concrete" ? op.source.subentity_id : null;
            const t = op.target?.kind === "concrete" ? op.target.subentity_id : null;
            if (s && t) ghostEdges.push({ key: `${pv.proposal.id}:${i}`, a: s, b: t, hyp: pv.proposal.event.kind === "hypothetical" });
          } else if (op.op === "add_subentity") {
            ghostSubs.push({ id: String(op.temp_id).replace(/^new:/, "") });
          } else if (op.op === "propose_superentity" && op.pattern?.id) {
            pendingPatterns.add(op.pattern.id);
          }
        });
      }
      for (const id of store.recentlyCreated) if (!ghostSubs.some((g) => g.id === id)) ghostSubs.push({ id });
    }
    // while a walkthrough is open its own ribbons (one market event, fuzzy to real) replace the live ones
    const ribbons = store.walkthrough ? (walkRibbons ?? []) : ribbonItems(store.view, live);
    return { ribbons, ghostEdges, ghostSubs, pendingPatterns, staged: null };
  }
  // what a staged review would change, for the canvas: new and retired items, each moved value's order, and
  // the interactions the ripple travels along
  function stagedMarks() {
    const r = store.staged?.review;
    if (!r) return null;
    const m = r.marks ?? {};
    const orders = new Map(Object.entries(m.orders ?? {}).map(([k, v]) => [k, v]));
    const path = new Set((r.ripple ?? []).flatMap((a) => a.via ?? []));
    return { new: new Set(m.new ?? []), retired: store.staged.retired ?? new Set(m.retired ?? []), orders, path,
             collapsed: new Set(m.collapsed ?? []) };
  }
  // a staged review opens the entities it touches, so their values and order tints show
  let fittedFor = null;
  // the transmission grid is the default view of a ripple (Oct 11): it opens once per proposal and per forecast
  let gridShownFor = null;
  // what the Transmission button opens: the staged ripple, or the forecast last shown
  let gridTarget = null;
  function setGridTarget(t) {
    gridTarget = t;
    $("#btn-grid").classList.toggle("hidden", !t);
  }
  function autoGrid(kind, id, has) {
    if (has) setGridTarget({ kind, id });
    else if (gridTarget?.kind === kind) setGridTarget(null);
    if (store.settings.gridAuto === false || !has || gridShownFor === `${kind}:${id}` || store.booting) return;
    gridShownFor = `${kind}:${id}`;
    emit("paths-open", { kind, id });
  }
  function showStagedItems(r) {
    autoGrid("proposal", r.proposal_id, (r.ripple ?? []).length > 0);
    const ents = new Set();
    for (const id of [...(r.marks?.new ?? []), ...Object.keys(r.marks?.orders ?? {})]) {
      const e = String(id).split(".")[0];
      if ((store.view?.entities ?? []).some((x) => x.id === e)) ents.add(e);
    }
    // open the entities the event touches most: what it adds, its own move, and the first orders of its ripple
    const near = new Set(ents);
    const order = r.marks?.orders ?? {};
    const firstOrders = Object.keys(order).filter((sid) => order[sid] <= 1).map((sid) => sid.split(".")[0]);
    const focusSet = new Set([...(r.marks?.new ?? []).map((id) => String(id).split(".")[0]), ...firstOrders].filter((e) => near.has(e)));
    for (const e of ents) if (!renderer.ui.expanded.has(e) && (ents.size <= 8 || focusSet.has(e))) renderer.toggleEntity(e, true);
    if (fittedFor !== r.proposal_id) {
      fittedFor = r.proposal_id;
      const frameOn = [...(focusSet.size ? focusSet : near)];
      setTimeout(() => (frameOn.length && (store.view?.entities ?? []).length > 12 ? renderer.frame(frameOn, { maxK: 1.1 }) : renderer.fit()), 380);
    }
    const banner = $("#staged-banner");
    banner.innerHTML = `<b>Staged: not committed.</b> <span class="lg new">new</span> <span class="lg retired">retired</span>
      <span class="lg o0">the event's move</span> <span class="lg o1">1st order</span> <span class="lg o2">2nd</span> <span class="lg o3">3rd</span>`;
    banner.classList.remove("hidden");
  }
  on("staged", (r) => {
    if (r) { if ((r.ripple ?? []).length && r.proposal_id) setGridTarget({ kind: "proposal", id: r.proposal_id }); return; }
    $("#staged-banner").classList.add("hidden");
    fittedFor = null;
    if (gridTarget?.kind === "proposal") setGridTarget(null);
  });
  on("staged-hover", (refs) => {
    if (!refs) { renderer.setHighlight(store.highlight); return; }
    const ents = new Set(refs.map((x) => String(x).split(".")[0]).filter((e) => (store.view?.entities ?? []).some((x) => x.id === e)));
    const links = new Set(refs.filter((x) => (store.view?.links ?? []).some((l) => l.id === x)));
    for (const l of store.view?.links ?? []) if (refs.includes(l.source) && refs.includes(l.target)) links.add(l.id);
    renderer.setHighlight({ entities: ents, links, hulls: new Set(), hot: links });
  });
  let walkRibbons = null;
  on("walk-ribbons", (r) => { walkRibbons = r; refreshRibbons(); });

  on("graph", (g) => {
    if (!g) return;
    renderer.setData(g, extras());
    const hint = $("#empty-hint");
    const empty = !g.entities.length && store.readOnlyVersion == null;
    hint.classList.toggle("hidden", !empty);
    if (empty && !hint.dataset.on) {
      hint.dataset.on = "1";
      hint.innerHTML = `<div class="eh-t">A blank canvas</div>
        <p>Build a world model from the ground up. Each step of the tutorial isolates one part of the framework, runs through learning on a
        staged copy, and stops at your review.</p><button class="primary" data-ex>Start the tutorial</button>`;
      hint.querySelector("[data-ex]").addEventListener("click", () => examples.open());
    }
    if (!empty) delete hint.dataset.on;
    $("#sim-version").textContent = `v${g.version}${store.readOnlyVersion != null ? " · read-only" : ""}`;
    if (g.today) $("#sim-date").textContent = fmtDay(g.today);
    if (store.selection) renderer.select(store.selection);
    predictCanvas();
  });
  const refreshRibbons = () => renderer.setExtras(extras());
  on("proposals", refreshRibbons);
  // a staged proposal's grid closes once that proposal is decided (the canvas comes back with it)
  on("proposals", () => {
    if (gridTarget?.kind === "proposal" && !(store.proposals ?? []).some((pv) => pv.proposal.id === gridTarget.id && pv.proposal.status === "pending")) {
      if (paths.isOpen()) paths.close();
      setGridTarget(null);
    }
  });
  // a review queue that opened by itself closes by itself once it is empty
  on("proposals", () => {
    if (reviewOpenedForYou && !(store.proposals ?? []).length && !left.hidden && left.dataset.tab === "review") {
      reviewOpenedForYou = false;
      setTimeout(() => { if (!(store.proposals ?? []).length) closeLeft(); }, 900);
    }
  });
  on("fuzzy", refreshRibbons);

  // -- status and toolbar ------------------------------------------------------------------------------
  let lastState = null;
  on("status", (st) => {
    if (!st) return;
    // the run waits on you: open the review queue now, even if the animation is still catching up
    if (st.state === "awaiting_review" && lastState !== "awaiting_review" && !store.booting) {
      reviewOpenedForYou = left.hidden || left.dataset.tab !== "review";
      openLeft("review");
    }
    lastState = st.state;
    document.body.classList.toggle("canvas-blank", st.canvas === "blank");
    document.body.classList.toggle("has-examples", !!st.examples);
    document.body.classList.toggle("has-imports", !!st.imports);
    $("#btn-examples").classList.toggle("primary", !!st.examples);
    const back = returnTo();
    const showBack = !!back && back !== st.scenario_id && !!st.examples;
    $("#btn-return").classList.toggle("hidden", !showBack);
    if (showBack) $("#btn-return").textContent = "← Back to your model";
    if (!store.graph?.today) $("#sim-date").textContent = fmtDay(st.sim_time);
    if (store.readOnlyVersion == null) $("#sim-version").textContent = `v${st.version}`;
    $("#step-label").textContent = `${stepShown()} / ${st.total_steps}`;
    const playing = st.state === "running";
    const play = $("#btn-play");
    play.textContent = playing ? "Pause" : "Play";
    play.setAttribute("aria-pressed", String(playing));
    $("#btn-step").disabled = st.state === "done" || playing || st.state === "awaiting_review";
    $("#btn-step").title = st.state === "awaiting_review" ? "Review the waiting proposals first" : "Run the next scripted step of the demo (→)";
    if (st.error) toast(`Scenario error: ${st.error}`, "err");
  });
  on("day", (p) => { if (p?.date) $("#sim-date").textContent = fmtDay(p.date); });
  on("caption", () => { if (store.status) $("#step-label").textContent = `${stepShown()} / ${store.status.total_steps}`; });

  const doStep = () => guarded(async () => { const r = await api.step(); scheduleRefresh(100); return r; });
  const doPlay = () => guarded(async () => {
    if (store.status?.state === "running") setStatus(await api.pause());
    else setStatus(await api.play());
  });
  $("#btn-step").addEventListener("click", doStep);
  $("#btn-play").addEventListener("click", doPlay);
  $("#btn-update").addEventListener("click", () => update.open());
  $("#btn-inbox").addEventListener("click", () => toggleLeft("inbox"));
  $("#btn-review").addEventListener("click", () => toggleLeft("review"));
  $("#btn-ask").addEventListener("click", () => (!right.hidden && right.dataset.tab === "thesis" ? closeRight() : openRight("thesis")));
  $("#btn-briefs").addEventListener("click", () => toggleLeft("briefs"));
  $("#btn-briefs-top").addEventListener("click", () => toggleLeft("briefs"));
  // the transmission grid: the staged ripple or the forecast last shown; again closes it
  $("#btn-grid").addEventListener("click", () => {
    const pid = store.staged?.review?.proposal_id;
    if (paths.isOpen()) paths.close();
    else if (gridTarget) emit("paths-open", gridTarget);
    else if (pid) emit("paths-open", { kind: "proposal", id: pid });
    else paths.open();
  });
  new MutationObserver(() => $("#btn-grid").setAttribute("aria-expanded", String(paths.isOpen())))
    .observe($("#paths"), { attributes: true, attributeFilter: ["class"] });
  // Briefs sits in the bar (Predict) once there is one to read
  const briefsTop = $("#briefs-count-top");
  new MutationObserver(() => {
    const n = +($("#briefs-count").textContent || 0);
    briefsTop.textContent = String(n);
    $("#btn-briefs-top").classList.toggle("hidden", !n);
  }).observe($("#briefs-count"), { childList: true, characterData: true, subtree: true });
  $("#btn-methods").addEventListener("click", () => methods.toggle());
  on("open-methods", ({ tab, anchor } = {}) => methods.open(tab, anchor));
  // full screen (Oct 8): every window over the canvas has a ⤢ button; it fills the space between the bars, and again
  // restores it. Double-clicking a window's header does the same.
  const WINDOWS = "#methods, #examples, #import, #manual, #checks, #paths, #console, #chat, #walkthrough, #left-panel, #right-panel, #drawer";
  const toggleMax = (win) => {
    const on_ = !win.classList.contains("win-max");
    win.classList.toggle("win-max", on_);
    for (const b of win.querySelectorAll("[data-max]")) {
      b.textContent = on_ ? "⤡" : "⤢";
      b.setAttribute("aria-label", on_ ? "Restore" : "Full screen");
    }
    window.dispatchEvent(new Event("resize"));
  };
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest?.("[data-max]");
    const win = b?.closest(WINDOWS);
    if (win) { ev.stopPropagation(); toggleMax(win); }
  }, true);
  document.addEventListener("dblclick", (ev) => {
    const hd = ev.target.closest?.("header, .walk-head");
    const win = hd?.closest(WINDOWS);
    if (win && !ev.target.closest("button, input, a")) toggleMax(win);
  });
  $("#btn-console").addEventListener("click", () => consolePane.toggle());
  $("#btn-examples").addEventListener("click", () => openTutorial());
  $("#btn-import").addEventListener("click", () => importer.toggle());
  $("#btn-return").addEventListener("click", async () => {
    const back = returnTo();
    try { sessionStorage.removeItem(RETURN); } catch { /* nothing kept */ }
    examples.close();
    if (back) await loadScenario(back);
  });

  // -- views (restructure): Learn for backend users, who update the one world model; Predict for everyone
  // else, who pose theses against committed versions and never change it --------------------------------
  // Predict's canvas state (see predictCanvas below); set up before setMode first runs
  const predict = { keep: new Set(), all: false, question: "", effects: new Map() };
  const predictHint = document.createElement("div");
  predictHint.id = "predict-hint";
  predictHint.className = "floating hidden";
  predictHint.setAttribute("role", "status");
  $("#canvas").appendChild(predictHint);
  function setMode(mode, announce = true) {
    if (mode === "learn") {
      clearForecastCanvas();
      // Predict's windows (a forecast, its brief, its grid) belong to Predict: Learn opens on the model itself
      if (store.settings.mode === "predict") {
        if (!right.hidden && ["forecast", "thesis"].includes(right.dataset.tab)) closeRight();
        if (!left.hidden && left.dataset.tab === "briefs") closeLeft();
        if (paths.isOpen() && gridTarget?.kind === "forecast") paths.close();
      }
    }
    store.settings.mode = mode;
    document.body.classList.toggle("mode-learn", mode === "learn");
    document.body.classList.toggle("mode-predict", mode === "predict");
    $("#mode-learn").setAttribute("aria-pressed", String(mode === "learn"));
    $("#mode-predict").setAttribute("aria-pressed", String(mode === "predict"));
    try { localStorage.setItem("axelrod.mode", mode); } catch { /* fine */ }
    if (mode === "predict") {
      if (consolePane.isOpen()) consolePane.close();
      if (examples.isOpen()) examples.close();
      if (importer.isOpen()) importer.close();
      if (!left.hidden && left.dataset.tab === "review") closeLeft();
      // Learn's windows belong to Learn: a staged proposal's grid closes, and Predict opens on its own canvas
      if (paths.isOpen() && gridTarget?.kind !== "forecast") paths.close();
      if (store.settings.draw) setDraw(false);
      if (announce) once("mode-predict", "Predict: pose a thesis against the committed version. Nothing you do here is learned.");
    } else if (announce) {
      once("mode-learn", "Learn: update the world model. Every change is vetted and committed; the Console shows each step.");
    }
    predictCanvas();
  }
  $("#mode-learn").addEventListener("click", () => setMode("learn"));
  $("#mode-predict").addEventListener("click", () => setMode("predict"));
  setMode((() => { try { return localStorage.getItem("axelrod.mode") === "predict" ? "predict" : "learn"; } catch { return "learn"; } })(), false);
  on("load-scenario", (id) => { consolePane.close(); examples.close(); loadScenario(id); });
  on("open-version", (v) => { openVersion(v).catch((err) => toast(errorText(err), "err")); });
  $("#btn-admin").addEventListener("click", () => admin.toggle());
  // the menu: everything that is not the moment's primary action; it closes once something is chosen
  const menuPanel = $("#menu-panel");
  const setMenu = (open) => { menuPanel.hidden = !open; $("#btn-menu").setAttribute("aria-expanded", String(open)); };
  $("#btn-menu").addEventListener("click", (ev) => { ev.stopPropagation(); setMenu(menuPanel.hidden); });
  menuPanel.addEventListener("click", (ev) => { if (ev.target.closest("button")) setMenu(false); });
  document.addEventListener("click", (ev) => { if (!menuPanel.hidden && !ev.target.closest(".menu-wrap")) setMenu(false); });
  $("#btn-keys").addEventListener("click", () => showShortcuts());
  $("#btn-ask-learn").addEventListener("click", () => { setMode("predict"); openRight("thesis"); });
  $("#btn-manual").addEventListener("click", () => { closeMenu(); manual.open(); });
  $("#btn-checks").addEventListener("click", () => { closeMenu(); checks.toggle(); });

  // canvas controls
  const detailButtons = { super: $("#lvl-super"), entity: $("#lvl-entity"), sub: $("#lvl-sub") };
  function setDetailButtons(lv) {
    for (const [k, b] of Object.entries(detailButtons)) b.setAttribute("aria-pressed", String(k === lv));
  }
  // detail follows zoom (Oct 9) unless a person picks a level by hand
  const autoBtn = $("#lvl-auto");
  function setAuto(on_) {
    renderer.autoDetail = on_;
    autoBtn.setAttribute("aria-pressed", String(on_));
    try { localStorage.setItem("axelrod.autoDetail", on_ ? "1" : "0"); } catch { /* private window */ }
    if (on_) { renderer.lod.reset(); renderer.scheduleAutoDetail(0); }
  }
  try { if (localStorage.getItem("axelrod.autoDetail") === "0") setAuto(false); } catch { /* ignore */ }
  // Oct 11: the zoom bar is one color unless colored by level (Admin > Settings); the grid opens with each review
  try {
    document.body.classList.toggle("zoom-bands", localStorage.getItem("axelrod.zoomBands") === "1");
    store.settings.gridAuto = localStorage.getItem("axelrod.gridAuto") !== "0";
  } catch { store.settings.gridAuto = true; }
  autoBtn.addEventListener("click", () => setAuto(!renderer.autoDetail));
  for (const [k, b] of Object.entries(detailButtons)) b.addEventListener("click", () => { setAuto(false); renderer.setDetail(k); });
  $("#btn-fit").addEventListener("click", () => renderer.fit());
  initZoomSlider($("#zoom-slider"), renderer, { names: (id) => renderer.entityName(id) });
  function setDraw(on_) {
    store.settings.draw = on_;
    $("#btn-draw").setAttribute("aria-pressed", String(on_));
    $("#canvas").classList.toggle("draw-mode", on_);
    if (on_) toast("Draw: drag from a subentity, entity, or superentity to another.");
    else draw.disarm();
  }
  $("#btn-draw").addEventListener("click", () => setDraw(!store.settings.draw));

  // -- undo, redo, walkthrough, shortcuts ---------------------------------------------------------------
  let hinted = false;
  function setHistoryState(nUndo) {
    admin?.refresh();
    if (nUndo && !hinted && !store.booting) {
      hinted = true;
      once("undo", `${MOD}Z undoes view changes · ? lists every shortcut`);
    }
  }
  function undo() {
    const label = renderer.undo();
    toast(label ? `Undid: ${label}` : "Nothing to undo.");
  }
  function redo() {
    const label = renderer.redo();
    toast(label ? `Redid: ${label}` : "Nothing to redo.");
  }
  function toggleWalk() {
    if (walk.isOpen()) { walk.close(); return; }
    const sc = walk.latestScope();
    if (sc) walk.open(sc);
    else toast("Nothing to walk through yet: step the demo, request an update, or ask a question first.");
  }
  function showShortcuts() {
    openModal(`<h3>Keyboard shortcuts</h3>
      <div class="keys">${SHORTCUTS.map(([g, rows]) => `<section><h4>${esc(g)}</h4><dl>${rows.map(([k, d]) =>
        `<dt>${k.split(" · ").map((x) => `<kbd>${esc(x)}</kbd>`).join(" ")}</dt><dd>${esc(d)}</dd>`).join("")}</dl></section>`).join("")}</div>
      <div class="actions"><button data-close class="primary">Close</button></div>`);
  }
  initFind({ renderer, toast });
  const colorKey = initColorKey({ renderer });
  levels = initLevels({ renderer, select: (sel, open) => select(sel, open) });
  on("tab", (name) => {
    if (name === "hypotheses") hyps.render();
    if (name === "decisions") decisions.render();
  });
  on("show-forecast", (fv) => {
    openRight("forecast");
    showForecastOnCanvas(fv);
    if ((fv?.transmission?.values ?? []).length && fv.forecast?.id) setGridTarget({ kind: "forecast", id: fv.forecast.id });
  });
  on("ask-started", ({ question }) => {
    store.forecastDismissed = false;
    progress.run = { scope: null, question, phase: "posed", nets: 0, total: 0, current: "" };
    emit("forecasting", progress.run);
    openRight("forecast");
  });
  on("asked", (fv) => {
    showForecastOnCanvas(fv);
    autoGrid("forecast", fv.forecast?.id, (fv.transmission?.values ?? []).length > 0);
    if (progress.run && progress.run.scope == null) { progress.run = null; emit("forecasting", null); }
    if (guide.run) briefs.expect(fv.forecast.thesis_id);
    else setTimeout(() => briefs.open(fv.forecast.id), 300);
  });
  on("walkthrough", (w) => { if (w) guide.stop(); });
  on("open-forecast", () => openRight("forecast"));

  // -- isolate (Oct 11): one node's upstream and downstream, on their own ------------------------------------
  const isoBanner = document.createElement("div");
  isoBanner.id = "isolate-banner";
  isoBanner.className = "floating hidden";
  isoBanner.setAttribute("role", "status");
  $("#canvas").appendChild(isoBanner);
  const WAY = { both: "what drives it and what it moves", up: "what drives it", down: "what it moves" };
  function isolate(ids, way = "both", hops = 3) {
    const keep = isolationSet(store.view, ids, way, hops);
    const name = ids.map((id) => renderer.entityName(id)).join(", ");
    renderer.setIsolation({ ids, keep, way, hops });
    isoBanner.innerHTML = `<b>Isolated:</b> ${esc(name)} <span class="muted">· ${esc(WAY[way])}, up to
      <select data-hops aria-label="How many interactions away">${[1, 2, 3, 4, 5].map((h) => `<option ${h === hops ? "selected" : ""}>${h}</option>`).join("")}</select>
      interactions away · ${keep.size} of ${store.view?.entities?.length ?? 0} entities</span>
      <span class="seg">${Object.keys(WAY).map((w) => `<button data-way="${w}" aria-pressed="${w === way}">${{ both: "Both", up: "Drivers", down: "Effects" }[w]}</button>`).join("")}</span>
      <button class="primary small" data-show-all title="Show the whole graph again (Esc)">Show all</button>`;
    isoBanner.classList.remove("hidden");
    isoBanner.querySelector("[data-hops]").addEventListener("change", (ev) => isolate(ids, way, +ev.target.value));
    for (const b of isoBanner.querySelectorAll("[data-way]")) b.addEventListener("click", () => isolate(ids, b.dataset.way, hops));
    isoBanner.querySelector("[data-show-all]").addEventListener("click", () => unisolate());
  }
  function unisolate() {
    if (!renderer.isolated) return false;
    // in Predict, leaving the forecast's view means asking to see the whole model
    if (renderer.isolated.way === "predict") { predict.all = true; predictCanvas(); return true; }
    const wasGrid = renderer.isolated.way === "grid";
    renderer.setIsolation(null);
    isoBanner.classList.add("hidden");
    if (wasGrid) { store.isolatedHighlight = null; renderer.setHighlight(store.highlight); }
    predictCanvas();
    return true;
  }

  // -- Predict's canvas (Oct 11): prediction is for people outside the team, so it opens on a blank canvas, and a
  // forecast brings forward what it reaches: the values it shocks, the entities it moves, and the watched names it
  // touches. The whole model stays one click away ("Show the whole model"), as it was when the forecast was made.
  function forecastEntities(fv) {
    const known = new Set((store.view?.entities ?? []).map((e) => e.id));
    const t = fv?.transmission ?? {};
    const out = new Set();
    for (const s of t.shocked ?? []) out.add(String(s.id).split(".")[0]);
    for (const v of t.values ?? []) if (v.material) out.add(v.entity_id);
    for (const n of t.watchlist?.names ?? []) if (n.status === "moves" || n.status === "shocked") out.add(n.id);
    return new Set([...out].filter((e) => known.has(e)));
  }
  function predictCanvas() {
    const on = store.settings.mode === "predict" && !store.walkthrough && !!store.view?.entities?.length;
    if (!on) {
      renderer.setRowOverride(null);
      document.body.classList.remove("predict-blank");
      if (renderer.isolated?.way === "predict") renderer.setIsolation(null);
      predictHint.classList.add("hidden");
      return;
    }
    document.body.classList.toggle("predict-blank", !predict.all && !predict.keep.size);
    renderer.setRowOverride(!predict.all && predict.keep.size ? predict.effects : null);
    if (renderer.isolated?.way === "grid") { predictHint.classList.add("hidden"); return; }   // the grid shows it
    const total = store.view.entities.length;
    if (predict.all) {
      renderer.setRowOverride(null);
      if (renderer.isolated?.way === "predict") { renderer.setIsolation(null); setTimeout(() => renderer.frameAll(420), 60); }
      predictHint.className = "floating predict-bar";
      predictHint.innerHTML = `<span><b>The whole model</b> <span class="muted">· ${total} entities, as of this version</span></span>
        ${predict.keep.size ? `<button class="small" data-back>Back to the forecast</button>` : `<button class="small" data-blank>Clear the canvas</button>`}`;
      return;
    }
    const keep = predict.keep;
    const was = renderer.isolated?.way === "predict" ? renderer.isolated.keep : null;
    const same = was && was.size === keep.size && [...keep].every((e) => was.has(e));
    if (!same) renderer.setIsolation({ ids: [...keep], keep, way: "predict", hops: 0, open: keep.size <= 6 });
    if (!keep.size) {
      predictHint.className = "floating predict-empty";
      predictHint.innerHTML = `<div class="eh-t">Ask about your world</div>
        <p>Pose a what-if. The forecast brings forward the actors and ideas it reaches, in the order the shock travels.</p>
        <div class="predict-acts"><button class="primary" data-ask>Ask a question</button>
          <button class="ghost small" data-all>Show the whole model</button></div>`;
    } else {
      predictHint.className = "floating predict-bar";
      const q = predict.question.length > 64 ? `${predict.question.slice(0, 62).trimEnd()}…` : predict.question;
      predictHint.innerHTML = `<span><b>What the forecast reaches</b> <span class="muted">· ${keep.size} of ${total} entities${q ? ` · <span title="${esc(predict.question)}">${esc(q)}</span>` : ""}</span></span>
        <button class="small" data-all>Show the whole model</button>`;
      if (!same) setTimeout(() => renderer.frame([...keep], { duration: 420, maxK: 1.1 }), 140);
    }
  }
  predictHint.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.ask != null) $("#btn-ask").click();
    else if (b.dataset.all != null) { predict.all = true; predictCanvas(); }
    else if (b.dataset.back != null) { predict.all = false; predictCanvas(); }
    else if (b.dataset.blank != null) { predict.all = false; predict.keep = new Set(); predictCanvas(); }
  });
  function showForecastOnCanvas(fv) {
    const keep = forecastEntities(fv);
    if (!keep.size) return;
    predict.effects = new Map((fv?.transmission?.values ?? []).map((v) => [v.id, v.peak]));
    predict.keep = keep;
    predict.all = false;
    predict.question = fv?.forecast?.question ?? fv?.thesis?.question ?? "";
    predictCanvas();
  }
  const GRID_DX = 330;      // world units between the grid's columns on the canvas
  const GRID_DY = 84;       // and between its rows
  function isolateGrid(g, lay) {
    const known = new Set((store.view?.entities ?? []).map((e) => e.id));
    const keep = new Set(Object.values(g.values ?? {}).map((v) => v.entity_id).filter((e) => known.has(e)));
    if (!keep.size) return;
    const same = renderer.isolated?.way === "grid" && renderer.isolated.keep.size === keep.size
      && [...keep].every((e) => renderer.isolated.keep.has(e));
    // the grid itself says what is isolated and switches it off, so no banner over the canvas
    isoBanner.classList.add("hidden");
    // each entity sits where the grid puts it: its column (where it is first reached) and its row, so the canvas reads
    // left to right the way the grid does
    const homes = new Map((lay?.rows ?? []).filter((r) => keep.has(r.id))
      .map((r, i) => [r.id, { x: 600 + (r.col - (lay.cols - 1) / 2) * GRID_DX, y: 440 + i * GRID_DY }]));
    const moved = renderer.isolated?.way === "grid" && [...homes].some(([id, h]) => {
      const o = renderer.isolated.homes?.get(id);
      return !o || o.x !== h.x || o.y !== h.y;
    });
    if (!same || moved) renderer.setIsolation({ ids: [...keep], keep, way: "grid", hops: 0, open: false, homes });
    const hot = new Set((g.edges ?? []).map((e) => e.key));
    store.isolatedHighlight = { entities: keep, links: hot, hulls: new Set(), hot };
    renderer.setHighlight(store.isolatedHighlight);
    // frame what is kept below the grid window, between the side panels (renderer.insets has the room)
    setTimeout(() => renderer.frame([...keep], { duration: same && !moved ? 300 : 420, maxK: 1.1 }), same && !moved ? 0 : 140);
  }


  // -- keyboard (§13.8) ----------------------------------------------------------------------------------
  document.addEventListener("keydown", (ev) => {
    const typing = ev.target.closest?.("input, textarea, select, [contenteditable]");
    const mod = ev.metaKey || ev.ctrlKey;
    // undo and redo change what the canvas shows; inside a text field they stay the field's own
    if (mod && !ev.altKey && !typing && !$("#modal-root").innerHTML) {
      const k = ev.key.toLowerCase();
      if (k === "z" && !ev.shiftKey) { ev.preventDefault(); undo(); return; }
      if ((k === "z" && ev.shiftKey) || (k === "y" && !ev.shiftKey)) { ev.preventDefault(); redo(); return; }
      if (k === "k") { ev.preventDefault(); $("#search").focus(); return; }
    }
    if (ev.key === "Escape") {
      if (!$("#menu-panel").hidden) { $("#menu-panel").hidden = true; $("#btn-menu").setAttribute("aria-expanded", "false"); return; }
      if (menuOpen()) { closeMenu(); return; }
      if ($("#modal-root").innerHTML) { $("#modal-root").innerHTML = ""; return; }
      if (walk.isOpen()) { walk.close(); return; }
      if (consolePane.isOpen()) { consolePane.close(); return; }
      if (manual.isOpen()) { manual.close(); return; }
      if (paths.isOpen()) { paths.close(); return; }
      if (unisolate()) return;
      if (checks.isOpen()) { checks.close(); return; }
      if (colorKey.isOpen()) { colorKey.close(); return; }
      if (examples.isOpen()) { examples.close(); return; }
      if (importer.isOpen()) { importer.close(); return; }
      if (methods.isOpen()) { methods.close(); return; }
      if (chat.isOpen()) { chat.close(); return; }
      if (guide.run) { guide.stop(); return; }
      if (memory.isOpen()) { memory.close(); return; }
      if (store.settings.draw) { setDraw(false); return; }
      if (!$("#pipeline").classList.contains("hidden")) { pipeline.setOpen(false); return; }
      if (store.readOnlyVersion != null) { backToLive(); return; }
      if (!right.hidden) { closeRight(); select(null, false); return; }
      if (!left.hidden) { closeLeft(); return; }
      select(null);
      return;
    }
    if (typing || $("#modal-root").innerHTML || menuOpen()) return;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    // inside a panel, arrows scroll and Space presses the focused button, as anywhere else; the demo keys act
    // from the canvas and the top bar
    const inPanel = !!ev.target.closest?.("#left-panel, #right-panel, #drawer, #admin, #methods, #console, #examples, #import, #checks, #paths, #walkthrough, #tooltip");
    const onControl = !!ev.target.closest?.("button, a, summary, select, [role=button], [role=tab]");
    if (ev.key === " " && (onControl || inPanel)) return;
    if ((ev.key === "ArrowRight" || ev.key === "ArrowLeft") && inPanel && !walk.isOpen()) return;
    if (walk.isOpen() && (ev.key === "ArrowRight" || ev.key === "ArrowLeft") && !ev.shiftKey) {
      ev.preventDefault();
      if (ev.key === "ArrowRight") walk.next(); else walk.prev();
      return;
    }
    if (ev.key === "?") { ev.preventDefault(); showShortcuts(); }
    else if (ev.key === "w" || ev.key === "W") toggleWalk();
    else if ((ev.key === "i" || ev.key === "I") && store.settings.mode !== "predict") consolePane.toggle();
    else if ((ev.key === "e" || ev.key === "E") && store.settings.mode !== "predict" && (store.status?.examples || store.status?.imports)) openTutorial();
    else if ((ev.key === "i" || ev.key === "I") && store.settings.mode !== "predict" && store.status?.imports) importer.toggle();
    else if (ev.key === "n" || ev.key === "N") toggleLeft("inbox");
    else if (ev.key === "b" || ev.key === "B") toggleLeft("briefs");
    else if (ev.key === ",") admin.toggle();
    else if (ev.key === "h" || ev.key === "H") methods.toggle();
    else if (ev.key === "q" || ev.key === "Q") $("#btn-ask").click();
    else if (ev.key === "m" || ev.key === "M") memory.setOpen(!memory.isOpen());
    else if (ev.key === "c" || ev.key === "C") checks.toggle();
    else if (ev.key === "x" || ev.key === "X") {
      // isolate the selected entity (or the entity of the selected value); again to show everything
      const sel = store.selection;
      const eid = sel?.kind === "entity" ? sel.id : sel?.kind === "subentity" ? sel.id.split(".")[0] : null;
      if (renderer.isolated) unisolate();
      else if (eid) isolate([eid], "both");
      else toast("Select an entity or a value first, then X isolates what drives it and what it moves.");
    } else if (ev.key === "g" || ev.key === "G") {
      $("#btn-grid").click();
    }
    else if (ev.key === "k" || ev.key === "K") colorKey.toggle();
    else if (ev.key === "[") levels?.up();
    else if (ev.key === "]") levels?.down();
    else if (store.settings.mode === "predict" && [" ", "ArrowRight", "u", "U", "d", "D", "a", "A", "r", "R"].includes(ev.key) && !ev.shiftKey) {
      toast("That control learns: switch to Learn to use it.");
    }
    else if (ev.key === " ") { ev.preventDefault(); doPlay(); }
    else if (ev.key === "ArrowRight" && ev.shiftKey) { ev.preventDefault(); timeline.stepForward(); }
    else if (ev.key === "ArrowLeft" && ev.shiftKey) { ev.preventDefault(); timeline.stepBack(); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); doStep(); }
    else if (ev.key === "u" || ev.key === "U") update.open();
    else if (ev.key === "1") { setAuto(false); renderer.setDetail("super"); }
    else if (ev.key === "2") { setAuto(false); renderer.setDetail("entity"); }
    else if (ev.key === "3") { setAuto(false); renderer.setDetail("sub"); }
    else if (ev.key === "0") setAuto(!renderer.autoDetail);
    else if (ev.key === "f" || ev.key === "F") renderer.fit();
    else if (ev.key === "+" || ev.key === "=") renderer.zoomBy(1.25);
    else if (ev.key === "-" || ev.key === "_") renderer.zoomBy(0.8);
    else if (ev.key === "d" || ev.key === "D") setDraw(!store.settings.draw);
    else if (ev.key === "/") { ev.preventDefault(); $("#search").focus(); }
    else if (ev.key === "a" || ev.key === "A") review.approveFocused();
    else if (ev.key === "r" || ev.key === "R") review.rejectFocused();
  });

  // -- data -------------------------------------------------------------------------------------------
  const player = new Player({ renderer, toast, guide, refresh: () => scheduleRefresh(150), refreshRibbons });
  window.axelrod.player = player;
  window.axelrod.guide = guide;

  const [layout, scenarios, cfg] = await Promise.all([
    api.layout().catch(() => null), api.scenarios().catch(() => []), api.config().catch(() => null)]);
  installGeneralizations(renderer);
  store.layout = layout;
  renderer.setLayout(layout);
  // DECISION (Oct 8): the example demos float in the gravity layout (entities arrive one article at a time, so a fixed
  // figure cannot place them well); so does any world with no hand-placed Figure 1. Admin › View switches back.
  const status0 = store.status ?? await api.status().catch(() => null);
  // what this person looks at, and at what zoom, is learned per world (graph/attention.js)
  renderer.useAttention(status0?.scenario_id ?? "default");
  if (status0?.examples || !Object.keys(layout?.entities ?? {}).length) {
    store.settings.layout = "gravity";
    renderer.quiet = true;                 // the default, not a view change to undo
    renderer.setLayoutMode("gravity");
    renderer.quiet = false;
  }
  store.scenarios = scenarios;
  store.config = cfg;

  // the trace so far fills the inbox, timeline, and caption without animating or opening panels
  store.booting = true;
  try {
    const evs = await api.trace(0);
    for (const ev of evs) applyTrace(ev);
  } catch (err) { console.warn("no trace backfill", err); }
  store.booting = false;
  timeline.backfill();
  setStatus(await api.status().catch(() => null));
  await refreshGraph();
  if (store.status?.state === "awaiting_review" && store.proposals.length) openLeft("review");

  const stream = new Stream({
    sinceSeq: () => store.lastSeq,
    onTrace: (ev) => { trackForecast(ev); player.push(ev); },
    onStatus: (st) => setStatus(st),
    onOpen: () => document.body.classList.remove("offline"),
    onClose: () => document.body.classList.add("offline"),
  });
  stream.connect();
  setTimeout(() => renderer.fitReadable(0), 400);
  // pills and tabs are sized by measuring text, so measure again once the web fonts have loaded
  document.fonts?.ready.then(() => { renderer.recompute("data"); });
}

// A fuzzy end that names a generalization ("a kind of firm") is drawn around every entity the taxonomy files
// under it: the object taxonomy's instances below the node, or the ends of the interactions below it.
function installGeneralizations(renderer) {
  const trees = {};
  const load = async () => {
    for (const kind of ["object", "interaction"]) {
      try {
        const t = await api.taxonomy(kind);
        trees[kind] = new Map(t.nodes.map((n) => [n.id, n]));
      } catch { /* drawn at a fallback spot */ }
    }
  };
  const below = (tree, id) => {
    const out = [];
    const stack = [id];
    while (stack.length) {
      const n = tree?.get(stack.pop());
      if (!n) continue;
      out.push(...n.instance_ids);
      stack.push(...n.children);
    }
    return out;
  };
  renderer.generalizationMembers = (ref) => {
    const m = /^gen:(obj|int):(.+)$/.exec(String(ref ?? ""));
    if (!m) return [];
    if (m[1] === "obj") return below(trees.object, m[2]);
    const links = new Map((store.view?.links ?? []).map((l) => [l.id, l]));
    return below(trees.interaction, m[2]).flatMap((i) => {
      const l = links.get(i);
      return l ? [l.source.split(".")[0], l.target.split(".")[0]] : [];
    });
  };
  load();
  on("memory", () => load());
  // the kinds gain members as the graph grows (the tutorial starts blank): reload after each new version
  let t = null;
  on("versions", () => { clearTimeout(t); t = setTimeout(load, 1500); });
}

boot().catch((err) => {
  console.error(err);
  const c = document.querySelector("#caption .text");
  if (c) c.textContent = `Could not start the demo: ${err.message}`;
});
