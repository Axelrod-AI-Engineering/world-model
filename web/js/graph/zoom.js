// Zoom and pan (§13.3). DECISION: zoom is only geometry. The plan's semantic zoom chose the level of
// detail from the zoom factor; the user found that confusing, so detail is chosen per node (right-click,
// double-click) or for everything at once with the Superentities / Entities / Subentities buttons, and
// zooming never opens or closes anything. The faint grid pans and scales with the canvas.
/* global d3 */

export function createZoom(svg, root, { onZoom, grid } = {}) {
  const zoom = d3.zoom()
    .scaleExtent([0.2, 3.5])
    .filter((ev) => (ev.type === "wheel" || (!ev.button && !ev.ctrlKey)) && ev.type !== "dblclick")
    .on("zoom", (ev) => {
      root.attr("transform", ev.transform);
      grid?.(ev.transform);
      onZoom?.(ev.transform);
    });
  svg.call(zoom).on("dblclick.zoom", null);

  const size = () => svg.node().getBoundingClientRect();
  const to = (next, duration) => (duration ? svg.transition().duration(duration).call(zoom.transform, next)
    : svg.call(zoom.transform, next));

  return {
    zoom,
    transform: () => d3.zoomTransform(svg.node()),
    by(factor, duration = 250) {
      svg.transition().duration(duration).call(zoom.scaleBy, factor);
    },
    // fit a box [[x0, y0], [x1, y1]] inside the viewport, leaving room for overlays
    fit(bounds, duration = 450, { maxK = 1.25, minK = 0.2, pad = { top: 64, right: 24, bottom: 64, left: 24 } } = {}) {
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
    set(t, duration = 450) {
      if (!t) return;
      to(d3.zoomIdentity.translate(t.x, t.y).scale(t.k), duration);
    },
    centerOn(x, y, k = null, duration = 450) {
      const { width, height } = size();
      const kk = k ?? Math.max(d3.zoomTransform(svg.node()).k, 1);
      to(d3.zoomIdentity.translate(width / 2 - x * kk, height / 2 - y * kk).scale(kk), duration);
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
  bg.append("rect").attr("width", "100%").attr("height", "100%").attr("fill", "url(#grid-minor)");
  bg.append("rect").attr("width", "100%").attr("height", "100%").attr("fill", "url(#grid-major)");
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
