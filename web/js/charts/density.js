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

// The forecast beside its baseline (Oct 14): two distributions on one shared axis, the baseline (without the shock)
// above and the forecast (with it) below, each with its median ticked and its 90% range under it, a dashed line at the
// baseline's median through both, and the shift between the medians marked under them. The server sends both densities
// measured from the baseline's median (inference/groups.split_at_horizon); this only draws them.
export function splitSvg(split, { width = 220, row = 14, labels = true } = {}) {
  const gut = labels ? 46 : 4;                  // room for the row labels
  const padR = 6;
  const gap = 5;
  const rows = [["baseline", "without", "split-base"], ["forecast", "with", "split-fc"]];
  const yS = row * 2 + gap + 9;                 // the shift's line
  const h = yS + 6;
  const s = split?.shift ?? 0;
  const said = `${Math.abs(s) < 0.005 ? "≈ 0" : `${s > 0 ? "▲" : "▼"} ${Math.abs(s).toFixed(2)}`} sd`;
  const svg = d3.create("svg").attr("class", "density split").attr("width", width).attr("height", h)
    .attr("viewBox", `0 0 ${width} ${h}`).attr("role", "img")
    .attr("aria-label", `At the horizon, without the shock and with it: the median shifts ${said}`);
  if (!split?.baseline?.length || !split?.forecast?.length) return svg.node();
  const xs = [...split.baseline, ...split.forecast].map((p) => p[0]).concat([0, ...(split.domain ?? [])]);
  const x = d3.scaleLinear().domain(d3.extent(xs)).range([gut, width - padR]);
  rows.forEach(([key, label, cls], i) => {
    const y0 = i * (row + gap) + row;           // the row's floor
    const y = d3.scaleLinear().domain([0, 1]).range([y0, y0 - row + 1]);
    const g = svg.append("g").attr("class", cls);
    if (labels) g.append("text").attr("class", "split-lab").attr("x", 0).attr("y", y0 - 2).text(label);
    g.append("path").attr("class", "split-area")
      .attr("d", d3.area().curve(SMOOTH).x((p) => x(p[0])).y0(y0).y1((p) => y(p[1]))(split[key]));
    g.append("path").attr("class", "split-line")
      .attr("d", d3.line().curve(SMOOTH).x((p) => x(p[0])).y((p) => y(p[1]))(split[key]));
    g.append("line").attr("class", "split-rule").attr("x1", gut).attr("x2", width - padR).attr("y1", y0).attr("y2", y0);
    const q = split[`${key}_q`] ?? [];
    if (q.length === 3) {
      g.append("line").attr("class", "split-med").attr("x1", x(q[1])).attr("x2", x(q[1])).attr("y1", y0 - row + 1).attr("y2", y0);
    }
  });
  // the baseline's median, through both rows
  svg.append("line").attr("class", "split-zero").attr("x1", x(0)).attr("x2", x(0)).attr("y1", 1).attr("y2", yS);
  // the shift: an arrow from the baseline's median to the forecast's
  const dir = s > 0 ? "up" : "down";
  if (Math.abs(x(s) - x(0)) >= 3) {
    svg.append("line").attr("class", `split-shift ${dir}`).attr("x1", x(0)).attr("x2", x(s)).attr("y1", yS).attr("y2", yS);
    svg.append("path").attr("class", `split-head ${dir}`).attr("d", `M${x(s)},${yS} l${s > 0 ? -4 : 4},-3 l0,6 z`);
  }
  // the number sits past the arrowhead when there is room, else on the other side of the baseline's median
  const W = 6 * said.length;
  let [lx, anchor] = s >= 0
    ? (width - padR - (x(s) + 6) >= W ? [x(s) + 6, "start"] : [x(0) - 5, "end"])
    : (x(s) - 6 - gut >= W ? [x(s) - 6, "end"] : [x(0) + 5, "start"]);
  // no room on either side (a large shift on a small card): the number takes the row label's place
  const cramped = (anchor === "start" && lx + W > width - padR) || (anchor === "end" && lx - W < gut);
  if (cramped && labels) [lx, anchor] = [0, "start"];
  else if (cramped) [lx, anchor] = [width - padR, "end"];
  svg.append("text").attr("class", `split-txt ${Math.abs(s) < 0.005 ? "" : dir}`)
    .attr("x", lx).attr("y", yS + 3.5).attr("text-anchor", anchor).text(cramped && labels ? said.replace(" sd", "").replace(" ", "") : said);
  if (labels && !cramped) svg.append("text").attr("class", "split-lab").attr("x", 0).attr("y", yS + 3.5).text("shift");
  return svg.node();
}
