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
import { SvgRenderer } from "./graph/renderer.js";
import { initAdmin } from "./panels/admin.js";
import { initBriefs } from "./panels/briefs.js";
import { initCaption } from "./panels/caption.js";
import { initChat } from "./panels/chat.js";
import { initDecisions } from "./panels/decisions.js";
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
import { applyTrace, backToLive, emit, on, refreshGraph, scheduleRefresh, setStatus, store } from "./store.js";
import { errorText, esc, fmt, signed } from "./util.js";

const $ = (sel) => document.querySelector(sel);
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = IS_MAC ? "⌘" : "Ctrl-";
const REDO_KEY = IS_MAC ? "⇧⌘Z" : "Ctrl-Y";

// the keyboard sheet (?): every shortcut in one place, so none needs a button on screen
const SHORTCUTS = [
  ["Canvas", [[`${MOD}Z`, "Undo a view change (open, close, move, layout)"], [`${REDO_KEY}`, "Redo"],
              ["1 · 2 · 3", "Superentities · entities · subentities"], ["+ · − · F", "Zoom in · zoom out · fit"],
              [`/ · ${MOD}K`, "Find an entity or value"], ["D", "Draw a proposed edge"], ["Esc", "Close the top thing"]]],
  ["Demo", [["→", "Next scripted step"], ["Space", "Play or pause"], ["⇧← · ⇧→", "Step through the timeline"],
            ["U", "Request an update"]]],
  ["Walkthrough", [["W", "Walk through the latest news or question"], ["← · →", "Previous · next step (while open)"]]],
  ["Panels", [["N", "News"], ["B", "Forecast briefs"], ["Q", "Ask a question"], ["M", "Long-term memory"],
              [",", "Admin: story, map, view, settings"], ["A · R", "Approve · reject the focused proposal"], ["?", "This sheet"]]],
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

function toast(text, kind = "real") {
  const box = $("#toast");
  const t = document.createElement("div");
  t.className = `t ${kind}`;
  t.textContent = text;
  box.prepend(t);
  while (box.children.length > 3) box.lastChild.remove();
  setTimeout(() => t.remove(), kind === "err" ? 9000 : 3600);
}

const fmtDay = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
};

// -- boot -----------------------------------------------------------------------------------------
async function boot() {
  const tooltip = $("#tooltip");
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
  function activateTab(name) {
    for (const b of document.querySelectorAll("#right-tabs [data-tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
    for (const p of document.querySelectorAll("#right-body .tabpanel")) p.classList.toggle("active", p.id === `tab-${name}`);
    right.dataset.tab = name;
    $("#btn-ask").setAttribute("aria-expanded", String(!right.hidden && name === "thesis"));
    emit("tab", name);
  }
  function openRight(name) {
    right.hidden = false;
    activateTab(name);
  }
  function closeRight() {
    right.hidden = true;
    $("#btn-ask").setAttribute("aria-expanded", "false");
  }
  function openLeft(name) {
    left.hidden = false;
    for (const b of left.querySelectorAll("[data-ltab]")) b.setAttribute("aria-selected", String(b.dataset.ltab === name));
    for (const p of left.querySelectorAll(".ltab")) p.classList.toggle("active", p.id === `ltab-${name}`);
    left.dataset.tab = name;
    $("#btn-inbox").setAttribute("aria-expanded", String(name === "inbox"));
    $("#btn-review").setAttribute("aria-expanded", String(name === "review"));
    $("#btn-briefs").setAttribute("aria-expanded", String(name === "briefs"));
    emit("tab-left", name);
  }
  function closeLeft() {
    left.hidden = true;
    left.classList.remove("wide");
    $("#btn-inbox").setAttribute("aria-expanded", "false");
    $("#btn-review").setAttribute("aria-expanded", "false");
    $("#btn-briefs").setAttribute("aria-expanded", "false");
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
      if (act === "toggle-entity") { renderer.toggleEntity(arg); select(store.selection); }
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
  const review = initReview({ openModal, toast });
  initInbox({ onWalk: (scope) => walk.open(scope) });
  initCaption({ onWalk: (scope) => walk.open(scope) });
  const pipeline = initPipeline();
  const timeline = initTimeline();
  const memory = initMemory({ onSelect: (sel) => select(sel) });
  const thesis = initThesis({ toast });
  initForecast({ renderer, activateTab: (name) => openRight(name), onWalk: (scope) => walk.open(scope) });
  const walk = initWalkthrough({ renderer, toast, openForecast: (id) => emit("open-forecast", id) });
  const guide = new Guide({ renderer, stage: $("#stage"), onModeChange: () => admin?.refresh() });
  const chat = initChat();
  const methods = initMethods();
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
      setPolicy: (pol) => setPolicy(pol), loadScenario: (id) => loadScenario(id),
      guideMode: () => guide.mode, setGuideMode: (m) => guide.setMode(m),
      guideAgain: () => { guide.seen = {}; try { localStorage.removeItem("axelrod.guide.seen"); } catch { /* none */ } toast("The guide will show the next forecast."); },
      toast,
    },
  });
  inspector.welcome();

  function select(sel, open = true) {
    store.selection = sel;
    renderer.select(sel);
    inspector.show(sel);
    if (sel && open) openRight("inspector");
    if (!sel && !right.hidden && right.dataset.tab === "inspector") closeRight();
  }

  // -- tooltips ------------------------------------------------------------------------------------
  const groupLabel = (k) => renderer.groupsInfo.byKey.get(k)?.label ?? k;
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
        html = `<div class="tt-h">${esc(e.name)}</div>
          <div class="tt-s">${e.category_tags.map((t) => esc(CATEGORY_NAMES[t] ?? t)).join(", ")} · ${subs.length} subentities</div>
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
          ${used.length ? `<div class="small muted">Used by ${used.map(esc).join("; ")}</div>` : ""}`;
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
          <div class="tt-f">double-click: ${closed ? "open" : "close into one card"} · right-click: options</div>`;
      }
    } else if (info.kind === "link") {
      const ls = (v?.links ?? []).filter((l) => info.ids.includes(l.id)).sort((a, b) => b.significance - a.significance);
      const name = (sid) => v.subentities.find((s) => s.id === sid)?.name ?? sid;
      html = ls.slice(0, 3).map((l) => `<div class="tt-h">${esc(l.label)}${l.edge_type === "learned_causal" ? " <span class='badge real'>learned</span>" : ""}</div>
        <div class="tt-s">${esc(name(l.source))} → ${esc(name(l.target))}</div>
        <div class="small">effect ${signed(l.effect)} · exists ${fmt(l.existence)} · confidence ${fmt(l.confidence)}</div>`).join("<hr>")
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
          { label: open ? "Hide its subentities" : "Show its subentities", kbd: "dbl-click", action: () => renderer.toggleEntity(target.id) },
          { label: "Inspect", kbd: "click", action: () => select({ kind: "entity", id: target.id }) },
          { label: "What if it moves?", action: () => { thesis.prefill(target.id); openRight("thesis"); } },
          { label: "Forecast it", action: () => forecastIt("entity", target.id) },
          ...walkItem(target.id),
          ...(gs.length ? [{ sep: true }, { group: "Its superentities" }] : []),
          ...gs.map((k) => {
            const closed = renderer.ui.collapsed.has(k);
            return { label: `${closed ? "Open" : "Close"} ${groupLabel(k)}`, swatch: swatch(k), action: () => renderer.toggleGroup(k) };
          }),
          { sep: true },
          { label: "Draw an edge from here", kbd: "D", action: () => setDraw(true) },
          ...(n?.pinned ? [{ label: "Return to its place", action: () => renderer.unpin(target.id) }] : []),
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
          { label: "Hide this entity's subentities", action: () => renderer.toggleEntity(s.entity_id, false) },
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
        ],
      });
    } else if (target.kind === "edge") {
      const ls = v.links.filter((l) => target.ids.includes(l.id));
      openMenu(at, {
        title: ls[0]?.label ?? "Link", subtitle: ls.length > 1 ? `${ls.length} links on this arrow` : null,
        items: ls.slice(0, 6).map((l) => ({ label: `Inspect ${l.label} (${l.id})`, action: () => select({ kind: "interaction", id: l.id, ids: target.ids }) })),
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
          { label: document.body.classList.contains("labels") ? "Hide link labels" : "Show every link label",
            action: () => document.body.classList.toggle("labels") },
          { sep: true },
          { label: "Fit everything", kbd: "F", action: () => renderer.fit() },
          { label: "Return every node to its place", action: () => renderer.resetLayout() },
          { sep: true },
          ...(walk.latestScope() ? [{ label: "Walk through the latest step", kbd: "W", action: () => walk.open(walk.latestScope()) }] : []),
          { label: "Keyboard shortcuts", kbd: "?", action: showShortcuts },
        ],
      });
    }
  }

  function forecastIt(kind, ref) {
    thesis.forecastFor(kind, ref);
    openRight("thesis");
    toast("Added to “Forecast for”. Ask a question to forecast it.");
  }

  // "Walk through": the latest news (or question) that touched this node, replayed step by step
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
    return sc ? [{ label: "Walk through the latest news about it", action: () => walk.open(sc) }] : [];
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
    setTimeout(() => renderer.fit(), 900);
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
    return { ribbons, ghostEdges, ghostSubs, pendingPatterns };
  }
  let walkRibbons = null;
  on("walk-ribbons", (r) => { walkRibbons = r; refreshRibbons(); });

  on("graph", (g) => {
    if (!g) return;
    renderer.setData(g, extras());
    $("#search-list").innerHTML = [...g.entities.map((e) => `<option value="${esc(e.name)}">${esc(e.id)}</option>`),
      ...g.subentities.map((s) => `<option value="${esc(s.name)}">${esc(s.id)}</option>`)].join("");
    $("#sim-version").textContent = `v${g.version}${store.readOnlyVersion != null ? " · read-only" : ""}`;
    if (g.today) $("#sim-date").textContent = fmtDay(g.today);
    if (store.selection) renderer.select(store.selection);
  });
  const refreshRibbons = () => renderer.setExtras(extras());
  on("proposals", refreshRibbons);
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
    if (!store.graph?.today) $("#sim-date").textContent = fmtDay(st.sim_time);
    if (store.readOnlyVersion == null) $("#sim-version").textContent = `v${st.version}`;
    $("#step-label").textContent = `${st.step_index} / ${st.total_steps}`;
    const playing = st.state === "running";
    const play = $("#btn-play");
    play.textContent = playing ? "Pause" : "Play";
    play.setAttribute("aria-pressed", String(playing));
    $("#btn-step").disabled = st.state === "done" || playing || st.state === "awaiting_review";
    $("#btn-step").title = st.state === "awaiting_review" ? "Review the waiting proposals first" : "Run the next scripted step of the demo (→)";
    if (st.error) toast(`Scenario error: ${st.error}`, "err");
  });
  on("day", (p) => { if (p?.date) $("#sim-date").textContent = fmtDay(p.date); });

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
  $("#btn-methods").addEventListener("click", () => methods.toggle());
  $("#btn-admin").addEventListener("click", () => admin.toggle());

  // canvas controls
  const detailButtons = { super: $("#lvl-super"), entity: $("#lvl-entity"), sub: $("#lvl-sub") };
  function setDetailButtons(lv) {
    for (const [k, b] of Object.entries(detailButtons)) b.setAttribute("aria-pressed", String(k === lv));
  }
  for (const [k, b] of Object.entries(detailButtons)) b.addEventListener("click", () => renderer.setDetail(k));
  $("#btn-fit").addEventListener("click", () => renderer.fit());
  $("#zoom-in").addEventListener("click", () => renderer.zoomBy(1.25));
  $("#zoom-out").addEventListener("click", () => renderer.zoomBy(0.8));
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
      toast(`${MOD}Z undoes view changes · ? lists every shortcut`);
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
  $("#search").addEventListener("change", (ev) => {
    const q = ev.target.value.trim().toLowerCase();
    if (!q) return;
    const v = store.view;
    const hit = v.entities.find((e) => e.id === q || e.name.toLowerCase() === q)
      ?? v.subentities.find((s) => s.id === q || s.name.toLowerCase() === q)
      ?? v.entities.find((e) => e.name.toLowerCase().includes(q))
      ?? v.subentities.find((s) => s.name.toLowerCase().includes(q) || s.id.includes(q));
    if (hit) { renderer.focusNode(hit.id); ev.target.value = ""; ev.target.blur(); }
    else toast(`Nothing matches “${q}”.`, "err");
  });
  on("tab", (name) => {
    if (name === "hypotheses") hyps.render();
    if (name === "decisions") decisions.render();
  });
  on("show-forecast", () => openRight("forecast"));
  on("ask-started", ({ question }) => {
    progress.run = { scope: null, question, phase: "posed", nets: 0, total: 0, current: "" };
    emit("forecasting", progress.run);
    openRight("forecast");
  });
  on("asked", (fv) => {
    if (progress.run && progress.run.scope == null) { progress.run = null; emit("forecasting", null); }
    if (guide.run) briefs.expect(fv.forecast.thesis_id);
    else setTimeout(() => briefs.open(fv.forecast.id), 300);
  });
  on("walkthrough", (w) => { if (w) guide.stop(); });
  on("open-forecast", () => openRight("forecast"));

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
      if (menuOpen()) { closeMenu(); return; }
      if ($("#modal-root").innerHTML) { $("#modal-root").innerHTML = ""; return; }
      if (walk.isOpen()) { walk.close(); return; }
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
    if (walk.isOpen() && (ev.key === "ArrowRight" || ev.key === "ArrowLeft") && !ev.shiftKey) {
      ev.preventDefault();
      if (ev.key === "ArrowRight") walk.next(); else walk.prev();
      return;
    }
    if (ev.key === "?") { ev.preventDefault(); showShortcuts(); }
    else if (ev.key === "w" || ev.key === "W") toggleWalk();
    else if (ev.key === "n" || ev.key === "N") toggleLeft("inbox");
    else if (ev.key === "b" || ev.key === "B") toggleLeft("briefs");
    else if (ev.key === ",") admin.toggle();
    else if (ev.key === "q" || ev.key === "Q") $("#btn-ask").click();
    else if (ev.key === "m" || ev.key === "M") memory.setOpen(!memory.isOpen());
    else if (ev.key === " ") { ev.preventDefault(); doPlay(); }
    else if (ev.key === "ArrowRight" && ev.shiftKey) { ev.preventDefault(); timeline.stepForward(); }
    else if (ev.key === "ArrowLeft" && ev.shiftKey) { ev.preventDefault(); timeline.stepBack(); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); doStep(); }
    else if (ev.key === "u" || ev.key === "U") update.open();
    else if (ev.key === "1") renderer.setDetail("super");
    else if (ev.key === "2") renderer.setDetail("entity");
    else if (ev.key === "3") renderer.setDetail("sub");
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
}

boot().catch((err) => {
  console.error(err);
  const c = document.querySelector("#caption .text");
  if (c) c.textContent = `Could not start the demo: ${err.message}`;
});
