// Color (Oct 9): color answers one question at a time, and every hue keeps one meaning across the app. The button in
// the canvas controls picks what pills are colored by (change, open, category, or nothing) and opens the key: what
// each color and line on the canvas means.
import { CATEGORY_NAMES } from "../graph/layouts.js";
import { esc } from "../util.js";

const MODES = [
  { id: "change", label: "Change", help: "How far each entity's largest value is from normal: green up, red down. Stronger is further." },
  { id: "open", label: "Blind spots", help: "How much of each entity's movement the graph does not explain yet: amber is a blind spot." },
  { id: "category", label: "Category", help: "Each entity's economic category." },
  { id: "none", label: "None", help: "Plain pills." },
];
const KEY = [
  ["sw up", "Moved up (▲), or a positive effect"],
  ["sw down", "Moved down (▼), or a negative effect"],
  ["sw learn", "Learning: new, staged, or learned structure (violet)"],
  ["sw hyp", "Hypothetical: a what-if, never learned (orchid)"],
  ["sw hull", "A superentity: one outline color per group"],
  ["sw open", "An open node: what the graph does not explain yet"],
  ["sw dash", "Dashed: not committed yet, or not yet sure (a candidate, a hedge)"],
];

export function initColorKey({ renderer }) {
  const host = document.getElementById("canvas-controls");
  const wrap = document.createElement("div");
  wrap.className = "ck-wrap";
  wrap.innerHTML = `<button id="btn-color" aria-haspopup="dialog" aria-expanded="false" title="What pills are colored by, and what every color means (K)">
      <span class="ck-sw" aria-hidden="true"></span><span class="ck-lab">Color</span></button>
    <div id="color-pop" class="color-pop hidden" role="dialog" aria-label="Color"></div>`;
  host.insertBefore(wrap, host.firstChild);
  const btn = wrap.querySelector("#btn-color");
  const pop = wrap.querySelector("#color-pop");
  let mode = "change";
  try { mode = localStorage.getItem("axelrod.colorBy") || "change"; } catch { /* private window */ }

  function apply(m) {
    mode = m;
    renderer.setOptions({ colorBy: m });
    try { localStorage.setItem("axelrod.colorBy", m); } catch { /* ignore */ }
    btn.querySelector(".ck-lab").textContent = `Color: ${MODES.find((x) => x.id === m)?.label ?? m}`;
    btn.dataset.mode = m;
    render();
  }
  function render() {
    pop.innerHTML = `<div class="cp-h">Color pills by</div>
      <div class="cp-modes" role="radiogroup">${MODES.map((m) => `<label class="cp-mode"><input type="radio" name="color-by" value="${m.id}" ${m.id === mode ? "checked" : ""}>
        <span><b>${esc(m.label)}</b><span class="small muted">${esc(m.help)}</span></span></label>`).join("")}</div>
      ${mode === "category" ? `<div class="cp-cats">${Object.entries(CATEGORY_NAMES).map(([k, n]) => `<span><i style="background:var(--cat-${k})"></i>${esc(k)} ${esc(n)}</span>`).join("")}</div>` : ""}
      <div class="cp-h">What the canvas shows</div>
      <ul class="cp-key">${KEY.map(([c, t]) => `<li><span class="${c}" aria-hidden="true"></span>${esc(t)}</li>`).join("")}</ul>`;
    for (const r of pop.querySelectorAll("input[name=color-by]")) r.addEventListener("change", () => apply(r.value));
  }
  const setOpen = (on) => { pop.classList.toggle("hidden", !on); btn.setAttribute("aria-expanded", String(on)); if (on) render(); };
  btn.addEventListener("click", (ev) => { ev.stopPropagation(); setOpen(pop.classList.contains("hidden")); });
  document.addEventListener("click", (ev) => { if (!wrap.contains(ev.target)) setOpen(false); });
  apply(mode);
  return { toggle: () => setOpen(pop.classList.contains("hidden")), close: () => setOpen(false), isOpen: () => !pop.classList.contains("hidden") };
}
