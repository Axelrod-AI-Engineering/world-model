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
// Oct 22: the svg is a layer a little larger than the canvas (this share of it past each edge, clipped) instead of
// overflow: visible. An unbounded layer made the compositor draw it again at every step of a zoom (measured: 14 s of
// painting against 0.1 s for a bounded one of the same drawing); a bounded one is drawn once and scaled. The margin is
// what a buffered pan or zoom out can reveal before the view is committed (a pan past three quarters of it commits).
export const MARGIN = 0.4;

export function createZoom(svg, root, { onZoom, onRest, grid } = {}) {
  const node = svg.node();
  const host = node.parentNode;   // the zoom lives on the svg's container, which never moves
  const ours = (ev) => ev.target === host || node.contains(ev.target);
  let gliding = false;
  let committed = d3.zoomIdentity;
  let restTimer = 0;
  const offset = () => ({ x: host.clientWidth * MARGIN, y: host.clientHeight * MARGIN });
  function commit(t = d3.zoomTransform(host)) {
    clearTimeout(restTimer);
    restTimer = 0;
    committed = t;
    // the svg's own origin sits MARGIN of the canvas up and to the left of the canvas's
    const o = offset();
    root.attr("transform", `translate(${t.x + o.x},${t.y + o.y}) scale(${t.k})`);
    node.style.transformOrigin = `${o.x}px ${o.y}px`;
    grid?.(t);
    node.style.transform = "";
    host.classList.remove("buffering");
  }
  function buffer(t) {
    const s = t.k / committed.k;
    const dx = t.x - s * committed.x;
    const dy = t.y - s * committed.y;
    const o = offset();
    if (s < SHARP[0] || s > SHARP[1] || Math.abs(dx) > o.x * 0.75 || Math.abs(dy) > o.y * 0.75) { commit(t); return; }
    host.classList.add("buffering");
    const css = `translate(${dx}px,${dy}px) scale(${s})`;
    node.style.transform = css;
    grid?.slide?.(css);
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
  window.addEventListener("resize", () => commit());
  commit();

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
// Oct 22: two CSS gradients on a layer of its own under the svg, not an svg pattern inside it. The pattern was the
// largest single cost of re-drawing the svg while the view moved (about half of what was left to paint once the graph had
// fewer elements); a gradient is cheap, and while the view moves the layer slides and scales with the drawing (`slide`).
export function installGrid(svg) {
  const host = svg.node().parentNode;
  const el = document.createElement("div");
  el.className = "grid-bg";
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = '<i class="minor"></i><i class="major"></i>';
  host.insertBefore(el, svg.node());
  const [minor, major] = el.children;
  let last = { x: 0, y: 0, k: 1 };
  const mod = (a, n) => ((a % n) + n) % n;
  const commit = (t) => {
    last = { x: t.x, y: t.y, k: t.k };
    // the layer is three canvases wide and tall, so a buffered pan or zoom out never slides past its edge
    const w = host.clientWidth;
    const h = host.clientHeight;
    el.style.transform = "";
    el.style.transformOrigin = `${w}px ${h}px`;
    for (const [layer, step] of [[minor, 24], [major, 120]]) {
      const s = step * t.k;
      layer.style.backgroundSize = `${s}px ${s}px`;
      layer.style.backgroundPosition = `${mod(t.x + w, s)}px ${mod(t.y + h, s)}px`;
    }
    // very far out, the minor grid would be a gray wash; let it fade
    minor.style.opacity = String(Math.max(0, Math.min(1, (t.k - 0.3) / 0.4)));
  };
  commit.slide = (css) => { el.style.transform = css; };
  window.addEventListener("resize", () => commit(d3.zoomIdentity.translate(last.x, last.y).scale(last.k)));
  commit(d3.zoomIdentity);
  return commit;
}
