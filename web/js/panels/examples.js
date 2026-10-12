// Examples (Oct 8 restructure): the demos' menu. Each example shows one feature of the framework through one or
// more sample articles, and the examples form one chain: running example n first plays examples 1 to n - 1, and
// running an earlier one rewinds to it. Under each example, "More like this" lists further articles of the same
// kind, which run on the current state without moving the chain. The list comes from the server
// (sim/examples/small.py and prod.py).
import { api } from "../api.js";
import { on, refreshGraph, store } from "../store.js";
import { errorText, esc } from "../util.js";

const MEMORY = { working: "Working memory", long_term: "Long-term memory", review: "Human review", intake: "Intake",
                 inference: "Inference" };

export function initExamples({ toast, onProposal, onQuestion, onReset, onManual }) {
  const pane = document.createElement("section");
  pane.id = "examples";
  pane.className = "examples hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Tutorial");
  document.getElementById("stage").appendChild(pane);
  const st = { list: [], open: null, busy: null, filter: "all" };

  async function load() {
    try { st.list = await api.examples(); } catch (err) { st.list = []; pane.innerHTML = `<p class="error small">${esc(errorText(err))}</p>`; return; }
    if (st.open == null) st.open = (st.list.find((x) => x.status === "waiting") ?? st.list.find((x) => x.status === "ready"))?.id ?? null;
    render();
  }

  const lastPlayed = () => st.list.reduce((k, x, i) => (x.status !== "ready" ? i : k), -1);

  function action(x, i) {
    if (x.status === "waiting") return `<button class="small" data-review="${esc(x.proposal_id ?? "")}">Review</button>`;
    // a manual addition opens the form, prefilled: the example shows how it is done (Oct 9)
    if (x.kind === "manual") {
      return `<button class="${x.rewinds ? "" : "primary "}small" data-manual="${esc(x.id)}" title="${x.rewinds ? "Go back to just before this step" : x.plays_first
        ? `Play steps ${i + 1 - x.plays_first} to ${i} first` : "Open it"}, then open the form, prefilled" ${st.busy ? "disabled" : ""}>${st.busy === x.id ? "Running…" : "Open the form"}</button>`;
    }
    const label = st.busy === x.id ? "Running…" : x.rewinds ? "Rewind to it" : "Run";
    const title = x.rewinds ? `Go back to the state before step ${x.n} and run it again`
      : x.plays_first ? `Plays steps ${i + 1 - x.plays_first} to ${i} first` : "Run it";
    return `<button class="${x.rewinds ? "" : "primary "}small" data-run="${esc(x.id)}" title="${esc(title)}" ${st.busy ? "disabled" : ""}>${label}</button>`;
  }

  function article(a) {
    return `<blockquote class="earticle"><div class="eh">${esc(a.headline)}</div>${a.body ? `<div>${esc(a.body)}</div>` : ""}
      <div class="esrc muted">${esc(a.source)} · synthetic</div></blockquote>`;
  }

  function render() {
    const waiting = st.list.find((x) => x.status === "waiting");
    const last = lastPlayed();
    const shown = st.list.filter((x) => st.filter === "all" || x.memory === st.filter
      || (st.filter === "working" && x.memory === "intake"));
    pane.innerHTML = `
      <header><div class="etitle">Tutorial</div><span class="spacer"></span>
        <button class="ghost small" data-reset title="Start again from the beginning">Start over</button>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close (Esc)">✕</button></header>
      <p class="small muted elede">Each step shows one feature through a sample article. It runs through learning on a staged copy and
        stops at your review. Steps follow one another: running one plays the ones before it, and an earlier one rewinds to it.</p>
      <div class="chips efilter" role="group" aria-label="Show">${[["all", "All"], ["working", "Working memory"], ["long_term", "Long-term memory"],
        ["review", "Review"], ["inference", "Inference"]].map(([k, l]) => `<button class="cchip" data-filter="${k}" aria-pressed="${st.filter === k}">${l}</button>`).join("")}</div>
      ${waiting ? `<p class="small ewarn">Step ${waiting.n} waits for your review. Approve or reject it to go on, or pick an earlier step to rewind.</p>` : ""}
      <ol class="elist">${shown.map((x) => {
        const i = st.list.indexOf(x);
        return `<li class="erow ${esc(x.status)}${st.open === x.id ? " open" : ""}${i === last ? " current" : ""}" data-id="${esc(x.id)}">
          <div class="eline">
            <span class="en">${x.n}</span>
            <button class="et linkish" data-toggle="${esc(x.id)}" aria-expanded="${st.open === x.id}">${esc(x.title)}</button>
            <span class="estage st-${esc(x.memory)}">${esc(MEMORY[x.memory] ?? x.memory)}</span>
            ${x.status === "done" ? `<span class="edone" title="Done">✓</span>` : x.status === "skipped" ? `<span class="eskip" title="Rejected or set aside">–</span>` : ""}
            ${action(x, i)}
          </div>
          <div class="eiso small muted">${esc(x.isolates)}${x.note ? ` · <i>skipped: ${esc(x.note.replace(/^nothing to change: /, ""))}</i>` : ""}</div>
          ${st.open === x.id ? `<div class="emore small">
            ${(x.steps ?? []).map((s) => article(s.article)).join("")}
            ${x.question ? `<blockquote class="earticle"><div class="eh">${esc(x.question)}</div><div class="esrc muted">A question, asked in Predict</div></blockquote>` : ""}
            ${x.kind === "edit" ? `<p class="muted">A backend user's edit, not an article.</p>` : ""}
            ${x.kind === "manual" ? `<p class="muted">No article: a backend user adds what they know. “${esc(x.manual?.note ?? "")}”</p>` : ""}
            <p>${esc(x.summary)}</p>
            <div><b>What to check:</b></div><ul>${x.watch.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
            ${x.more?.length ? `<div class="elib"><b>More like this</b> <span class="muted">(runs on the current state; the chain stays where it is)</span>
              <ul>${x.more.map((m) => `<li><span>${esc(m.title)}</span>
                ${m.status === "waiting" ? `<span class="muted">waits for review</span>` : m.status === "done" ? `<span class="edone">✓</span>` : ""}
                <button class="small" data-lib="${esc(m.id)}" ${st.busy || waiting ? "disabled" : ""}>Add</button></li>`).join("")}</ul></div>` : ""}
          </div>` : ""}
        </li>`;
      }).join("")}</ol>`;
    pane.querySelector(".close").addEventListener("click", close);
    pane.querySelector("[data-reset]").addEventListener("click", async () => { close(); await onReset?.(); });
    for (const b of pane.querySelectorAll("[data-filter]")) b.addEventListener("click", () => { st.filter = b.dataset.filter; render(); });
    for (const b of pane.querySelectorAll("[data-toggle]")) {
      b.addEventListener("click", () => { st.open = st.open === b.dataset.toggle ? null : b.dataset.toggle; render(); });
    }
    for (const b of pane.querySelectorAll("[data-run]")) b.addEventListener("click", () => run(b.dataset.run));
    for (const b of pane.querySelectorAll("[data-manual]")) b.addEventListener("click", () => openForm(b.dataset.manual));
    for (const b of pane.querySelectorAll("[data-lib]")) b.addEventListener("click", () => runLibrary(b.dataset.lib));
    for (const b of pane.querySelectorAll("[data-review]")) b.addEventListener("click", () => { close(); onProposal?.(b.dataset.review); });
  }

  async function go(id, call, describe) {
    if (st.busy) return;
    st.busy = id;
    render();
    try {
      const out = await call();
      const said = describe(out);
      if (said) toast(said);
      close();
      if (out.proposal_id) onProposal?.(out.proposal_id);
      else if (out.question) onQuestion?.(out.question);
      else if (out.note) toast(`Skipped: ${out.note}.`);
    } catch (err) {
      toast(errorText(err), "err");
    } finally {
      st.busy = null;
      if (isOpen()) load();
    }
  }
  // "Played examples 1–13 first.": the numbers, not the titles, so the note stays one line
  const playedFirst = (ids) => {
    const ns = ids.map((id) => st.list.find((e) => e.id === id)?.n).filter((n) => n != null);
    if (!ns.length) return "";
    return ns.length === 1 ? `Played step ${ns[0]} first.` : `Played steps ${ns[0]}–${ns[ns.length - 1]} first.`;
  };
  // a manual example: first bring the canvas to just before it (play or rewind the earlier examples), then open the
  // prefilled form over what they built (Oct 9)
  async function openForm(id) {
    if (st.busy) return;
    const x = st.list.find((e) => e.id === id);
    st.busy = id;
    render();
    try {
      const out = await api.prepareExample(id);
      if (out.rewound) toast(`Rewound to just before step ${x.n}.`);
      else { const said = playedFirst(out.played ?? []); if (said) toast(said); }
      await refreshGraph();
      close();
      onManual?.(x.manual, x.id);
    } catch (err) {
      toast(errorText(err), "err");
    } finally {
      st.busy = null;
      if (isOpen()) load();
    }
  }

  function run(id) {
    return go(id, () => api.runExample(id), (out) => (out.rewound ? `Rewound to step ${st.list.find((e) => e.id === id)?.n}.`
      : playedFirst(out.played ?? [])));
  }
  function runLibrary(id) {
    return go(id, () => api.runLibrary(id), (out) => playedFirst(out.played ?? []));
  }

  const isOpen = () => !pane.classList.contains("hidden");
  function open() {
    pane.classList.remove("hidden");
    document.getElementById("btn-examples")?.setAttribute("aria-expanded", "true");
    load();
  }
  function close() {
    pane.classList.add("hidden");
    document.getElementById("btn-examples")?.setAttribute("aria-expanded", "false");
  }
  on("status", () => { if (isOpen() && !st.busy) load(); });
  on("reviewed", () => { if (isOpen()) load(); });
  return { open, close, isOpen, run, toggle: () => (isOpen() ? close() : open()), has: () => !!store.status?.examples };
}
