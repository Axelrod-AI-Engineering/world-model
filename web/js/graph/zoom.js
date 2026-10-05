// Semantic zoom (§13.3): three levels chosen by the zoom factor k.
/* global d3 */

export const LEVELS = {
  super: { maxK: 0.7, jumpK: 0.5 },
  entity: { maxK: 1.8, jumpK: 1.0 },
  sub: { maxK: Infinity, jumpK: 1.95 },
};

export function levelFor(k) {
  if (k < 0.7) return "super";
  if (k < 1.8) return "entity";
  return "sub";
}

export function createZoom(svg, root, { onZoom, onLevel }) {
  let level = "entity";
  const zoom = d3.zoom()
    .scaleExtent([0.15, 6])
    .filter((ev) => (!ev.ctrlKey || ev.type === "wheel") && !ev.button && !(ev.type === "dblclick"))
    .on("zoom", (ev) => {
      root.attr("transform", ev.transform);
      onZoom?.(ev.transform);
      const lv = levelFor(ev.transform.k);
      if (lv !== level) {
        level = lv;
        onLevel?.(lv);
      }
    });
  svg.call(zoom).on("dblclick.zoom", null);

  const api = {
    zoom,
    get level() { return level; },
    transform: () => d3.zoomTransform(svg.node()),
    jumpTo(lv, duration = 450) {
      const t = d3.zoomTransform(svg.node());
      const { width, height } = svg.node().getBoundingClientRect();
      const cx = (width / 2 - t.x) / t.k;
      const cy = (height / 2 - t.y) / t.k;
      const k = LEVELS[lv].jumpK;
      const next = d3.zoomIdentity.translate(width / 2 - cx * k, height / 2 - cy * k).scale(k);
      svg.transition().duration(duration).call(zoom.transform, next);
    },
    fit(bounds, duration = 450, maxK = 1.6, minK = 0.15) {
      if (!bounds) return;
      const { width, height } = svg.node().getBoundingClientRect();
      const [[x0, y0], [x1, y1]] = bounds;
      const w = Math.max(x1 - x0, 1);
      const h = Math.max(y1 - y0, 1);
      const k = Math.max(minK, Math.min(maxK, 0.92 * Math.min(width / w, height / h)));
      const next = d3.zoomIdentity.translate(width / 2 - ((x0 + x1) / 2) * k, height / 2 - ((y0 + y1) / 2) * k).scale(k);
      svg.transition().duration(duration).call(zoom.transform, next);
    },
    zoomToPoint(x, y, k = 2.3, duration = 500) {
      const { width, height } = svg.node().getBoundingClientRect();
      const next = d3.zoomIdentity.translate(width / 2 - x * k, height / 2 - y * k).scale(k);
      svg.transition().duration(duration).call(zoom.transform, next);
    },
  };
  return api;
}
