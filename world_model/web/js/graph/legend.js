// The key (§13.2): the eight categories behind the codes on every pill, then Figure 1's symbols plus
// learned edges and observed versus propagated values (Oct 17: superentities are no longer drawn, so their symbols left). Hovering a category lights up its
// entities; the symbols fold away so the first view stays quiet.
import { CATEGORY_BLURBS, CATEGORY_CODES, CATEGORY_NAMES } from "./layouts.js";
import { esc } from "../util.js";

export const SYMBOLS = [
  ["Entity", `<svg width="30" height="14"><rect x="1" y="2" width="28" height="10" rx="4" fill="#FFFDF8" stroke="#C2B8A8"/></svg>`],
  ["Causal interaction", `<svg width="30" height="14"><line x1="2" y1="7" x2="23" y2="7" stroke="#857C70" stroke-width="1.6"/><path d="M22 3.5L29 7L22 10.5Z" fill="#857C70"/></svg>`],
  ["Learned interaction", `<svg width="30" height="14"><line x1="2" y1="7" x2="23" y2="7" stroke="#7C64C4" stroke-width="1.2"/><path d="M22 3.5L29 7L22 10.5Z" fill="#7C64C4"/><text x="9" y="13.5" font-size="7.5" font-weight="700" fill="#4A3590">L</text></svg>`],
  ["Co-movement, not yet causal", `<svg width="30" height="14"><line x1="2" y1="7" x2="28" y2="7" stroke="#93465F" stroke-width="1.5" stroke-dasharray="4 3"/></svg>`],
  ["Moved up / down", `<svg width="30" height="14"><text x="2" y="11" font-size="10" style="fill:var(--up)">▲</text><text x="16" y="11" font-size="10" style="fill:var(--down)">▼</text></svg>`],
  ["A value: its distribution and mean, in its unit", `<svg width="30" height="14"><path d="M2 12 C8 12 9 3 12 3 C15 3 16 12 22 12" fill="#DCE6F0" stroke="#3B5B7C" stroke-width="1"/><line x1="12" y1="2" x2="12" y2="12" stroke="#3B5B7C" stroke-width="1.2"/></svg>`],
  ["Observed today / propagated", `<svg width="30" height="14"><circle cx="7" cy="7" r="3.2" fill="#665E54"/><circle cx="21" cy="7" r="3.2" fill="none" stroke="#665E54" stroke-dasharray="1.5 1.5"/></svg>`],
];

export function renderLegend(el, { onCategory } = {}) {
  let symbolsOpen = false;
  let collapsed = false;
  let counts = {};
  function render() {
    el.classList.toggle("collapsed", collapsed);
    el.innerHTML = `
      <div class="head"><h2>Categories</h2>
        <button class="link" id="key-toggle" aria-expanded="${!collapsed}">${collapsed ? "show key" : "hide"}</button></div>
      <div class="cats">${CATEGORY_CODES.map((c) => `<div class="cat" data-cat="${c}" tabindex="0" title="${esc(CATEGORY_BLURBS[c])}">
        <code>${c}</code><span>${esc(CATEGORY_NAMES[c])}</span><span class="n">${counts[c] ?? ""}</span></div>`).join("")}</div>
      <div class="syms">
        <button class="link" id="sym-toggle" aria-expanded="${symbolsOpen}">${symbolsOpen ? "symbols ▾" : "symbols ▸"}</button>
        ${symbolsOpen ? SYMBOLS.map(([label, svg]) => `<div class="sym">${svg}<span>${label}</span></div>`).join("") : ""}
      </div>`;
    el.querySelector("#key-toggle").addEventListener("click", () => { collapsed = !collapsed; render(); });
    el.querySelector("#sym-toggle")?.addEventListener("click", () => { symbolsOpen = !symbolsOpen; render(); });
    for (const row of el.querySelectorAll("[data-cat]")) {
      const c = row.dataset.cat;
      const on = (ev) => onCategory?.(c, ev);
      const off = () => onCategory?.(null);
      row.addEventListener("mouseenter", on);
      row.addEventListener("focus", on);
      row.addEventListener("mouseleave", off);
      row.addEventListener("blur", off);
    }
  }
  render();
  return {
    setCounts(view) {
      counts = {};
      for (const e of view?.entities ?? []) for (const t of e.category_tags ?? []) counts[t] = (counts[t] ?? 0) + 1;
      for (const row of el.querySelectorAll("[data-cat]")) row.querySelector(".n").textContent = counts[row.dataset.cat] ?? "";
    },
  };
}
