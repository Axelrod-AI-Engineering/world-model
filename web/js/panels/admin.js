// Admin (addition). DECISION: the user asked to replace the categories widget with an admin window that
// can be minimized or popped out and that makes the main idea easy to navigate. It has four tabs: Story
// (every scripted step, with walkthroughs of the ones that ran), Map (the eight categories, the
// superentities grouped by what they are, the actors, and the key of symbols), View (detail, layout,
// labels, undo and redo), and Settings (the guide, animation, review, scenario, and the other panels).
// It starts minimized to its title bar; "⧉" moves it into its own browser window, where it keeps
// working (its handlers live in this page), and closing that window brings it back.
import { api } from "../api.js";
import { CATEGORY_BLURBS, CATEGORY_CODES, CATEGORY_NAMES } from "../graph/layouts.js";
import { SYMBOLS } from "../graph/legend.js";
import { paletteOf } from "../graph/hulls.js";
import { on, store } from "../store.js";
import { esc } from "../util.js";

const KEY = "axelrod.admin";
const ACTOR_KINDS = new Set(["company", "agency", "person"]);
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { return {}; } };
const save = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* per session only */ } };

export function initAdmin({ renderer, actions }) {
  const stage = document.getElementById("stage");
  const win = document.createElement("section");
  win.id = "admin";
  win.className = "admin";
  win.setAttribute("role", "dialog");
  win.setAttribute("aria-label", "Admin");
  stage.appendChild(win);
  const saved = load();
  let state = { mode: saved.mode ?? "min", tab: saved.tab ?? "story", x: saved.x ?? null, y: saved.y ?? null };
  let script = [];
  let popup = null;
  const persist = () => save({ mode: state.mode, tab: state.tab, x: state.x, y: state.y });

  function frame() {
    win.classList.toggle("minimized", state.mode === "min");
    win.classList.toggle("hidden", state.mode === "closed");
    win.classList.toggle("popped", !!popup);
    if (!popup && state.x != null && state.y != null) {
      const maxX = Math.max(0, stage.clientWidth - 120);
      const maxY = Math.max(0, stage.clientHeight - 40);
      win.style.left = `${Math.min(maxX, Math.max(0, state.x))}px`;
      win.style.top = `${Math.min(maxY, Math.max(0, state.y))}px`;
      win.style.bottom = "auto";
    } else if (!popup) {
      // docked: bottom-left of the canvas, beside the left panel when it is open
      const lp = document.getElementById("left-panel");
      const off = lp && !lp.hidden ? lp.getBoundingClientRect().right - stage.getBoundingClientRect().left + 10 : 14;
      win.style.left = `${Math.round(off)}px`;
      win.style.top = "";
      win.style.bottom = "";
    }
    document.getElementById("btn-admin")?.setAttribute("aria-expanded", String(state.mode === "open"));
  }

  function render() {
    win.innerHTML = `
      <header class="bar">
        <span class="grip" aria-hidden="true">⋮⋮</span><b>Admin</b><span class="sub">navigate the model</span><span class="spacer"></span>
        ${popup ? "" : `<button data-a="pop" title="Pop out into its own window" aria-label="Pop out">⧉</button>`}
        <button data-a="min" title="${state.mode === "min" ? "Expand" : "Minimize"}" aria-label="${state.mode === "min" ? "Expand" : "Minimize"}">${state.mode === "min" ? "▴" : "–"}</button>
        ${popup ? "" : `<button data-a="close" title="Close (reopen with Admin or ,)" aria-label="Close">✕</button>`}
      </header>
      <nav class="tabs" role="tablist">${[["story", "Story"], ["map", "Map"], ["view", "View"], ["settings", "Settings"]]
        .map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${l}</button>`).join("")}</nav>
      <div class="body">${state.tab === "story" ? storyTab() : state.tab === "map" ? mapTab() : state.tab === "view" ? viewTab() : settingsTab()}</div>`;
    bind();
    frame();
  }

  // -- tabs ---------------------------------------------------------------------------------------------
  function stepScopes(i) {
    // the news and questions a step produced: trace events between its caption and the next one
    const caps = store.traces.filter((e) => e.kind === "scenario.caption");
    const start = caps.find((e) => e.payload.step_index === i)?.seq;
    if (start == null) return [];
    const next = caps.find((e) => e.seq > start)?.seq ?? Infinity;
    const out = [];
    for (const e of store.traces) {
      if (e.seq <= start || e.seq >= next || !e.scope || out.includes(e.scope)) continue;
      if (/^T-/.test(e.scope) || (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope))) out.push(e.scope);
    }
    return out;
  }

  function storyTab() {
    const st = store.status ?? {};
    const at = st.step_index ?? 0;
    const kinds = { update: "news", question: "question", hypothesis: "what if", evaluation: "evaluate", decision: "decision", caption: "intro" };
    return `
      <div class="row story-ctl"><span class="mono small">${at} / ${st.total_steps ?? script.length}</span>
        <span class="small muted">${esc(st.state ?? "")}</span><span class="spacer"></span>
        <button data-a="step" ${st.state === "running" || st.state === "awaiting_review" || st.state === "done" ? "disabled" : ""}>Step ▸</button>
        <button data-a="play">${st.state === "running" ? "Pause" : "Play"}</button></div>
      <ol class="story">${script.map((s) => {
        const done = s.index < at;
        const cur = s.index === at;
        const scopes = done ? stepScopes(s.index) : [];
        return `<li class="${done ? "done" : cur ? "cur" : "todo"}">
          <div class="meta"><span class="mono">${s.index}</span><span class="badge">${esc(kinds[s.kind] ?? s.kind)}</span>
            <span class="faint">${esc(new Date(s.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }))}</span></div>
          <div class="cap">${esc(s.caption)}</div>
          ${scopes.length ? `<div class="row">${scopes.slice(0, 3).map((sc) => `<button class="ghost small" data-walk="${esc(sc)}">${/^T-/.test(sc) ? "How it forecast" : "How it learned"} ▸</button>`).join("")}</div>` : ""}
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
      <div class="seg" role="group"><button data-layout="figure1" aria-pressed="${store.settings.layout === "figure1"}">Figure 1</button>
        <button data-layout="gravity" aria-pressed="${store.settings.layout === "gravity"}">Gravity</button></div>
      <div class="toggles">
        ${tog("candidates", "Candidate superentities", store.settings.showCandidates)}
        ${tog("labels", "Every link label", document.body.classList.contains("labels"))}
        ${tog("f1links", "Figure 1 links only", store.settings.figure1LinksOnly)}
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
  function bind() {
    const $$ = (sel) => win.querySelectorAll(sel);
    for (const b of $$("[data-tab]")) b.addEventListener("click", () => { state.tab = b.dataset.tab; persist(); render(); });
    for (const b of $$("header [data-a]")) {
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const a = b.dataset.a;
        if (a === "min") setMode(state.mode === "min" ? "open" : "min");
        else if (a === "close") setMode("closed");
        else if (a === "pop") popOut();
      });
    }
    win.querySelector("header").addEventListener("dblclick", () => setMode(state.mode === "min" ? "open" : "min"));
    const act = {
      step: actions.step, play: actions.play, fit: actions.fit, zin: () => actions.zoom(1.25), zout: () => actions.zoom(0.8),
      undo: actions.undo, redo: actions.redo, hyps: actions.hypotheses, decs: actions.decisions, methods: actions.methods,
      keys: actions.shortcuts, "guide-again": actions.guideAgain,
    };
    for (const b of $$(".body [data-a]")) b.addEventListener("click", () => { act[b.dataset.a]?.(); setTimeout(render, 60); });
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
    for (const b of $$("[data-toggle]")) b.addEventListener("click", () => { renderer.toggleGroup(b.dataset.toggle); setTimeout(render, 80); });
    for (const b of $$("[data-node]")) b.addEventListener("click", () => actions.focusNode(b.dataset.node));
    for (const b of $$("[data-detail]")) b.addEventListener("click", () => { renderer.setDetail(b.dataset.detail); setTimeout(render, 60); });
    for (const b of $$("[data-layout]")) b.addEventListener("click", () => { actions.setLayout(b.dataset.layout); render(); });
    for (const b of $$("[data-guide]")) b.addEventListener("click", () => { actions.setGuideMode(b.dataset.guide); render(); });
    for (const b of $$("[data-speed]")) b.addEventListener("click", () => { actions.setSpeed(+b.dataset.speed); render(); });
    for (const b of $$("[data-policy]")) b.addEventListener("click", async () => { await actions.setPolicy(b.dataset.policy); render(); });
    for (const b of $$("[data-load]")) b.addEventListener("click", () => actions.loadScenario(b.dataset.load));
    for (const c of $$("[data-tog]")) {
      c.addEventListener("change", () => {
        const k = c.dataset.tog;
        if (k === "candidates") actions.setCandidates(c.checked);
        else if (k === "labels") document.body.classList.toggle("labels", c.checked);
        else if (k === "f1links") actions.setFigure1Links(c.checked);
        else if (k === "reduced") actions.setReducedMotion(c.checked);
      });
    }
    dragOn(win.querySelector("header"));
  }

  function dragOn(handle) {
    if (popup) return;
    handle.addEventListener("pointerdown", (ev) => {
      if (ev.button || ev.target.closest("button")) return;
      const r = win.getBoundingClientRect();
      const s = stage.getBoundingClientRect();
      const dx = ev.clientX - r.left;
      const dy = ev.clientY - r.top;
      handle.setPointerCapture(ev.pointerId);
      const move = (e) => {
        state.x = e.clientX - s.left - dx;
        state.y = e.clientY - s.top - dy;
        frame();
      };
      const up = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        persist();
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
  }

  function setMode(mode) {
    state.mode = mode;
    persist();
    render();
  }

  // -- pop out: the same element moves into its own window and keeps working ---------------------------------
  function popOut() {
    const w = window.open("", "axelrod-admin", "popup=yes,width=380,height=720");
    if (!w) { actions.toast?.("The browser blocked the pop-up; allow pop-ups for this page to pop the Admin window out."); return; }
    const base = location.href.replace(/[#?].*$/, "").replace(/[^/]*$/, "");
    w.document.open();
    w.document.write(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Axelrod · Admin</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,600;12..96,700&family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap">
      <link rel="stylesheet" href="${base}css/tokens.css"><link rel="stylesheet" href="${base}css/app.css"></head>
      <body class="admin-window"></body></html>`);
    w.document.close();
    popup = w;
    state.mode = "open";
    w.document.body.appendChild(w.document.adoptNode(win));
    render();
    const back = () => {
      if (!popup) return;
      popup = null;
      stage.appendChild(document.adoptNode(win));
      render();
    };
    w.addEventListener("pagehide", back);
    const poll = setInterval(() => { if (w.closed) { clearInterval(poll); back(); } }, 600);
    window.addEventListener("beforeunload", () => { try { w.close(); } catch { /* already closed */ } });
  }

  // keep it current
  let timer = null;
  const later = () => { clearTimeout(timer); timer = setTimeout(() => { if (state.mode === "open") render(); }, 250); };
  on("status", later);
  on("graph", later);
  on("caption", later);
  // follow the left panel as it opens, closes, or widens for a brief
  const lp = document.getElementById("left-panel");
  if (lp) new MutationObserver(() => frame()).observe(lp, { attributes: true, attributeFilter: ["hidden", "class"] });
  window.addEventListener("resize", () => frame());
  api.script().then((s) => { script = s; render(); }).catch(() => render());
  render();

  return {
    toggle() { setMode(state.mode === "open" ? "min" : "open"); },
    open(tab) { if (tab) state.tab = tab; setMode("open"); },
    isOpen: () => state.mode === "open",
    minimize: () => setMode("min"),
    refresh: render,
  };
}
