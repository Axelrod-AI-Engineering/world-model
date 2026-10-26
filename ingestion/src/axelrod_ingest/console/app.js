"use strict";
// The ingestion console: plain JS, no framework. Every string from the lake or an upload is put on the page as a text
// node (the `h` helper), never as markup: document text is untrusted.

const $ = (id) => document.getElementById(id);
const SOURCE_TYPES = ["other", "broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model"];
const MODES = ["keyword", "prefix", "semantic", "hybrid", "graph"];
const state = { token: "", tenant: "", tab: "lake", view: null, counts: {}, timings: {},
  lake: { offset: 0, limit: 50, open: null, version: null, baseline: null, latest: null, paused: false, fails: 0, err: "", timer: null,
    seqs: {}, updated: null, newCount: 0, cur: -1 } };

// ---- helpers ---------------------------------------------------------------------------------------------------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
const show = (el, ...kids) => { clear(el).append(...kids.flat().filter((k) => k !== null && k !== undefined)); return el; };
const loading = (what) => h("div", { class: "loading" }, `Loading ${what}...`);
const empty = (what) => h("div", { class: "empty" }, what);
const chip = (label) => h("span", { class: `chip ${label}` }, label);
const when = (t) => (t ? String(t).replace("T", " ").replace(/(\.\d+)?(\+00:00|Z)$/, "Z") : "");
const secs = (s) => (s < 0.001 ? "<1 ms" : s < 1 ? `${(s * 1000).toFixed(0)} ms` : `${s.toFixed(2)} s`);
const bytes = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const toast = (msg) => {
  const t = $("toast");
  t.textContent = msg; t.hidden = false;
  setTimeout(() => { t.hidden = true; }, 3000);
};

function keep(token) {
  try { if (token) sessionStorage.setItem("ingest-token", token); else sessionStorage.removeItem("ingest-token"); } catch (e) { /* no storage: the token lives in this page only */ }
  state.token = token;
}
function kept() {
  try { return sessionStorage.getItem("ingest-token") || ""; } catch (e) { return ""; }
}

class Problem extends Error {
  constructor(title, detail, status) { super(detail ? `${title}: ${detail}` : title); this.status = status; }
}
function failure(err) {
  return h("div", { class: "error panel", role: "alert" }, err instanceof Error ? err.message : String(err));
}

async function api(path, opts = {}) {
  const headers = { Authorization: `Bearer ${state.token}`, ...(opts.headers || {}) };
  let body = opts.body;
  if (opts.json !== undefined) { body = JSON.stringify(opts.json); headers["Content-Type"] = "application/json"; }
  const resp = await fetch(path, { method: opts.method || "GET", headers, body, signal: opts.signal });
  if (resp.status === 401) { keep(""); gate("That token was not accepted."); throw new Problem("Authentication required", "", 401); }
  if (!resp.ok) {
    let p = {};
    try { p = await resp.json(); } catch (e) { /* not a problem body */ }
    throw new Problem(p.title || `HTTP ${resp.status}`, p.detail || "", resp.status);
  }
  return opts.blob ? resp.blob() : resp.json();
}
const q = (params) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== "" && v !== null && v !== undefined) u.set(k, v);
  return u.toString() ? `?${u}` : "";
};
const lakePath = (tenant, rest = "") => `/v1/lake/${encodeURIComponent(tenant)}${rest}`;

// ---- gate and tabs ---------------------------------------------------------------------------------------------
function gate(message) {
  stopPolling();
  $("gate").hidden = false; $("app").hidden = true; $("signout").hidden = true;
  $("gate-error").hidden = !message; $("gate-error").textContent = message || "";
  $("token").value = ""; $("token").focus();
}
function lastTenant() {
  try { return localStorage.getItem("ingest-tenant") || ""; } catch (e) { return ""; }
}
async function loadTenants() {
  try {
    const { tenants, documents } = await api("/v1/tenants");
    state.counts = documents;
    show($("tenants"), tenants.map((t) => h("option", { value: t, label: `${documents[t]} documents` })));
    showTenantNote();
    return tenants;
  } catch (err) {
    if (err.status !== 401) toast(err.message);
    return null;
  }
}
function showTenantNote() {
  const n = state.counts[state.tenant];
  $("tenant-note").textContent = n === undefined ? "new tenant" : `${n} documents`;
}
async function enter() {
  $("gate").hidden = true; $("app").hidden = false; $("signout").hidden = false;
  try {
    const s = await api("/v1/supported");
    Q.supported = s;
    for (const sel of [$("a-type"), $("d-type")]) { const cur = sel.value; show(sel, s.source_types.map((t) => h("option", { value: t }, t))); sel.value = cur || "other"; }
  } catch (err) { if (err.status === 401) return; toast(err.message); }
  const tenants = await loadTenants();
  if (tenants === null && !state.token) return;                     // the gate is showing again
  if (!state.tenant) setTenant(tenants && tenants.includes(lastTenant()) ? lastTenant() : (tenants && tenants[0]) || "default");
  refresh();
}
function setTenant(t) {
  state.tenant = t; $("tenant").value = t; $("a-tenant").value = t;
  try { localStorage.setItem("ingest-tenant", t); } catch (e) { /* no storage: the next visit starts at the first tenant */ }
  showTenantNote();
}
function switchTab(tab) {
  const changed = tab !== state.tab;
  state.tab = tab;
  for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("on", b.dataset.tab === tab);
  for (const s of document.querySelectorAll(".tab")) s.hidden = s.id !== `tab-${tab}`;
  if (changed) refresh();
}
function refresh() {
  if (!state.token) return;
  if (state.tab === "lake") loadLake().then(schedule); else stopPolling();
  if (state.tab === "debug") loadStored();
}
function ask(title, text, yes, danger) {
  return new Promise((resolve) => {
    const d = $("confirm");
    $("confirm-title").textContent = title; $("confirm-text").textContent = text; $("confirm-yes").textContent = yes;
    $("confirm-yes").classList.toggle("danger", !!danger);
    d.returnValue = "";
    d.addEventListener("close", () => resolve(d.returnValue === "yes"), { once: true });
    d.showModal();
  });
}

// ---- 1. Lake ---------------------------------------------------------------------------------------------------
// The tab stays current by itself: `poll` asks the cheap /changes route every few seconds and reads the summary, the
// activity and the table again only when its version moved. Nothing the person is doing is reset by a refresh: filters,
// the open document and the highlighted row stay, and the table keeps the row at the top of the window where it was.
const L = state.lake;
const EPOCH = "1970-01-01T00:00:00+00:00";
const hms = (d) => d.toLocaleTimeString([], { hour12: false });
const retry = (err, again) => h("div", { class: "error panel", role: "alert" }, err.message, " ", h("button", { type: "button", class: "link", onclick: again }, "Retry"));
const seq = (name) => (L.seqs[name] = (L.seqs[name] || 0) + 1);

function stopPolling() { clearTimeout(L.timer); L.timer = null; }
function schedule() {
  stopPolling();
  setLive();
  if (!state.token || state.tab !== "lake" || L.paused || document.visibilityState === "hidden") return;
  L.timer = setTimeout(poll, L.fails ? Math.min(60000, 5000 * 2 ** L.fails) : 5000);
}
function setLive() {
  const hidden = document.visibilityState === "hidden";
  const when = L.updated ? hms(L.updated) : "";
  const text = L.paused ? `paused, last updated ${when || "never"}` : L.fails ? `update failed (${L.err}), retrying` :
    hidden ? `waiting: this tab is hidden, last updated ${when}` : L.updated ? `last updated ${when}` : "loading";
  $("live-text").textContent = text;
  $("live-dot").className = `dot ${L.paused || hidden ? "idle" : L.fails ? "bad" : "on"}`;
  $("live-toggle").textContent = L.paused ? "Resume" : "Pause";
}
async function poll() {
  stopPolling();
  if (!state.token || state.tab !== "lake") return;
  try {
    const c = await api(lakePath(state.tenant, "/changes") + q({ since: L.baseline }));
    const ok = c.version === L.version ? true : await loadLake({ quiet: true });
    if (ok) { L.fails = 0; L.updated = new Date(); } else { L.fails++; }
    setNew(c.new);
  } catch (err) {
    if (err.status === 401) return;
    L.fails++; L.err = err.message;
  }
  schedule();
}
function setNew(n) {
  L.newCount = n;
  const chip = $("new-chip");
  chip.hidden = !n; chip.textContent = `${n} new`;
  chip.title = "Rows ingested since you last looked. Click to mark them seen.";
}
function markSeen() {
  L.baseline = L.latest || EPOCH; setNew(0); loadTable({ quiet: true });
}

// the row at the top of the window, so a redraw can put it back where it was
function anchor() {
  if (!window.scrollY) return null;
  const row = [...document.querySelectorAll("#table tbody tr")].find((r) => r.getBoundingClientRect().bottom > 60);
  return row ? { id: row.dataset.id, top: row.getBoundingClientRect().top } : null;
}
function restore(a) {
  const row = a && [...document.querySelectorAll("#table tbody tr")].find((r) => r.dataset.id === a.id);
  if (row) window.scrollBy(0, row.getBoundingClientRect().top - a.top);
}

async function loadLake({ quiet = false } = {}) {
  const ok = await Promise.all([loadSummary(quiet), loadActivity(quiet), loadTable({ quiet })]);
  if (ok.every(Boolean)) { L.updated = new Date(); L.fails = 0; }
  setLive();
  return ok.every(Boolean);
}
async function loadSummary(quiet) {
  const mine = seq("summary");
  if (!quiet) show($("summary"), loading("summary"));
  try {
    const [s] = await Promise.all([api(lakePath(state.tenant, "/summary")), quiet ? loadTenants() : null]);
    if (mine !== L.seqs.summary) return true;
    L.version = s.version; L.latest = s.last_ingested_at;
    if (L.baseline === null) L.baseline = s.last_ingested_at || EPOCH;
    state.counts[state.tenant] = s.stats.documents; showTenantNote();
    const stat = (n, label) => h("div", { class: "stat" }, h("b", {}, n), h("span", {}, label));
    const count = (title, o) => h("div", {}, h("b", {}, title), Object.entries(o).map(([k, v]) => h("span", { class: "mono" }, `${k} ${v}`)));
    show($("summary"),
      h("div", { class: "stats" }, Object.entries(s.stats).map(([k, v]) => stat(v, k)), stat(`${s.embedder.name} / ${s.embedder.dim}`, "embedder")),
      h("div", { class: "counts" }, count("status", s.by_status), count("type", s.by_type), count("language", s.by_language)));
    for (const [id, o] of [["f-status", s.by_status], ["f-type", s.by_type], ["f-language", s.by_language]]) {
      const sel = $(id), cur = sel.value;
      show(sel, h("option", { value: "" }, sel.options[0].text), Object.keys(o).map((k) => h("option", { value: k === "unknown" ? "" : k }, k)));
      sel.value = cur;
    }
    return true;
  } catch (err) {
    L.err = err.message;
    if (!quiet) show($("summary"), retry(err, () => loadSummary(false)));
    return false;
  }
}
const stages = (t) => (t ? Object.entries(t).map(([k, v]) => `${k} ${secs(v)}`).join("  ") : "");
async function loadActivity(quiet) {
  const mine = seq("activity"), box = $("activity");
  if (!quiet) show(box, loading("activity"));
  try {
    const r = await api(lakePath(state.tenant, "/activity") + q({ limit: 8 }));
    if (mine !== L.seqs.activity) return true;
    $("activity-note").textContent = r.documents.length ? `the latest ${r.documents.length} ingests` : "";
    if (!r.documents.length) { show(box, empty("Nothing has been ingested into this tenant yet.")); return true; }
    show(box, h("table", { class: "feed" }, h("tbody", {}, r.documents.map((d) => h("tr", { class: d.status === "failed" ? "bad" : "" },
      h("td", { class: "mono time" }, hms(new Date(d.ingested_at))),
      h("td", { title: d.filename }, h("a", { onclick: () => openDoc(state.tenant, d.id) }, d.title || d.filename)),
      h("td", {}, chip(d.status)), h("td", { class: "num" }, `${d.chunks} chunks`),
      h("td", { class: "mono muted", title: d.error || stages(state.timings[d.id]) }, d.error || stages(state.timings[d.id])))))));
    return true;
  } catch (err) {
    L.err = err.message;
    if (!quiet) show(box, retry(err, () => loadActivity(false)));
    return false;
  }
}

async function loadTable({ quiet = false } = {}) {
  const mine = seq("table");
  if (!quiet) show($("table"), loading("documents"));
  const params = { status: $("f-status").value, type: $("f-type").value, language: $("f-language").value, q: $("f-q").value,
    order: $("f-order").value, dir: $("f-dir").value, limit: L.limit, offset: L.offset };
  try {
    const r = await api(lakePath(state.tenant, "/documents") + q(params));
    if (mine !== L.seqs.table) return true;
    const keep = quiet ? anchor() : null;
    if (!r.documents.length) {
      const filtered = params.status || params.type || params.language || params.q;
      show($("table"), empty(filtered ? "No documents match." : "This tenant holds no documents yet. Add files from the second tab."));
      return true;
    }
    const th = (t, cls) => h("th", { class: cls }, t);
    const rows = r.documents.map((d, k) => h("tr", { class: `pick${L.open === d.id ? " sel" : ""}${d.ingested_at > L.baseline ? " fresh" : ""}${L.cur === k ? " cur" : ""}`,
      "data-id": d.id, onclick: () => openDoc(state.tenant, d.id) },
      h("td", { class: "wrap" }, h("span", { class: "dot", title: "new since you last looked" }), d.title || d.filename,
        d.title && d.title !== d.filename ? h("div", { class: "muted mono" }, d.filename) : null),
      h("td", {}, chip(d.status)), h("td", {}, d.type), h("td", {}, d.language),
      h("td", { class: "mono opt" }, d.published_at ? d.published_at.slice(0, 10) : "", d.published_source ? h("div", { class: "muted" }, d.published_source) : null),
      h("td", { class: "mono opt" }, d.period), h("td", { class: "num opt" }, d.pages ?? ""), h("td", { class: "num" }, d.chunks),
      h("td", { class: "num" }, bytes(d.size)), h("td", { class: "mono" }, when(d.ingested_at))));
    const last = Math.min(r.total, L.offset + r.documents.length);
    show($("table"),
      h("table", {}, h("thead", {}, h("tr", {}, th("document"), th("status"), th("type"), th("lang"), th("published", "opt"), th("period", "opt"),
        th("pages", "num opt"), th("chunks", "num"), th("size", "num"), th("ingested"))), h("tbody", {}, rows)),
      h("div", { class: "pager" },
        h("button", { type: "button", disabled: L.offset === 0, onclick: () => { L.offset = Math.max(0, L.offset - L.limit); L.cur = -1; loadTable(); } }, "Previous"),
        h("span", { class: "mono" }, `${L.offset + 1}-${last} of ${r.total}`),
        h("button", { type: "button", disabled: last >= r.total, onclick: () => { L.offset += L.limit; L.cur = -1; loadTable(); } }, "Next")));
    restore(keep);
    return true;
  } catch (err) {
    L.err = err.message;
    if (!quiet) show($("table"), retry(err, () => loadTable()));
    return false;
  }
}
function moveCur(step) {
  const rows = [...document.querySelectorAll("#table tbody tr")];
  if (!rows.length) return;
  L.cur = Math.max(0, Math.min(rows.length - 1, L.cur + step));
  rows.forEach((r, k) => r.classList.toggle("cur", k === L.cur));
  rows[L.cur].scrollIntoView({ block: "nearest" });
}

function section(title, obj) {
  const rows = Object.entries(obj || {}).filter(([, v]) => v !== "" && v !== null && v !== undefined);
  if (!rows.length) return null;
  return h("div", {}, h("h3", {}, title), h("dl", { class: "kv" }, rows.map(([k, v]) => [h("dt", {}, k), h("dd", {}, typeof v === "object" ? JSON.stringify(v) : String(v))])));
}
async function openDoc(tenant, id, { scroll = true } = {}) {
  if (tenant !== state.tenant) { setTenant(tenant); resetLake(); }
  if (state.tab !== "lake") { state.lake.open = id; switchTab("lake"); }
  state.lake.open = id;
  for (const tr of document.querySelectorAll("#table tbody tr")) tr.classList.toggle("sel", tr.dataset.id === id);
  show($("detail"), loading("document"));
  try {
    const r = await api(lakePath(tenant, `/documents/${encodeURIComponent(id)}`));
    const d = r.document, m = d.meta || {};
    const dates = m.dates || {};
    const raw = h("button", { type: "button", onclick: async () => {
      try {
        const blob = await api(lakePath(tenant, `/documents/${encodeURIComponent(id)}/raw`), { blob: true });
        const a = h("a", { href: URL.createObjectURL(blob), download: d.filename });
        document.body.append(a); a.click(); a.remove();
      } catch (err) { toast(err.message); }
    } }, "Download raw file");
    const reprocess = h("button", { type: "button", onclick: async () => {
      const how = state.view ? `recognized against ${state.view.name}` : "with an empty world view, so nothing is recognized and its mentions are cleared";
      if (!await ask("Reprocess this document?", `It is parsed, typed, dated, chunked and embedded again, and extracted ${how}.`, "Reprocess")) return;
      try {
        const res = (await api("/v1/process", { method: "POST", json: { tenant, doc_id: id, world_view: viewJson(),
          inverted: state.view ? state.view.inverted : [] } })).result;
        state.timings[id] = res.timings;
        toast(`Reprocessed: ${res.document.status}, ${res.chunks} chunks`);
        openDoc(tenant, id, { scroll: false }); refreshNow();
      } catch (err) { toast(err.message); }
    } }, "Reprocess");
    const remove = h("button", { type: "button", class: "danger", onclick: async () => {
      const text = `Removes ${d.filename} from tenant ${tenant}: the file, its text, chunks, mentions and embeddings. Bundles made from this ` +
        "document alone that no import used are removed too; a bundle built from other documents, or one already imported, is kept.";
      if (!await ask("Delete this document?", text, "Delete", true)) return;
      try {
        const res = await api(lakePath(tenant, `/documents/${encodeURIComponent(id)}`), { method: "DELETE" });
        toast(`Deleted. ${res.bundles_removed} bundles removed, ${res.bundles_kept} kept.`);
        L.open = null; show($("detail")); refreshNow();
      } catch (err) { toast(err.message); }
    } }, "Delete");
    const view = { chunkPage: 0, listPage: 0 };
    const textBox = h("div", { class: "text" }), textPager = h("div", { class: "pager" });
    const listBox = h("div"), similar = h("div");
    const drawText = () => drawChunks(textBox, textPager, r.text, r.chunks, view, "chunkPage", 25, drawText);
    const drawList = () => drawChunkList(listBox, r.chunks, view, similar, tenant, id, drawList);
    show($("detail"),
      h("h2", {}, d.title || d.filename),
      h("div", { class: "row" }, chip(d.status), h("span", { class: "mono muted" }, id), raw, reprocess, remove,
        h("a", { onclick: () => debugStored(tenant, id) }, "Run the stage debugger on it")),
      d.error ? h("div", { class: "error" }, d.error) : null,
      h("div", { class: "cols" },
        section("Document", { file: d.filename, mime: d.mime, size: d.size, sha256: d.sha256, source: d.source, source_type: d.source_type,
          uploaded_by: d.uploaded_by, parser: r.parser, ingested: when(d.ingested_at), event_time: when(d.event_time) }),
        section("Type", m.doc_type), section("Dating", dates), section("Decoding", m.encoding),
        section("OCR", { engine: (m.ocr || {}).engine, version: (m.ocr || {}).version, pages_read: (m.ocr || {}).pages ? JSON.stringify(m.ocr.pages) : "",
          needs_ocr: (m.needs_ocr || []).join(", ") }),
        section("Yen", (m.currency || {}).yen), section("Manifest", m.manifest), section("Shared origin", m.shared_origin),
        section("Extraction", { language: m.language, chunks: r.chunks.length, mentions: r.mentions, bundles: r.bundles.length, signals: r.signals })),
      h("h2", {}, `Text (${r.text.length} characters)`), textPager, h("div", { class: "panel" }, textBox),
      h("h2", {}, `Chunks (${r.chunks.length})`), listBox, similar);
    drawText(); drawList();
    if (scroll) $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) { show($("detail"), failure(err)); }
}
function pager(box, total, per, view, key, redraw) {
  const pages = Math.max(1, Math.ceil(total / per));
  return show(box, h("button", { type: "button", disabled: view[key] === 0, onclick: () => { view[key]--; redraw(); } }, "Previous"),
    h("span", { class: "mono" }, `${view[key] + 1} / ${pages}`),
    h("button", { type: "button", disabled: view[key] >= pages - 1, onclick: () => { view[key]++; redraw(); } }, "Next"));
}
// The text of a document, one window of chunks at a time, with the chunk boundaries drawn faintly and each chunk's ordinal and page.
function drawChunks(box, pagerBox, text, chunks, view, key, per, redraw) {
  if (!chunks.length) { pagerBox.hidden = true; show(box, text ? h("span", {}, text.slice(0, 20000)) : empty("No text.")); return; }
  pagerBox.hidden = false;
  pager(pagerBox, chunks.length, per, view, key, redraw);
  const win = chunks.slice(view[key] * per, view[key] * per + per);
  const parts = [];
  let at = win[0].start;
  for (const c of win) {
    if (c.start > at) parts.push(h("span", { class: "gap" }, text.slice(at, c.start)));
    parts.push(h("span", { class: "chunk" }, h("span", { class: "tag" }, `#${c.ord}${c.page ? ` p.${c.page}` : ""}`), text.slice(c.start, c.end)));
    at = c.end;
  }
  show(box, parts);
}
function drawChunkList(box, chunks, view, similar, tenant, id, redraw) {
  const per = 20, win = chunks.slice(view.listPage * per, view.listPage * per + per);
  const pg = h("div", { class: "pager" });
  pager(pg, chunks.length, per, view, "listPage", redraw);
  show(box, h("table", {}, h("thead", {}, h("tr", {}, ["ord", "page", "span", "text", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, win.map((c) => h("tr", {}, h("td", { class: "num" }, c.ord), h("td", { class: "num" }, c.page ?? ""),
      h("td", { class: "mono" }, `${c.start}-${c.end}`), h("td", { class: "wrap mono" }, c.text.slice(0, 160) + (c.text.length > 160 ? "..." : "")),
      h("td", {}, h("button", { type: "button", class: "link", onclick: () => findSimilar(similar, tenant, id, c.ord) }, "similar")))))), pg);
}
async function findSimilar(into, tenant, id, ord) {
  show(into, h("h2", {}, `Passages like chunk #${ord}`), loading("passages"));
  try {
    const r = await api("/v1/similar", { method: "POST", json: { tenant, doc_id: id, ord, limit: 10 } });
    show(into, h("h2", {}, `Passages like chunk #${ord}`), hitList(r.hits, "", tenant));
  } catch (err) { show(into, failure(err)); }
}

// ---- 2. Add files ----------------------------------------------------------------------------------------------
// Files and folders go into a queue, a few at a time to POST /v1/ingest?mode=async: the service answers 202 with a job at
// once (a proxy cuts a request at 300 s, and a scanned PDF takes longer), and each row polls /v1/jobs/{id} until it ends. Unsupported types are left out here (the
// service says which: /v1/supported), a MANIFEST.md in a folder is read by the service (/v1/manifest) and its entries
// label the files beside it, and every file keeps its own state, so a failure never stops the rest.
const Q = { items: [], running: false, cancel: false, aborts: new Set(), manifests: {}, supported: { extensions: [], mimes: [] },
  skipped: [], drawing: false };
const EMPTY_VIEW = '{"entities":[],"values":[],"links":[]}';
const viewJson = () => (state.view ? state.view.json : EMPTY_VIEW);

function worldViewFile(input, note) {
  input.addEventListener("change", async () => {
    const f = input.files[0];
    if (!f) { state.view = null; } else {
      try {
        const body = JSON.parse(await f.text());
        const view = body.world_view || body;                       // the pack export wraps it with its inverted patterns
        if (!Array.isArray(view.entities)) throw new Error("no entities");
        state.view = { name: f.name, json: JSON.stringify(view), inverted: body.inverted || [], entities: view.entities.length };
      } catch (err) { state.view = null; input.value = ""; toast(`${f.name} is not a world view: ${err.message}`); }
    }
    syncView();
  });
}
function syncView() {
  const v = state.view;
  $("a-view-note").textContent = v ? `${v.name}: ${v.entities} entities` : "none: an empty world view";
  $("s-view-note").textContent = v ? `${v.name}: ${v.entities} entities` : "none: graph mode and model-name prefix hits are off";
  const graph = $("s-mode").querySelector("[value=graph]");
  graph.disabled = !v;
  if (!v && $("s-mode").value === "graph") $("s-mode").value = "hybrid";
}

// what a drop holds, folders walked: [{file, path}]. The entries must be taken before the first await.
async function collect(dt) {
  const entries = [...(dt.items || [])].map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean);
  const out = [];
  if (!entries.length) return [...dt.files].map((file) => ({ file, path: file.name }));
  for (const e of entries) await walk(e, "", out);
  return out;
}
async function walk(entry, dir, out) {
  if (entry.isFile) {
    out.push({ file: await new Promise((ok, no) => entry.file(ok, no)), path: dir + entry.name });
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    for (let batch = await readBatch(reader); batch.length; batch = await readBatch(reader)) {
      for (const child of batch) await walk(child, `${dir}${entry.name}/`, out);
    }
  }
}
const readBatch = (reader) => new Promise((ok, no) => reader.readEntries(ok, no));

const extOf = (name) => (name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "");
const isManifest = (path) => /(^|\/)manifest\.md$/i.test(path);
const dirOf = (path) => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
function supportedFile(file) {
  return Q.supported.extensions.includes(extOf(file.name)) || Q.supported.mimes.includes(file.type);
}
function manifestFor(path) {
  for (let dir = dirOf(path); ; dir = dirOf(dir)) {
    const m = Q.manifests[dir];
    if (m && m[path.slice(path.lastIndexOf("/") + 1)]) return m[path.slice(path.lastIndexOf("/") + 1)];
    if (!dir) return null;
  }
}
async function enqueue(found) {
  let manifests = 0;
  for (const { file, path } of found.filter((f) => isManifest(f.path))) {
    try {
      const m = await api("/v1/manifest", { method: "POST", json: { text: await file.text() } });
      Q.manifests[dirOf(path)] = m.entries; manifests++;
    } catch (err) { toast(`${path}: ${err.message}`); }
  }
  let added = 0;
  const have = new Set(Q.items.map((i) => `${i.path}|${i.file.size}|${i.file.lastModified}`));
  for (const { file, path } of found) {
    if (isManifest(path) || file.name.startsWith(".")) continue;     // a manifest labels files; it is not one of them
    if (!supportedFile(file)) { Q.skipped.push(path); continue; }
    const key = `${path}|${file.size}|${file.lastModified}`;
    if (have.has(key)) continue;
    have.add(key);
    Q.items.push({ file, path, state: "queued", tries: 0, result: null, error: "" });
    added++;
  }
  toast(`${added} queued${manifests ? `, ${manifests} manifest read` : ""}${Q.skipped.length ? `, ${Q.skipped.length} skipped (unsupported)` : ""}`);
  drawQueue();
}

function metaFor(it, tenant) {
  const published = $("a-published").value, entry = manifestFor(it.path);
  let source = $("a-source").value;
  if (entry && !source && entry.url) { try { source = new URL(entry.url).host; } catch (e) { /* not a URL: no source */ } }
  return { tenant, source, source_type: $("a-type").value, inverted: state.view ? state.view.inverted : [],
    ...(published ? { published_at: `${published}T00:00:00Z` } : {}), ...(entry ? { meta: { manifest: entry } } : {}) };
}
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
const pollDelay = (since) => { const s = (Date.now() - since) / 1000; return s < 30 ? 1000 : s < 120 ? 2000 : 5000; };
const elapsed = (since) => { const s = Math.floor((Date.now() - since) / 1000); return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m`; };
// the document's id in the lake: the first 24 hex digits of the file's SHA-256 (empty where the browser has no SubtleCrypto)
async function contentId(file) {
  try {
    const sum = new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()));
    return [...sum.slice(0, 12)].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch (e) { return ""; }
}
function finishItem(it, r) {
  state.timings[r.document.id] = r.timings;
  it.state = r.new ? "new" : "already stored";
  it.result = { id: r.document.id, status: r.document.status, warnings: r.warnings, error: r.document.error, timings: r.timings };
}
// The service no longer knows the job (a restart loses them, and the queue may be long gone): did the file reach the lake?
async function lostJob(it, tenant) {
  try {
    const d = (await api(lakePath(tenant, `/documents/${encodeURIComponent(it.contentId)}`))).document;
    it.state = "already stored"; it.note = "stored (the service lost its job record)";
    it.result = { id: d.id, status: d.status, warnings: [], error: d.error || "", timings: null };
  } catch (err) {
    it.state = "failed";
    it.error = err.status === 404 ? "the service lost this job (a restart) before the file was stored: send it again" : err.message;
  }
}
// Poll the job until it ends, 1 s at first, then 2 s, then 5 s. Cancel does not stop this: a running job cannot be cancelled.
async function follow(it, tenant) {
  let misses = 0;
  for (;;) {
    await sleep(pollDelay(it.since));
    let job;
    try { job = await api(`/v1/jobs/${encodeURIComponent(it.job)}`); misses = 0; } catch (err) {
      if (err.status === 401) { it.state = "failed"; it.error = err.message; Q.cancel = true; return; }
      if (err.status === 404 || ++misses >= 5) { await lostJob(it, tenant); return; }
      continue;
    }
    if (job.status === "succeeded") { finishItem(it, job.results[0]); return; }
    if (job.status === "failed") { it.state = "failed"; it.error = job.error || "the job failed"; return; }
    it.state = job.status === "running" ? "running" : "waiting";
    it.progress = job.progress;
    drawQueue();
  }
}
async function sendOne(it, tenant) {
  const form = new FormData(), ctl = new AbortController();
  it.contentId = it.contentId || await contentId(it.file);
  form.append("meta", JSON.stringify(metaFor(it, tenant)));
  form.append("world_view", new Blob([viewJson()], { type: "application/json" }), "world_view.json");
  form.append("files", it.file, it.file.name);
  Q.aborts.add(ctl);
  let job;
  try {
    job = await api("/v1/ingest?mode=async", { method: "POST", body: form, signal: ctl.signal });
  } catch (err) {
    if (ctl.signal.aborted) { it.state = "cancelled"; }
    else if ((err.status === undefined || err.status >= 502) && it.tries < 1) { it.tries++; it.state = "queued"; }     // the network, once more
    else { it.state = "failed"; it.error = err.message; if (err.status === 401) Q.cancel = true; }
    return;
  } finally { Q.aborts.delete(ctl); }
  it.job = job.id; it.since = Date.now(); it.state = "waiting"; drawQueue();
  await follow(it, tenant);
}
async function runQueue() {
  const tenant = $("a-tenant").value.trim();
  if (Q.running) return;
  if (!tenant) { toast("A tenant is required."); return; }
  Q.running = true; Q.cancel = false; drawQueue();
  const worker = async () => {
    while (!Q.cancel) {
      const it = Q.items.find((i) => i.state === "queued");
      if (!it) return;
      it.state = "sending"; drawQueue();
      await sendOne(it, tenant);
      drawQueue();
    }
  };
  const tick = setInterval(drawQueue, 1000);                          // the elapsed time of a running job
  await Promise.all(Array.from({ length: +$("a-conc").value || 1 }, worker));
  clearInterval(tick);
  Q.running = false; drawQueue();
  const left = Q.items.filter((i) => i.state === "failed").length;
  toast(Q.cancel ? "Cancelled: nothing more is sent." : left ? `Finished, ${left} failed.` : "Finished.");
  if (state.tab === "lake") loadLake({ quiet: true });
}
function cancelQueue() {
  Q.cancel = true;
  for (const ctl of Q.aborts) ctl.abort();
  for (const it of Q.items) if (it.state === "queued") it.state = "cancelled";
  drawQueue();
}
function retryFailed() {
  for (const it of Q.items) if (it.state === "failed" || it.state === "cancelled") { it.state = "queued"; it.tries = 0; it.error = ""; it.note = ""; }
  runQueue();
}

function drawQueue() {
  if (Q.drawing) return;
  Q.drawing = true;
  requestAnimationFrame(() => { Q.drawing = false; paintQueue(); });
}
const QSTATES = ["new", "already stored", "failed", "cancelled", "running", "waiting", "sending", "queued"];
const chipFor = (it) => h("span", { class: `chip ${it.state}` },
  it.state === "running" || it.state === "waiting" ? `${it.state}… ${elapsed(it.since)}` : it.state);
function detailOf(it) {
  const r = it.result, p = it.progress;
  if (r) return [it.note, r.warnings.join("; ") || r.error || stages(r.timings)].filter(Boolean).join(" ");
  if (it.state === "waiting") return "queued on the service behind earlier jobs";
  if (it.state === "running") return p && p.current ? `working on ${p.current}` : "";
  return "";
}
function paintQueue() {
  const by = (s) => Q.items.filter((i) => i.state === s);
  const total = Q.items.length, counts = Object.fromEntries(QSTATES.map((s) => [s, by(s).length]));
  const finished = counts.new + counts["already stored"] + counts.failed + counts.cancelled;
  $("queue-head").hidden = !total;
  $("a-progress").max = Math.max(1, total); $("a-progress").value = finished;
  show($("a-counts"), [`${finished} of ${total}`, ...QSTATES.filter((s) => counts[s]).map((s) => `${s} ${counts[s]}`),
    Q.skipped.length ? h("span", { title: Q.skipped.slice(0, 50).join("\n") }, `skipped ${Q.skipped.length} unsupported`) : null]
    .filter(Boolean).flatMap((x, k) => (k ? [" · ", x] : [x])));
  $("a-send").disabled = Q.running || !counts.queued;
  $("a-cancel").disabled = !Q.running;
  $("a-retry").disabled = Q.running || !(counts.failed + counts.cancelled);
  $("a-clear").disabled = Q.running || !(counts.new + counts["already stored"]);
  if (!total) { show($("queue")); return; }
  // a long queue shows what matters: what failed, what is in flight, the latest finished, the next to go
  const CAP = { failed: 100, cancelled: 20, running: 4, waiting: 8, sending: 4, new: 15, "already stored": 15, queued: 25 };
  const shown = [...by("failed").slice(0, CAP.failed), ...by("cancelled").slice(0, CAP.cancelled), ...by("running"),
    ...by("waiting").slice(0, CAP.waiting), ...by("sending"),
    ...[...by("new"), ...by("already stored")].slice(-CAP.new), ...by("queued").slice(0, CAP.queued)];
  const hidden = total - shown.length;
  show($("queue"), h("table", {}, h("thead", {}, h("tr", {}, ["file", "state", "document", "detail", ""].map((t) => h("th", {}, t)))),
    h("tbody", {}, shown.map((it) => {
      const r = it.result;
      return h("tr", {}, h("td", { class: "mono wrap" }, it.path), h("td", {}, chipFor(it)), h("td", {}, r ? chip(r.status) : null),
        h("td", { class: `wrap ${it.state === "failed" ? "error" : "muted"}` }, it.error || detailOf(it)),
        h("td", {}, r ? h("a", { onclick: () => openDoc($("a-tenant").value.trim(), r.id) }, "open in Lake") : null));
    }))),
    hidden ? h("div", { class: "muted" }, `${hidden} more not shown (finished earlier or still waiting)`) : null);
}

// ---- 3. Search -------------------------------------------------------------------------------------------------
function highlight(text, query) {
  const words = [...new Set(query.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 1))];
  if (!words.length) return [text];
  const re = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "giu");
  const out = [];
  let at = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m[0] === "") { re.lastIndex++; continue; }
    out.push(text.slice(at, m.index), h("mark", {}, m[0]));
    at = m.index + m[0].length;
  }
  out.push(text.slice(at));
  return out;
}
function hitList(hits, query, tenant, mode) {
  if (!hits.length) return empty("No hits.");
  return h("div", {}, hits.map((x) => {
    const sim = h("div");
    if (x.kind !== "chunk") {
      return h("div", { class: "hit" }, h("div", { class: "head" }, h("b", {}, x.text), h("span", { class: "mono" }, x.kind), h("span", { class: "mono" }, `score ${x.score}`),
        h("span", {}, (x.why || []).join(", "))));
    }
    return h("div", { class: "hit" },
      h("div", { class: "head" }, h("span", { class: "mono" }, `score ${x.score}`), mode ? chip(mode) : null,
        h("span", {}, (x.why || []).join(", ")), h("b", {}, x.title || x.filename),
        h("span", { class: "mono" }, `#${x.ord}${x.page ? ` p.${x.page}` : ""}`), h("span", { class: "mono" }, when(x.event_time)),
        h("a", { onclick: () => openDoc(tenant, x.doc_id) }, "open"),
        h("button", { type: "button", class: "link", onclick: () => findSimilar(sim, tenant, x.doc_id, x.ord) }, "similar")),
      h("div", { class: "body" }, highlight(x.text || "", query)), sim);
  }));
}
async function runSearch(mode, limit) {
  const body = { tenant: state.tenant, q: $("s-q").value, mode, limit, world_view: state.view ? state.view.json : null };
  return (await api("/v1/search", { method: "POST", json: body })).hits;
}
async function search(ev) {
  ev.preventDefault();
  const query = $("s-q").value, mode = $("s-mode").value;
  if (!query.trim()) { show($("search-results"), empty("Type a query.")); return; }
  show($("search-results"), loading("hits"));
  try { show($("search-results"), hitList(await runSearch(mode, +$("s-limit").value || 10), query, state.tenant, mode)); }
  catch (err) { show($("search-results"), failure(err)); }
}
async function compare() {
  const query = $("s-q").value;
  if (!query.trim()) { show($("search-results"), empty("Type a query.")); return; }
  const modes = MODES.filter((m) => m !== "graph" || state.view);
  show($("search-results"), loading("hits"));
  const limit = +$("s-limit").value || 10;
  const cols = await Promise.all(modes.map(async (m) => {
    try { return h("div", {}, h("h3", {}, m), hitList(await runSearch(m, limit), query, state.tenant)); }
    catch (err) { return h("div", {}, h("h3", {}, m), failure(err)); }
  }));
  show($("search-results"), h("div", { class: "cols" }, cols));
}

// ---- 4. Stage debugger -----------------------------------------------------------------------------------------
async function loadStored() {
  const sel = $("d-doc");
  try {
    const r = await api(lakePath(state.tenant, "/documents") + q({ order: "ingested_at", limit: 200 }));
    show(sel, r.documents.map((d) => h("option", { value: d.id }, `${d.title || d.filename}  ${d.id.slice(0, 8)}`)));
  } catch (err) { show(sel, h("option", { value: "" }, err.message)); }
}
async function debugStored(tenant, id) {
  if (tenant !== state.tenant) setTenant(tenant);
  document.querySelector("input[name=d-from][value=stored]").checked = true;
  $("d-file-row").hidden = true; $("d-stored-row").hidden = false;
  switchTab("debug");
  await loadStored();
  if (![...$("d-doc").options].some((o) => o.value === id)) $("d-doc").append(h("option", { value: id }, id.slice(0, 8)));
  $("d-doc").value = id;
  runDebug({ preventDefault() {} });
}
async function runDebug(ev) {
  ev.preventDefault();
  const out = $("debug-results");
  const stored = document.querySelector("input[name=d-from]:checked").value === "stored";
  let opts;
  if (stored) {
    if (!$("d-doc").value) { toast("Pick a document."); return; }
    opts = { method: "POST", json: { tenant: state.tenant, doc_id: $("d-doc").value } };
  } else {
    const f = $("d-file").files[0];
    if (!f) { toast("Choose a file."); return; }
    const published = $("d-published").value;
    const form = new FormData();
    form.append("file", f, f.name);
    form.append("meta", JSON.stringify({ tenant: state.tenant, source_type: $("d-type").value, ...(published ? { published_at: `${published}T00:00:00Z` } : {}) }));
    opts = { method: "POST", body: form };
  }
  show(out, loading("the dry run"));
  try { drawStages(out, await api("/v1/debug/stages", { method: "POST", ...opts })); } catch (err) { show(out, failure(err)); }
}
const kv = (o) => h("dl", { class: "kv" }, Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "")
  .map(([k, v]) => [h("dt", {}, k), h("dd", {}, typeof v === "object" ? JSON.stringify(v) : String(v))]));
const table = (heads, rows) => h("table", {}, h("thead", {}, h("tr", {}, heads.map((t) => h("th", { class: /^#/.test(t) ? "num" : "" }, t.replace(/^#/, ""))))), h("tbody", {}, rows));

function drawStages(out, r) {
  const render = { store: cardStore, parse: cardParse, type: cardType, chunk: cardChunk, index: cardIndex, duplicates: cardDuplicates };
  show(out, h("div", { class: "row" }, h("span", { class: "mono" }, r.filename), h("span", { class: "mono muted" }, r.doc_id),
    r.stopped ? h("span", { class: "error" }, `stops at ${r.stopped.stage}: ${r.stopped.reason}`) : null),
    r.stages.map((s) => h("details", { class: "card", open: s.status !== "skipped" && s.id !== "duplicates" },
      h("summary", {}, h("b", {}, s.title), chip(s.status), h("span", { class: "decision" }, s.decision), h("span", { class: "sec" }, secs(s.seconds))),
      h("div", { class: "inner" }, s.status === "skipped" ? h("div", { class: "muted" }, s.decision) : render[s.id](s.data, r)))));
}
function cardStore(d) {
  return h("div", {}, kv({ doc_id: d.doc_id, sha256: d.sha256, size: `${d.size} bytes`, mime: d.mime }),
    d.stored ? h("div", {}, h("h3", {}, "In the lake"), kv(d.stored), h("a", { onclick: () => openDoc(state.tenant, d.doc_id) }, "open in Lake")) : null);
}
function cardParse(d) {
  if (d.error) return h("div", { class: "error" }, d.error);
  const sel = h("select", { "aria-label": "Page" }, h("option", { value: "all" }, `whole text (${d.chars} characters)`),
    d.segments.filter((s) => s.chars).map((s) => h("option", { value: s.index }, `${s.label || (s.page ? `page ${s.page}` : `segment ${s.index}`)} (${s.chars})`)));
  const box = h("pre", { class: "text panel" });
  const more = h("div", { class: "muted" });
  const draw = () => {
    const seg = sel.value === "all" ? { start: 0, end: d.text.length } : d.segments[+sel.value];
    const t = d.text.slice(seg.start, seg.end);
    show(box, t.slice(0, 20000)); show(more, t.length > 20000 ? `showing the first 20,000 of ${t.length} characters` : "");
  };
  sel.addEventListener("change", draw); draw();
  return h("div", {}, kv({ format: d.format, parser: d.parser, title: d.title, characters: d.chars, encoding: d.encoding,
    needs_ocr: (d.needs_ocr || []).join(", "), ocr: d.ocr }),
    h("h3", {}, "Segments"), table(["segment", "page", "label", "#chars", "span"], d.segments.map((s) => h("tr", {}, h("td", { class: "num" }, s.index),
      h("td", {}, s.page ?? ""), h("td", {}, s.label), h("td", { class: "num" }, s.chars), h("td", { class: "mono" }, s.start === null ? "" : `${s.start}-${s.end}`)))),
    h("h3", {}, "Normalized text"), sel, box, more);
}
function cardType(d) {
  return h("div", { class: "cols" }, h("div", {}, h("h3", {}, "Type"), kv({ type: d.doc_type.type, basis: d.doc_type.basis, excluded: d.doc_type.excluded,
    reason: d.doc_type.reason, substance: d.substance, source_type: d.source_type, screened: d.screened })),
    h("div", {}, h("h3", {}, "Dates"), kv({ published_at: d.published_at, rule: d.published_source, period: d.period, period_source: d.period_source }),
      h("pre", { class: "json" }, JSON.stringify(d.dates, null, 1))),
    h("div", {}, h("h3", {}, "Language and yen"), kv({ language: d.language, yen: d.yen.code, basis: d.yen.basis }),
      h("pre", { class: "json" }, JSON.stringify(d.yen, null, 1))));
}
function cardChunk(d) {
  const max = Math.max(1, ...d.histogram.bins.map((b) => b.count), d.histogram.over);
  const bar = (cls, title, n) => { const b = h("div", { class: cls, title }); b.style.height = `${(100 * n) / max}%`; return b; };   // CSSOM: the CSP has no inline styles
  const bars = d.histogram.bins.map((b) => bar("", `${b.from}-${b.to}: ${b.count}`, b.count));
  if (d.histogram.over) bars.push(bar("over", `over ${d.limit}: ${d.histogram.over}`, d.histogram.over));
  const view = { page: 0 }, box = h("div"), pg = h("div", { class: "pager" });
  const draw = () => {
    show(box, d.chunks.slice(view.page * 25, view.page * 25 + 25).map((c) => h("div", { class: "hit" },
      h("div", { class: "head" }, h("b", {}, `#${c.ord}`), h("span", { class: "mono" }, `page ${c.page ?? "-"}`), h("span", { class: "mono" }, `${c.start}-${c.end}`),
        h("span", { class: "mono" }, `weight ${c.weight}`), c.cut ? h("span", { class: "chip failed" }, "cut from a long sentence") : null),
      h("div", { class: `body${c.cut ? " cut" : ""}` }, sentenceSpans(c)))));
    pager(pg, d.chunks.length, 25, view, "page", draw);
  };
  draw();
  return h("div", {}, h("h3", {}, `Chunk weights (limit ${d.limit}${d.histogram.over ? `, ${d.histogram.over} over it` : ""})`),
    h("div", { class: "hist" }, bars), h("div", { class: "hist-axis" }, h("span", {}, "0"), h("span", {}, String(d.limit))), pg, box);
}
function sentenceSpans(c) {
  const out = [];
  let at = 0;
  for (const [a, b] of c.sentences) {
    if (a > at) out.push(c.text.slice(at, a));
    out.push(h("span", { class: "sent" }, c.text.slice(a, b)));
    at = b;
  }
  out.push(c.text.slice(at));
  return out;
}
function cardIndex(d) {
  const k = d.keyword, e = d.embedding, sel = h("select", { "aria-label": "Chunk" }, k.chunks.map((c) => h("option", { value: c.ord }, `chunk #${c.ord}`)));
  const terms = h("div");
  const draw = () => {
    const c = k.chunks.find((x) => String(x.ord) === sel.value);
    show(terms, c ? table(["term", "as indexed (stemmed by FTS5)", "#count"], c.terms.slice(0, 200).map((t) => h("tr", {}, h("td", { class: "mono" }, t.term),
      h("td", { class: "mono" }, t.norm), h("td", { class: "num" }, t.count)))) : empty("No chunks."));
  };
  sel.addEventListener("change", draw); draw();
  return h("div", {}, h("h3", {}, "Keyword index"), h("p", { class: "muted" }, `${k.note}. Terms below are cut with text.tokens and normalized with text.norm (a plural's s dropped); the Porter stem itself is applied inside SQLite and is not shown. First ${k.detail_chunks} chunks.`),
    sel, terms,
    h("h3", {}, "Embedding"), kv({ embedder: e.name, dimension: e.dim }),
    table(["chunk", "#norm", "first 8 components"], e.chunks.map((c) => h("tr", {}, h("td", { class: "mono" }, `#${c.ord}`),
      h("td", { class: "num" }, c.norm.toFixed(4)), h("td", { class: "mono" }, c.head.map((x) => x.toFixed(4)).join("  "))))),
    h("h3", {}, "Nearest stored passages"),
    d.nearest ? d.nearest.map((n) => h("div", {}, h("div", { class: "muted mono" }, `chunk #${n.ord}`),
      n.hits.length ? hitList(n.hits.map((x) => ({ ...x, kind: "chunk", why: [] })), "", state.tenant) : empty("None in this tenant's lake."))) : empty("No tenant: no lake to search."));
}
function cardDuplicates(d) {
  return h("div", {}, kv({ period_end: d.period_end, figures: d.figures, distinct_figures: d.distinct, fingerprint: d.digest }),
    d.compared ? [h("h3", {}, "Containment against stored documents of this period"),
      d.compared.length ? table(["document", "#containment", "#shared", "#figures", "same"], d.compared.map((c) => h("tr", {},
        h("td", { class: "wrap" }, h("a", { onclick: () => openDoc(state.tenant, c.doc_id) }, c.title)), h("td", { class: "num" }, c.containment),
        h("td", { class: "num" }, c.shared), h("td", { class: "num" }, c.figures), h("td", {}, c.matches ? "yes" : "no")))) : empty("None."),
      d.group ? kv({ group: d.group.id, role: d.group.role, primary: d.group.primary, members: d.group.members.join(", "), rule: d.group.rule }) : null] : null);
}

// ---- wiring ----------------------------------------------------------------------------------------------------
function typing(ev) {
  const t = ev.target;
  return t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA" || t.isContentEditable);
}
const KEYS = [["1 2 3 4", "Lake, Add files, Search, Stage debugger"], ["/", "Search"], ["j k", "Next or previous row in the Lake table"],
  ["Enter", "Open the highlighted row"], ["r", "Refresh the Lake now"], ["p", "Pause or resume the live refresh"],
  ["n", "Mark new rows as seen"], ["?", "This list"], ["Esc", "Close a dialog"]];
function toggleHelp() {
  const d = $("help");
  if (d.open) { d.close(); return; }
  show($("help-keys"), KEYS.flatMap(([k, what]) => [h("dt", {}, h("kbd", {}, k)), h("dd", {}, what)]));
  d.showModal();
}
const refreshNow = () => { L.version = null; poll(); };
function togglePause() { L.paused = !L.paused; if (L.paused) stopPolling(); else poll(); setLive(); }
function resetLake() {
  Object.assign(L, { offset: 0, open: null, version: null, baseline: null, latest: null, cur: -1, fails: 0, updated: null });
  setNew(0); show($("detail"));
}
async function takeFiles(found) {
  if (!state.token) return;
  await enqueue(found);
}
function init() {
  for (const sel of [$("a-type"), $("d-type")]) show(sel, SOURCE_TYPES.map((t) => h("option", { value: t }, t)));
  for (const b of document.querySelectorAll("#tabs button")) b.addEventListener("click", () => switchTab(b.dataset.tab));
  $("gate-form").addEventListener("submit", (ev) => { ev.preventDefault(); keep($("token").value.trim()); enter(); });
  $("signout").addEventListener("click", () => { keep(""); gate(""); });
  $("help-open").addEventListener("click", toggleHelp);
  $("tenant").addEventListener("change", () => { setTenant($("tenant").value.trim() || "default"); resetLake(); refresh(); });
  $("filters").addEventListener("submit", (ev) => { ev.preventDefault(); L.offset = 0; L.cur = -1; loadTable(); });
  for (const id of ["f-status", "f-type", "f-language", "f-order", "f-dir"]) $(id).addEventListener("change", () => { L.offset = 0; L.cur = -1; loadTable(); });
  $("f-limit").addEventListener("change", () => { L.limit = +$("f-limit").value; L.offset = 0; loadTable(); });
  $("live-toggle").addEventListener("click", togglePause);
  $("live-now").addEventListener("click", refreshNow);
  $("new-chip").addEventListener("click", markSeen);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") poll(); else schedule(); });
  $("pick").addEventListener("click", () => $("files").click());
  $("pick-dir").addEventListener("click", () => $("dir").click());
  for (const id of ["files", "dir"]) {
    $(id).addEventListener("change", async () => {
      await takeFiles([...$(id).files].map((file) => ({ file, path: file.webkitRelativePath || file.name })));
      $(id).value = "";
    });
  }
  const drop = $("drop");
  drop.addEventListener("dragover", (ev) => { ev.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (ev) => { ev.preventDefault(); drop.classList.remove("over"); collect(ev.dataTransfer).then(takeFiles); });
  $("add-form").addEventListener("submit", (ev) => { ev.preventDefault(); runQueue(); });
  $("a-cancel").addEventListener("click", cancelQueue);
  $("a-retry").addEventListener("click", retryFailed);
  $("a-clear").addEventListener("click", () => { Q.items = Q.items.filter((i) => i.state !== "new" && i.state !== "already stored"); Q.skipped = []; drawQueue(); });
  worldViewFile($("a-view"), $("a-view-note")); worldViewFile($("s-view"), $("s-view-note"));
  $("search-form").addEventListener("submit", search);
  $("s-compare").addEventListener("click", compare);
  $("debug-form").addEventListener("submit", runDebug);
  for (const r of document.querySelectorAll("input[name=d-from]")) {
    r.addEventListener("change", () => { const s = document.querySelector("input[name=d-from]:checked").value === "stored";
      $("d-file-row").hidden = s; $("d-stored-row").hidden = !s; if (s) loadStored(); });
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey || typing(ev) || $("app").hidden || document.querySelector("dialog[open]") && ev.key !== "?") return;
    if (ev.key === "/") { ev.preventDefault(); switchTab("search"); $("s-q").focus(); }
    if (ev.key === "?") toggleHelp();
    const tab = { 1: "lake", 2: "add", 3: "search", 4: "debug" }[ev.key];
    if (tab) switchTab(tab);
    if (state.tab !== "lake") return;
    if (ev.key === "j") moveCur(1);
    if (ev.key === "k") moveCur(-1);
    if (ev.key === "Enter" && ev.target.tagName !== "BUTTON" && L.cur >= 0) { const row = document.querySelectorAll("#table tbody tr")[L.cur]; if (row) row.click(); }
    if (ev.key === "r") refreshNow();
    if (ev.key === "p") togglePause();
    if (ev.key === "n") markSeen();
  });
  syncView(); setLive(); drawQueue();
  keep(kept());
  if (state.token) enter(); else gate("");
}
init();
