// Update dialog and strip (§13.6, §7.8). An update collects news and data up to a date and folds them in
// day by day; it is the only way the world enters the model. The strip shows the stages and the
// current day, pauses on "awaiting review", and the report lands in the inspector.
import { api } from "../api.js";
import { on, store } from "../store.js";
import { errorText, esc, fmtDate } from "../util.js";

const KIND_LABEL = { news: "News", analyst: "Analyst note", data: "Data release", filing: "Filing" };

export function initUpdate({ openModal, toast, startDraw, openReview, showReport }) {
  const strip = document.getElementById("update-strip");
  let draft = { headline: "", events: [], drawn: [], until: null, sources: null };

  const sim = () => store.status?.sim_time ?? store.graph?.sim_time ?? new Date().toISOString();
  function defaultUntil() {
    // DECISION (§13.6): the next scripted step's date in the demo, else the simulated date
    const nxt = store.status?.next_step_at;
    return String(nxt ?? sim()).slice(0, 10);
  }

  function sources() {
    return store.config?.params?.update?.sources ?? ["mock_web_scraper"];
  }

  function open() {
    if (store.activeUpdate) {
      toast("An update is already running; it finishes first.", "err");
      return;
    }
    if (!draft.until) draft.until = defaultUntil();
    if (!draft.sources) draft.sources = new Set(sources());
    openModal(`
      <h3>Update the model</h3>
      <p class="sub">Collect news and data published up to a date, then fold them in one day at a time.
        Anything that changes the graph's structure waits for your review.</p>
      <div class="form-grid">
        <label for="up-until">Until</label>
        <input id="up-until" type="date" value="${esc(draft.until)}" min="${esc(String(store.graph?.today ?? "").slice(0, 10))}">
        <label>Sources</label>
        <div class="row">${sources().map((s) => `<label class="small"><input type="checkbox" data-src="${esc(s)}" ${draft.sources.has(s) ? "checked" : ""}>
          ${esc(s.replace(/_/g, " "))}</label>`).join("")}</div>
      </div>
      <fieldset><legend>Add news of your own</legend>
        <div class="form-grid">
          <label for="up-head">Headline</label><input id="up-head" type="text" placeholder="e.g. Central bank signals a pause">
          <label for="up-body">Body</label><input id="up-body" type="text" placeholder="optional">
          <label for="up-kind">Kind</label>
          <select id="up-kind">${Object.entries(KIND_LABEL).map(([k, v]) => `<option value="${k}" ${k === "analyst" ? "selected" : ""}>${v}</option>`).join("")}</select>
          <label for="up-pub">Published</label><input id="up-pub" type="datetime-local" title="optional; inside the window">
        </div>
        <div class="row" style="margin-top:8px"><button id="up-attach">Attach</button>
          <button id="up-draw" title="Draw an edge on the canvas and attach it to this update">Draw an edge…</button></div>
        <div class="attached">${[...draft.events.map((e, i) => `<div class="item"><span class="badge">${esc(KIND_LABEL[e.kind] ?? e.kind)}</span>
            <span style="flex:1">${esc(e.headline)}</span><button class="ghost small" data-rm-ev="${i}" aria-label="Remove">✕</button></div>`),
          ...draft.drawn.map((g, i) => `<div class="item"><span class="badge real">Drawn</span><span style="flex:1">${esc(g.ops?.[0]?.label ?? g.id)}</span>
            <button class="ghost small" data-rm-dr="${i}" aria-label="Remove">✕</button></div>`)].join("")}</div>
      </fieldset>
      <div class="error" id="up-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="primary" id="up-run">Run update</button></div>`,
    (root, close) => {
      const keep = () => {
        draft.until = root.querySelector("#up-until").value || draft.until;
        draft.sources = new Set([...root.querySelectorAll("[data-src]")].filter((c) => c.checked).map((c) => c.dataset.src));
      };
      root.querySelector("#up-attach").addEventListener("click", () => {
        const headline = root.querySelector("#up-head").value.trim();
        if (!headline) { root.querySelector("#up-err").textContent = "A headline is required."; return; }
        const pub = root.querySelector("#up-pub").value;
        draft.events.push({ headline, body: root.querySelector("#up-body").value.trim(), kind: root.querySelector("#up-kind").value,
                            ...(pub ? { published_at: `${pub}:00Z` } : {}) });
        keep();
        close();
        open();
      });
      root.querySelector("#up-draw").addEventListener("click", () => {
        keep();
        close();
        startDraw((ev) => { draft.drawn.push(ev); open(); });
      });
      for (const b of root.querySelectorAll("[data-rm-ev]")) b.addEventListener("click", () => { keep(); draft.events.splice(+b.dataset.rmEv, 1); close(); open(); });
      for (const b of root.querySelectorAll("[data-rm-dr]")) b.addEventListener("click", () => { keep(); draft.drawn.splice(+b.dataset.rmDr, 1); close(); open(); });
      root.querySelector("#up-run").addEventListener("click", async () => {
        keep();
        const body = { until: draft.until, sources: [...draft.sources], user_market_events: draft.events,
                       user_graph_update_events: draft.drawn };
        try {
          const run = await api.requestUpdate(body);
          toast(`Update ${run.id} started: ${run.first_day} to ${run.last_day}.`);
          draft = { events: [], drawn: [], until: null, sources: null };
          close();
        } catch (err) {
          root.querySelector("#up-err").textContent = errorText(err);
        }
      });
    });
  }

  // -- the strip ---------------------------------------------------------------------------------
  function renderStrip() {
    const u = store.updates.get(store.activeUpdate) ?? null;
    const showing = !!u && ["collecting", "running", "awaiting_review"].includes(u.state);
    strip.classList.toggle("hidden", !showing);
    document.body.classList.toggle("strip", showing);
    if (!showing) { strip.innerHTML = ""; return; }
    const days = Math.max(1, u.days || 1);
    const n = Math.min(days, (u.done ?? 0) + (u.state === "collecting" ? 0 : 1));
    const pending = store.proposals?.length ?? 0;
    const collected = Object.values(u.collected ?? {}).reduce((a, b) => a + b, 0);
    strip.classList.toggle("awaiting", u.state === "awaiting_review");
    strip.innerHTML = `
      <b>Update</b><span class="id">${esc(u.id)}</span>
      <span class="stage ${u.state === "collecting" ? "now" : "done"}">collecting${collected ? ` (${collected} new)` : ""}</span>
      <span class="stage ${u.state === "running" ? "now" : u.state === "awaiting_review" ? "done" : ""}">day ${n} of ${days}${u.current ? ` · ${esc(fmtDate(u.current))}` : ""}</span>
      ${u.state === "awaiting_review" ? `<span class="stage now">awaiting review (${pending})</span>` : ""}
      <div class="bar" aria-hidden="true"><div style="width:${Math.round((100 * (u.done ?? 0)) / days)}%"></div></div>
      <span class="spacer"></span>
      ${u.state === "awaiting_review" ? `<button id="us-review" class="primary">Review</button>` : ""}
      <button id="us-cancel" title="Stop after the current day">Cancel</button>`;
    strip.querySelector("#us-review")?.addEventListener("click", () => openReview());
    strip.querySelector("#us-cancel").addEventListener("click", async () => {
      try {
        await api.cancelUpdate(u.id);
        toast(`Update ${u.id} cancelled after its current day.`);
      } catch (err) { toast(errorText(err), "err"); }
    });
  }

  on("update", renderStrip);
  on("proposals", renderStrip);
  // replaying the trace when the page opens rebuilds the state quietly: no panels pop open
  on("awaiting-review", () => { if (!store.booting) openReview(); });
  on("update-done", async (u) => {
    renderStrip();
    if (store.booting) return;
    if (u.state === "failed") { toast(`Update ${u.id} failed: ${u.error ?? ""}`, "err"); return; }
    if (u.requestedBy === "init") return;
    try { showReport(await api.update(u.id)); } catch { /* the report is in the trace too */ }
  });
  on("status", (st) => {
    // a page opened mid-run learns about the run from the status
    if (st?.update_id && !store.updates.has(st.update_id)) {
      api.update(st.update_id).then((run) => {
        store.updates.set(run.id, { id: run.id, state: run.state, first: run.first_day, last: run.last_day, current: run.current_day,
                                     days: run.days_total, done: run.days_done, collected: {}, report: run.report });
        store.activeUpdate = run.id;
        renderStrip();
      }).catch(() => {});
    }
  });
  return { open, renderStrip };
}

function subLabel(sid) {
  const s = store.view?.subentities.find((x) => x.id === sid);
  const e = s && store.view.entities.find((x) => x.id === s.entity_id);
  return s ? `${s.name}${e ? ` · ${e.name}` : ""}` : sid;
}

// The update report (§7.8) for the inspector.
export function reportView(run) {
  const r = run.report;
  if (!r) return `<p class="empty">No report yet.</p>`;
  const collected = Object.entries(r.collected ?? {});
  const stat = (n, label) => `<div class="stat"><b>${n}</b><span>${label}</span></div>`;
  return `
    <div class="group-label">Update report</div>
    <h3>${esc(run.id)}</h3>
    <p class="lede">${esc(fmtDate(run.first_day))} to ${esc(fmtDate(run.last_day))} · ${r.days} day${r.days === 1 ? "" : "s"} ·
      version v${r.version_before} → v${r.version_after}</p>
    <div class="report-grid">
      ${stat(collected.reduce((a, [, n]) => a + n, 0), "collected")}
      ${stat(r.duplicates_dropped, "duplicates dropped")}
      ${stat(r.translated, "translated")}
      ${stat(r.auto_applied, "applied automatically")}
      ${stat(r.approved, "approved")}
      ${stat(r.rejected + r.deferred, "rejected or deferred")}
    </div>
    <div class="section"><h4>Collected</h4>${collected.length ? collected.map(([s, n]) => `<div class="small">${esc(s.replace(/_/g, " "))}: ${n}</div>`).join("") : `<div class="small muted">nothing new</div>`}
      ${r.late_collected ? `<div class="small muted">${r.late_collected} published before the window, folded in on its first day</div>` : ""}</div>
    ${r.model_edits_proposed?.length ? `<div class="section"><h4>Model edits proposed</h4><div class="small mono">${r.model_edits_proposed.map(esc).join(", ")}</div></div>` : ""}
    <div class="section"><h4>Biggest moves</h4>${(r.biggest_moves ?? []).map(([sid, dz]) => `<div class="subrow"><span class="nm">${esc(subLabel(sid))}</span>
      <span class="val ${dz > 0 ? "z-up" : "z-down"}">${dz > 0 ? "▲" : "▼"} ${Math.abs(dz).toFixed(2)} sd</span></div>`).join("") || `<div class="small muted">no moves</div>`}</div>
    ${r.reposed_theses?.length ? `<div class="section"><h4>Theses re-posed</h4><div class="small">${r.reposed_theses.map(esc).join(", ")}</div></div>` : ""}
    ${r.not_translated?.length ? `<div class="section"><h4>Not translated</h4><div class="small mono">${r.not_translated.map(esc).join(", ")}</div></div>` : ""}`;
}
