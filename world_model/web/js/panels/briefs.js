// Forecast briefs (addition). A written reading of a forecast in the left sidebar, built by the server from what the model
// holds (GET /api/forecasts/{id}/brief). DECISION (Oct 14, review meeting): the brief is short, and keeps what a PM needs:
// what moves, when, through which transmission path, and how sure. The bottom line comes first; then the transmission
// path, which the reader can rewind order by order and watch build up; then the timeline as a table (when → what moves →
// by how much → order and path); then who is affected, what to watch, what would change the view, and the news. The
// "Why" list, "Most moved overall", and "How it travels" are gone: the transmission path says all three once.
// Readers can annotate a section or a line of the timeline; notes are kept on the server with the forecast and logged in
// the ledger as records that change no state, so inference never learns from them. Edit reopens Ask with the thesis
// filled in; Re-run poses it again at the latest committed version, and the earlier forecast stays one click away.
// Selecting text in a brief offers "Ask about this", a chat mock-up that is not implemented yet.
import { api } from "../api.js";
import { qualifiedHtml } from "../names.js";
import { emit, on } from "../store.js";
import { errorText, esc, fmt } from "../util.js";

const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "");
const arrow = (v, unit = "sd") => (Math.abs(v) < 0.005 ? `<span class="faint">≈ 0</span>`
  : `<span class="${v > 0 ? "z-up" : "z-down"}">${v > 0 ? "▲" : "▼"} ${fmt(Math.abs(v))}${unit ? ` ${unit}` : ""}</span>`);
const ORD_SHORT = (n) => (n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`);
const SCEN = ["#E8CFEC", "#DCE6F0", "#F7E1D3", "#E1ECDF"];

export function initBriefs({ openLeft, onWalk, onChat, focusNode, openForecast, onEdit, onRerun }) {
  const body = document.getElementById("briefs-body");
  const panel = document.getElementById("left-panel");
  const counters = [document.getElementById("briefs-count"), document.getElementById("briefs-count-tab")];
  let list = [];
  let openId = null;
  let writing = null;            // the forecast being computed: {scope, question, phase}
  const cache = new Map();
  let noting = null;             // the anchor a note is being written for

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
    // an open brief already on screen is left as it is (Oct 14): redrawing it for news about other forecasts replaced the
    // text a person was reading or selecting, which dropped the selection
    const shown = openId && body.querySelector(`.brief[data-brief="${CSS.escape(openId)}"]`);
    if (!panel.hidden && panel.dataset.tab === "briefs" && !shown) render();
  }

  let onCanvas = null;           // the brief whose transmission path the canvas shows
  function render() {
    panel.classList.toggle("wide", !!openId && panel.dataset.tab === "briefs");
    // opening a brief lays its forecast's transmission path out on the canvas (main.js), once per brief opened
    if (openId && openId !== onCanvas && panel.dataset.tab === "briefs" && !panel.hidden) emit("brief-canvas", openId);
    onCanvas = openId;
    if (openId) renderBrief(openId);
    else renderList();
  }

  function renderList() {
    body.innerHTML = `
      <div class="group-label">Forecast briefs</div>
      <p class="small muted">A concise reading of each forecast: what moves, when, through which channels, and with what confidence.
        Add a note to any section or line; select any text to ask about it.</p>
      ${writing ? `<div class="card brief-card writing"><div class="meta"><span class="spinner" aria-hidden="true"></span>
        <span>Writing the brief…</span><span class="spacer"></span><span class="faint">${esc(writing.phase ?? "")}</span></div>
        <div class="title">${esc(writing.question ?? "")}</div></div>` : ""}
      ${list.length ? "" : `<p class="empty">No forecasts yet. Ask a question (Q).</p>`}
      ${list.map((f) => `<article class="card selectable brief-card" data-fc="${esc(f.id)}" tabindex="0" title="Open the brief">
        <div class="title">${esc(f.question || f.thesis_id)}</div>
        <div class="meta"><span>${esc(day(f.created))}</span><span class="faint">v${esc(f.version)}</span><span class="spacer"></span>
          <span class="mono faint">${esc(f.id)}</span></div>
        ${cache.has(f.id) ? `<div class="small muted">${esc(cache.get(f.id).bottom_line.split(". ")[0])}.</div>` : ""}
      </article>`).join("")}`;
    for (const card of body.querySelectorAll("[data-fc]")) {
      const go = () => { openId = card.dataset.fc; render(); };
      card.addEventListener("click", go);
      card.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
    }
  }

  // -- annotations -------------------------------------------------------------------------------------------------
  const notesFor = (b, anchor) => (b.annotations ?? []).filter((n) => n.anchor === anchor);
  const noteBtn = (anchor, label = "Note") => `<button class="ghost note-btn" data-note="${esc(anchor)}" title="Add a note here (kept with this forecast; never learned)" aria-label="Add a note">✎ ${esc(label)}</button>`;
  function notesHtml(b, anchor) {
    const ns = notesFor(b, anchor);
    const form = noting === anchor ? `<form class="note-form" data-form="${esc(anchor)}">
        <textarea rows="2" maxlength="2000" placeholder="Your note on this ${anchor.startsWith("row:") ? "line" : "section"}" aria-label="Note"></textarea>
        <div class="row"><button class="small primary" type="submit">Save note</button><button class="small ghost" type="button" data-cancel>Cancel</button>
          <span class="faint small">Kept with this forecast. The model never learns from notes.</span></div></form>` : "";
    return ns.length || form ? `<div class="notes">${ns.map((n) => `<div class="note"><span class="note-txt">${esc(n.text)}</span>
        <span class="faint small">${esc(n.by)} · ${esc(day(n.created_at))}</span>
        <button class="ghost x" data-unnote="${esc(n.id)}" aria-label="Delete this note" title="Delete this note">✕</button></div>`).join("")}${form}</div>` : "";
  }
  const head = (b, title, anchor, extra = "") => `<div class="b-head"><h4>${title}</h4>${extra}<span class="spacer"></span>${noteBtn(anchor)}</div>${notesHtml(b, anchor)}`;

  // -- the transmission path (Oct 15): drawn on the canvas, laid out as the grid is; the brief only points to it
  function transmissionHtml(b) {
    const n = b.transmission?.steps?.length ?? 0;
    if (!n) return "";
    const wl = b.transmission.watchlist;
    const c = wl?.counts ?? {};
    return `<section data-sec="paths">${head(b, "Transmission path", "section:paths",
        `<button class="small" data-act="canvas" title="Lay the transmission path out on the canvas again">Show on the canvas</button>
         <button class="small ghost" data-act="grid" title="The same path as a grid, moving day by day (G)">As a grid</button>`)}
      <p class="small muted">Laid out on the canvas from the shock (left) through each order to the outputs (right), with each value's
        peak effect.${wl ? ` ${esc(wl.name)}: ${c.moves ?? 0} names move, ${c.small ?? 0} marginally, ${(c.negligible ?? 0) + (c.no_path ?? 0)} are not reached.` : ""}</p>
    </section>`;
  }

  // -- the timeline, as a table ---------------------------------------------------------------------------------------
  function timelineHtml(b) {
    if (!b.timeline.length) return "";
    const year = new Date(b.posed_at).getUTCFullYear();
    const short = (iso) => {
      if (!iso) return "";
      const d = new Date(iso);
      return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", ...(d.getUTCFullYear() !== year ? { year: "2-digit" } : {}), timeZone: "UTC" });
    };
    const row = (r) => {
      const anchor = `row:${r.ref}`;
      const ns = notesFor(b, anchor);
      // the path up to this value: where it comes from, and the last interaction's verb (the value itself is in the row)
      const path = r.kind === "value" && r.path.length
        ? `from ${r.path.slice(0, -1).map(esc).join(" → ")}${r.via.length ? `, <i class="via">${esc(r.via.at(-1))}</i>` : ""}`
        : `<span class="faint">average of ${r.members ?? "its"} values</span>`;
      return `<tr data-row="${esc(r.ref)}">
          <td class="mono nowrap">${esc(short(r.onset))}</td>
          <td>${r.kind === "value" ? `<a href="#" data-node="${esc(r.ref)}">${r.entity ? qualifiedHtml(r.name, r.entity) : esc(r.name)}</a>`
            : `<span class="k">${esc(r.kind)}</span> ${esc(r.name)}`}</td>
          <td class="nowrap">${arrow(r.peak)}<div class="faint small">peak ${esc(short(r.peak_date))}</div></td>
          <td class="small">${r.order ? `<span class="tl-ord o${Math.min(3, r.order)}">${ORD_SHORT(r.order)}</span> ` : ""}${path}</td>
          <td class="tl-note">${noteBtn(anchor, "")}</td></tr>
        ${ns.length || noting === anchor ? `<tr class="tl-notes"><td></td><td colspan="4">${notesHtml(b, anchor)}</td></tr>` : ""}`;
    };
    return `<section data-sec="timeline">${head(b, "Expected timing", "section:timeline")}
      <table class="tl-table"><thead><tr><th title="When the effect is half in">Onset</th><th>Value</th><th title="The median effect at its peak, in sd of the value">Peak effect</th>
        <th title="The order (how many interactions from the shock) and the channel that carries it">Order · channel</th><th></th></tr></thead>
      <tbody>${b.timeline.map(row).join("")}</tbody></table></section>`;
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
    const sub = (x) => `<a href="#" data-node="${esc(x.id)}">${x.entity ? qualifiedHtml(x.name, x.entity) : esc(x.name)}</a>`;
    const evCard = (e) => `<div class="ev">
        <div class="meta"><span class="rel" title="relevance ${fmt(e.relevance)}"><i style="width:${Math.round(e.relevance * 100)}%"></i></span>
          <span class="faint">${esc(day(e.published_at))}</span>${e.after ? `<span class="badge ${e.stance === "supports" ? "wm" : e.stance === "pushes against" ? "front" : ""}">${esc(e.stance)}</span>` : ""}
          <span class="spacer"></span><button class="ghost small" data-walk="${esc(e.id)}" title="Step through how the model incorporated this item">How it learned ▸</button></div>
        <div class="title">${esc(e.headline)}</div>
        <ul class="reasons">${e.reasons.slice(0, 2).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
    const runs = b.runs ?? [];
    const at = runs.findIndex((r) => r.id === id);
    const newer = at >= 0 && at < runs.length - 1 ? runs[runs.length - 1] : null;
    const news = b.shaped_by.length + b.since.length + b.tracking.length;
    body.innerHTML = `<article class="brief" data-brief="${esc(id)}">
      <button class="ghost small back">◀ All briefs</button>
      <div class="group-label">Forecast brief · ${esc(b.thesis_id)} · ${esc(b.forecast_id)}${runs.length > 1 ? ` · run ${at + 1} of ${runs.length}` : ""}</div>
      <h3>${esc(b.question)}</h3>
      <div class="small muted">Posed ${esc(day(b.posed_at))} at v${b.version} · ${b.horizon_days} days ahead, to ${esc(day(b.horizon))}</div>
      <div class="b-acts">
        <button class="small" data-act="edit" title="Reopen Ask with this thesis filled in: question, shocks, targets, horizon">Edit</button>
        <button class="small" data-act="rerun" title="Pose the same thesis again at the latest committed version (v${b.latest_version}); this forecast stays">Re-run${b.latest_version !== b.version ? ` at v${b.latest_version}` : ""}</button>
        <button class="small ghost" data-act="charts" title="The forecast's charts, on the right">Charts ▸</button>
        <button class="small ghost hyp" data-act="walk" title="Step through how the model made this forecast">How it inferred ▸</button>
        ${runs.length > 1 ? `<span class="small faint b-runs">runs ${runs.map((r, i) => (r.id === id ? `<b>#${i + 1}</b>` : `<a href="#" data-run="${esc(r.id)}" title="${esc(r.id)} at v${r.version}">#${i + 1}</a>`)).join(" ")}</span>` : ""}
      </div>
      ${newer ? `<p class="small b-newer">A newer run of this thesis exists (v${newer.version}). <a href="#" data-run="${esc(newer.id)}">Open it ▸</a></p>` : ""}
      <section data-sec="bottom">${head(b, "Summary", "section:bottom")}<p class="lede">${esc(b.bottom_line)}</p>
        ${b.scenarios.length > 1 ? `<div class="weightbar small" title="Confidence: the scenarios the forecast mixes, by weight">${b.scenarios.map((s, i) => `<div style="width:${(s.weight * 100).toFixed(1)}%;background:${SCEN[i % 4]}" title="${esc(s.name)}: ${Math.round(s.weight * 100)}%">${s.weight > 0.16 ? esc(`${s.name.split(" · ")[0]} ${Math.round(s.weight * 100)}%`) : ""}</div>`).join("")}</div>` : ""}</section>
      ${transmissionHtml(b)}
      ${timelineHtml(b)}
      ${b.affected.length ? `<section data-sec="affected">${head(b, "Exposures", "section:affected")}
        ${b.affected.map((a) => `<div class="small b-aff"><span class="pick ${["sector", "superentity", "category"].includes(a.kind) ? a.kind : "actor"}"><span class="k">${esc(a.kind)}</span>${esc(a.name)}</span>
          ${arrow(a.effect)} on average${a.top.length ? `, led by ${a.top.slice(0, 2).map((t) => `${esc(t.name)} ${arrow(t.effect)}`).join(", ")}` : ""}</div>`).join("")}</section>` : ""}
      ${b.watch.length || b.change.length ? `<section data-sec="watch">${head(b, "Indicators and risks to the view", "section:watch")}
        <ul class="wlist">${b.watch.map((w) => `<li>${sub(w)}${w.direction ? `, expected to ${w.direction === "up" ? "rise" : "decline"}` : ""} <span class="faint">· ${esc(w.why)}</span></li>`).join("")}
        ${b.change.map((c) => `<li class="b-change">${esc(c.text)}${c.kind === "hypothesis" ? ` <span class="faint small">p ${fmt(c.probability)}</span>` : ""}</li>`).join("")}</ul></section>` : ""}
      <details class="section fold" data-sec="news" ${notesFor(b, "section:news").length ? "open" : ""}><summary><h4>Evidence and subsequent developments <span class="faint small">${news ? `${b.shaped_by.length + b.since.length} items` : "none"}</span></h4></summary>
        ${notesHtml(b, "section:news")}
        ${b.shaped_by.length ? b.shaped_by.map(evCard).join("") : `<p class="small muted">No research to date bears on its drivers; the view rests on the model as calibrated.</p>`}
        ${b.tracking.length ? `<div class="small muted" style="margin:8px 0 4px">Realized values against the forecast:</div>${b.tracking.map((t) => `<div class="track ${t.where.startsWith("inside") ? "ok" : "off"}">
          ${sub(t)}: ${fmt(t.realized)} sd after ${t.days} days, ${esc(t.where)}</div>`).join("")}` : ""}
        ${b.since.length ? `<div class="small muted" style="margin:8px 0 4px">Developments since the forecast:</div>${b.since.map(evCard).join("")}` : ""}
        <div style="margin-top:4px">${noteBtn("section:news")}</div></details>
      <details class="section fold"><summary><h4>Caveats and assumptions</h4></summary><ul class="wlist small">${b.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>
      <p class="small faint">Select any text to ask about it.</p>
    </article>`;
    wire(b, id);
  }

  function wire(b, id) {
    body.querySelector(".back").addEventListener("click", () => { openId = null; noting = null; render(); });
    body.querySelector('[data-act="charts"]').addEventListener("click", () => openForecast?.(id));
    body.querySelector('[data-act="walk"]').addEventListener("click", () => onWalk?.(b.thesis_id));
    body.querySelector('[data-act="edit"]').addEventListener("click", () => onEdit?.({ thesis_id: b.thesis_id, forecast_id: id }));
    body.querySelector('[data-act="rerun"]').addEventListener("click", (ev) => {
      ev.currentTarget.disabled = true;
      ev.currentTarget.textContent = "Re-running…";
      onRerun?.(id);
    });
    body.querySelector('[data-act="grid"]')?.addEventListener("click", () => emit("paths-open", { kind: "forecast", id }));
    for (const a of body.querySelectorAll("[data-node]")) {
      a.addEventListener("click", (ev) => { ev.preventDefault(); focusNode?.(a.dataset.node); });
    }
    for (const a of body.querySelectorAll("[data-run]")) a.addEventListener("click", (ev) => { ev.preventDefault(); openId = a.dataset.run; noting = null; render(); });
    for (const w of body.querySelectorAll("[data-walk]")) w.addEventListener("click", () => onWalk?.(w.dataset.walk));
    body.querySelector('[data-act="canvas"]')?.addEventListener("click", () => emit("brief-canvas", id));
    // notes
    for (const n of body.querySelectorAll("[data-note]")) n.addEventListener("click", () => { noting = n.dataset.note; renderBrief(id).then(focusNote); });
    for (const f of body.querySelectorAll("[data-form]")) {
      f.querySelector("[data-cancel]").addEventListener("click", () => { noting = null; renderBrief(id); });
      f.querySelector("textarea").addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") { ev.stopPropagation(); noting = null; renderBrief(id); }
        if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) f.requestSubmit();
      });
      f.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const text = f.querySelector("textarea").value.trim();
        if (!text) return;
        try {
          const note = await api.annotate(id, f.dataset.form, text);
          b.annotations = [...(b.annotations ?? []), note];
          noting = null;
          renderBrief(id);
        } catch (err) { f.insertAdjacentHTML("beforeend", `<div class="error small">${esc(errorText(err))}</div>`); }
      });
    }
    for (const x of body.querySelectorAll("[data-unnote]")) x.addEventListener("click", async () => {
      try {
        await api.removeAnnotation(id, x.dataset.unnote);
        b.annotations = (b.annotations ?? []).filter((n) => n.id !== x.dataset.unnote);
        renderBrief(id);
      } catch (err) { console.warn(err); }
    });
  }
  function focusNote() { body.querySelector(".note-form textarea")?.focus({ preventScroll: false }); }

  // selecting text in a brief offers "Ask about this"
  document.addEventListener("mouseup", () => {
    setTimeout(() => {
      const sel = window.getSelection();
      const text = sel?.toString().trim() ?? "";
      const node = sel?.anchorNode?.parentElement;
      if (!text || text.length < 3 || !node?.closest?.(".brief") || node.closest(".note-form")) { askBtn.classList.add("hidden"); return; }
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
  // a forecast is in: the list updates; the brief waits to be asked for (Oct 14: the first view is the transmission path)
  on("brief-ready", () => refresh());
  on("tab-left", (name) => { if (name === "briefs") render(); else if (name !== "review") panel.classList.remove("wide"); });
  refresh();
  return {
    refresh,
    invalidate() { cache.clear(); },
    render,
    open(id) { openId = id; noting = null; openLeft("briefs"); render(); },
  };
}
