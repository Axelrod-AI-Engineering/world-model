"use strict";
// The ingestion console: plain JS, no framework. Every string from the lake or an upload is put on the page as a text
// node (the `h` helper), never as markup: document text is untrusted.

const $ = (id) => document.getElementById(id);
const SOURCE_TYPES = ["other", "broker_research", "expert_call", "news", "central_bank", "data", "filing", "client_model"];
const MODES = ["keyword", "prefix", "semantic", "hybrid", "graph"];
const state = { token: "", tenant: "", tab: "lake", view: null, lake: { offset: 0, limit: 50, open: null }, files: [] };

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
  const resp = await fetch(path, { method: opts.method || "GET", headers, body });
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
  $("gate").hidden = false; $("app").hidden = true; $("signout").hidden = true;
  $("gate-error").hidden = !message; $("gate-error").textContent = message || "";
  $("token").value = ""; $("token").focus();
}
async function enter() {
  $("gate").hidden = true; $("app").hidden = false; $("signout").hidden = false;
  try {
    const { tenants } = await api("/v1/tenants");
    show($("tenants"), tenants.map((t) => h("option", { value: t })));
    if (!state.tenant) setTenant(tenants[0] || "default");
  } catch (err) {
    if (err.status === 401) return;                                 // the gate is showing again
    toast(err.message);
    if (!state.tenant) setTenant("default");
    return;
  }
  refresh();
}
function setTenant(t) {
  state.tenant = t; $("tenant").value = t; $("a-tenant").value = t;
}
function switchTab(tab) {
  state.tab = tab;
  for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("on", b.dataset.tab === tab);
  for (const s of document.querySelectorAll(".tab")) s.hidden = s.id !== `tab-${tab}`;
  refresh();
}
function refresh() {
  if (!state.token) return;
  if (state.tab === "lake") loadLake();
  if (state.tab === "debug") loadStored();
}

// ---- 1. Lake ---------------------------------------------------------------------------------------------------
async function loadLake() {
  show($("summary"), loading("summary"));
  try {
    const s = await api(lakePath(state.tenant, "/summary"));
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
  } catch (err) { show($("summary"), failure(err)); }
  loadTable();
}
async function loadTable() {
  const L = state.lake;
  show($("table"), loading("documents"));
  const params = { status: $("f-status").value, type: $("f-type").value, language: $("f-language").value, q: $("f-q").value,
    order: $("f-order").value, dir: $("f-dir").value, limit: L.limit, offset: L.offset };
  try {
    const r = await api(lakePath(state.tenant, "/documents") + q(params));
    if (!r.documents.length) { show($("table"), empty("No documents match.")); return; }
    const th = (t, cls) => h("th", { class: cls }, t);
    const rows = r.documents.map((d) => h("tr", { class: `pick${L.open === d.id ? " sel" : ""}`, onclick: () => openDoc(state.tenant, d.id) },
      h("td", { class: "wrap" }, d.title || d.filename, d.title && d.title !== d.filename ? h("div", { class: "muted mono" }, d.filename) : null),
      h("td", {}, chip(d.status)), h("td", {}, d.type), h("td", {}, d.language),
      h("td", { class: "mono" }, d.published_at ? d.published_at.slice(0, 10) : "", d.published_source ? h("div", { class: "muted" }, d.published_source) : null),
      h("td", { class: "mono" }, d.period), h("td", { class: "num" }, d.pages ?? ""), h("td", { class: "num" }, d.chunks),
      h("td", { class: "num" }, bytes(d.size)), h("td", { class: "mono" }, when(d.ingested_at))));
    const last = Math.min(r.total, L.offset + r.documents.length);
    show($("table"),
      h("table", {}, h("thead", {}, h("tr", {}, th("document"), th("status"), th("type"), th("lang"), th("published"), th("period"),
        th("pages", "num"), th("chunks", "num"), th("size", "num"), th("ingested"))), h("tbody", {}, rows)),
      h("div", { class: "pager" },
        h("button", { type: "button", disabled: L.offset === 0, onclick: () => { L.offset = Math.max(0, L.offset - L.limit); loadTable(); } }, "Previous"),
        h("span", { class: "mono" }, `${L.offset + 1}-${last} of ${r.total}`),
        h("button", { type: "button", disabled: last >= r.total, onclick: () => { L.offset += L.limit; loadTable(); } }, "Next")));
  } catch (err) { show($("table"), failure(err)); }
}

function section(title, obj) {
  const rows = Object.entries(obj || {}).filter(([, v]) => v !== "" && v !== null && v !== undefined);
  if (!rows.length) return null;
  return h("div", {}, h("h3", {}, title), h("dl", { class: "kv" }, rows.map(([k, v]) => [h("dt", {}, k), h("dd", {}, typeof v === "object" ? JSON.stringify(v) : String(v))])));
}
async function openDoc(tenant, id) {
  if (tenant !== state.tenant) setTenant(tenant);
  if (state.tab !== "lake") { state.lake.open = id; switchTab("lake"); }
  state.lake.open = id;
  for (const tr of document.querySelectorAll("#table tbody tr")) tr.classList.remove("sel");
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
    const view = { chunkPage: 0, listPage: 0 };
    const textBox = h("div", { class: "text" }), textPager = h("div", { class: "pager" });
    const listBox = h("div"), similar = h("div");
    const drawText = () => drawChunks(textBox, textPager, r.text, r.chunks, view, "chunkPage", 25, drawText);
    const drawList = () => drawChunkList(listBox, r.chunks, view, similar, tenant, id, drawList);
    show($("detail"),
      h("h2", {}, d.title || d.filename),
      h("div", { class: "row" }, chip(d.status), h("span", { class: "mono muted" }, id), raw,
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
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
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
function drawPicked() {
  show($("picked"), state.files.map((f) => h("li", { class: "mono" }, `${f.name}  `, h("span", { class: "muted" }, bytes(f.size)))));
}
async function sendFiles(ev) {
  ev.preventDefault();
  if (!state.files.length) { toast("Choose at least one file."); return; }
  const out = $("add-results"), tenant = $("a-tenant").value.trim();
  if (!tenant) { toast("A tenant is required."); return; }
  $("a-send").disabled = true;
  show(out, h("h2", {}, "Results"));
  const body = h("tbody");
  out.append(h("table", {}, h("thead", {}, h("tr", {}, ["file", "result", "status", "warnings", "stage timings", ""].map((t) => h("th", {}, t)))), body));
  const published = $("a-published").value;
  const view = state.view ? state.view.json : '{"entities":[],"values":[],"links":[]}';
  for (const f of state.files) {
    const row = h("tr", {}, h("td", { class: "mono wrap" }, f.name), h("td", { colspan: 5 }, "sending..."));
    body.append(row);
    const meta = { tenant, source: $("a-source").value, source_type: $("a-type").value, inverted: state.view ? state.view.inverted : [],
      ...(published ? { published_at: `${published}T00:00:00Z` } : {}) };
    const form = new FormData();
    form.append("meta", JSON.stringify(meta));
    form.append("world_view", new Blob([view], { type: "application/json" }), "world_view.json");
    form.append("files", f, f.name);
    try {
      const r = (await api("/v1/ingest", { method: "POST", body: form })).results[0];
      const d = r.document;
      show(row, h("td", { class: "mono wrap" }, f.name), h("td", {}, r.new ? "new" : "already stored"), h("td", {}, chip(d.status)),
        h("td", { class: "wrap" }, r.warnings.join("; ") || (d.error || "")),
        h("td", { class: "mono" }, Object.entries(r.timings).map(([k, v]) => `${k} ${secs(v)}`).join("  ")),
        h("td", {}, h("a", { onclick: () => openDoc(tenant, d.id) }, "open in Lake")));
    } catch (err) { show(row, h("td", { class: "mono wrap" }, f.name), h("td", { colspan: 5, class: "error" }, err.message)); }
  }
  $("a-send").disabled = false;
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
function init() {
  for (const sel of [$("a-type"), $("d-type")]) show(sel, SOURCE_TYPES.map((t) => h("option", { value: t }, t)));
  for (const b of document.querySelectorAll("#tabs button")) b.addEventListener("click", () => switchTab(b.dataset.tab));
  $("gate-form").addEventListener("submit", (ev) => { ev.preventDefault(); keep($("token").value.trim()); enter(); });
  $("signout").addEventListener("click", () => { keep(""); gate(""); });
  $("tenant").addEventListener("change", () => { setTenant($("tenant").value.trim() || "default"); state.lake.offset = 0; state.lake.open = null; show($("detail")); refresh(); });
  $("filters").addEventListener("submit", (ev) => { ev.preventDefault(); state.lake.offset = 0; loadTable(); });
  $("pick").addEventListener("click", () => $("files").click());
  $("files").addEventListener("change", () => { state.files = [...$("files").files]; drawPicked(); });
  const drop = $("drop");
  drop.addEventListener("dragover", (ev) => { ev.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (ev) => { ev.preventDefault(); drop.classList.remove("over"); state.files = [...ev.dataTransfer.files]; drawPicked(); });
  $("add-form").addEventListener("submit", sendFiles);
  worldViewFile($("a-view"), $("a-view-note")); worldViewFile($("s-view"), $("s-view-note"));
  $("search-form").addEventListener("submit", search);
  $("s-compare").addEventListener("click", compare);
  $("debug-form").addEventListener("submit", runDebug);
  for (const r of document.querySelectorAll("input[name=d-from]")) {
    r.addEventListener("change", () => { const s = document.querySelector("input[name=d-from]:checked").value === "stored";
      $("d-file-row").hidden = s; $("d-stored-row").hidden = !s; if (s) loadStored(); });
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey || ev.metaKey || ev.altKey || typing(ev) || $("app").hidden) return;
    if (ev.key === "/") { ev.preventDefault(); switchTab("search"); $("s-q").focus(); }
    const tab = { 1: "lake", 2: "add", 3: "search", 4: "debug" }[ev.key];
    if (tab) switchTab(tab);
  });
  syncView();
  keep(kept());
  if (state.token) enter(); else gate("");
}
init();
