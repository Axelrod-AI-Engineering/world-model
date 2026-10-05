// Fan charts (§13.6): 5-95% band, 25-75% band, median line, native units, dates on the axis.
// `compare` overlays another forecast's band outline and median.
/* global d3 */

export function fanChart({ dates, series, compare = null, width = 340, height = 150, unit = "", title = "",
                           zeroLine = false }) {
  const svg = d3.create("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img")
    .attr("aria-label", `${title} fan chart`);
  const m = { top: 8, right: 8, bottom: 20, left: 44 };
  const parse = d3.utcParse("%Y-%m-%d");
  const ts = dates.map((d) => parse(d));
  const all = [...series, ...(compare ?? [])].flatMap((s) => [s.q05, s.q95]).filter(Number.isFinite);
  if (!all.length) return svg.node();
  const x = d3.scaleUtc().domain(d3.extent(ts)).range([m.left, width - m.right]);
  const y = d3.scaleLinear().domain(d3.extent(zeroLine ? [...all, 0] : all)).nice().range([height - m.bottom, m.top]);
  const area = (lo, hi) => d3.area().x((d, i) => x(ts[i])).y0((d) => y(d[lo])).y1((d) => y(d[hi]));
  const line = (k) => d3.line().x((d, i) => x(ts[i])).y((d) => y(d[k]));
  svg.append("path").attr("class", "band95").attr("d", area("q05", "q95")(series));
  svg.append("path").attr("class", "band50").attr("d", area("q25", "q75")(series));
  if (zeroLine && y.domain()[0] < 0 && y.domain()[1] > 0) {
    svg.append("line").attr("class", "zero").attr("x1", m.left).attr("x2", width - m.right).attr("y1", y(0)).attr("y2", y(0));
  }
  if (compare?.length) {
    const n = Math.min(compare.length, ts.length);
    const c = compare.slice(0, n);
    svg.append("path").attr("class", "cmp-band").attr("d", line("q05")(c));
    svg.append("path").attr("class", "cmp-band").attr("d", line("q95")(c));
    svg.append("path").attr("class", "cmp-median").attr("d", line("q50")(c));
  }
  svg.append("path").attr("class", "median").attr("d", line("q50")(series));
  const fmt = d3.format(Math.max(...all.map(Math.abs)) >= 100 ? ",.0f" : ".2f");
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - m.bottom})`)
    .call(d3.axisBottom(x).ticks(4).tickSizeOuter(0).tickFormat(d3.utcFormat("%b %y")));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.left},0)`)
    .call(d3.axisLeft(y).ticks(4).tickSizeOuter(0).tickFormat(fmt));
  if (unit) {
    svg.append("text").attr("x", m.left + 4).attr("y", m.top + 8).attr("font-size", 9.5).attr("fill", "#665E54").text(unit);
  }
  return svg.node();
}

// A small scatter for the frontier promotion chart: earlier move against later innovation.
export function scatter(pairs, { width = 260, height = 150, xLabel = "earlier move", yLabel = "later innovation" } = {}) {
  const svg = d3.create("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img").attr("aria-label", "co-movement scatter");
  const m = { top: 8, right: 8, bottom: 26, left: 34 };
  if (!pairs?.length) {
    svg.append("text").attr("x", width / 2).attr("y", height / 2).attr("text-anchor", "middle").attr("font-size", 11)
      .attr("fill", "#665E54").text("no points yet");
    return svg.node();
  }
  const x = d3.scaleLinear().domain(d3.extent(pairs, (d) => d[0])).nice().range([m.left, width - m.right]);
  const y = d3.scaleLinear().domain(d3.extent(pairs, (d) => d[1])).nice().range([height - m.bottom, m.top]);
  svg.append("g").selectAll("circle").data(pairs).join("circle").attr("cx", (d) => x(d[0])).attr("cy", (d) => y(d[1]))
    .attr("r", 2.6).attr("fill", "#93465F").attr("fill-opacity", 0.6);
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - m.bottom})`).call(d3.axisBottom(x).ticks(4));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.left},0)`).call(d3.axisLeft(y).ticks(4));
  svg.append("text").attr("x", width / 2).attr("y", height - 2).attr("text-anchor", "middle").attr("font-size", 9.5)
    .attr("fill", "#665E54").text(xLabel);
  svg.append("text").attr("transform", `translate(9,${height / 2}) rotate(-90)`).attr("text-anchor", "middle")
    .attr("font-size", 9.5).attr("fill", "#665E54").text(yLabel);
  return svg.node();
}
