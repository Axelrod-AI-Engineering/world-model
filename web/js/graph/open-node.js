// The open node (Oct 9): every node carries an empty terminal node, the probability mass the graph does not account
// for yet (a value's movement its interactions do not explain, a kind's reserve for one not seen yet). It is drawn as
// a small dashed empty circle attached by a short stub; its size grows with the open share, so a well-explained node
// shows a dot and a node driven from outside the graph shows a larger empty ring. The share itself shows on hover.
/* global d3 */

export const openRadius = (share, min = 2, max = 5.5) => min + (max - min) * Math.max(0, Math.min(1, share ?? 1));

// draw (or update) an open node in `g` (a d3 selection), attached at (x, y), pointing right
export function openNode(g, x, y, share, { min = 2, max = 5.5, stub = 3 } = {}) {
  let o = g.select("g.open-node");
  if (o.empty()) {
    o = g.append("g").attr("class", "open-node").attr("aria-hidden", "true");
    o.append("line");
    o.append("circle");
  }
  const r = openRadius(share, min, max);
  o.attr("transform", `translate(${x},${y})`).classed("wide", (share ?? 1) >= 0.5);
  o.select("line").attr("x1", 0).attr("x2", stub).attr("y1", 0).attr("y2", 0);
  o.select("circle").attr("cx", stub + r).attr("cy", 0).attr("r", r);
  return o;
}

export function openWords(share, what = "value") {
  const p = Math.round(100 * (share ?? 1));
  if (what === "kind") return `${p}% reserved for a concept not seen yet`;
  if (what === "pattern") return `${p}% reserved for a group not seen yet`;
  return `${p}% of its movement is not explained by the graph yet`;
}
