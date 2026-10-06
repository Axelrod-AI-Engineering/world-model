// Forecast briefs (addition). DECISION: after a question is asked, a written brief opens in the left
// sidebar: the bottom line, what moves and when, who is affected, why, the news that shaped the forecast
// and the news since (with how the realized values track its bands), what to watch, and what would
// change the view. The server builds it from what the model holds (GET /api/forecasts/{id}/brief).
// Selecting text in a brief offers "Ask about this", a chat mock-up that is not implemented yet.
import { api } from "../api.js";
import { on, store } from "../store.js";
import { esc, fmt } from "../util.js";

const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "");
const arrow = (v, unit = "sd") => (Math.abs(v) < 0.005 ? `<span class="faint">≈ 0</span>`
  : `<span class="${v > 0 ? "z-up" : "z-down"}">${v > 0 ? "▲" : "▼"} ${fmt(Math.abs(v))} ${unit}</span>`);

export function initBriefs({ openLeft, onWalk, onChat, focusNode, openForecast }) {
  const body = document.getElementById("briefs-body");
  const panel = document.getElementById("left-panel");
  const counters = [document.getElementById("briefs-count"), document.getElementById("briefs-count-tab")];
  let list = [];
  let openId = null;
  let writing = null;            // the forecast being computed: {scope, question, phase}
  const cache = new Map();
  const asked = new Set();       // thesis ids the user asked in this session: their briefs open by themselves

  const askBtn = document.createElement("button");
  askBtn.className = "ask-sel hidden";
  askBtn.type = "button";
  askBtn.textContent = "Ask about this ▸";
  document.body.appendChild(askBtn);
  let selected = "";
  askBtn.addEventListener("mousedown", (ev) => ev.preventDefault());
  askBtn.addEventListener("click", () => {
    askBtn.classList.add("hidden");
    onChat?.({ quote: selected, source: openId ? `Brief ${openId}` : "Brief" });
  });

  async function refresh() {
    try { list = (await api.forecasts()).slice().reverse(); } catch { return; }
    for (const c of counters) if (c) c.textContent = String(list.length);
    if (!panel.hidden && panel.dataset.tab === "briefs") render();
  }

  function render() {
    panel.classList.toggle("wide", !!openId && panel.dataset.tab === "briefs");
    if (openId) renderBrief(openId);
    else renderList();
  }

  function renderList() {
    body.innerHTML = `
      <div class="group-label">Forecast briefs</div>
      <p class="small muted">A written reading of each forecast: the bottom line, the timeline, who is affected and why, the
        news behind it and since, and what to watch. Select any text in a brief to ask about it.</p>
      ${writing ? `<div class="card brief-card writing"><div class="meta"><span class="spinner" aria-hidden="true"></span>
        <span>Writing the brief…</span><span class="spacer"></span><span class="faint">${esc(writing.phase ?? "")}</span></div>
        <div class="title">${esc(writing.question ?? "")}</div></div>` : ""}
      ${list.length ? "" : `<p class="empty">No forecasts yet. Ask a question (Q), or step the demo to step 13.</p>`}
      ${list.map((f) => `<article class="card selectable brief-card" data-fc="${esc(f.id)}" tabindex="0">
        <div class="meta"><span class="badge hyp">${esc(f.thesis_id)}</span><span class="mono faint">${esc(f.id)}</span>
          <span class="spacer"></span><span>${esc(day(f.created_at))}</span></div>
        <div class="title">${esc(f.question || f.thesis_id)}</div>
        ${cache.has(f.id) ? `<div class="small muted">${esc(cache.get(f.id).bottom_line.split(". ")[0])}.</div>` : ""}
      </article>`).join("")}`;
    for (const card of body.querySelectorAll("[data-fc]")) {
      const go = () => { openId = card.dataset.fc; render(); };
      card.addEventListener("click", go);
      card.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
    }
  }

  async function renderBrief(id) {
    let b = cache.get(id);
    if (!b) {
      body.innerHTML = `<p class="empty"><span class="spinner" aria-hidden="true"></span> Loading the brief…</p>`;
      try { b = await api.brief(id); cache.set(id, b); } catch (err) {
        body.innerHTML = `<p class="error">${esc(err.message)}</p>`;
        return;
      }
      if (openId !== id) return;
    }
    const sub = (x) => `<a href="#" data-node="${esc(x.id)}">${esc(x.name)}</a>`;
    const evCard = (e) => `<div class="ev">
        <div class="meta"><span class="rel" title="relevance ${fmt(e.relevance)}"><i style="width:${Math.round(e.relevance * 100)}%"></i></span>
          <span class="faint">${esc(day(e.published_at))}</span>${e.after ? `<span class="badge ${e.stance === "supports" ? "wm" : e.stance === "pushes against" ? "front" : ""}">${esc(e.stance)}</span>` : ""}
          <span class="spacer"></span><button class="ghost small" data-walk="${esc(e.id)}">How it learned ▸</button></div>
        <div class="title">${esc(e.headline)}</div>
        <ul class="reasons">${e.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
    body.innerHTML = `<article class="brief" data-brief="${esc(id)}">
      <button class="ghost small back">◀ All briefs</button>
      <div class="group-label">Forecast brief · ${esc(b.thesis_id)} · ${esc(b.forecast_id)}</div>
      <h3>${esc(b.question)}</h3>
      <div class="small muted">Posed ${esc(day(b.posed_at))} at v${b.version} · ${b.horizon_days} days ahead, to ${esc(day(b.horizon))}</div>
      <div class="row" style="margin:8px 0 2px"><button class="small" data-act="charts">Charts ▸</button>
        <button class="small hyp" data-act="walk">How it forecast ▸</button></div>
      <section><h4>Bottom line</h4><p class="lede">${esc(b.bottom_line)}</p>
        ${b.scenarios.length > 1 ? `<div class="weightbar small">${b.scenarios.map((s, i) => `<div style="width:${(s.weight * 100).toFixed(1)}%;background:${["#E8CFEC", "#DCE6F0", "#F7E1D3", "#E1ECDF"][i % 4]}" title="${esc(s.name)}">${s.weight > 0.16 ? esc(`${s.name.split(" · ")[0]} ${Math.round(s.weight * 100)}%`) : ""}</div>`).join("")}</div>` : ""}</section>
      ${b.timeline.length ? `<section><h4>What moves, and when</h4><ol class="timeline-list">${b.timeline.map((t) => `<li><span class="mono faint">${esc(day(t.onset))}</span>
        <span>${esc(t.name)} starts to ${t.direction === "up" ? "rise" : "fall"}; ${arrow(t.peak)} at its peak (${esc(day(t.peak_date))})</span></li>`).join("")}</ol></section>` : ""}
      ${b.affected.length || b.movers.length ? `<section><h4>Who is affected</h4>
        ${b.affected.map((a) => `<div class="small" style="margin:3px 0"><span class="pick ${a.kind === "sector" ? "sector" : a.kind === "superentity" ? "superentity" : a.kind === "category" ? "category" : "actor"}"><span class="k">${esc(a.kind)}</span>${esc(a.name)}</span>
          ${arrow(a.effect)} on average${a.top.length ? `, led by ${a.top.map((t) => `${esc(t.name)} ${arrow(t.effect)}`).join(", ")}` : ""}</div>`).join("")}
        ${b.movers.length ? `<p class="small muted" style="margin-top:6px">Most moved overall:</p><div class="chips">${b.movers.map((m) => `<span class="pick actor" title="${esc(m.name)}"><a href="#" data-node="${esc(m.entity)}">${esc(m.entity_name)}</a>${arrow(m.effect)}</span>`).join("")}</div>` : ""}</section>` : ""}
      ${b.why.length ? `<section><h4>Why</h4><ul class="wlist">${b.why.map((w) => `<li>${esc(w.text)} <span class="faint small">${Math.round(w.share * 100)}%</span></li>`).join("")}</ul></section>` : ""}
      <section><h4>The news that shaped it</h4>${b.shaped_by.length ? b.shaped_by.map(evCard).join("") : `<p class="small muted">No news so far touched its drivers: it rests on the history the model was built from.</p>`}</section>
      <section><h4>Since this forecast</h4>
        ${b.tracking.length ? `<div class="small muted" style="margin-bottom:4px">How the realized values track the forecast so far:</div>${b.tracking.map((t) => `<div class="track ${t.where.startsWith("inside") ? "ok" : "off"}">
          ${sub(t)}: ${fmt(t.realized)} sd after ${t.days} days, ${esc(t.where)} <span class="faint">(median ${fmt(t.median)}, 90% ${fmt(t.q05)} to ${fmt(t.q95)})</span></div>`).join("")}`
          : `<p class="small muted">Nothing realized yet: the model has not processed a day since it was posed.</p>`}
        ${b.since.length ? `<div class="small muted" style="margin:8px 0 4px">News since that bears on it:</div>${b.since.map(evCard).join("")}` : ""}</section>
      ${b.watch.length ? `<section><h4>What to watch</h4><ul class="wlist">${b.watch.map((w) => `<li>${sub(w)} (${esc(w.entity)})${w.direction ? `, expected to ${w.direction === "up" ? "rise" : "fall"}` : ""}: ${esc(w.why)}</li>`).join("")}</ul></section>` : ""}
      ${b.change.length ? `<section><h4>What would change the view</h4><ul class="wlist">${b.change.map((c) => `<li>${esc(c.text)}${c.kind === "hypothesis" ? ` <span class="faint small">p ${fmt(c.probability)}</span>` : ""}</li>`).join("")}</ul></section>` : ""}
      <details class="section fold"><summary><h4>Caveats</h4></summary><ul class="wlist small">${b.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>
      <p class="small faint">Select any text to ask about it.</p>
    </article>`;
    body.querySelector(".back").addEventListener("click", () => { openId = null; render(); });
    body.querySelector('[data-act="charts"]').addEventListener("click", () => openForecast?.(id));
    body.querySelector('[data-act="walk"]').addEventListener("click", () => onWalk?.(b.thesis_id));
    for (const a of body.querySelectorAll("[data-node]")) {
      a.addEventListener("click", (ev) => { ev.preventDefault(); focusNode?.(a.dataset.node); });
    }
    for (const w of body.querySelectorAll("[data-walk]")) w.addEventListener("click", () => onWalk?.(w.dataset.walk));
  }

  // selecting text in a brief offers "Ask about this"
  document.addEventListener("mouseup", () => {
    setTimeout(() => {
      const sel = window.getSelection();
      const text = sel?.toString().trim() ?? "";
      const node = sel?.anchorNode?.parentElement;
      if (!text || text.length < 3 || !node?.closest?.(".brief")) { askBtn.classList.add("hidden"); return; }
      selected = text.length > 400 ? `${text.slice(0, 400)}…` : text;
      const r = sel.getRangeAt(0).getBoundingClientRect();
      askBtn.style.left = `${Math.min(window.innerWidth - 150, r.right + 6)}px`;
      askBtn.style.top = `${Math.max(8, r.top - 30)}px`;
      askBtn.classList.remove("hidden");
    }, 0);
  });
  document.addEventListener("mousedown", (ev) => { if (ev.target !== askBtn) askBtn.classList.add("hidden"); });

  on("forecasting", (run) => {
    writing = run && run.phase !== "ready" ? run : null;
    if (!panel.hidden && panel.dataset.tab === "briefs" && !openId) renderList();
    document.getElementById("btn-briefs")?.classList.toggle("busy", !!writing);
  });
  on("brief-ready", async (p) => {
    await refresh();
    if (asked.has(p.thesis_id)) {
      asked.delete(p.thesis_id);
      openId = p.forecast_id;
      openLeft("briefs");
      render();
    }
  });
  on("tab-left", (name) => { if (name === "briefs") render(); else panel.classList.remove("wide"); });
  refresh();
  return {
    refresh,
    render,
    expect(thesisId) { if (thesisId) asked.add(thesisId); },
    open(id) { openId = id; openLeft("briefs"); render(); },
  };
}
