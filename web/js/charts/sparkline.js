// Sparklines, with an optional band (e.g. the weight p(w, t) with q05-q95).
/* global d3 */

export function sparkline(points, { width = 220, height = 42, value = (d) => d.value, lo = null, hi = null,
                                    color = "#2F2A25", band = "#DCE6F0", label = null } = {}) {
  const svg = d3.create("svg").attr("class", "spark").attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img").attr("aria-label", label ?? "sparkline");
  const pts = points.filter((d) => Number.isFinite(value(d)));
  if (pts.length < 2) {
    svg.append("text").attr("x", 4).attr("y", height / 2).attr("class", "muted").attr("font-size", 10)
      .attr("dominant-baseline", "central").text(pts.length ? `${(+value(pts[0])).toFixed(3)}` : "no history");
    return svg.node();
  }
  const ys = pts.flatMap((d) => [value(d), lo ? lo(d) : value(d), hi ? hi(d) : value(d)]).filter(Number.isFinite);
  const x = d3.scaleLinear().domain([0, pts.length - 1]).range([2, width - 2]);
  const y = d3.scaleLinear().domain(d3.extent(ys)).nice().range([height - 3, 3]);
  if (lo && hi) {
    svg.append("path").attr("class", "band").attr("fill", band)
      .attr("d", d3.area().x((d, i) => x(i)).y0((d) => y(lo(d))).y1((d) => y(hi(d)))(pts));
  }
  svg.append("path").attr("class", "line").attr("stroke", color)
    .attr("d", d3.line().x((d, i) => x(i)).y((d) => y(value(d)))(pts));
  const last = pts[pts.length - 1];
  svg.append("circle").attr("cx", x(pts.length - 1)).attr("cy", y(value(last))).attr("r", 2).attr("fill", color);
  return svg.node();
}
