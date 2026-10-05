// A small distribution glyph from a DistSummary: the 5-95% whisker, the 25-75% box, and the median.
/* global d3 */

export function densityGlyph(sel, summary, { width = 34, height = 10, color = "#3B5B7C", fill = "#DCE6F0" } = {}) {
  sel.selectAll("*").remove();
  if (!summary) return;
  const lo = summary.q05;
  const hi = summary.q95;
  const pad = (hi - lo) * 0.08 || Math.abs(summary.q50) * 0.05 || 1;
  const x = d3.scaleLinear().domain([lo - pad, hi + pad]).range([-width / 2, width / 2]);
  sel.append("line").attr("x1", x(summary.q05)).attr("x2", x(summary.q95)).attr("y1", 0).attr("y2", 0)
    .attr("stroke", color).attr("stroke-width", 1);
  sel.append("rect").attr("x", x(summary.q25)).attr("y", -height / 2)
    .attr("width", Math.max(1, x(summary.q75) - x(summary.q25))).attr("height", height)
    .attr("fill", fill).attr("stroke", color).attr("stroke-width", 0.8).attr("rx", 1.5);
  sel.append("line").attr("x1", x(summary.q50)).attr("x2", x(summary.q50)).attr("y1", -height / 2 - 1)
    .attr("y2", height / 2 + 1).attr("stroke", color).attr("stroke-width", 1.6);
}

// A standalone glyph as an <svg> element, for panels.
export function densitySvg(summary, opts = {}) {
  const w = (opts.width ?? 80) + 8;
  const h = (opts.height ?? 12) + 8;
  const svg = d3.create("svg").attr("width", w).attr("height", h).attr("viewBox", `${-w / 2} ${-h / 2} ${w} ${h}`)
    .attr("aria-hidden", "true");
  densityGlyph(svg.append("g"), summary, { width: opts.width ?? 80, height: opts.height ?? 12, ...opts });
  return svg.node();
}
