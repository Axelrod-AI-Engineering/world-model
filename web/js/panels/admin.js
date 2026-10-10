// Admin (addition). DECISION: the user asked to replace the categories widget with a window that can be
// minimized or enlarged and that makes the main idea easy to navigate. It has four tabs: Story (every
// scripted step, with walkthroughs of the ones that ran), Map (the eight categories, the superentities
// grouped by what they are, the actors, and the key of symbols), View (detail, layout, labels, undo and
// redo), and Settings (the guide, animation, review, scenario, and the other panels).
// It behaves like an ordinary window, with nothing to learn: minimize (a small bar docked bottom-left;
// click it to open), maximize or restore (double-click the title bar too), and close (the Admin button or
// "," brings it back). Open, it docks bottom-left or stays where it is dragged, always wholly on screen;
// dropping it near its dock docks it again.
import { api } from "../api.js";
import { CATEGORY_BLURBS, CATEGORY_CODES, CATEGORY_NAMES } from "../graph/layouts.js";
import { SYMBOLS } from "../graph/legend.js";
import { paletteOf } from "../graph/hulls.js";
import { on, stepShown, store } from "../store.js";
import { esc } from "../util.js";

const KEY = "axelrod.admin";
const ACTOR_KINDS = new Set(["company", "agency", "person"]);
const MODES = new Set(["min", "open", "max", "closed"]);
const MARGIN = 8;
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { return {}; } };
const save = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* per session only */ } };

const ICON = {
  min: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 9.5h7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  max: `<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="2.25" y="2.25" width="7.5" height="7.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>`,
  restore: `<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="1.75" y="4.25" width="6" height="6" rx="1" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4.25 4.25V2.25h6v6H7.75" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  close: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  up: `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 7.5l3-3 3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

export function initAdmin({ renderer, actions }) {
  const stage = document.getElementById("stage");
  const win = document.createElement("section");
  win.id = "admin";
  win.className = "admin";
  win.setAttribute("role", "dialog");
  win.setAttribute("aria-label", "Admin");
  stage.appendChild(win);
  const saved = load();
  const state = { mode: MODES.has(saved.mode) ? saved.mode : "min", tab: saved.tab ?? "story",
                  x: Number.isFinite(saved.x) ? saved.x : null, y: Number.isFinite(saved.y) ? saved.y : null };
  let script = [];
  let lastBody = "";              // the body's last markup: live updates re-render only when it changed
  const scrollByTab = {};         // each tab keeps its own scroll position
  let shownStep = null;           // the story scrolls to the current step when the step changes
  const persist = () => save({ mode: state.mode, tab: state.tab, x: state.x, y: state.y });
  const isUp = () => state.mode === "open" || state.mode === "max";

  // -- placement --------------------------------------------------------------------------------------------
  function dockX() {
    const lp = document.getElementById("left-panel");
    return lp && !lp.hidden ? lp.getBoundingClientRect().right - stage.getBoundingClientRect().left + 10 : 14;
  }
  function clamped() {
    const w = win.offsetWidth || 336;
    const h = win.offsetHeight || 40;
    return {
      x: Math.min(Math.max(MARGIN, state.x), Math.max(MARGIN, stage.clientWidth - w - MARGIN)),
      y: Math.min(Math.max(MARGIN, state.y), Math.max(MARGIN, stage.clientHeight - h - MARGIN)),
    };
  }
  function frame() {
    win.classList.toggle("minimized", state.mode === "min");
    win.classList.toggle("maximized", state.mode === "max");
    win.classList.toggle("hidden", state.mode === "closed");
    // minimized and maximized have fixed places (CSS); only an open window can sit where it was dragged
    if (state.mode === "open" && state.x != null && state.y != null) {
      const c = clamped();
      win.style.left = `${c.x}px`;
      win.style.top = `${c.y}px`;
      win.style.bottom = "auto";
    } else if (state.mode === "max") {
      win.style.left = win.style.top = win.style.bottom = "";
    } else {
      win.style.left = `${Math.round(dockX())}px`;
      win.style.top = "";
      win.style.bottom = "";
    }
    const btn = document.getElementById("btn-admin");
    btn?.setAttribute("aria-expanded", String(isUp()));
  }

  // -- the shell: title bar and tabs (the body is filled by renderBody) -------------------------------------
  function render() {
    if (state.mode === "min") {
      win.innerHTML = `<header class="bar" role="button" tabindex="0" data-a="restore" title="Open Admin (,)">
          <b>Admin</b><span class="ctl">${ICON.up}</span></header>`;
      lastBody = "";
      bindShell();
      frame();
      return;
    }
    const max = state.mode === "max";
    win.innerHTML = `
      <header class="bar" title="${max ? "" : "Drag to move · double-click to maximize"}">
        <b>Admin</b><span class="sub">navigate the model</span><span class="spacer"></span>
        <button data-a="min" title="Minimize" aria-label="Minimize">${ICON.min}</button>
        <button data-a="${max ? "restore" : "max"}" title="${max ? "Restore" : "Maximize"}" aria-label="${max ? "Restore" : "Maximize"}">${max ? ICON.restore : ICON.max}</button>
        <button data-a="close" title="Close (reopen with Admin or ,)" aria-label="Close">${ICON.close}</button>
      </header>
      <nav class="tabs" role="tablist">${[["story", "Story"], ["map", "Map"], ["view", "View"], ["settings", "Settings"]]
        .map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${l}</button>`).join("")}</nav>
      <div class="body"></div>`;
    bindShell();
    lastBody = "";
    renderBody(true);
    frame();
  }

  function bodyHtml() {
    return state.tab === "story" ? storyTab() : state.tab === "map" ? mapTab() : state.tab === "view" ? viewTab() : settingsTab();
  }

  function renderBody(force = false) {
    if (!isUp()) return;
    const body = win.querySelector(".body");
    if (!body) return;
    const html = bodyHtml();
    if (!force && html === lastBody) return;
    const top = lastBody ? body.scrollTop : (scrollByTab[state.tab] ?? 0);
    body.innerHTML = html;
    lastBody = html;
    bindBody(body);
    body.scrollTop = top;
    // keep the current step in view as the story advances
    const at = store.status?.step_index ?? 0;
    if (state.tab === "story" && at !== shownStep) {
      shownStep = at;
      const cur = body.querySelector("li.cur");
      if (cur) {
        const r = cur.getBoundingClientRect();
        const b = body.getBoundingClientRect();
        if (r.top < b.top || r.bottom > b.bottom) body.scrollTop += r.top - b.top - 40;
      }
    }
  }

  // -- tabs ---------------------------------------------------------------------------------------------
  // the news and questions each step produced: trace events between its caption and the next one
  function scopesByStep() {
    const out = new Map();
    let cur = null;
    for (const e of store.traces) {
      if (e.kind === "scenario.caption") {
        cur = e.payload.step_index;
        if (!out.has(cur)) out.set(cur, []);
        continue;
      }
      if (cur == null || !e.scope) continue;
      const arr = out.get(cur);
      if (arr.includes(e.scope)) continue;
      if (/^T-/.test(e.scope) || (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope))) arr.push(e.scope);
    }
    return out;
  }

  function storyTab() {
    const st = store.status ?? {};
    const at = st.step_index ?? 0;
    const kinds = { update: "news", question: "question", hypothesis: "what if", evaluation: "evaluate", decision: "decision", caption: "intro" };
    const scopes = scopesByStep();
    return `
      <div class="row story-ctl"><span class="mono small">${stepShown()} / ${st.total_steps ?? script.length}</span>
        <span class="small muted">${esc(st.state ?? "")}</span><span class="spacer"></span>
        <button data-a="step" ${st.state === "running" || st.state === "awaiting_review" || st.state === "done" ? "disabled" : ""}>Step ▸</button>
        <button data-a="play">${st.state === "running" ? "Pause" : "Play"}</button></div>
      <ol class="story">${script.map((s) => {
        const done = s.index < at;
        const cur = s.index === at;
        const mine = done ? scopes.get(s.index) ?? [] : [];
        return `<li class="${done ? "done" : cur ? "cur" : "todo"}">
          <div class="meta"><span class="mono">${s.index + 1}</span><span class="badge">${esc(kinds[s.kind] ?? s.kind)}</span>
            <span class="faint">${esc(new Date(s.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }))}</span></div>
          <div class="cap">${esc(s.caption)}</div>
          ${mine.length ? `<div class="row">${mine.slice(0, 3).map((sc) => `<button class="ghost small" data-walk="${esc(sc)}">${/^T-/.test(sc) ? "How it inferred" : "How it learned"} ▸</button>`).join("")}</div>` : ""}
        </li>`;
      }).join("")}</ol>`;
  }

  function groupKind(g) {
    if (g.composite) return "Made of superentities";
    if (/^HP\d/.test(g.pattern_id)) return "From history";
    if (g.status === "candidate") return "Candidates";
    const ents = new Map((store.view?.entities ?? []).map((e) => [e.id, e]));
    const actors = [...g.members].filter((m) => ACTOR_KINDS.has(ents.get(m)?.kind) || ents.get(m)?.features?.sector).length;
    return actors >= Math.max(2, g.members.size - 1) ? "Actors together" : "Patterns in the economy";
  }

  function mapTab() {
    const v = store.view;
    const counts = {};
    for (const e of v?.entities ?? []) for (const t of e.category_tags ?? []) counts[t] = (counts[t] ?? 0) + 1;
    const groups = renderer.groupsInfo.groups.filter((g) => !g.transient);
    const order = ["Actors together", "Patterns in the economy", "Made of superentities", "From history", "Candidates"];
    const byKind = new Map(order.map((k) => [k, []]));
    for (const g of groups) byKind.get(groupKind(g))?.push(g);
    const shared = (g) => [...g.members].filter((m) => (renderer.model?.owners.get(m) ?? []).length > 1).length;
    const actors = (v?.entities ?? []).filter((e) => ACTOR_KINDS.has(e.kind) || e.features?.sector);
    return `
      <h4>Categories</h4>
      <div class="cats">${CATEGORY_CODES.map((c) => `<div class="cat" data-cat="${c}" tabindex="0" title="${esc(CATEGORY_BLURBS[c])}">
        <code>${c}</code><span>${esc(CATEGORY_NAMES[c])}</span><span class="n">${counts[c] ?? 0}</span></div>`).join("")}</div>
      <h4>Superentities</h4>
      ${order.filter((k) => byKind.get(k).length).map((k) => `<div class="gk">${esc(k)}</div>${byKind.get(k).map((g) => {
        const p = paletteOf(g, v?.palettes);
        const closed = renderer.ui.collapsed.has(g.key);
        const sh = shared(g);
        return `<div class="grow-row" data-group="${esc(g.key)}" tabindex="0">
          <span class="sw" style="background:${p.fill};border-color:${p.line}"></span>
          <span class="nm">${esc(g.label)}</span>
          <span class="n faint">${g.members.size}${sh ? ` · ${sh} shared` : ""}</span>
          <button class="ghost small" data-toggle="${esc(g.key)}" title="${closed ? "Open it" : "Close it into a card"}">${closed ? "open" : "close"}</button></div>`;
      }).join("")}`).join("")}
      <h4>Actors</h4>
      <div class="chips">${actors.map((e) => `<button class="pick actor" data-node="${esc(e.id)}">${esc(e.name)}</button>`).join("")}</div>
      <details class="section fold"><summary><h4>Key of symbols</h4></summary>
        <div class="syms">${SYMBOLS.map(([label, svg]) => `<div class="sym">${svg}<span>${esc(label)}</span></div>`).join("")}</div></details>`;
  }

  function viewTab() {
    const lv = renderer.detailLevel?.();
    const u = renderer.undoStack.at(-1)?.label;
    const r = renderer.redoStack.at(-1)?.label;
    const tog = (k, label, onv) => `<label class="tog"><input type="checkbox" data-tog="${k}" ${onv ? "checked" : ""}> ${esc(label)}</label>`;
    return `
      <h4>Detail</h4>
      <div class="seg" role="group">${[["super", "Superentities"], ["entity", "Entities"], ["sub", "Subentities"]]
        .map(([k, l]) => `<button data-detail="${k}" aria-pressed="${lv === k}">${l}</button>`).join("")}</div>
      <p class="small muted">Or per node: double-click, or right-click for options. Zoom never changes what is open.</p>
      <h4>Camera</h4>
      <div class="row"><button data-a="fit">Fit everything</button><button data-a="zin">Zoom in</button><button data-a="zout">Zoom out</button></div>
      <h4>Layout</h4>
      <div class="seg" role="group"><button data-layout="figure1" aria-pressed="${store.settings.layout === "figure1"}" title="Every node in its place in Figure 1">Figure 1</button>
        <button data-layout="gravity" aria-pressed="${store.settings.layout === "gravity"}" title="Nodes settle where their interactions pull them">Gravity</button></div>
      <div class="toggles">
        ${tog("candidates", "Candidate superentities", store.settings.showCandidates)}
        ${tog("labels", "Every interaction label", document.body.classList.contains("labels"))}
        ${tog("f1links", "Figure 1 interactions only", store.settings.figure1LinksOnly)}
      </div>
      <h4>History</h4>
      <div class="row"><button data-a="undo" ${u ? "" : "disabled"} title="${esc(u ?? "")}">Undo${u ? `: ${esc(u)}` : ""}</button>
        <button data-a="redo" ${r ? "" : "disabled"} title="${esc(r ?? "")}">Redo${r ? `: ${esc(r)}` : ""}</button></div>`;
  }

  function settingsTab() {
    const gm = actions.guideMode();
    const pol = store.config?.review_policy;
    return `
      <h4>The guide</h4>
      <p class="small muted">A raccoon that shows what the model does, step by step, while it forecasts or reads news.</p>
      <div class="seg" role="group">${[["first", "First time"], ["always", "Every time"], ["off", "Off"]]
        .map(([k, l]) => `<button data-guide="${k}" aria-pressed="${gm === k}">${l}</button>`).join("")}</div>
      <div class="row" style="margin-top:6px"><button class="ghost small" data-a="guide-again">Show it on the next forecast</button></div>
      <h4>Story</h4>
      <div class="toggles"><label class="tog"><input type="checkbox" data-tog="captions" ${store.settings.captions !== false ? "checked" : ""}> Story captions above the canvas</label></div>
      <h4>Animation</h4>
      <div class="seg" role="group">${[0.5, 1, 2, 4].map((x) => `<button data-speed="${x}" aria-pressed="${store.settings.speed === x}">${x}×</button>`).join("")}</div>
      <div class="toggles"><label class="tog"><input type="checkbox" data-tog="reduced" ${store.settings.reducedMotion ? "checked" : ""}> Reduced motion</label></div>
      <h4>Review</h4>
      <div class="seg" role="group"><button data-policy="default" aria-pressed="${pol === "default"}">Structural changes wait</button>
        <button data-policy="auto_approve_all" aria-pressed="${pol === "auto_approve_all"}">Approve all</button></div>
      <h4>Scenario</h4>
      <div class="row">${(store.scenarios ?? []).map((s) => `<button class="small" data-load="${esc(s.id)}">Load ${esc(s.title)}</button>`).join("")}</div>
      <h4>Panels</h4>
      <div class="row"><button data-a="hyps">Hypotheses</button><button data-a="decs">Decisions</button>
        <button data-a="methods">Methods</button><button data-a="keys">Shortcuts</button></div>`;
  }

  // -- events ---------------------------------------------------------------------------------------------
  function bindBody(body) {
    const $$ = (sel) => body.querySelectorAll(sel);
    const refresh = () => setTimeout(() => renderBody(true), 60);
    const act = {
      step: actions.step, play: actions.play, fit: actions.fit, zin: () => actions.zoom(1.25), zout: () => actions.zoom(0.8),
      undo: actions.undo, redo: actions.redo, hyps: actions.hypotheses, decs: actions.decisions, methods: actions.methods,
      keys: actions.shortcuts, "guide-again": actions.guideAgain,
    };
    for (const b of $$("[data-a]")) b.addEventListener("click", () => { act[b.dataset.a]?.(); refresh(); });
    for (const b of $$("[data-walk]")) b.addEventListener("click", () => actions.walk(b.dataset.walk));
    for (const row of $$("[data-cat]")) {
      const c = row.dataset.cat;
      row.addEventListener("mouseenter", () => actions.highlightCategory(c));
      row.addEventListener("focus", () => actions.highlightCategory(c));
      row.addEventListener("mouseleave", () => actions.highlightCategory(null));
      row.addEventListener("blur", () => actions.highlightCategory(null));
      row.addEventListener("click", () => actions.frameCategory(c));
    }
    for (const row of $$("[data-group]")) {
      const k = row.dataset.group;
      row.addEventListener("mouseenter", () => renderer.setFocus({ group: k }));
      row.addEventListener("mouseleave", () => renderer.setFocus(null));
      row.addEventListener("click", (ev) => { if (!ev.target.closest("[data-toggle]")) actions.frameGroup(k); });
    }
    for (const b of $$("[data-toggle]")) b.addEventListener("click", () => { renderer.toggleGroup(b.dataset.toggle); refresh(); });
    for (const b of $$("[data-node]")) b.addEventListener("click", () => actions.focusNode(b.dataset.node));
    for (const b of $$("[data-detail]")) b.addEventListener("click", () => { renderer.setDetail(b.dataset.detail); refresh(); });
    for (const b of $$("[data-layout]")) b.addEventListener("click", () => { actions.setLayout(b.dataset.layout); refresh(); });
    for (const b of $$("[data-guide]")) b.addEventListener("click", () => { actions.setGuideMode(b.dataset.guide); refresh(); });
    for (const b of $$("[data-speed]")) b.addEventListener("click", () => { actions.setSpeed(+b.dataset.speed); refresh(); });
    for (const b of $$("[data-policy]")) b.addEventListener("click", async () => { await actions.setPolicy(b.dataset.policy); refresh(); });
    for (const b of $$("[data-load]")) b.addEventListener("click", () => actions.loadScenario(b.dataset.load));
    for (const c of $$("[data-tog]")) {
      c.addEventListener("change", () => {
        const k = c.dataset.tog;
        if (k === "candidates") actions.setCandidates(c.checked);
        else if (k === "labels") document.body.classList.toggle("labels", c.checked);
        else if (k === "f1links") actions.setFigure1Links(c.checked);
        else if (k === "reduced") actions.setReducedMotion(c.checked);
        else if (k === "captions") actions.setCaptions(c.checked);
      });
    }
  }

  function bindShell() {
    const header = win.querySelector("header");
    if (state.mode === "min") {
      // the minimized bar is one button: click it (or Enter) to open
      const open = () => setMode("open");
      header.addEventListener("click", open);
      header.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } });
      return;
    }
    for (const b of win.querySelectorAll("[data-tab]")) {
      b.addEventListener("click", () => {
        const body = win.querySelector(".body");
        if (body) scrollByTab[state.tab] = body.scrollTop;
        state.tab = b.dataset.tab;
        persist();
        render();
      });
    }
    for (const b of header.querySelectorAll("[data-a]")) {
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const a = b.dataset.a;
        if (a === "min") setMode("min");
        else if (a === "max") setMode("max");
        else if (a === "restore") setMode("open");
        else if (a === "close") setMode("closed");
      });
    }
    header.addEventListener("dblclick", (ev) => {
      if (ev.target.closest("button")) return;
      setMode(state.mode === "max" ? "open" : "max");
    });
    if (state.mode === "open") dragOn(header);
  }

  function dragOn(handle) {
    handle.addEventListener("pointerdown", (ev) => {
      if (ev.button || ev.target.closest("button")) return;
      const r = win.getBoundingClientRect();
      const s = stage.getBoundingClientRect();
      const dx = ev.clientX - r.left;
      const dy = ev.clientY - r.top;
      let moved = false;
      handle.setPointerCapture(ev.pointerId);
      const move = (e) => {
        if (!moved && Math.hypot(e.clientX - ev.clientX, e.clientY - ev.clientY) < 3) return;
        moved = true;
        state.x = e.clientX - s.left - dx;
        state.y = e.clientY - s.top - dy;
        frame();
      };
      const up = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", up);
        if (!moved || state.x == null) return;
        const c = clamped();
        state.x = c.x;
        state.y = c.y;
        // dropped near its dock (bottom-left): dock it again
        const bottomGap = stage.clientHeight - (c.y + win.offsetHeight);
        if (Math.abs(c.x - dockX()) < 40 && Math.abs(bottomGap - 14) < 40) { state.x = null; state.y = null; }
        frame();
        persist();
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
      handle.addEventListener("pointercancel", up);
    });
  }

  function setMode(mode) {
    if (!MODES.has(mode) || mode === state.mode) return;
    const wasUp = isUp();
    state.mode = mode;
    persist();
    render();
    // a quick settle-in, so a change of size reads as one window changing, not a jump
    if (!store.settings.reducedMotion && isUp() && (!wasUp || mode === "max" || mode === "open")) {
      win.animate?.([{ opacity: 0.55, transform: "translateY(6px) scale(0.985)" }, { opacity: 1, transform: "none" }],
                    { duration: 130, easing: "ease-out" });
    }
  }

  // keep it current
  let timer = null;
  const later = () => { clearTimeout(timer); timer = setTimeout(() => renderBody(), 250); };
  on("status", later);
  on("graph", later);
  on("caption", later);
  // follow the left panel as it opens, closes, or widens for a brief; and the stage as it resizes
  const lp = document.getElementById("left-panel");
  if (lp) new MutationObserver(() => frame()).observe(lp, { attributes: true, attributeFilter: ["hidden", "class"] });
  window.addEventListener("resize", () => frame());
  if (window.ResizeObserver) new ResizeObserver(() => frame()).observe(stage);
  document.fonts?.ready.then(() => frame());
  api.script().then((s) => { script = s; lastBody = ""; renderBody(true); }).catch(() => {});
  render();

  return {
    // the Admin button and ",": open it if it is minimized or closed, minimize it if it is up
    toggle() { setMode(isUp() ? "min" : "open"); },
    open(tab) { if (tab) state.tab = tab; if (isUp()) render(); else setMode("open"); },
    isOpen: isUp,
    minimize: () => setMode("min"),
    refresh: () => renderBody(),
  };
}
