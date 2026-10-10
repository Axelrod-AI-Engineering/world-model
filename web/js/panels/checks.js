// Checks (Oct 9): what the model is testing now, how close each test is to its bound, and when and how each kind of
// check happens. A check weighs one piece of evidence and moves one stored weight; enough of them, past a bound,
// raise a proposal for review. The pane opens on the live list; how the checks work sits below it.
import { api } from "../api.js";
import { on } from "../store.js";
import { errorText, esc, fmt } from "../util.js";

const KIND = {
  hedge: { word: "Fuzzy ends", help: "An article named an end loosely; the candidates share the probability, with an open share for one not in the graph yet." },
  frontier: { word: "Co-movements", help: "Two values moved together with nothing in the graph to explain it; each spaced check passes or fails." },
  superentity: { word: "Superentities", help: "A group of interactions that fire together; each spaced day they do counts once." },
};
// when each kind runs, as one line of the day: each article, then the day's close, then a person's review
const RHYTHM = [
  { at: "Each article", ids: ["hedge", "existence", "frontier", "kinds"] },
  { at: "Each day's close", ids: ["superentity"] },
  { at: "Your review", ids: [], text: "A check never changes the structure by itself: past its bound, it raises a proposal, and a person approves or rejects it." },
];

export function initChecks({ toast, onSelect }) {
  const pane = document.createElement("section");
  pane.id = "checks";
  pane.className = "manual checks hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Checks");
  document.getElementById("stage").appendChild(pane);
  let data = null;

  const meter = (m) => {
    const frac = m.below ? Math.min(1, m.bound / Math.max(m.value, 1e-6)) : Math.min(1, m.value / Math.max(m.bound, 1e-6));
    const met = m.below ? m.value < m.bound : m.value >= m.bound;
    const val = m.unit === "pct" ? `${Math.round(100 * m.value)}%` : m.unit === "r" ? fmt(m.value, 2) : fmt(m.value, 1);
    const bnd = m.unit === "pct" ? `${Math.round(100 * m.bound)}%` : m.unit === "r" ? fmt(m.bound, 2) : fmt(m.bound, 0);
    return `<div class="ck-row ${met ? "met" : ""}"><span class="ck-what">${esc(m.what)}</span>
      <span class="ck-bar wide"><i style="width:${(100 * frac).toFixed(0)}%"></i></span>
      <span class="mono ck-val">${val} <span class="muted">${m.below ? "falls below" : "of"} ${bnd}</span></span></div>`;
  };

  function render() {
    if (!data) { pane.querySelector(".mbody").innerHTML = `<p class="small muted">Loading…</p>`; return; }
    const byKind = new Map();
    for (const x of data.live) {
      if (!byKind.has(x.kind)) byKind.set(x.kind, []);
      byKind.get(x.kind).push(x);
    }
    const cat = new Map(data.catalog.map((c) => [c.id, c]));
    pane.querySelector(".mbody").innerHTML = `
      <p class="small muted">A check weighs one piece of evidence and moves one stored weight. Enough checks, past a bound,
        raise a proposal; nothing changes the structure until a person reviews it.${data.today ? ` Today is ${esc(data.today)}.` : ""}</p>
      <section class="mf-sec"><h4>Being checked now <span class="small muted">${data.live.length} item${data.live.length === 1 ? "" : "s"}</span></h4>
        ${data.live.length ? [...byKind.entries()].map(([k, xs]) => `<div class="ck-group"><div class="ck-gh" title="${esc(KIND[k]?.help ?? "")}">${esc(KIND[k]?.word ?? k)}</div>
          ${xs.map((x) => `<div class="ck-item" data-kind="${esc(x.kind)}" data-id="${esc(x.id)}" tabindex="0" role="button">
            <div class="ck-label"><b>${esc(x.label)}</b>${x.status && x.status !== "holding" ? ` <span class="badge">${esc(x.status.replace(/_/g, " "))}</span>` : ""}</div>
            ${x.progress.map(meter).join("")}
            <div class="small muted">${x.last ? `last checked ${esc(x.last)} · ` : ""}next: ${esc(x.next)}${x.passed != null ? ` · passed ${x.passed}, failed ${x.failed}` : ""}</div></div>`).join("")}</div>`).join("")
          : `<p class="small muted">Nothing is being checked: no fuzzy end is hedged, no co-movement is held, and no candidate superentity waits.</p>`}
      </section>
      <section class="mf-sec"><h4>When checks happen</h4>
        <ol class="ck-rhythm">${RHYTHM.map((r) => `<li><div class="ck-at">${esc(r.at)}</div>
          ${r.ids.length ? `<div class="ck-chips">${r.ids.map((id) => `<a href="#ck-${esc(id)}" class="badge ${cat.get(id)?.memory === "working" ? "wm" : "ltm"}">${esc(cat.get(id)?.name ?? id)}</a>`).join("")}</div>` : `<div class="small muted">${esc(r.text)}</div>`}</li>`).join("")}</ol>
      </section>
      <section class="mf-sec"><h4>How each check works</h4>
        ${data.catalog.map((c) => `<details class="ck-cat" id="ck-${esc(c.id)}"><summary><b>${esc(c.name)}</b> <span class="small muted">${esc(c.when)}</span></summary>
          <dl class="ck-dl"><dt>How</dt><dd>${esc(c.how)}</dd><dt>Reads</dt><dd>${esc(c.reads)}</dd>
            <dt>Updates exactly</dt><dd>${esc(c.updates)}</dd><dt>Bound</dt><dd>${esc(c.bound)}</dd>
            ${c.after_review ? `<dt>After review</dt><dd>${esc(c.after_review)}</dd>` : ""}</dl></details>`).join("")}
      </section>`;
    for (const it of pane.querySelectorAll(".ck-item")) {
      const go = () => {
        const k = it.dataset.kind;
        if (k === "frontier") onSelect?.({ kind: "frontier", id: it.dataset.id });
        else if (k === "superentity") onSelect?.({ kind: "pattern", id: it.dataset.id });
      };
      it.addEventListener("click", go);
      it.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
    }
    for (const a of pane.querySelectorAll(".ck-chips a")) {
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        const d = pane.querySelector(a.getAttribute("href"));
        if (d) { d.open = true; d.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
      });
    }
  }

  async function load() {
    try { data = await api.checks(); } catch (err) { toast(errorText(err), "err"); data = { catalog: [], live: [] }; }
    if (isOpen()) render();
  }

  pane.innerHTML = `<header><div class="mtitle">Checks</div><span class="small muted">what the model is testing</span><span class="spacer"></span>
    <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button>
    <button class="close" aria-label="Close (Esc)">✕</button></header><div class="mbody"></div>`;
  pane.querySelector(".close").addEventListener("click", () => close());
  const isOpen = () => !pane.classList.contains("hidden");
  function open() { pane.classList.remove("hidden"); render(); load(); }
  function close() { pane.classList.add("hidden"); }
  let timer = null;
  on("graph", () => { if (isOpen()) { clearTimeout(timer); timer = setTimeout(load, 400); } });
  return { open, close, isOpen, toggle: () => (isOpen() ? close() : open()) };
}
