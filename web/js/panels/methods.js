// How it works (Oct 8 restructure): Learning, Inference, Literature, and Implementation. "Learning" (the default)
// is the tutorial's reading: an overview of the five learning stages, each with its input and output, then each
// stage's own flowchart (every condition, branch, and loop labeled), the examples that show it, how a new world
// model fills up, and the words. "Inference" is drawn the same way and stands apart: it reads the model and never
// writes it.
// "Literature" is the literature review the methods draw on (web/literature.md). "Implementation" is the ML
// stack, component by component, with every component's contract (web/implementation.html and /api/contracts).
// Each tab builds a contents list from its headings.
import { api } from "../api.js";
import { renderMarkdown } from "../md.js";
import { emit, store } from "../store.js";
import { esc } from "../util.js";
import { overviewMarkup } from "./flowchart.js";

const TABS = [
  ["how", "Learning", null],
  ["inference", "Inference", null],
  ["literature", "Literature", "literature.md"],
  ["implementation", "Implementation", "implementation.html"],
];

const WORDS = [
  ["Entity", "An actor (a company, an agency) or an economic idea (oil, inflation): a node of the graph."],
  ["Subentity", "One of an entity's values, such as Delta's jet fuel cost: a number with a distribution, in standard units."],
  ["Interaction", "A directed causal relation between two subentities, with an effect, a belief that it exists, and a lag kernel."],
  ["Superentity", "A group of entities and the interactions among them, kept as one pattern: a sector, a rivalry, a shock."],
  ["Graph update event", "What a market event (or a backend user's edit) stands for, as operations on the graph."],
  ["Fuzzy end (hedge)", "An end the article describes but does not name (“a US carrier”). It keeps a probability for each candidate and a share for one not in the graph yet; its soft interactions are as strong as they are probable, until evidence carries one past the bound and a person approves."],
  ["Your confidence", "How far you trust what you approve, for an article or one change. It shrinks an interaction's existence prior, weakens a report, and scales a move's expected size; 100% takes the article as stated."],
  ["Working memory", "The current graph and its values: what the world is like now."],
  ["Long-term memory", "What generalizes: concepts (object and interaction generalizations), superentity patterns, entity memories, the correlation frontier, prior states."],
  ["The ripple", "How one move travels: first order is direct; second order passes through one value; third order through two. In review, each value's ripple can be deselected or given the probability that it arrives."],
  ["Open node", "The empty node every node carries: the mass the graph does not account for yet. For a value, the share of its movement no interaction explains; for a concept, the chance the next item belongs to a concept not seen yet. Larger rings are blind spots."],
  ["Check", "One test of one belief: a fuzzy end weighed by an article, a co-movement checked again after a spaced interval, a group of interactions counted on a day. Enough checks past a bound raise a proposal; the Checks pane (C) shows what is being tested now."],
  ["Composite superentity", "A superentity made of superentities. The path above the canvas names each level; [ and ] move up and down."],
  ["Thesis", "A what-if question. It runs on a branch of a committed version and never changes the model."],
  ["Inference", "Answering a thesis: isolate the networks the shock reaches, simulate and couple them, weigh rival scenarios, and read out every value by order and path."],
  ["Hypothesis frontier", "Open questions ranked by how much answering them would move the forecasts being watched."],
];

// the flowchart's own terms first (flows/__init__.py, one source for the chart and this list), then the rest
const plain = (w) => w.toLowerCase().replace(/^the /, "");
function words(overview) {
  const terms = (overview?.terms ?? []).map((t) => [t.term, t.meaning]);
  const have = new Set(terms.map(([w]) => plain(w)));
  return [...terms, ...WORDS.filter(([w]) => !have.has(plain(w)))];
}

const FILLS = [
  ["Construction files", "entities, values, interactions, each concept's defaults", "by whoever writes them", "both memories (construction)"],
  ["News, filings, analyst notes", "a graph update event: new or retired structure, moved values", "yes: a staged review", "working, then long-term memory"],
  ["Data releases", "observed values", "yes in the tutorial; routine releases may be signed off by policy", "working, then long-term memory"],
  ["A backend user's edit", "a collapse, an expansion, an addition, a retirement", "yes", "one structural commit"],
  ["A backend user's own knowledge (☰ → Add from your own knowledge)", "a new entity, its values, interactions, with their reason and confidence", "yes: a staged review", "one structural commit"],
  ["What long-term memory proposes", "a promoted interaction, an admitted or dissolved superentity, a resolved refinement", "yes", "one structural commit"],
  ["A thesis (inference)", "a shock on a branch", "never merged", "nothing"],
];

export function initMethods() {
  const pane = document.createElement("section");
  pane.id = "methods";
  pane.className = "methods hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "How it works, methods, and implementation");
  document.getElementById("stage").appendChild(pane);
  pane.innerHTML = `<header>
      <nav class="mtabs" role="tablist" aria-label="Briefings">${TABS.map(([id, label]) =>
        `<button role="tab" data-mtab="${id}" aria-selected="${id === "how"}">${label}</button>`).join("")}</nav>
      <span class="spacer"></span>
      <a class="small" data-own href="implementation.html" target="_blank" rel="noopener" hidden>Open on its own ↗</a>
      <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" aria-label="Close (Esc)">✕</button></header>
    <div class="mbody"><nav class="toc" aria-label="Contents"></nav><article class="doc"><p class="empty">Loading…</p></article></div>`;
  pane.querySelector(".close").addEventListener("click", close);
  const art = pane.querySelector("article.doc");
  const toc = pane.querySelector(".toc");
  const cache = new Map();          // tab -> {html, scroll}
  let current = "how";
  for (const b of pane.querySelectorAll("[data-mtab]")) b.addEventListener("click", () => show(b.dataset.mtab));

  // one stage of an overview: its summary, input and output, its own flowchart, and the examples that show it
  const stageSection = (ph, k, sub, xs, cls) => `<h2 id="stage-${esc(ph.id)}" class="st-h ${cls}"><span class="st-n">${k + 1}</span> ${esc(ph.title)}</h2>
    <p>${esc(sub?.summary ?? ph.detail)}</p>
    <dl class="fc-io-row"><dt>In</dt><dd>${esc(ph.input)}</dd><dt>Out</dt><dd>${esc(ph.output)}</dd></dl>
    <figure class="flow stage-flow ${cls}" data-flow="${esc(ph.flow)}"><p class="empty small">Drawing…</p></figure>
    ${xs.length ? `<p class="small"><b>Tutorial steps that show it:</b> ${xs.map((x) => `<button class="linkish" data-try="${esc(x.id)}"
      title="${esc(x.isolates)}">${x.n}. ${esc(x.title)}</button>`).join(" · ")}</p>` : ""}`;
  const KEY = `<p class="small muted">Solid steps always run; <span class="fc-key optional">dashed</span> steps run only when their condition holds.
    A diamond is a decision, and its answers label its arrows; an arrow that climbs back is a loop. WM and LTM mark what writes working and long-term memory.</p>`;

  async function howHtml() {
    const [flows, examples] = await Promise.all([api.flows(), api.examples().catch(() => [])]);
    const overview = flows.find((f) => f.id === "world-model");
    const byId = new Map(flows.map((f) => [f.id, f]));
    const tutorial = !!store.status?.examples;
    return `<h1>How it learns</h1>
      <p class="meta">One world model, built like version control. ${tutorial ? "Tutorial in the top bar runs each step below on the canvas." : "The small demo builds one from a blank canvas, one tutorial step at a time."}</p>
      <div class="abstract"><p>Backend users <b>teach</b> the model (Learn); everyone else only <b>asks</b> it (Predict).
        Every change starts as an article and runs through learning on a <b>staged copy</b>: first working memory, then long-term memory.
        A person then checks every change to both memories, including the second- and third-order ripple, keeps what makes sense,
        and only that is <b>committed</b>. Answering questions is a separate process, <a href="#" data-mtab-go="inference">inference</a>, which never writes.</p></div>
      <h2 id="overview">The five stages of learning</h2>
      <p>Each stage takes one thing in and hands one thing on. Pick a stage to see how it gets from its input to its output.
        Each stage keeps its color everywhere: here, in the review pane, and in the examples.</p>
      <figure class="fc">${overviewMarkup(overview, (ph) => `st-${ph.id}`)}</figure>
      ${overview.phases.map((ph, k) => stageSection(ph, k, byId.get(ph.flow), examples.filter((x) => x.stage === ph.id), `st-${ph.id}`)).join("")}
      ${KEY}
      <h2 id="fills">How a new world model fills up</h2>
      <table><thead><tr><th>Input</th><th>Arrives as</th><th>Reviewed</th><th>Writes</th></tr></thead>
        <tbody>${FILLS.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>
      <h2 id="words">Words</h2>
      <table><tbody>${words(overview).map(([w, d]) => `<tr><th>${esc(w)}</th><td>${esc(d)}</td></tr>`).join("")}</tbody></table>
      <p class="meta">All news and data are synthetic. Real company and agency names make the graph concrete; nothing here is a claim about them.</p>`;
  }

  async function inferenceHtml() {
    const [flows, examples] = await Promise.all([api.flows(), api.examples().catch(() => [])]);
    const overview = flows.find((f) => f.id === "inference");
    const byId = new Map(flows.map((f) => [f.id, f]));
    const xs = examples.filter((x) => x.stage === "inference");
    return `<h1>How it infers</h1>
      <p class="meta">Inference reads the world model; it never writes it.</p>
      <div class="abstract"><p>A <b>thesis</b> is a what-if question: “what if oil rose 30% next quarter?” It runs on a <b>branch</b> of a committed
        version, and the branch is never merged, so asking never changes the model and the same question on the same version gets the same answer.
        The model does not pick one story: where long-term memory holds <b>rival</b> explanations of the same moves, each becomes a scenario,
        and the forecast is their mixture, weighted by support, fit, and track record. Every value is read out with the <b>order</b> and
        <b>path</b> by which the shock reaches it. Only one thing flows back: once a decision's horizon passes, the outcome scores the
        forecast, and the superentities that called it gain track record.</p></div>
      <h2 id="inf-overview">The ${overview.phases.length} stages of inference</h2>
      <p>Each stage answers one question: it takes one thing in and hands one thing on, and no step belongs to two stages.</p>
      <figure class="fc">${overviewMarkup(overview, () => "st-inference")}</figure>
      ${overview.phases.map((ph, k) => stageSection(ph, k, byId.get(ph.flow), k === 0 ? xs : [], "st-inference")).join("")}
      ${KEY}
      <h2 id="inf-vs">Learning and inference, side by side</h2>
      <table><thead><tr><th></th><th>Learning</th><th>Inference</th></tr></thead><tbody>
        <tr><th>Who</th><td>Backend users, in Learn</td><td>Everyone, in Predict</td></tr>
        <tr><th>Input</th><td>An article, a data release, or an edit</td><td>A thesis, on a committed version</td></tr>
        <tr><th>Runs on</th><td>A staged copy, then the model itself once approved</td><td>A branch that is never merged</td></tr>
        <tr><th>Reviewed</th><td>Every change, by a person</td><td>Nothing to review: nothing changes</td></tr>
        <tr><th>Output</th><td>A new version</td><td>A forecast by order and path, and a brief</td></tr>
      </tbody></table>`;
  }

  async function drawStageFlows() {
    for (const fig of art.querySelectorAll("figure.stage-flow[data-flow]")) {
      try { fig.innerHTML = await api.flowSvg(fig.dataset.flow, true); } catch { fig.innerHTML = `<p class="error small">Could not draw it.</p>`; }
    }
  }

  async function contractsTable() {
    const contracts = await api.contracts().catch(() => []);
    return `<table><thead><tr><th>Component</th><th>Inputs</th><th>Outputs</th><th>Writes</th><th>Runs</th></tr></thead><tbody>${contracts.map((c) => `
      <tr><td><code>${esc(c.slot)}</code><div class="meta">${esc(c.process)} · ${esc(c.cadence)}</div></td><td>${esc(c.inputs.join("; "))}</td>
        <td>${esc(c.outputs.join("; "))}</td><td>${esc(c.writes.join("; ") || "—")}</td>
        <td>${c.mandatory ? "always" : esc(c.condition ? `if ${c.condition}` : "when called")}</td></tr>`).join("")}</tbody></table>`;
  }

  async function load(tab) {
    if (cache.has(tab)) return cache.get(tab);
    const spec = TABS.find((t) => t[0] === tab);
    let html;
    if (spec[2]?.endsWith(".md")) {
      html = renderMarkdown(await (await fetch(spec[2])).text());
    } else if (spec[2]) {
      const text = await (await fetch(spec[2])).text();
      const doc = new DOMParser().parseFromString(text, "text/html");
      const holder = doc.querySelector("#contracts-table");
      if (holder) holder.innerHTML = await contractsTable();
      html = doc.querySelector("main")?.innerHTML ?? doc.body.innerHTML;
    } else {
      html = tab === "inference" ? await inferenceHtml() : await howHtml();
    }
    const entry = { html, scroll: 0 };
    if (spec[2]) cache.set(tab, entry);          // How it works follows the tutorial's state, so it is rebuilt each time
    return entry;
  }

  function wire() {
    for (const b of art.querySelectorAll("[data-try]")) {
      b.addEventListener("click", () => {
        close();
        if (store.status?.examples) emit("run-example", b.dataset.try);
        else emit("load-scenario", "small_demo");
      });
    }
    for (const a of art.querySelectorAll("[data-mtab-go]")) a.addEventListener("click", (ev) => { ev.preventDefault(); show(a.dataset.mtabGo); });
    art.querySelector("[data-load-tutorial]")?.addEventListener("click", () => { close(); emit("load-scenario", "small_demo"); });
    for (const a of art.querySelectorAll('a[href^="#"]:not([data-mtab-go])')) {
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        const target = art.querySelector(`#${CSS.escape(a.getAttribute("href").slice(1))}`);
        if (target) art.scrollTo({ top: target.getBoundingClientRect().top - art.getBoundingClientRect().top + art.scrollTop - 8 });
      });
    }
  }

  async function show(tab, anchor = null) {
    if (cache.has(current)) cache.get(current).scroll = art.scrollTop;
    current = tab;
    for (const b of pane.querySelectorAll("[data-mtab]")) b.setAttribute("aria-selected", String(b.dataset.mtab === tab));
    const own = pane.querySelector("[data-own]");
    const spec = TABS.find((t) => t[0] === tab);
    own.hidden = !spec[2] || spec[2].endsWith(".md");
    if (spec[2]) own.setAttribute("href", spec[2]);
    art.innerHTML = `<p class="empty">Loading…</p>`;
    toc.innerHTML = "";
    try {
      const entry = await load(tab);
      if (current !== tab) return;
      art.innerHTML = entry.html;
      wire();
      if (tab === "how" || tab === "inference") {
        const drawn = drawStageFlows();
        if (anchor) await drawn;           // the figures above the anchor must have their height first
        if (current !== tab) return;
      }
      // the contents: stage and section headings (and the literature's parts and sections)
      const heads = [...art.querySelectorAll("h2[id], h3[id]")];
      toc.innerHTML = heads.map((h) => `<a href="#${esc(h.id)}" class="${h.tagName === "H3" ? "sub" : ""}">${esc(h.textContent)}</a>`).join("");
      for (const a of toc.querySelectorAll("a")) {
        a.addEventListener("click", (ev) => {
          ev.preventDefault();
          // scroll the article only (scrollIntoView would also scroll the page and shift the whole app)
          const target = art.querySelector(`#${CSS.escape(a.getAttribute("href").slice(1))}`);
          if (target) {
            const top = target.getBoundingClientRect().top - art.getBoundingClientRect().top + art.scrollTop - 8;
            art.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
          }
        });
      }
      art.scrollTop = entry.scroll;
      const target = anchor && art.querySelector(`#${CSS.escape(anchor)}`);
      if (target) art.scrollTop = target.getBoundingClientRect().top - art.getBoundingClientRect().top + art.scrollTop - 8;
    } catch (err) {
      art.innerHTML = `<p class="error">Could not load it: ${esc(err.message)}</p>`;
    }
  }

  function open(tab, anchor = null) {
    pane.classList.remove("hidden");
    document.getElementById("btn-methods")?.setAttribute("aria-expanded", "true");
    show(tab ?? current, anchor);
  }
  function close() {
    pane.classList.add("hidden");
    document.getElementById("btn-methods")?.setAttribute("aria-expanded", "false");
  }
  return { open, close, toggle: () => (pane.classList.contains("hidden") ? open() : close()), isOpen: () => !pane.classList.contains("hidden") };
}
