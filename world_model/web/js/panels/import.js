// Import (Oct 11): how new information reaches a client's world model. A bundle is research a collection agent has
// already read and categorized (intake/bundle.py): dated items, each with its source, summary, the entities it is
// about, a category, and the changes it claims. The dialog shows the bundle as a dated timeline, says what each item
// would change (and what it cannot map), and imports the chosen items: each is folded in on its own date and waits
// for review, in date order. Bundles come from a file on the person's computer, or from the server's imports folder
// when it has one (a local checkout).
//
// Oct 17: a raw document too (PDF, DOCX, XLSX, HTML, CSV, Markdown, text). The server runs it through the ingestion
// pipeline (stored in the lakehouse, chunked, names recognized, signals extracted) into a bundle, and the dialog can
// show the graph update each item would make, on the canvas (graph/update.js) beside a list of its operations, each
// with the sentence or table row it came from. Nothing changes until the items are imported and reviewed.
import { api } from "../api.js";
import { UpdateLayer, opText } from "../graph/update.js";
import { qualified } from "../names.js";
import { store } from "../store.js";
import { errorText, esc } from "../util.js";

const SOURCE = { broker_research: "Broker research", expert_call: "Expert call", news: "News", central_bank: "Central bank",
                 data: "Data", filing: "Filing", client_model: "Client model", other: "Other" };
const CHANGE = { observe_value: "level", change_value: "move", add_interaction: "new link", reweight_interaction: "evidence" };
const DOC_TYPES = ".pdf,.docx,.xlsx,.xlsm,.html,.htm,.csv,.tsv,.md,.markdown,.txt,.json";

export function initImport({ toast, onProposal, renderer = null }) {
  const pane = document.createElement("section");
  pane.id = "import";
  pane.className = "examples import hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Import research");
  document.getElementById("stage").appendChild(pane);
  const st = { bundle: null, preview: null, local: [], picked: new Set(), open: null, busy: false, filter: "all", error: null,
              name: null, done: new Set(),
              doc: null, docs: [], reading: false,      // a document read through ingestion, and those already stored
              gu: null };                                 // the graph update shown: {scope: "all" | item id, op, chunk}
  let layer = null;                                       // the canvas layer that draws it, made on first use

  const day = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  const clock = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

  async function use(bundle) {
    st.error = null;
    try {
      st.preview = await api.importPreview(bundle);
      st.bundle = bundle;
      st.picked = new Set(st.preview.items.filter((x) => x.status !== "imported" && x.changes > 0).map((x) => x.id));
      st.open = null;
      st.fresh = true;          // the rows arrive one after another, once
    } catch (err) { st.error = errorText(err); }
    render();
    st.fresh = false;
  }

  async function pick(name) {
    try { st.name = name; st.doc = null; await use(await api.importLocal(name)); } catch (err) { st.error = errorText(err); render(); }
  }

  // a document through the ingestion pipeline: its bundle goes into the timeline, and its update can be drawn
  async function readDocument(get) {
    hideUpdate();
    st.reading = true; st.error = null; st.name = null; render();
    try {
      const view = await get();
      st.doc = view;
      st.reading = false;
      if (view.bundle) await use(view.bundle);
      else { st.preview = null; st.bundle = null; render(); }
    } catch (err) { st.reading = false; st.error = errorText(err); render(); }
  }

  // one bundle, or several (a run of daily files) merged into one
  async function readFiles(files) {
    hideUpdate();
    st.name = null; st.doc = null;
    const bundles = [];
    for (const f of files) {
      try { bundles.push(JSON.parse(await f.text())); } catch (err) { st.error = `${f.name}: ${errorText(err)}`; render(); return; }
    }
    if (bundles.length === 1) { await use(bundles[0]); return; }
    const first = bundles[0];
    await use({ ...first, title: `${String(first.title ?? "Research").split(",")[0]}, ${bundles.length} days`,
                description: `${bundles.length} bundles merged`, items: bundles.flatMap((b) => b.items ?? []) });
  }

  // bundles sorted into one file per day (Oct 15): the next day after the model's, and a picker for any day
  const DAILY = /^(\d{4}-\d{2}-\d{2})\.json$/;
  function nextDay() {
    // a day is still to come when it ends after the model's clock (a day already processed ends at or before it)
    const at = String(store.status?.sim_time ?? "").replace("Z", "").slice(0, 19);
    return st.local.find((b) => DAILY.test(b.name) && !st.done.has(b.name) && `${b.name.slice(0, 10)}T23:59:59` > at) ?? null;
  }

  function chooser() {
    const daily = st.local.length > 6 && st.local.every((b) => DAILY.test(b.name));
    const next = daily ? nextDay() : null;
    const local = daily
      ? `${next ? `<button class="small" data-local="${esc(next.name)}" title="The first day after your model's date">Next day: ${day(next.name.slice(0, 10) + "T12:00:00Z")} <span class="muted">· ${next.items}</span></button>` : ""}
         <select class="small" data-day aria-label="A day's research"><option value="">Any day…</option>${st.local.map((b) =>
           `<option value="${esc(b.name)}">${day(b.name.slice(0, 10) + "T12:00:00Z")} · ${b.items} item${b.items === 1 ? "" : "s"}${st.done.has(b.name) ? " ✓" : ""}</option>`).join("")}</select>`
      : st.local.map((b) => `<button class="small" data-local="${esc(b.name)}" title="${esc(b.collected_by)}">${esc(b.title)} <span class="muted">· ${b.items}</span></button>`).join("");
    return `<div class="imp-src">
      <label class="primary small imp-file">Choose a bundle…<input type="file" accept=".json,application/json" multiple hidden></label>
      <label class="small imp-file imp-doc" title="A PDF, Word, Excel, HTML, CSV, Markdown, or text file: read into a bundle on the server, and nothing changes until you import">${st.reading ? "Reading…" : "Read a document…"}<input type="file" data-doc accept="${DOC_TYPES}" hidden ${st.reading ? "disabled" : ""}></label>
      ${st.docs.length ? `<select class="small" data-stored aria-label="A document already stored"><option value="">Stored documents…</option>${st.docs.map((d) =>
        `<option value="${esc(d.id)}">${esc(d.title || d.filename)} · ${day(d.event_time)}</option>`).join("")}</select>` : ""}
      ${local}
      <span class="muted small">${daily ? `or a day from this server's imports folder (${st.local.length} days)` : st.local.length ? "or one from this server's imports folder" : "a JSON bundle from your research agent"}</span>
    </div>`;
  }

  function row(x) {
    const off = x.status === "imported" || x.changes === 0;
    const kinds = x.change_kinds.map((k) => CHANGE[k] ?? k).join(", ");
    return `<li class="imp-row ${esc(x.status)}${st.open === x.id ? " open" : ""}${!st.picked.has(x.id) ? " picked-off" : ""}" data-id="${esc(x.id)}"
      style="animation-delay:${st.fresh ? Math.min(400, 12 * st.rowIndex++) : 0}ms${st.fresh ? "" : ";animation:none"}">
      <div class="imp-line">
        <input type="checkbox" data-pick="${esc(x.id)}" ${st.picked.has(x.id) ? "checked" : ""} ${off || st.busy ? "disabled" : ""}
          aria-label="Import ${esc(x.headline)}">
        <span class="imp-time mono muted">${clock(x.published_at)}</span>
        <button class="et linkish" data-toggle="${esc(x.id)}" aria-expanded="${st.open === x.id}">${esc(x.headline)}</button>
        ${x.category ? `<span class="imp-cat">${esc(x.category)}</span>` : ""}
        <span class="imp-n small" title="${esc(kinds)}">${x.changes ? `${x.changes} change${x.changes === 1 ? "" : "s"}` : "nothing to map"}</span>
        ${x.status === "imported" ? `<span class="edone" title="Already imported">✓</span>` : x.status === "late" ? `<span class="imp-late small" title="Older than the model's last processed day: folded in late">late</span>` : ""}
      </div>
      <div class="imp-meta small muted">${esc(SOURCE[x.source_type] ?? x.source_type)} · ${esc(x.source)}${x.stance ? ` · ${esc(x.stance)}` : ""}
        <span class="imp-rel" title="Relevance to the book, as the agent judged it"><i style="width:${Math.round(100 * x.relevance)}%"></i></span></div>
      ${st.open === x.id ? `<div class="emore small">
        ${x.summary ? `<blockquote class="earticle"><div>${esc(x.summary)}</div><div class="esrc muted">${esc(x.source)} · ${day(x.published_at)} ${clock(x.published_at)} UTC</div></blockquote>` : ""}
        <div class="imp-tags">${x.entities.map((e) => `<span class="cchip">${esc(e)}</span>`).join("")}${x.tickers.map((t) => `<span class="cchip mono">${esc(t)}</span>`).join("")}</div>
        <p>${x.changes ? `Would propose ${esc(kinds)} (${x.changes}) for your review.` : "Nothing in it maps onto this model."}
          The agent's confidence in its reading: ${Math.round(100 * x.confidence)}%.</p>
        ${x.dropped.length ? `<p class="muted">Not mapped: ${x.dropped.map(esc).join("; ")}.</p>` : ""}
        ${docItem(x.id) ? `<button class="small" data-gu="${esc(x.id)}">See its graph update</button>` : ""}
      </div>` : ""}
    </li>`;
  }

  const docItem = (id) => st.doc?.items.find((x) => x.id === id) ?? null;

  // what the pipeline read: the document, how much of it named the model, and how many changes came of it
  function docHead() {
    const v = st.doc;
    if (!v) return "";
    const t = v.trace;
    const n = v.items.reduce((s, x) => s + x.ops.length, 0);
    const warn = [...t.warnings, ...(v.document.error && !t.warnings.includes(v.document.error) ? [v.document.error] : [])];
    return `<div class="imp-doc-head small">
      <div><b>${esc(v.document.title || v.document.filename)}</b> <span class="muted">· ${esc(v.document.filename)} · ${day(v.document.event_time)}${t.new ? "" : " · stored before"}</span></div>
      <div class="muted">Read into ${t.chunks} passage${t.chunks === 1 ? "" : "s"}, ${t.mentions} name${t.mentions === 1 ? "" : "s"} of the model, ${t.signals} claim${t.signals === 1 ? "" : "s"}${t.llm_signals ? ` (${t.llm_signals} by the language model)` : ""}: ${v.items.length} item${v.items.length === 1 ? "" : "s"}, ${n} change${n === 1 ? "" : "s"}.</div>
      ${warn.map((w) => `<div class="imp-late">${esc(w)}</div>`).join("")}
      ${n ? `<button class="small" data-gu="all">See the graph update</button>` : ""}
    </div>`;
  }

  // -- the graph update view -------------------------------------------------------------------------------------
  const KIND = { observe_value: "Level", change_value: "Move", add_interaction: "New link", reweight_interaction: "Evidence" };
  const SIGNAL = { observe: "observe", move: "move", link: "link", support: "support", contradict: "contradict" };
  function guOps() {
    // every op in scope, numbered across items, so the canvas and the list name each one once
    const items = st.gu.scope === "all" ? st.doc.items : st.doc.items.filter((x) => x.id === st.gu.scope);
    const out = [];
    for (const it of items) for (const op of it.ops) out.push({ ...op, index: out.length, item: it });
    return { items, ops: out };
  }
  function opLine(op) {
    const V = st.doc.values;
    const nm = (id) => { const v = V[id]; return v ? qualified(v.name, v.entity) : id; };
    if (op.op === "observe_value" || op.op === "change_value") return `${esc(nm(op.values[0]))} <b class="gu-${op.z > 0.005 ? "up" : op.z < -0.005 ? "down" : "flat"}">${esc(opText(op, V[op.values[0]]))}</b>`;
    const word = op.op === "add_interaction" ? esc(op.label) : op.supports ? `for “${esc(op.label)}”` : `against “${esc(op.label)}”`;
    return `${esc(nm(op.source))} <span class="muted">→</span> ${esc(nm(op.target))} <span class="muted">· ${word}</span>`;
  }
  function chunkText(it, op) {
    const c = st.doc.chunks.find((x) => x.ord === it.chunk);
    const text = c?.text ?? it.summary;
    const at = op.quote ? text.indexOf(op.quote) : -1;
    const body = at < 0 ? esc(text) : `${esc(text.slice(0, at))}<mark>${esc(op.quote)}</mark>${esc(text.slice(at + op.quote.length))}`;
    return `<blockquote class="earticle gu-chunk"><div>${body}</div></blockquote>`;
  }
  function guView() {
    const { items, ops } = guOps();
    const d = st.doc.document;
    const one = st.gu.scope !== "all" ? items[0] : null;
    const list = items.map((it) => {
      const mine = ops.filter((o) => o.item === it);
      return `<li class="gu-item">
        ${one ? "" : `<div class="gu-ihead small"><span class="muted mono">${esc(it.id)}</span> ${esc(it.headline)}</div>`}
        <ol class="gu-ops">${mine.map((op) => {
          const open = st.gu.op === op.index;
          const ref = `${esc(d.filename)}${it.page != null ? ` · p. ${it.page}` : ""}${it.chunk != null ? ` · passage ${it.chunk}` : ""}`;
          return `<li class="gu-op${open ? " open" : ""}" data-gop="${op.index}">
            <button class="gu-opline" data-gop="${op.index}" aria-expanded="${open}"><span class="gu-kind ${esc(op.op)}">${KIND[op.op] ?? esc(op.op)}</span>
              <span class="gu-what">${opLine(op)}</span></button>
            ${open ? `<div class="gu-ev small">
              ${op.quote ? `<button class="gu-quote" data-chunk="${op.index}" title="Show the passage it came from">${op.table_row ? `<span class="imp-cat">table row</span> ` : ""}“${esc(op.quote)}”</button>` : ""}
              <div class="muted">${ref} · signal: ${SIGNAL[op.signal] ?? esc(op.signal)}${op.note ? ` (${esc(op.note)})` : ""}</div>
              ${st.gu.chunk === op.index ? chunkText(it, op) : ""}
            </div>` : ""}
          </li>`;
        }).join("")}</ol>
        ${it.dropped.length ? `<div class="gu-dropped small"><b>Not mapped</b>${it.dropped.map((x) => `<div class="muted">${esc(x.signal)}: ${esc(x.reason)}${x.quote ? ` · “${esc(x.quote)}”` : ""}</div>`).join("")}</div>` : ""}
      </li>`;
    }).join("");
    const ids = items.filter((it) => it.ops.length && !it.imported).map((it) => it.id);
    const dropped = items.reduce((s, it) => s + it.dropped.length, 0);
    return `<div class="gu-head small">
        <button class="ghost small" data-gu-back>← Items</button>
        <span><b>Graph update</b> <span class="muted">· ${one ? esc(one.headline.length > 60 ? `${one.headline.slice(0, 58).trimEnd()}…` : one.headline) : `${items.length} item${items.length === 1 ? "" : "s"}`} · ${ops.length} change${ops.length === 1 ? "" : "s"}${dropped ? `, ${dropped} not mapped` : ""}</span></span>
      </div>
      ${one?.event_id ? `<p class="small muted gu-lede">Importing makes <span class="mono">${esc(one.event_id)}</span>, reviewed before it changes anything.</p>`
        : `<p class="small muted gu-lede">What importing would propose, one update per item, each reviewed before it changes anything.</p>`}
      <ol class="gu-list">${list}</ol>
      <footer class="imp-foot"><span class="muted small">Nothing changes until you import and approve</span><span class="spacer"></span>
        <button class="primary" data-gu-go="${esc(ids.join(","))}" ${ids.length && !st.busy ? "" : "disabled"}>${st.busy ? "Importing…" : ids.length === 1 && one ? "Import this item" : `Import ${ids.length}`}</button></footer>`;
  }

  // draw it on the canvas, and frame what is lit in the part the dialog leaves visible
  function drawUpdate(frame = true) {
    if (!renderer || !st.gu) return;
    layer ??= new UpdateLayer(renderer, { onPick: (id) => {
      const op = guOps().ops.find((o) => o.values.includes(id));
      if (op) { st.gu.op = op.index; st.gu.chunk = null; render(); }
    } });
    const { ops } = guOps();
    const scope = st.gu.scope === "all" ? `${st.doc.document.title || st.doc.document.filename}` : docItem(st.gu.scope)?.headline ?? "";
    const bounds = layer.show(ops, st.doc.values, `${st.doc.bundle_id}:${st.gu.scope}`, scope.length > 70 ? `${scope.slice(0, 68).trimEnd()}…` : scope);
    const op = ops.find((o) => o.index === st.gu.op);
    const lit = layer.focus(op ? op.values : null) ?? bounds;
    if (!frame) return;
    const cv = document.getElementById("canvas").getBoundingClientRect();
    const pr = pane.getBoundingClientRect();
    const left = pane.classList.contains("win-max") ? 24 : Math.max(24, pr.right - cv.left + 24);
    renderer.zoom.fit(lit, store.settings?.reducedMotion ? 0 : 380, { maxK: op ? 1.3 : 1.1, pad: renderer.freePad({ top: 72, right: 24, bottom: 64, left }) });
  }
  function hideUpdate() {
    st.gu = null;
    pane.classList.remove("gu-mode");
    layer?.hide();
  }

  function render() {
    if (st.gu && st.doc) {
      pane.classList.add("gu-mode");
      pane.innerHTML = `
      <header><div class="etitle">Import</div><span class="spacer"></span>
        <button class="close" aria-label="Close (Esc)">✕</button></header>
      ${st.error ? `<p class="error small">${esc(st.error)}</p>` : ""}
      ${guView()}`;
      return;
    }
    const p = st.preview;
    const cats = p ? [...new Set(p.items.map((x) => x.category).filter(Boolean))] : [];
    const shown = p ? p.items.filter((x) => st.filter === "all" || x.category === st.filter) : [];
    const days = [];
    for (const x of shown) {
      const d = x.published_at.slice(0, 10);
      if (!days.length || days[days.length - 1].d !== d) days.push({ d, items: [] });
      days[days.length - 1].items.push(x);
    }
    const n = st.picked.size;
    st.rowIndex = 0;
    pane.innerHTML = `
      <header><div class="etitle">Import</div><span class="spacer"></span>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close (Esc)">✕</button></header>
      <p class="small muted elede">Research your agent has collected and categorized. Each item is folded in on its own date, and nothing changes
        your model until you approve it.</p>
      ${chooser()}
      ${st.error ? `<p class="error small">${esc(st.error)}</p>` : ""}
      ${docHead()}
      ${p ? `<div class="imp-head small">
          <b>${esc(p.title)}</b> · ${esc(p.collected_by)}${p.collected_at ? ` · collected ${day(p.collected_at)}` : ""} · ${p.items.length} items
          <span class="muted">· your model is at ${day(p.model_date)}</span>
          ${p.description ? `<div class="muted">${esc(p.description)}</div>` : ""}</div>
        <div class="chips efilter" role="group" aria-label="Show">${[["all", "All"], ...cats.map((c) => [c, c])].map(([k, l]) =>
          `<button class="cchip" data-filter="${esc(k)}" aria-pressed="${st.filter === k}">${esc(l)}</button>`).join("")}</div>
        <div class="imp-tools small muted">Select <button class="ghost small" data-all>all</button><button class="ghost small" data-none>none</button></div>
        <div class="imp-list">${days.map((g) => `<h4 class="imp-day">${day(g.d + "T12:00:00Z")}</h4><ol class="elist">${g.items.map(row).join("")}</ol>`).join("")}</div>
        <footer class="imp-foot"><span class="muted small">${n ? `${n} item${n === 1 ? "" : "s"}, reviewed one by one in date order` : "Pick the items to import"}</span>
          <span class="spacer"></span><button class="primary" data-go ${n && !st.busy ? "" : "disabled"}>${st.busy ? "Importing…" : `Import ${n || ""}`}</button></footer>` : ""}`;
  }

  pane.addEventListener("change", (ev) => {
    const sel = ev.target.closest?.("[data-day]");
    if (sel?.value) { pick(sel.value); return; }
    const doc = ev.target.closest?.("[data-doc]");
    if (doc?.files?.length) { const f = doc.files[0]; readDocument(() => api.importDocument(f)); return; }
    const stored = ev.target.closest?.("[data-stored]");
    if (stored?.value) { const id = stored.value; readDocument(() => api.importStoredDocument(id)); return; }
    const f = ev.target.closest?.(".imp-file input");
    if (f?.files?.length) { readFiles([...f.files]); return; }
    const box = ev.target.closest?.("[data-pick]");
    if (box) { box.checked ? st.picked.add(box.dataset.pick) : st.picked.delete(box.dataset.pick); render(); }
  });
  pane.addEventListener("click", async (ev) => {
    const t = ev.target.closest?.("button");
    if (!t) return;
    if (t.classList.contains("close")) return close();
    if (t.dataset.max != null) { pane.classList.toggle("win-max"); return; }
    if (t.dataset.gu) { st.gu = { scope: t.dataset.gu, op: null, chunk: null }; render(); drawUpdate(); return; }
    if (t.dataset.guBack != null) { hideUpdate(); render(); return; }
    if (t.dataset.chunk != null) { const k = +t.dataset.chunk; st.gu.chunk = st.gu.chunk === k ? null : k; render(); return; }
    if (t.dataset.gop != null) {
      const k = +t.dataset.gop;
      st.gu.op = st.gu.op === k ? null : k; st.gu.chunk = null;
      render(); drawUpdate(); return;
    }
    if (t.dataset.guGo != null) { st.picked = new Set(t.dataset.guGo.split(",").filter(Boolean)); }
    if (t.dataset.toggle) { st.open = st.open === t.dataset.toggle ? null : t.dataset.toggle; render(); return; }
    if (t.dataset.filter) { st.filter = t.dataset.filter; render(); return; }
    if (t.dataset.local) { pick(t.dataset.local); return; }
    const usable = (st.preview?.items ?? []).filter((x) => x.status !== "imported" && x.changes > 0
      && (st.filter === "all" || x.category === st.filter));
    if (t.dataset.all != null) { usable.forEach((x) => st.picked.add(x.id)); render(); return; }
    if (t.dataset.none != null) { st.picked.clear(); render(); return; }
    if (t.dataset.go != null || t.dataset.guGo != null) {
      st.busy = true; render();
      try {
        const res = await api.importRun(st.bundle, [...st.picked]);
        if (st.name) st.done.add(st.name);
        toast(`Imported ${res.imported.length} item${res.imported.length === 1 ? "" : "s"}: each waits for your review, oldest first.`);
        close();
        if (res.waiting_on) onProposal?.(res.waiting_on);
      } catch (err) { st.error = errorText(err); }
      st.busy = false;
      if (!pane.classList.contains("hidden")) render();
    }
  });

  async function open() {
    pane.classList.remove("hidden");
    document.getElementById("btn-import")?.setAttribute("aria-expanded", "true");
    try { st.local = await api.importLocalList(); } catch { st.local = []; }
    try { st.docs = await api.importDocuments(); } catch { st.docs = []; }
    if (st.bundle) await use(st.bundle);       // what is already imported may have changed
    else render();
  }
  function close() {
    hideUpdate();
    pane.classList.add("hidden");
    document.getElementById("btn-import")?.setAttribute("aria-expanded", "false");
  }
  const isOpen = () => !pane.classList.contains("hidden");
  return { open, close, isOpen, toggle: () => (isOpen() ? close() : open()), ready: () => !!store.status?.imports };
}
