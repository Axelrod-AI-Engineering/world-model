// The zoom slider (Oct 11), in place of the − and + buttons. It is logarithmic, so each step of the thumb is the same
// factor of zoom, and it shows:
//   - bands for what the canvas shows at each zoom: superentities as cards, entities, values (the values band starts
//     at the learned threshold, graph/attention.js);
//   - up to three detents: zoom levels this person keeps settling at. The thumb snaps to them, and clicking one
//     returns to that zoom centered on what was looked at there.
// Dragging zooms about the focus point: the middle of the view, pulled toward what has been looked at most.

import { fromUnit, K_MAX, K_MIN, toUnit } from "./attention.js";

const SNAP = 0.025;           // within this share of the track, the thumb snaps to a detent

export function initZoomSlider(root, renderer, { names = (id) => id } = {}) {
  root.innerHTML = `
    <button class="zs-step icon" data-step="0.8" title="Zoom out (−)" aria-label="Zoom out">−</button>
    <div class="zs-track">
      <div class="zs-bands" aria-hidden="true"><span class="b-cards"></span><span class="b-ents"></span><span class="b-vals"></span></div>
      <div class="zs-detents"></div>
      <input id="zoom-range" type="range" min="0" max="1000" step="1" value="500" aria-label="Zoom">
    </div>
    <button class="zs-step icon" data-step="1.25" title="Zoom in (+)" aria-label="Zoom in">+</button>`;
  const range = root.querySelector("#zoom-range");
  const bands = root.querySelector(".zs-bands");
  const detentBox = root.querySelector(".zs-detents");
  let detents = [];
  let dragging = false;
  let anchor = null;

  const pct = (k) => `${Math.round(k * 100)}%`;
  function title(k) {
    const kOpen = renderer.attention.kOpen;
    return `Zoom ${pct(k)}. Values open from ${pct(kOpen)} (learned from what you open and close). `
      + (detents.length ? "Ticks mark the zooms you settle at: click one to go back to it." : "Zooms you settle at will appear as ticks.");
  }

  function paintBands() {
    // cards below roughly 0.45, entities to the values threshold, values above it; widths on the log track
    const uCards = toUnit(0.45);
    const uVals = toUnit(renderer.attention.kOpen);
    const [c, e, v] = bands.children;
    c.style.width = `${uCards * 100}%`;
    e.style.width = `${(uVals - uCards) * 100}%`;
    v.style.width = `${(1 - uVals) * 100}%`;
    c.title = "Superentities close into cards";
    e.title = "Entities";
    v.title = `Values open (from ${pct(renderer.attention.kOpen)})`;
  }

  let detentKey = "";
  function paintDetents() {
    detents = renderer.attention.detents();
    const key = detents.map((d) => `${toUnit(d.k).toFixed(3)}:${d.nodes.map((n) => n.id).join(",")}`).join("|");
    if (key === detentKey) return;
    detentKey = key;
    detentBox.innerHTML = detents.map((d, i) => {
      const what = d.nodes.slice(0, 3).map((n) => names(n.id)).filter(Boolean).join(", ");
      return `<button class="zs-detent" data-i="${i}" style="left:${toUnit(d.k) * 100}%"
        title="${pct(d.k)}: you often look here${what ? ` (${what})` : ""}" aria-label="Zoom to ${pct(d.k)}"></button>`;
    }).join("");
  }

  function sync(t) {
    if (!dragging) range.value = String(Math.round(toUnit(t.k) * 1000));
    range.setAttribute("aria-valuetext", pct(t.k));
    root.title = title(t.k);
  }

  range.addEventListener("pointerdown", () => { dragging = true; anchor = renderer.focusPoint(); });
  const end = () => { dragging = false; anchor = null; };
  range.addEventListener("pointerup", end);
  range.addEventListener("change", end);
  range.addEventListener("input", () => {
    let u = +range.value / 1000;
    const near = detents.find((d) => Math.abs(toUnit(d.k) - u) < SNAP);
    if (near) { u = toUnit(near.k); range.value = String(Math.round(u * 1000)); }
    // keyboard on the slider: animate; pointer drags: follow the thumb exactly
    renderer.zoomToScale(fromUnit(u), { duration: dragging ? 0 : 200, anchor: anchor ?? undefined });
  });
  root.addEventListener("click", (ev) => {
    const step = ev.target.closest("[data-step]");
    if (step) { renderer.zoomBy(+step.dataset.step); return; }
    const det = ev.target.closest(".zs-detent");
    if (!det) return;
    const d = detents[+det.dataset.i];
    if (!d) return;
    // back to that zoom, centered on what was looked at there (the nodes still on the canvas)
    const pts = d.nodes.map((n) => ({ n: renderer.nodes.get(n.id), w: n.w })).filter((p) => p.n);
    if (!pts.length) { renderer.zoomToScale(d.k, { duration: 420 }); return; }
    const sw = pts.reduce((a, p) => a + p.w, 0);
    const wx = pts.reduce((a, p) => a + p.n.x * p.w, 0) / sw;
    const wy = pts.reduce((a, p) => a + p.n.y * p.w, 0) / sw;
    renderer.personZoomUntil = performance.now() + 600;
    renderer.zoom.centerOn(wx, wy, d.k, 480);
  });

  renderer.handlers.onZoomChange = sync;
  renderer.handlers.onAttention = () => { paintBands(); paintDetents(); };
  paintBands();
  paintDetents();
  sync(renderer.zoom.transform());
  return { refresh() { paintBands(); paintDetents(); sync(renderer.zoom.transform()); }, K_MIN, K_MAX };
}
