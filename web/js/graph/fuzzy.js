// Fuzzy to real (§13.4): a fuzzy op is a wide translucent ribbon, violet for real events and orchid
// for hypothetical ones. Widths follow the least specific end: generalization 28, entity 14, subentity 4.
/* global d3 */

export const RIBBON_WIDTH = { generalization: 28, entity: 14, subentity: 4 };

export function prettyNode(ref) {
  if (!ref) return "?";
  const m = /^gen:(obj|int):(.+)$/.exec(ref);
  const s = m ? m[2] : String(ref).replace(/^new:/, "");
  return s.replace(/[._]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Normalize server fuzzy views and live translation ops into ribbon items.
export function ribbonItems(view, liveOps) {
  const items = [];
  for (const f of view?.fuzzy ?? []) {
    const ends = {};
    for (const name of ["source", "target", "subject"]) if (f[name]) ends[name] = f[name];
    items.push({ key: `srv:${f.pending_id}:${f.proposal_id ?? ""}`, ends, label: f.label, relation: f.relation,
                 hyp: f.kind === "hypothetical", pending: f.status === "pending", proposed: f.status === "proposed" });
  }
  for (const o of liveOps?.values() ?? []) {
    const ends = o.ends ?? {};
    const levels = Object.values(ends).map((e) => e.level);
    if (!levels.length) continue;
    if (o.op === "add_interaction" && levels.every((l) => l === "subentity") && !o.lastStep) continue;
    items.push({ key: `live:${o.key}`, ends, label: o.label, hyp: o.hyp, live: true });
  }
  return items;
}

function widthOf(ends) {
  let w = 4;
  for (const e of Object.values(ends)) w = Math.max(w, RIBBON_WIDTH[e.level] ?? 14);
  return w;
}

// Draw the ribbons. `anchor(end)` returns {x, y, blob: [[x, y], ...] | null} in canvas coordinates.
export function drawRibbons(layer, items, anchor, colors, { animate = true, duration = 700 } = {}) {
  const data = items.map((it) => {
    const names = Object.keys(it.ends);
    const a = anchor(it.ends[names.includes("source") ? "source" : names[0]]);
    const b = names.includes("target") ? anchor(it.ends.target) : null;
    return { ...it, a, b, width: widthOf(it.ends) };
  }).filter((d) => d.a);
  const color = (d) => (d.hyp ? colors.hyp : colors.real);
  const g = layer.selectAll("g.ribbon").data(data, (d) => d.key);
  g.exit().transition().duration(animate ? 400 : 0).style("opacity", 0).remove();
  const enter = g.enter().append("g").attr("class", "ribbon").style("opacity", 0);
  enter.append("path").attr("class", "fuzzy-blob");
  enter.append("path").attr("class", "fuzzy-blob-b");
  enter.append("path").attr("class", "fuzzy-ribbon");
  enter.append("text").attr("class", "fuzzy-label");
  enter.append("g").attr("class", "badge-g");
  const all = enter.merge(g);
  all.transition().duration(animate ? 300 : 0).style("opacity", 1);
  const blobPath = (blob) => (blob && blob.length >= 3
    ? d3.line().curve(d3.curveCatmullRomClosed.alpha(0.5))(blob) : null);
  all.select("path.fuzzy-blob").attr("fill", (d) => (d.hyp ? colors.hypFill : colors.realFill))
    .attr("stroke", color).attr("d", (d) => blobPath(d.a.blob));
  all.select("path.fuzzy-blob-b").attr("class", "fuzzy-blob fuzzy-blob-b")
    .attr("fill", (d) => (d.hyp ? colors.hypFill : colors.realFill)).attr("stroke", color)
    .attr("d", (d) => blobPath(d.b?.blob));
  const ribbon = all.select("path.fuzzy-ribbon").attr("stroke", color)
    .attr("d", (d) => {
      if (!d.b) return `M${d.a.x} ${d.a.y}h0.01`;
      const mx = (d.a.x + d.b.x) / 2;
      const my = (d.a.y + d.b.y) / 2 - 24;
      return `M${d.a.x} ${d.a.y}Q${mx} ${my} ${d.b.x} ${d.b.y}`;
    });
  (animate ? ribbon.transition().duration(duration) : ribbon).attr("stroke-width", (d) => d.width);
  all.select("text.fuzzy-label").attr("fill", (d) => (d.hyp ? colors.hypInk : colors.realInk))
    .attr("x", (d) => (d.b ? (d.a.x + d.b.x) / 2 : d.a.x + 18))
    .attr("y", (d) => (d.b ? (d.a.y + d.b.y) / 2 - 22 : d.a.y - 18))
    .attr("text-anchor", "middle")
    .text((d) => {
      const gen = Object.values(d.ends).find((e) => e.level === "generalization");
      const tag = d.pending ? " · fuzzy" : d.proposed ? " · awaiting review" : "";
      return `${d.label ? d.label.slice(0, 48) : ""}${gen ? ` (${prettyNode(gen.ref)})` : ""}${tag}`;
    });
  return all;
}

// Short-lived flashes of candidate entities with their scores (each refine step).
export function flashCandidates(layer, candidates, position, duration = 700) {
  const pts = (candidates ?? []).map(([id, score]) => ({ id, score, p: position(id) })).filter((d) => d.p);
  const g = layer.append("g").attr("class", "cand-flash");
  g.selectAll("text").data(pts).join("text").attr("x", (d) => d.p.x).attr("y", (d) => d.p.y - 20)
    .attr("text-anchor", "middle").attr("font-size", 11).attr("font-weight", 700).attr("fill", "#4A3590")
    .text((d) => d.score.toFixed(2));
  g.selectAll("circle").data(pts).join("circle").attr("cx", (d) => d.p.x).attr("cy", (d) => d.p.y).attr("r", 10)
    .attr("fill", "none").attr("stroke", "#7C64C4").attr("stroke-width", 2)
    .transition().duration(duration).attr("r", 34).style("opacity", 0);
  g.transition().delay(duration).duration(250).style("opacity", 0).remove();
}
