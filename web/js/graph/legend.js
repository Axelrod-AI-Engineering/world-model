// The key (§13.2): the eight categories behind the codes on every pill, then Figure 1's symbols plus
// learned edges, nesting, and observed versus propagated values. Hovering a category lights up its
// entities; the symbols fold away so the first view stays quiet.
import { CATEGORY_BLURBS, CATEGORY_CODES, CATEGORY_NAMES } from "./layouts.js";
import { esc } from "../util.js";

export const SYMBOLS = [
  ["Entity", `<svg width="30" height="14"><rect x="1" y="2" width="28" height="10" rx="4" fill="#FFFDF8" stroke="#C2B8A8"/></svg>`],
  ["Entity in no superentity", `<svg width="30" height="14"><rect x="1" y="2" width="28" height="10" rx="4" fill="#FFFDF8" stroke="#A69C8E" stroke-dasharray="3 3"/></svg>`],
  ["Superentity", `<svg width="30" height="14"><rect x="1" y="1" width="28" height="12" rx="5" fill="#F3E1A6" fill-opacity=".55" stroke="#B08F2E" stroke-dasharray="5 3"/></svg>`],
  ["Superentity of superentities", `<svg width="30" height="14"><rect x="1" y="1" width="28" height="12" rx="5" fill="#EAE2D6" fill-opacity=".6" stroke="#8C7A66" stroke-dasharray="7 2 1.5 2"/><rect x="7" y="4" width="16" height="6" rx="3" fill="#F4CDB6" stroke="#C9825A" stroke-dasharray="3 2"/></svg>`],
  ["Candidate superentity", `<svg width="30" height="14"><rect x="1" y="1" width="28" height="12" rx="5" fill="none" stroke="#9A8C74" stroke-dasharray="1.5 3"/></svg>`],
  ["Causal link", `<svg width="30" height="14"><line x1="2" y1="7" x2="23" y2="7" stroke="#857C70" stroke-width="1.6"/><path d="M22 3.5L29 7L22 10.5Z" fill="#857C70"/></svg>`],
  ["Learned link", `<svg width="30" height="14"><line x1="2" y1="7" x2="23" y2="7" stroke="#7C64C4" stroke-width="1.2"/><path d="M22 3.5L29 7L22 10.5Z" fill="#7C64C4"/><text x="9" y="13.5" font-size="7.5" font-weight="700" fill="#4A3590">L</text></svg>`],
  ["Co-movement, not yet causal", `<svg width="30" height="14"><line x1="2" y1="7" x2="28" y2="7" stroke="#93465F" stroke-width="1.5" stroke-dasharray="4 3"/></svg>`],
  ["Moved up / down (sd)", `<svg width="30" height="14"><text x="2" y="11" font-size="10" fill="#B5523B">▲</text><text x="16" y="11" font-size="10" fill="#2F5F8A">▼</text></svg>`],
  ["Observed today / propagated", `<svg width="30" height="14"><circle cx="7" cy="7" r="3.2" fill="#665E54"/><circle cx="21" cy="7" r="3.2" fill="none" stroke="#665E54" stroke-dasharray="1.5 1.5"/></svg>`],
  ["Used by a superentity", `<svg width="30" height="14"><rect x="4" y="2" width="3" height="10" rx="1.5" fill="#C9825A"/><rect x="9" y="2" width="3" height="10" rx="1.5" fill="#B08F2E"/></svg>`],
  ["Shared by two superentities (a stripe per owner)", `<svg width="30" height="14"><rect x="1" y="1.5" width="28" height="11" rx="4" fill="#FFFDF8" stroke="#C2B8A8"/><rect x="4" y="3.5" width="2.4" height="7" rx="1.2" fill="#6B84A8"/><rect x="8" y="3.5" width="2.4" height="7" rx="1.2" fill="#B07688"/></svg>`],
  ["Where two superentities overlap", `<svg width="30" height="14"><defs><pattern id="lgp" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.5" height="5" fill="#6B84A8" fill-opacity=".35"/><rect x="2.5" width="2.5" height="5" fill="#B07688" fill-opacity=".35"/></pattern></defs><rect x="1" y="1" width="18" height="12" rx="4" fill="#DCE3EE" stroke="#6B84A8" stroke-dasharray="3 2"/><rect x="11" y="1" width="18" height="12" rx="4" fill="#F1D9DF" fill-opacity=".7" stroke="#B07688" stroke-dasharray="3 2"/><rect x="11" y="1" width="8" height="12" fill="url(#lgp)"/></svg>`],
  ["A closed superentity's member drawn elsewhere", `<svg width="30" height="14"><rect x="1" y="3" width="13" height="8" rx="4" fill="none" stroke="#B07688" stroke-dasharray="2 1.5"/><path d="M14 7 Q21 1 28 7" fill="none" stroke="#B07688" stroke-dasharray="2 2"/><circle cx="28" cy="7" r="1.8" fill="#B07688"/></svg>`],
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
