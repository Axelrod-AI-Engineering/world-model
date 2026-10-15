// The Console (restructure): the world model as version control. One world model; every change to it is a
// commit that names its process, its memory, and who vetted it. Here a backend user reads the log, opens one
// commit, compares two versions, or opens an old version read-only. (Vetting itself happens in Review, at the
// end of learning, on a staged copy: panels/review.js.)
import { api } from "../api.js";
import { names } from "../names.js";
import { emit, on } from "../store.js";
import { esc, errorText } from "../util.js";

// a changed value reads "Entity · subentity" (names.js); anything else as the log names it
const changeName = (ch) => (/^subentit/.test(ch.kind) && ch.id ? names().valueHtml(ch.id) : esc(ch.name));

const PROCESS_GROUPS = [
  ["all", "All", []],
  ["working", "Working memory", ["learn.working"]],
  ["long_term", "Long-term memory", ["learn.long_term"]],
  ["day", "Each day", ["day.predict", "day.record", "day.distill", "day.close"]],
  ["structural", "Structure", ["structural"]],
  ["review", "Review", ["review"]],
];
const MEMORY = { working: "WM", long_term: "LTM", both: "WM + LTM", forecast: "forecast" };
const dayOf = (iso) => (iso ? String(iso).slice(0, 10) : "");

export function initConsole({ toast, onFocus }) {
  const pane = document.createElement("section");
  pane.id = "console";
  pane.className = "console hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Console: the commit log of the world model");
  document.getElementById("stage").appendChild(pane);
  pane.innerHTML = `
    <header>
      <div class="ctitle">Console</div>
      <span class="chint small muted">The log: every commit to the one world model, newest first.</span>
      <span class="spacer"></span>
      <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close the console (Esc)">✕</button>
    </header>
    <div class="cbody log">
      <aside class="clist" aria-label="Commits"></aside>
      <section class="cflow" aria-label="Commit"></section>
      <section class="csteps" aria-label="Changes"></section>
    </div>`;
  const $ = (sel) => pane.querySelector(sel);
  const list = $(".clist");
  const flow = $(".cflow");
  const steps = $(".csteps");
  const st = { logFilter: "all", commits: [], commit: null };
  pane.querySelector(".close").addEventListener("click", close);

  // -- the log ---------------------------------------------------------------------------------------------
  async function loadLog(reset) {
    if (reset) { st.commits = []; st.commit = null; }
    const group = PROCESS_GROUPS.find((g) => g[0] === st.logFilter);
    const before = !reset && st.commits.length ? st.commits.at(-1).version : null;
    try {
      const more = await api.repoLog({ limit: 60, before, process: group?.[2] ?? [] });
      st.commits = reset ? more : st.commits.concat(more);
    } catch (err) { toast(errorText(err), "err"); }
    renderLog();
  }
  function renderLog() {
    list.innerHTML = `
      <div class="chips" role="group" aria-label="Process">${PROCESS_GROUPS.map(([k, l]) =>
        `<button class="cchip" data-proc="${k}" aria-pressed="${k === st.logFilter}">${esc(l)}</button>`).join("")}</div>
      ${st.commits.length ? `<ol class="crows">${st.commits.map((c) => `
        <li><button class="crow commit${st.commit?.commit?.version === c.version ? " sel" : ""}" data-v="${c.version}">
          <span class="ch"><b>v${c.version}</b> ${esc(c.message)}</span>
          <span class="cm">${esc(c.process)} · ${esc(MEMORY[c.memory] ?? c.memory ?? "")} · ${esc(dayOf(c.recorded_at))}${c.vetted_by ? ` · vetted by ${esc(c.vetted_by)}` : ""}</span>
        </button></li>`).join("")}</ol>
        <button class="linkish more" data-older>Older commits</button>`
      : `<p class="empty small">No commits in this session's ledger yet.</p>`}`;
    for (const b of list.querySelectorAll("[data-proc]")) b.addEventListener("click", () => { st.logFilter = b.dataset.proc; loadLog(true); });
    for (const b of list.querySelectorAll("[data-v]")) b.addEventListener("click", () => openCommit(+b.dataset.v));
    list.querySelector("[data-older]")?.addEventListener("click", () => loadLog(false));
    if (!st.commit) {
      flow.innerHTML = `<div class="cintro"><h3>The world model as version control</h3>
        <p>Every change is a commit, and only what a person approved in Review is committed. A market event commits twice, once per learning process: to working memory, then to long-term memory. Each day commits four times: it opens (predict), is recorded, is distilled into long-term memory, and closes. A backend user's edit (collapse, expand, add, retire) commits once.</p>
        <p class="small muted">Theses never commit: each reads a branch of a committed version, which is never merged. Pick a commit to see what it changed; compare two versions with Diff.</p>
        <div class="diffform"><label>Diff from <input type="number" data-from min="0" placeholder="version"></label>
          <label>to <input type="number" data-to min="0" placeholder="now"></label><button data-diff>Diff</button></div></div>`;
      steps.innerHTML = "";
      wireDiff();
    }
  }
  async function openCommit(version) {
    try { st.commit = await api.repoShow(version); } catch (err) { toast(errorText(err), "err"); return; }
    for (const b of list.querySelectorAll("[data-v]")) b.classList.toggle("sel", +b.dataset.v === version);
    const c = st.commit.commit;
    flow.innerHTML = `<div class="cintro">
      <h3>v${c.version} · ${esc(c.message)}</h3>
      <p class="small">${esc(c.process_text)}</p>
      <table class="ctable"><tbody>
        <tr><th>Commit</th><td>${esc(c.id)} (cause ${esc(c.cause)})</td></tr>
        <tr><th>Memory</th><td>${esc(MEMORY[c.memory] ?? c.memory)}</td></tr>
        <tr><th>Recorded</th><td>${esc(String(c.recorded_at).replace("T", " ").slice(0, 16))}</td></tr>
        ${c.proposal_id ? `<tr><th>Proposal</th><td>${esc(c.proposal_id)}</td></tr>` : ""}
        <tr><th>Vetted by</th><td>${esc(c.vetted_by ?? "—")}</td></tr>
        <tr><th>Changes</th><td>${c.total_changes}</td></tr></tbody></table>
      <h4>By kind</h4><ul class="cchanges">${Object.entries(c.counts).map(([kind, verbs]) =>
        `<li>${esc(kind)}: ${Object.entries(verbs).map(([v, n]) => `${n} ${esc(v)}`).join(", ")}</li>`).join("")}</ul>
      <div class="diffform"><label>Diff from <input type="number" data-from min="0" value="${c.version - 1}"></label>
        <label>to <input type="number" data-to min="0" value="${c.version}"></label><button data-diff>Diff</button>
        <button data-checkout title="See the graph as it was at this version (read-only)">Open this version</button></div></div>`;
    steps.innerHTML = `<h4>Structure it changed</h4>${st.commit.changes.length ? `<ul class="cchanges">${st.commit.changes.map((ch) =>
      `<li><span class="act ${esc(ch.action)}">${esc(ch.action)}</span> ${esc(ch.kind)}: ${changeName(ch)}${ch.fields?.length ? ` <span class="small muted">(${ch.fields.slice(0, 6).map(esc).join(", ")})</span>` : ""}</li>`).join("")}</ul>`
      : `<p class="small muted">No structural change: values, statistics, or bookkeeping only.</p>`}`;
    wireDiff();
    flow.querySelector("[data-checkout]")?.addEventListener("click", () => { close(); emit("open-version", version); });
  }
  function wireDiff() {
    flow.querySelector("[data-diff]")?.addEventListener("click", async () => {
      const from = +flow.querySelector("[data-from]").value;
      const toRaw = flow.querySelector("[data-to]").value;
      if (!Number.isFinite(from) || flow.querySelector("[data-from]").value === "") { toast("Give a version to diff from.", "err"); return; }
      try {
        const d = await api.repoDiff(from, toRaw === "" ? null : +toRaw);
        steps.innerHTML = `<h4>v${d.from_version} → v${d.to_version}: ${d.commits} commits</h4>
          <p class="small">${Object.entries(d.by_process).map(([k, n]) => `${esc(k)} ${n}`).join(" · ")}</p>
          <h4>Net structural changes</h4>${d.changes.length ? `<ul class="cchanges">${d.changes.map((ch) =>
            `<li><span class="act ${esc(ch.action)}">${esc(ch.action)}</span> ${esc(ch.kind)}: ${changeName(ch)}</li>`).join("")}</ul>`
            : `<p class="small muted">None.</p>`}`;
      } catch (err) { toast(errorText(err), "err"); }
    });
  }

  // -- open, close, refresh ----------------------------------------------------------------------------------
  let timer = null;
  on("status", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (!pane.classList.contains("hidden") && !st.commit) loadLog(true); }, 900);
  });
  function open() {
    pane.classList.remove("hidden");
    document.getElementById("btn-console")?.setAttribute("aria-expanded", "true");
    loadLog(true);
    onFocus?.(true);
  }
  function close() {
    pane.classList.add("hidden");
    document.getElementById("btn-console")?.setAttribute("aria-expanded", "false");
    onFocus?.(false);
  }
  return { open, close, toggle: () => (pane.classList.contains("hidden") ? open() : close()),
           isOpen: () => !pane.classList.contains("hidden") };
}
