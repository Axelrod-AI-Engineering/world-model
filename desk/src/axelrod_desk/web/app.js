// The export desk's page: plain JavaScript over the desk's /api. Every value from the server is escaped before it is
// shown (esc), because document titles, quotes and labels come from client files.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const CLASS_NAMES = { company: "Company", sell_side: "Sell-side", other: "Other" };
let me = null, catalog = null, timer = null;

async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts };
  if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(path, init);
  if (r.status === 401 && path !== "/api/login") { showSignin(); throw new Error("sign in first"); }
  if (r.status === 204) return null;
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status}`);
  return body;
}

// -- sign-in ------------------------------------------------------------------------------------------------------------
async function showSignin() {
  $("#shell").hidden = true; $("#signin").hidden = false;
  const { needed } = await api("/api/setup");
  $("#name-row").hidden = !needed;
  $("#signin-note").textContent = needed ? "Make the first account. It is an admin, who adds the others." : "Sign in with your desk account.";
  $("#signin-form").dataset.setup = needed ? "1" : "";
  $("#signin-form button").textContent = needed ? "Create account" : "Sign in";
}

$("#signin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target), setup = e.target.dataset.setup;
  try {
    await api(setup ? "/api/setup" : "/api/login", { method: "POST", json: { email: f.get("email"), password: f.get("password"), name: f.get("name") || "" } });
    start();
  } catch (err) { $("#signin-error").textContent = err.message; }
});

$("#signout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showSignin(); });

async function start() {
  try { me = await api("/api/me"); } catch { return; }
  catalog = await api("/api/catalog");
  $("#signin").hidden = true; $("#shell").hidden = false;
  $("#me").textContent = me.name;
  $("#accounts-tab").hidden = !me.admin;
  fillSelects();
  route();
}

function fillSelects() {
  const co = catalog.companies.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
  const cl = catalog.classes.map((c) => `<option value="${esc(c)}">${esc(CLASS_NAMES[c] || c)}</option>`).join("");
  $("#up-company").innerHTML = `<option value="">detect</option>${co}`;
  $("#f-company").innerHTML = `<option value="">all</option>${co}`;
  $("#fact-company").innerHTML = co;
  $("#up-class").innerHTML = `<option value="">detect</option>${cl}`;
  $("#f-class").innerHTML = `<option value="">all</option>${cl}`;
}

// -- routing ------------------------------------------------------------------------------------------------------------
const VIEWS = { library: loadLibrary, facts: loadFacts, "world-models": loadWorldModels, reader: loadReader, accounts: loadAccounts };
function route() {
  const asked = (location.hash || "#library").slice(1);
  const view = Object.hasOwn(VIEWS, asked) ? asked : "library";      // only our own views: never an inherited name
  clearInterval(timer);
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== view));
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${view}`));
  closeDrawer();
  VIEWS[view]();
}
window.addEventListener("hashchange", route);

// -- library ------------------------------------------------------------------------------------------------------------
const badge = (s) => `<span class="badge ${esc(String(s).split(" ")[0])}">${esc(s)}</span>`;
const when = (t) => esc((t || "").replace("T", " ").slice(0, 16));                       // 2026-11-02 20:55, UTC
const companyName = (id) => (catalog.companies.find((c) => c.id === id) || {}).name || id || "";

async function loadLibrary() {
  const q = new URLSearchParams({ company: $("#f-company").value, source_class: $("#f-class").value, status: $("#f-status").value });
  const docs = await api(`/api/documents?${q}`);
  $("#doc-count").textContent = `${docs.length} document(s)`;
  $("#docs").innerHTML = docs.map((d) => `<tr class="click" data-sha="${esc(d.sha256)}">
    <td>${esc(d.title || d.filename)}<div class="muted">${d.title && d.title !== d.filename.replace(/\.[^.]+$/, "") ? esc(d.filename) : ""}${d.origin_role === "duplicate" ? " · a copy" : d.origin_role === "primary" ? " · has copies" : ""}</div></td>
    <td>${esc(companyName(d.company))}</td><td>${esc(CLASS_NAMES[d.source_class] || d.source_class)}</td>
    <td>${esc(d.publisher)}</td><td class="nowrap">${esc(d.published)}</td><td class="num">${d.pages}</td><td class="nowrap">${badge(d.status)}</td></tr>`).join("");
  document.querySelectorAll("#docs tr").forEach((tr) => tr.addEventListener("click", () => openDocument(tr.dataset.sha)));
  if (docs.some((d) => d.status === "reading" || d.status === "new")) timer = setTimeout(loadLibrary, 8000);
}
["#f-company", "#f-class", "#f-status"].forEach((s) => $(s).addEventListener("change", loadLibrary));

async function upload(files) {
  const list = [...files].filter((f) => !f.name.startsWith("."));
  if (!list.length) return;
  const log = $("#upload-log");
  log.textContent = `Adding ${list.length} file(s)…`;
  const form = new FormData();
  list.forEach((f) => form.append("files", f, f.name));
  form.append("company", $("#up-company").value); form.append("source_class", $("#up-class").value);
  form.append("publisher", $("#up-publisher").value); form.append("published", $("#up-published").value);
  try {
    const res = await api("/api/documents", { method: "POST", body: form });
    log.innerHTML = res.added.map((a) => `${esc(a.filename)}: ${esc(a.outcome)}${a.status ? ` (${esc(a.status)})` : ""}${a.error ? ` — ${esc(a.error)}` : ""}`).join("<br>")
      + (res.skipped.length ? `<br>not a document type the desk reads: ${res.skipped.map(esc).join(", ")}` : "")
      + (res.groups ? `<br>${res.groups} group(s) of copies in the library` : "");
  } catch (err) { log.textContent = err.message; }
  loadLibrary();
}
$("#pick-files").addEventListener("change", (e) => upload(e.target.files));
$("#pick-folder").addEventListener("change", (e) => upload(e.target.files));
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", async (e) => {
  e.preventDefault(); drop.classList.remove("over");
  const files = [];
  const walk = async (entry) => {
    if (entry.isFile) files.push(await new Promise((ok) => entry.file(ok)));
    else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do { batch = await new Promise((ok) => reader.readEntries(ok)); for (const x of batch) await walk(x); } while (batch.length);
    }
  };
  for (const item of e.dataTransfer.items) { const en = item.webkitGetAsEntry && item.webkitGetAsEntry(); if (en) await walk(en); }
  upload(files.length ? files : e.dataTransfer.files);
});

function closeDrawer() { $("#drawer").hidden = true; }
$("#drawer-close").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

async function openDocument(sha) {
  const x = await api(`/api/documents/${sha}`), d = x.document;
  const opts = (items, cur) => items.map(([v, n]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(n)}</option>`).join("");
  const ok = x.records.filter((r) => r.ok), bad = x.records.filter((r) => !r.ok);
  const row = (r) => { const o = r.data; return `<tr><td>${esc(o.label)}<div class="muted">${esc(o.metric_id || "")} · ${esc(o.kind)}</div>
      ${r.problems.length ? `<div class="problems">${r.problems.map(esc).join("<br>")}</div>` : ""}</td>
    <td>${esc(o.period?.label)}<div class="muted">${esc(o.period?.start)} – ${esc(o.period?.end)}</div></td>
    <td class="num">${esc(o.value)} <span class="muted">${esc(o.unit)}</span></td>
    <td>p. ${esc(o.page)}<div class="quote">“${esc(o.quote)}”</div></td></tr>`; };
  $("#drawer-body").innerHTML = `<h2>${esc(d.title || d.filename)}</h2>
    <p>${badge(d.status)} <a href="/api/documents/${esc(sha)}/file" target="_blank">open the file</a> ·
      <button class="link" id="reread">read again</button></p>
    <dl class="meta"><dt>File</dt><dd>${esc(d.filename)} (${d.pages} pages, ${esc(d.text_engine)})</dd>
      <dt>SHA-256</dt><dd><code>${esc(sha)}</code></dd>
      <dt>Company</dt><dd><select id="e-company"><option value="">—</option>${opts(catalog.companies.map((c) => [c.id, c.name]), d.company)}</select></dd>
      <dt>Source</dt><dd><select id="e-class">${opts(catalog.classes.map((c) => [c, CLASS_NAMES[c] || c]), d.source_class)}</select></dd>
      <dt>Publisher</dt><dd><input id="e-publisher" value="${esc(d.publisher)}"></dd>
      <dt>Published</dt><dd><input id="e-published" type="date" value="${esc(d.published)}"> <button class="small" id="e-save">Save</button></dd>
      <dt>Type, language</dt><dd>${esc(d.doc_type)} ${esc(d.language)} ${d.period ? `· period ${esc(d.period)}` : ""}</dd>
      <dt>Copies</dt><dd>${x.copies.length ? x.copies.map((c) => `${esc(c.filename)} (${esc(c.language)}, ${esc(c.origin_role)})`).join("<br>") : "none"}</dd>
      <dt>Added</dt><dd>${x.uploads.map((u) => `${esc(u.name || "")} ${esc(u.at)} ${esc(u.outcome)}`).join("<br>")}</dd>
      <dt>Readings</dt><dd>${x.readings.map((r) => `${badge(r.status)} ${esc(r.reader)} ${esc(r.finished_at || r.started_at)} · ${r.accepted} accepted, ${r.rejected} rejected${r.error ? ` · ${esc(r.error)}` : ""}`).join("<br>") || "not read yet"}</dd></dl>
    <h3>${ok.length} figure(s) accepted</h3>
    <table class="grid"><tbody>${ok.map(row).join("")}</tbody></table>
    ${bad.length ? `<h3>${bad.length} rejected</h3><table class="grid"><tbody>${bad.map(row).join("")}</tbody></table>` : ""}
    ${x.themes.length ? `<h3>Themes</h3>${x.themes.map((t) => `<p><b>${esc(t.theme)}</b>: ${esc(t.summary)}</p>`).join("")}` : ""}`;
  $("#drawer").hidden = false;
  $("#e-save").addEventListener("click", async () => {
    await api(`/api/documents/${sha}`, { method: "PATCH", json: { company: $("#e-company").value || null, source_class: $("#e-class").value,
      publisher: $("#e-publisher").value, published: $("#e-published").value || null } });
    openDocument(sha); loadLibrary();
  });
  $("#reread").addEventListener("click", async () => { try { await api(`/api/documents/${sha}/reread`, { method: "POST" }); openDocument(sha); loadLibrary(); } catch (err) { alert(err.message); } });
}

// -- facts --------------------------------------------------------------------------------------------------------------
async function loadFacts() {
  const co = $("#fact-company").value || catalog.companies[0]?.id;
  if (!co) return;
  const facts = await api(`/api/facts?company=${encodeURIComponent(co)}&conflicts=${$("#fact-conflicts").checked}`);
  $("#fact-count").textContent = `${facts.length} fact(s) from read documents`;
  $("#fact-rows").innerHTML = facts.map((f) => {
    const cites = f.citations.map((c) => c.baseline ? `<div class="muted">base model ${esc(c.observation_id)}</div>`
      : `<div><a href="#" data-sha="${esc(c.sha256)}">${esc(c.filename)}</a> p.${esc(c.page)}<div class="quote">“${esc(c.quote)}”</div></div>`).join("");
    const rv = f.review?.decision;
    return `<tr><td>${esc(f.label)}<div class="muted">${esc(f.metric_id || "")}</div>${f.conflict ? badge("conflict") : ""}${f.baseline ? " " + badge("in base model") : ""}</td>
      <td>${esc(f.period.label)}<div class="muted">${esc(f.period.start)} – ${esc(f.period.end)}</div></td>
      <td class="num">${esc(f.value)} <span class="muted">${esc(f.unit)}</span></td><td>${esc(f.speaker)}</td><td>${esc(f.claim)}</td>
      <td>${cites}</td>
      <td data-key="${esc(f.key)}">${rv ? badge(rv) + " " : ""}<button class="small ghost" data-d="approve">Approve</button>
        <button class="small ghost" data-d="reject">Reject</button>${rv ? ' <button class="small link" data-d="clear">clear</button>' : ""}</td></tr>`;
  }).join("");
  document.querySelectorAll("#fact-rows button").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/facts/review", { method: "POST", json: { key: b.parentElement.dataset.key, decision: b.dataset.d } });
    loadFacts();
  }));
  document.querySelectorAll("#fact-rows a[data-sha]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); openDocument(a.dataset.sha); }));
}
$("#fact-company").addEventListener("change", loadFacts);
$("#fact-conflicts").addEventListener("change", loadFacts);

// -- world models -------------------------------------------------------------------------------------------------------
function chips(el, items, name, chosen) {
  el.innerHTML = items.map(([v, n]) => `<label><input type="checkbox" name="${name}" value="${esc(v)}"${chosen.includes(v) ? " checked" : ""}> ${esc(n)}</label>`).join("");
}
function resetWm(w = null) {
  const f = $("#wm-form");
  f.reset(); f.id.value = w ? w.id : ""; f.name.value = w ? w.name : ""; f.apply.checked = w ? w.apply : false;
  $("#wm-title").textContent = w ? `Edit ${w.name}` : "New world model";
  chips($("#wm-companies"), catalog.companies.map((c) => [c.id, c.name]), "companies", w ? w.companies : []);
  chips($("#wm-groups"), Object.entries(catalog.groups).map(([k, g]) => [k, `${g.name} (${g.companies.length})`]), "groups", w ? w.groups : []);
  chips($("#wm-classes"), catalog.classes.map((c) => [c, CLASS_NAMES[c] || c]), "classes", w ? w.classes : ["company"]);
  $("#wm-error").textContent = "";
}
$("#wm-reset").addEventListener("click", () => resetWm());
$("#wm-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, all = (n) => [...f.querySelectorAll(`input[name=${n}]:checked`)].map((i) => i.value);
  const body = { name: f.name.value, companies: all("companies"), groups: all("groups"), classes: all("classes"), apply: f.apply.checked };
  try {
    await api(f.id.value ? `/api/world-models/${f.id.value}` : "/api/world-models", { method: f.id.value ? "PUT" : "POST", json: body });
    resetWm(); loadWorldModels();
  } catch (err) { $("#wm-error").textContent = err.message; }
});

async function loadWorldModels() {
  if (!$("#wm-companies").innerHTML) resetWm();
  const wms = await api("/api/world-models");
  const summary = (b) => b.summary ? `${b.summary.documents} documents, ${b.summary.facts} facts, ${b.summary.conflicts} conflicts · `
    + Object.entries(b.summary.counts).map(([k, v]) => `${esc(k)} ${v}`).join(", ") : "";
  $("#wm-list").innerHTML = wms.map((w) => `<div class="card" data-id="${w.id}">
    <h2>${esc(w.name)}</h2>
    <p class="muted">${esc(w.companies.map(companyName).concat(w.groups.map((g) => catalog.groups[g]?.name || g)).join(", "))} ·
      ${esc(w.classes.map((c) => CLASS_NAMES[c] || c).join(" + "))} · ${w.apply ? "approved figures applied" : "beside the baseline"}</p>
    <p><button data-act="build">Build</button> <button class="ghost" data-act="edit">Edit</button> <button class="link" data-act="delete">Delete</button></p>
    ${w.builds.map((b) => `<div>${badge(b.status)} build ${b.id} · ${when(b.finished_at || b.started_at)}
      ${b.status === "done" ? ` · <a href="/api/builds/${b.id}/download">download the zip</a>` : ""}
      ${b.error ? `<div class="problems">${esc(b.error.split("\n")[0])}</div>` : ""}<div class="muted" data-build="${b.id}"></div></div>`).join("")}
  </div>`).join("");
  for (const w of wms) {
    const card = document.querySelector(`#wm-list [data-id="${w.id}"]`);
    card.querySelector("[data-act=build]").addEventListener("click", async () => { await api(`/api/world-models/${w.id}/builds`, { method: "POST" }); loadWorldModels(); });
    card.querySelector("[data-act=edit]").addEventListener("click", () => { resetWm(w); window.scrollTo(0, 0); });
    card.querySelector("[data-act=delete]").addEventListener("click", async () => { if (confirm(`Delete ${w.name}?`)) { await api(`/api/world-models/${w.id}`, { method: "DELETE" }); loadWorldModels(); } });
    for (const b of w.builds.filter((x) => x.status === "done")) {
      api(`/api/builds/${b.id}`).then((full) => { const el = card.querySelector(`[data-build="${b.id}"]`); if (el) el.innerHTML = summary(full); });
    }
  }
  if (wms.some((w) => w.builds.some((b) => b.status === "queued" || b.status === "running"))) timer = setTimeout(loadWorldModels, 5000);
}

// -- reader -------------------------------------------------------------------------------------------------------------
function readerCommand(token) {
  return `axelrod-desk reader --url ${location.origin} --token ${token || "<your reader token>"}`;
}
async function loadReader() {
  me = await api("/api/me");
  $("#reader-cmd").textContent = readerCommand();
  $("#reader-has").textContent = me.reader ? `You have a token (made ${me.reader.created_at}${me.reader.last_used ? `, last used ${me.reader.last_used}` : ""}).` : "You have no reader token yet.";
  const q = await api("/api/reader/status");
  $("#queue").innerHTML = `<div class="stats">${Object.entries(q.documents).map(([k, v]) => `<span><b>${v}</b>${esc(k)}</span>`).join("")}</div>
    ${q.running.length ? `<p>Reading now: ${q.running.map((r) => `${esc(r.name || "")} on ${esc(r.reader)} since ${when(r.started_at)}`).join("; ")}</p>` : "<p class=\"muted\">No reader is reading.</p>"}
    <table class="grid"><thead><tr><th>Document</th><th>Reader</th><th>Status</th><th class="num">Accepted</th><th class="num">Rejected</th><th>Finished (UTC)</th></tr></thead><tbody>
    ${q.recent.map((r) => `<tr><td>${esc(r.filename)}</td><td>${esc(r.reader)} ${esc(r.model || "")}</td><td>${badge(r.status)}${r.error ? `<div class="problems">${esc(r.error)}</div>` : ""}</td>
      <td class="num">${r.accepted}</td><td class="num">${r.rejected}</td><td class="nowrap">${when(r.finished_at)}</td></tr>`).join("")}</tbody></table>`;
  timer = setTimeout(loadReader, 8000);
}
$("#reader-token").addEventListener("click", async () => {
  const { token } = await api("/api/me/reader-token", { method: "POST" });
  $("#reader-cmd").textContent = readerCommand(token);
  $("#reader-has").textContent = "Copy the command now: the token is not shown again.";
});

// -- accounts -----------------------------------------------------------------------------------------------------------
async function loadAccounts() {
  const rows = await api("/api/accounts");
  $("#account-rows").innerHTML = rows.map((a) => `<tr><td>${esc(a.name)}</td><td>${esc(a.email)}</td><td>${a.admin ? "yes" : ""}</td></tr>`).join("");
}
$("#account-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("/api/accounts", { method: "POST", json: { name: f.name.value, email: f.email.value, password: f.password.value, admin: f.admin.checked } });
    f.reset(); $("#account-error").textContent = ""; loadAccounts();
  } catch (err) { $("#account-error").textContent = err.message; }
});

start().catch(() => showSignin());
