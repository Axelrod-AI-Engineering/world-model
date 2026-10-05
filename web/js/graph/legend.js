// The legend repeats Figure 1's key and adds learned causal edges and fuzzy ribbons (§13.2).
import { CATEGORY_CODES, CATEGORY_NAMES } from "./layouts.js";

const ITEMS = [
  ["entity", `<svg width="34" height="14"><rect x="1" y="1" width="32" height="12" rx="6" fill="#FFFDF8" stroke="#8B8173"/></svg>`],
  ["entity in no superentity", `<svg width="34" height="14"><rect x="1" y="1" width="32" height="12" rx="6" fill="#FBF8F2" stroke="#8B8173" stroke-dasharray="4 3"/></svg>`],
  ["inferred superentity", `<svg width="34" height="14"><rect x="1" y="1" width="32" height="12" rx="4" fill="#F4CDB6" fill-opacity=".6" stroke="#C9825A" stroke-dasharray="5 3"/></svg>`],
  ["candidate superentity", `<svg width="34" height="14"><rect x="1" y="1" width="32" height="12" rx="4" fill="none" stroke="#9A8C74" stroke-dasharray="1.5 3"/></svg>`],
  ["causal edge", `<svg width="34" height="14"><line x1="2" y1="7" x2="28" y2="7" stroke="#6F665B" stroke-width="2"/><path d="M26 3L33 7L26 11Z" fill="#6F665B"/></svg>`],
  ["learned causal edge (L)", `<svg width="34" height="14"><line x1="2" y1="7" x2="28" y2="7" stroke="#7C64C4" stroke-width="1"/><path d="M26 3L33 7L26 11Z" fill="#7C64C4"/><text x="12" y="13" font-size="8" font-weight="700" fill="#4A3590">L</text></svg>`],
  ["co-movement on the frontier", `<svg width="34" height="14"><line x1="2" y1="7" x2="32" y2="7" stroke="#D9A9B8" stroke-width="2.2" stroke-dasharray="5 4"/></svg>`],
  ["fuzzy op (real / hypothetical)", `<svg width="34" height="14"><line x1="4" y1="7" x2="16" y2="7" stroke="#7C64C4" stroke-width="8" stroke-linecap="round" opacity=".45"/><line x1="20" y1="7" x2="31" y2="7" stroke="#B07CC0" stroke-width="8" stroke-linecap="round" opacity=".45"/></svg>`],
  ["deviation up / down", `<svg width="34" height="14"><text x="2" y="11" font-size="11" fill="#B5523B">▲</text><text x="18" y="11" font-size="11" fill="#2F5F8A">▼</text></svg>`],
];

export function renderLegend(el) {
  el.innerHTML = `
    <div class="row"><b class="small">Key</b><span class="spacer"></span>
      <button class="small" id="legend-toggle" aria-expanded="true" style="padding:0 6px">hide</button></div>
    <div class="items">${ITEMS.map(([label, svg]) => `<span class="item">${svg}<span>${label}</span></span>`).join("")}</div>
    <div class="codes small">${CATEGORY_CODES.map((c) => `<b>${c}</b> ${CATEGORY_NAMES[c]}`).join(" · ")}</div>`;
  const btn = el.querySelector("#legend-toggle");
  btn.addEventListener("click", () => {
    const collapsed = el.classList.toggle("collapsed");
    btn.textContent = collapsed ? "key" : "hide";
    btn.setAttribute("aria-expanded", String(!collapsed));
  });
}
