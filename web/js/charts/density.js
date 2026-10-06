// Small distribution pictures (the user asked for a small version of the distribution rather than a box
// plot). The server sends each distribution as points (x, density / peak); the client only draws them.
/* global d3 */

const SMOOTH = d3.curveBasis;

// A filled density curve into `sel` (a <g>), centered on 0 horizontally, sitting on its baseline at y = h/2.
// Options: width, height, fill, stroke, prior (points drawn dashed behind), marker (x drawn as a tick),
// zero (draw the x = 0 line, for effects), domain ([x0, x1] shared with other curves).
export function densityCurve(sel, points, { width = 34, height = 10, fill = "#DCE6F0", stroke = "#3B5B7C",
                                            prior = null, marker = null, zero = false, domain = null } = {}) {
  sel.selectAll("*").remove();
  if (!points?.length) return;
  const all = prior?.length ? points.concat(prior) : points;
  const dom = domain ?? d3.extent(all, (p) => p[0]);
  if (zero) { dom[0] = Math.min(dom[0], 0); dom[1] = Math.max(dom[1], 0); }
  if (!(dom[1] > dom[0])) return;
  const x = d3.scaleLinear().domain(dom).range([-width / 2, width / 2]);
  const y = d3.scaleLinear().domain([0, 1]).range([height / 2, -height / 2]);
  const area = d3.area().curve(SMOOTH).x((p) => x(p[0])).y0(height / 2).y1((p) => y(p[1]));
  const line = d3.line().curve(SMOOTH).x((p) => x(p[0])).y((p) => y(p[1]));
  if (prior?.length) {
    sel.append("path").attr("d", line(prior)).attr("fill", "none").attr("stroke", stroke).attr("stroke-width", 1)
      .attr("stroke-dasharray", "2 2").attr("opacity", 0.55);
  }
  sel.append("path").attr("d", area(points)).attr("fill", fill).attr("stroke", "none");
  sel.append("path").attr("d", line(points)).attr("fill", "none").attr("stroke", stroke).attr("stroke-width", 1.2);
  sel.append("line").attr("x1", -width / 2).attr("x2", width / 2).attr("y1", height / 2).attr("y2", height / 2)
    .attr("stroke", stroke).attr("stroke-opacity", 0.35).attr("stroke-width", 0.8);
  if (zero && dom[0] < 0 && dom[1] > 0) {
    sel.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", -height / 2 - 1).attr("y2", height / 2)
      .attr("stroke", "#665E54").attr("stroke-dasharray", "1.5 1.5").attr("stroke-width", 0.8);
  }
  if (marker != null && Number.isFinite(marker)) {
    sel.append("line").attr("x1", x(marker)).attr("x2", x(marker)).attr("y1", -height / 2 - 1.5).attr("y2", height / 2)
      .attr("stroke", stroke).attr("stroke-width", 1.4);
  }
}

// A standalone density picture as an <svg>, for panels; with labels for the ends when `labels` is set.
export function densitySvg(points, { width = 120, height = 28, labels = false, unit = "", fmt = null, ...opts } = {}) {
  const pad = labels ? 12 : 2;
  const svg = d3.create("svg").attr("width", width).attr("height", height + pad).attr("class", "density")
    .attr("viewBox", `${-width / 2} ${-height / 2 - 1} ${width} ${height + pad}`).attr("role", "img")
    .attr("aria-label", "distribution");
  densityCurve(svg.append("g"), points, { width: width - 4, height, ...opts });
  if (labels && points?.length) {
    const f = fmt ?? d3.format(".3~g");
    const xs = (opts.prior?.length ? points.concat(opts.prior) : points).map((p) => p[0]);
    const lo = Math.min(...xs, opts.zero ? 0 : Infinity);
    const hi = Math.max(...xs, opts.zero ? 0 : -Infinity);
    svg.append("text").attr("x", -width / 2 + 2).attr("y", height / 2 + 10).attr("font-size", 9)
      .attr("fill", "#93897C").attr("font-family", "IBM Plex Mono, monospace").text(`${f(lo)}${unit ? ` ${unit}` : ""}`);
    svg.append("text").attr("x", width / 2 - 2).attr("y", height / 2 + 10).attr("font-size", 9).attr("text-anchor", "end")
      .attr("fill", "#93897C").attr("font-family", "IBM Plex Mono, monospace").text(f(hi));
  }
  return svg.node();
}
