// Zoom and pan (§13.3). The faint grid pans and scales with the canvas. Detail is chosen per node (right-click,
// double-click) or for everything at once with the Superentities / Entities / Subentities buttons.
// DECISION (Oct 11): with "Auto" on, detail follows zoom gradually, node by node (graph/lod.js). The wheel glides, like a
// map: each notch moves a target scale, and the view eases toward it about the cursor, so steps never jump.
/* global d3 */

const K_EXTENT = [0.2, 3.5];
// DECISION (Oct 11): zooming and panning are buffered, like map tiles. While the view moves, the drawing already made is
// slid and scaled as one composited layer (a CSS transform on the svg), so no frame re-lays out or repaints the
// graph; the real transform is committed once the view rests, or sooner once the layer has been scaled so far it
// would blur. Zoomed in, a frame used to repaint every value row, outline, and label.
const REST_MS = 140;
const SHARP = [0.67, 1.5];       // commit mid-gesture once the buffered scale leaves this range

export function createZoom(svg, root, { onZoom, onRest, grid } = {}) {
  const node = svg.node();
  const host = node.parentNode;   // the zoom lives on the svg's container, which never moves
  const ours = (ev) => ev.target === host || node.contains(ev.target);
  let gliding = false;
  let committed = d3.zoomIdentity;
  let restTimer = 0;
  function commit(t = d3.zoomTransform(host)) {
    clearTimeout(restTimer);
    restTimer = 0;
    committed = t;
    root.attr("transform", t);
    grid?.(t);
    node.style.transform = "";
    host.classList.remove("buffering");
  }
  function buffer(t) {
    const s = t.k / committed.k;
    if (s < SHARP[0] || s > SHARP[1]) { commit(t); return; }
    host.classList.add("buffering");
    node.style.transform = `translate(${t.x - s * committed.x}px,${t.y - s * committed.y}px) scale(${s})`;
  }
  const zoom = d3.zoom()
    .scaleExtent(K_EXTENT)
    // the wheel is ours (below); d3 keeps drag-to-pan and pinch on touch screens, on the canvas only (not its overlays)
    .filter((ev) => ev.type !== "wheel" && !ev.button && !ev.ctrlKey && ev.type !== "dblclick" && ours(ev))
    .on("zoom", (ev) => {
      buffer(ev.transform);
      clearTimeout(restTimer);
      restTimer = setTimeout(() => { commit(); onRest?.(); }, REST_MS);
      onZoom?.(ev.transform, !!ev.sourceEvent || gliding);      // the second argument: a person moved the view
    });
  d3.select(host).call(zoom).on("dblclick.zoom", null);

  // the gliding wheel: notches (or a trackpad's stream of small deltas, or a pinch, which arrives as ctrl+wheel) move a
  // target scale; each frame the view covers a share of the remaining distance in log scale, about the cursor
  let target = null;
  let anchor = null;
  let raf = 0;
  const glide = () => {
    const t = d3.zoomTransform(host);
    const lk = Math.log(t.k);
    const lt = Math.log(target);
    const done = Math.abs(lt - lk) < 0.003;
    const k = done ? target : Math.exp(lk + (lt - lk) * 0.3);
    const wx = (anchor[0] - t.x) / t.k;
    const wy = (anchor[1] - t.y) / t.k;
    gliding = true;
    d3.select(host).call(zoom.transform, d3.zoomIdentity.translate(anchor[0] - wx * k, anchor[1] - wy * k).scale(k));
    gliding = false;
    if (done) { target = null; raf = 0; return; }
    raf = requestAnimationFrame(glide);
  };
  host.addEventListener("wheel", (ev) => {
    if (!ours(ev)) return;
    ev.preventDefault();
    d3.select(host).interrupt();
    const unit = ev.deltaMode === 1 ? 0.05 : ev.deltaMode === 2 ? 1 : 0.002;
    const f = Math.pow(2, -ev.deltaY * unit * (ev.ctrlKey ? 4 : 1));
    const base = target ?? d3.zoomTransform(host).k;
    target = Math.max(K_EXTENT[0], Math.min(K_EXTENT[1], base * f));
    const r = host.getBoundingClientRect();
    anchor = [ev.clientX - r.left, ev.clientY - r.top];
    if (!raf) raf = requestAnimationFrame(glide);
  }, { passive: false });

  const size = () => host.getBoundingClientRect();
  // jumps buffer too (the slider's drag is a stream of them); screen boxes measured meanwhile include the layer's slide
  const to = (next, duration) => (duration ? d3.select(host).transition().duration(duration).call(zoom.transform, next)
    : d3.select(host).call(zoom.transform, next));

  return {
    zoom,
    transform: () => d3.zoomTransform(host),
    // the canvas's box on screen (the svg itself slides while a zoom is buffered)
    rect: () => host.getBoundingClientRect(),
    by(factor, duration = 180) {
      d3.select(host).transition().duration(duration).call(zoom.scaleBy, factor);
    },
    // fit a box [[x0, y0], [x1, y1]] inside the viewport, leaving room for overlays
    fit(bounds, duration = 320, { maxK = 1.25, minK = 0.2, pad = { top: 64, right: 24, bottom: 64, left: 24 } } = {}) {
      if (!bounds) return;
      const { width, height } = size();
      const [[x0, y0], [x1, y1]] = bounds;
      const w = Math.max(x1 - x0, 1);
      const h = Math.max(y1 - y0, 1);
      const aw = Math.max(80, width - pad.left - pad.right);
      const ah = Math.max(80, height - pad.top - pad.bottom);
      const k = Math.max(minK, Math.min(maxK, Math.min(aw / w, ah / h)));
      const cx = pad.left + aw / 2;
      const cy = pad.top + ah / 2;
      to(d3.zoomIdentity.translate(cx - ((x0 + x1) / 2) * k, cy - ((y0 + y1) / 2) * k).scale(k), duration);
    },
    // return to a saved camera ({x, y, k}), e.g. when undo reverses a preset that refit the view
    set(t, duration = 280) {
      if (!t) return;
      to(d3.zoomIdentity.translate(t.x, t.y).scale(t.k), duration);
    },
    // dx shifts the center, e.g. to the middle of what the side panels leave visible
    centerOn(x, y, k = null, duration = 300, dx = 0) {
      const { width, height } = size();
      const kk = k ?? Math.max(d3.zoomTransform(host).k, 1);
      to(d3.zoomIdentity.translate(width / 2 + dx - x * kk, height / 2 - y * kk).scale(kk), duration);
    },
    // move the view by screen pixels
    panBy(dx, dy, duration = 260) {
      const t = d3.zoomTransform(host);
      to(d3.zoomIdentity.translate(t.x + dx, t.y + dy).scale(t.k), duration);
    },
  };
}

// A faint grid in screen space whose pattern follows the zoom transform, so lines stay one pixel wide.
export function installGrid(svg, defs) {
  const minor = defs.append("pattern").attr("id", "grid-minor").attr("patternUnits", "userSpaceOnUse")
    .attr("width", 24).attr("height", 24);
  const minorLine = minor.append("path").attr("d", "M24 0H0V24").attr("fill", "none").attr("class", "grid-minor-line");
  const major = defs.append("pattern").attr("id", "grid-major").attr("patternUnits", "userSpaceOnUse")
    .attr("width", 120).attr("height", 120);
  const majorLine = major.append("path").attr("d", "M120 0H0V120").attr("fill", "none").attr("class", "grid-major-line");
  const bg = svg.insert("g", ":first-child").attr("class", "grid-bg").attr("pointer-events", "none");
  // three canvases wide and tall, so a buffered pan or zoom out never slides past its edge
  for (const id of ["grid-minor", "grid-major"]) {
    bg.append("rect").attr("x", "-100%").attr("y", "-100%").attr("width", "300%").attr("height", "300%").attr("fill", `url(#${id})`);
  }
  return (t) => {
    const tr = `translate(${t.x},${t.y}) scale(${t.k})`;
    minor.attr("patternTransform", tr);
    major.attr("patternTransform", tr);
    minorLine.attr("stroke-width", 1 / t.k);
    majorLine.attr("stroke-width", 1 / t.k);
    // very far out, the minor grid would be a gray wash; let it fade
    minorLine.attr("stroke-opacity", Math.max(0, Math.min(1, (t.k - 0.3) / 0.4)));
  };
}
