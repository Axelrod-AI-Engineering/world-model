// The flowchart (Oct 8 restructure), drawn from /api/flows: the overview of learning or of inference. Each stage
// is a column with its input, its steps, and its output; optional steps are dashed and say when they run; a
// decision lists its answers. A stage can carry "Try it" buttons for the tutorial examples that isolate it.
import { esc } from "../util.js";

const MEM = { working: "WM", long_term: "LTM", both: "WM + LTM" };

export function flowMarkup(flow, { examples = [] } = {}) {
  const byId = new Map(examples.map((x) => [x.id, x]));
  const out = (n) => flow.edges.filter((e) => e.src === n.id);
  const steps = (ph) => flow.nodes.filter((n) => n.phase === ph.id && !n.side);
  const sides = (ph) => flow.nodes.filter((n) => n.phase === ph.id && n.side);
  return `<ol class="fc-grid" aria-label="${esc(flow.title)}">${flow.phases.map((ph, k) => `
    <li class="fc-stage ${esc(ph.id)}" data-phase="${esc(ph.id)}">
      <div class="fc-h"><span class="fc-n">${k + 1}</span>${esc(ph.title)}</div>
      <div class="fc-io in"><span>In</span>${esc(ph.input)}</div>
      <ol class="fc-steps">${steps(ph).map((n) => `
        <li class="fc-step ${esc(n.kind)}${n.mandatory ? "" : " optional"}" data-node="${esc(n.id)}" title="${esc(n.detail || n.label)}">
          <span class="fc-l">${n.kind === "decision" ? "◆ " : n.kind === "store" ? "▣ " : ""}${esc(n.label)}</span>
          ${n.when ? `<span class="fc-when">if ${esc(n.when)}</span>` : ""}
          ${n.kind === "decision" ? `<span class="fc-when">${out(n).map((e) => esc(e.label)).join(" · ")}</span>` : ""}
          ${n.writes ? `<span class="fc-mem ${esc(n.writes)}" title="Writes ${n.writes === "working" ? "working memory" : "long-term memory"}">${MEM[n.writes]}</span>` : ""}
        </li>`).join("")}${sides(ph).map((n) => `<li class="fc-step side ${esc(n.kind)}" data-node="${esc(n.id)}"><span class="fc-l">↳ ${esc(n.label)}</span></li>`).join("")}</ol>
      <div class="fc-io out"><span>Out</span>${esc(ph.output)}</div>
      ${ph.detail ? `<details class="fc-more"><summary>More</summary><p>${esc(ph.detail)}</p></details>` : ""}
      ${(ph.examples ?? []).filter((id) => byId.has(id)).length ? `<div class="fc-try">${ph.examples.filter((id) => byId.has(id)).map((id) =>
        `<button class="small" data-try="${esc(id)}" title="${esc(byId.get(id).isolates)}">Try: ${esc(byId.get(id).title)}</button>`).join("")}</div>` : ""}
    </li>`).join("")}</ol>`;
}

// An overview (learning's five stages, or inference's six) as a grid of cards, each with only its input and output,
// colored by stage (`cls`). A card links to the stage's own flowchart further down the page.
export function overviewMarkup(flow, cls = (ph) => ph.id) {
  return `<ol class="fc-grid overview" aria-label="${esc(flow.title)}">${flow.phases.map((ph, k) => `
    <li class="fc-stage ${esc(cls(ph))}" data-phase="${esc(ph.id)}">
      <a class="fc-h" href="#stage-${esc(ph.id)}"><span class="fc-n">${k + 1}</span>${esc(ph.title)}</a>
      <div class="fc-io in"><span>In</span>${esc(ph.input)}</div>
      <div class="fc-io out"><span>Out</span>${esc(ph.output)}</div>
    </li>`).join("")}</ol>`;
}
