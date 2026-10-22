// The graph update a document would make (Oct 17), drawn on the canvas before anything changes. Only the values the
// update touches, as chips under their entity's names (like the transmission path): a value it observes or moves
// carries its direction and size (a bar as long as the move is large, in the value's standard deviations), a proposed
// new link is dashed between its ends, and a link the document is evidence for (or against) is solid, with a mark at
// its middle. The model's own furniture is hidden while it is shown; the canvas keeps its paper, grid, pan, and zoom.
import { ownOf } from "../names.js";
import { fmtNumber, fmtValue } from "./model.js";

const CHIP_W = 250;
const CHIP_H = 40;
const GAP_Y = 8;
const GROUP_GAP = 22;
const HEAD_H = 18;
const COL_GAP = 150;
const PER_COL = 6;          // values to a column when nothing links them: the update wraps into columns, never scrolls

const dir = (z) => (z > 0.005 ? "up" : z < -0.005 ? "down" : "flat");

// an op's change in the value's own unit: "→ 1.25%" (a level), "▲0.25pp", "▲4%", "▼0.5 sd" (moves)
export function opText(op, v) {
  const unit = v?.unit ?? "";
  if (op.op === "observe_value") return `→ ${fmtValue(op.value, unit)}`;
  const arrow = op.delta > 0 ? "▲" : op.delta < 0 ? "▼" : "";
  const d = Math.abs(op.delta);
  if (op.mode === "relative") return `${arrow}${fmtNumber(100 * d)}%`;
  if (op.mode === "standardized") return `${arrow}${fmtNumber(d)} sd`;
  if (/^pct\b/.test(unit)) return `${arrow}${fmtNumber(d)}pp`;
  return `${arrow}${fmtValue(d, unit)}`;
}

// where each value goes: a link's targets on the right, everything else on the left (wrapped into columns when there
// are no links); entities hold their values in the order the update first names them
export function updatePlacement(ops, values) {
  const order = [];
  const seen = new Set();
  for (const op of ops) for (const id of op.values) if (!seen.has(id) && values[id]) { seen.add(id); order.push(id); }
  const links = ops.filter((o) => o.source && o.target);
  const sources = new Set(links.map((o) => o.source));
  const right = new Set(links.map((o) => o.target).filter((t) => !sources.has(t)));
  const lists = [order.filter((id) => !right.has(id)), order.filter((id) => right.has(id))].filter((l) => l.length);
  const cols = [];
  for (const [i, list] of lists.entries()) {
    // with no links, a long list wraps into columns of at most PER_COL
    const parts = links.length ? [list] : Array.from({ length: Math.ceil(list.length / PER_COL) }, (_, k) => list.slice(k * PER_COL, (k + 1) * PER_COL));
    for (const part of parts) cols.push({ ids: part, side: i ? "to" : "from" });
  }
  const chips = new Map();
  const groups = [];
  let H = 0;
  cols.forEach((c, ci) => {
    const x = ci * (CHIP_W + COL_GAP);
    const byEnt = new Map();
    for (const id of c.ids) {
      const e = values[id].entity_id;
      if (!byEnt.has(e)) byEnt.set(e, { id: e, name: values[id].entity, x, vals: [] });
      byEnt.get(e).vals.push(id);
    }
    let y = 0;
    for (const g of byEnt.values()) {
      g.y = y;
      y += HEAD_H;
      for (const id of g.vals) { chips.set(id, { id, x, y }); y += CHIP_H + GAP_Y; }
      y += GROUP_GAP - GAP_Y;
      groups.push(g);
    }
    c.h = y - GROUP_GAP;
    H = Math.max(H, c.h);
  });
  // columns sit centered on one another
  cols.forEach((c, ci) => {
    const dy = (H - c.h) / 2;
    for (const g of groups) if (g.x === ci * (CHIP_W + COL_GAP)) { g.y += dy; for (const id of g.vals) chips.get(id).y += dy; }
  });
  return { chips, groups, width: Math.max(0, cols.length * (CHIP_W + COL_GAP) - COL_GAP), height: H, columns: cols.length };
}

export class UpdateLayer {
  constructor(renderer, { onPick } = {}) {
    this.r = renderer;
    this.onPick = onPick;
    this.g = renderer.root.append("g").attr("class", "layer-gupdate");
    const defs = renderer.defs;
    for (const [id, cls] of [["gu-arr-up", "up"], ["gu-arr-down", "down"], ["gu-arr-ev", "ev"]]) {
      if (!defs.select(`#${id}`).empty()) continue;
      defs.append("marker").attr("id", id).attr("class", `gu-arrow ${cls}`).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
        .attr("markerWidth", 7).attr("markerHeight", 7).attr("orient", "auto-start-reverse")
        .append("path").attr("d", "M0,0 L10,5 L0,10 z");
    }
    this.shown = null;
    this.bounds = null;
    this.chips = new Map();
  }

  // draw the update's ops; returns its bounds in world units, for framing
  show(ops, values, key, title = "Graph update") {
    if (this.shown === key) return this.bounds;
    this.shown = key;
    const reduce = !!this.r.opts.reducedMotion;
    const P = updatePlacement(ops, values);
    const ox = 600 - P.width / 2;
    const oy = 440 - P.height / 2;
    this.g.selectAll("*").remove();
    const root = this.g.append("g").attr("class", "gu-root").attr("transform", `translate(${ox},${oy})`);
    root.append("text").attr("class", "gu-title").attr("x", 0).attr("y", -30).text(title);
    // links first, under the chips
    const edges = root.append("g").attr("class", "gu-edges");
    for (const op of ops) {
      if (!op.source || !op.target) continue;
      const a = P.chips.get(op.source);
      const b = P.chips.get(op.target);
      if (!a || !b) continue;
      const x1 = a.x + CHIP_W;
      const y1 = a.y + CHIP_H / 2;
      let d;
      let mx;
      let my;
      if (b.x > a.x) {
        const x2 = b.x;
        const y2 = b.y + CHIP_H / 2;
        const dx = Math.max(30, (x2 - x1) * 0.5);
        d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2 - 2},${y2}`;
        [mx, my] = [(x1 + x2) / 2, (y1 + y2) / 2];
      } else {
        // both ends in one column: an arc out of the right side and back
        const y2 = b.y + CHIP_H / 2;
        const xr = Math.max(x1, b.x + CHIP_W) + 48;
        d = `M${x1},${y1} C${xr},${y1} ${xr},${y2} ${b.x + CHIP_W + 2},${y2}`;
        [mx, my] = [x1 + 36, (y1 + y2) / 2];
      }
      const isNew = op.op === "add_interaction";
      const cls = isNew ? (op.polarity >= 0 ? "up" : "down") : "ev";
      const g = edges.append("g").attr("class", `gu-link ${isNew ? "new" : op.supports ? "supports" : "contradicts"}`)
        .attr("data-op", op.index).attr("data-s", op.source).attr("data-t", op.target);
      g.append("path").attr("class", `gu-edge ${cls}`).attr("d", d).attr("marker-end", `url(#gu-arr-${cls})`)
        .attr("stroke-width", isNew ? (1.4 + 3 * Math.min(1, Math.abs(op.effect ?? 0.3))).toFixed(2) : 2);
      const mark = isNew ? `new · ${op.label}` : op.supports ? `✓ ${op.label}` : `✗ ${op.label}`;
      const w = 14 + 6.4 * mark.length;
      g.append("rect").attr("class", "gu-mark-bg").attr("x", mx - w / 2).attr("y", my - 10).attr("width", w).attr("height", 20).attr("rx", 10);
      g.append("text").attr("class", "gu-mark").attr("x", mx).attr("y", my + 4).attr("text-anchor", "middle").text(mark);
      g.append("title").text(isNew
        ? `A new link, proposed for review: ${op.label} (${op.effect >= 0 ? "+" : ""}${op.effect} sd per sd)`
        : `Evidence ${op.supports ? "for" : "against"} this link (${op.label}), strength ${op.strength}`);
    }
    // entities' names and their values' chips
    const nodes = root.append("g").attr("class", "gu-nodes");
    const opsOf = new Map();
    for (const op of ops) if (op.op === "observe_value" || op.op === "change_value") {
      const id = op.values[0];
      if (!opsOf.has(id)) opsOf.set(id, []);
      opsOf.get(id).push(op);
    }
    this.chips = P.chips;
    for (const g of P.groups) {
      const grp = nodes.append("g").attr("class", "gu-ent");
      grp.append("text").attr("class", "gu-entname").attr("x", g.x + 2).attr("y", g.y + 12).text(g.name);
      for (const id of g.vals) {
        const ch = P.chips.get(id);
        const v = values[id];
        const own = ownOf(v.name, v.entity);
        const mine = opsOf.get(id) ?? [];
        const z = mine.reduce((t, o) => (Math.abs(o.z) > Math.abs(t) ? o.z : t), 0);
        const chip = grp.append("g").attr("class", `gu-chip ${mine.length ? dir(z) : "end"}`).attr("data-id", id)
          .attr("data-ops", [...ops.filter((o) => o.values.includes(id)).map((o) => o.index)].join(","))
          .attr("transform", `translate(${ch.x},${ch.y})`).attr("tabindex", 0).attr("role", "button");
        chip.append("rect").attr("class", "gu-box").attr("width", CHIP_W).attr("height", CHIP_H).attr("rx", 9);
        chip.append("rect").attr("class", "gu-bar").attr("width", 5).attr("height", CHIP_H).attr("rx", 2.5);
        // the move's size: a bar under the name, as long as the move is large (3 sd fills it)
        if (mine.length) chip.append("rect").attr("class", "gu-size").attr("x", 14).attr("y", CHIP_H - 7)
          .attr("width", Math.max(3, (CHIP_W - 28) * Math.min(1, Math.abs(z) / 3))).attr("height", 3).attr("rx", 1.5);
        chip.append("text").attr("class", "gu-name").attr("x", 14).attr("y", CHIP_H / 2 + 2).text(own.length > 22 ? `${own.slice(0, 21).trimEnd()}…` : own);
        const txt = mine.map((o) => opText(o, v)).join(" · ");
        chip.append("text").attr("class", `gu-num ${dir(z)}`).attr("x", CHIP_W - 10).attr("y", CHIP_H / 2 + 2).attr("text-anchor", "end")
          .text(mine.length ? txt : "");
        const now = fmtValue(v.mean, v.unit);
        chip.attr("aria-label", `${v.entity} ${own}: now ${now}${txt ? `; the update: ${txt}` : ""}`);
        chip.append("title").text(`${v.entity} · ${own}: now ${now}${mine.length ? `; ${mine.map((o) => `${o.op === "observe_value" ? "observed" : "moved"} ${opText(o, v)} (${o.z >= 0 ? "+" : ""}${o.z.toFixed(2)} sd)`).join("; ")}` : "; an end of a link"}`);
      }
    }
    nodes.selectAll("g.gu-chip")
      .on("click", (ev) => { ev.stopPropagation(); this.onPick?.(ev.currentTarget.dataset.id); })
      .on("keydown", (ev) => { if (ev.key === "Enter") this.onPick?.(ev.currentTarget.dataset.id); });
    this.origin = [ox, oy];
    document.body.classList.add("gupdate");
    if (reduce) this.g.classed("in", true);
    else requestAnimationFrame(() => this.g.classed("in", true));
    this.bounds = [[ox - 40, oy - 56], [ox + P.width + 40, oy + P.height + 30]];
    return this.bounds;
  }

  // light up these values (an op's ends) and the links between them; null lights everything
  focus(ids) {
    const on = ids ? new Set(ids) : null;
    this.g.selectAll("g.gu-chip").classed("dim", function () { return !!on && !on.has(this.dataset.id); })
      .classed("hot", function () { return !!on && on.has(this.dataset.id); });
    this.g.selectAll("g.gu-link").classed("dim", function () { return !!on && !(on.has(this.dataset.s) && on.has(this.dataset.t)); });
    if (!on) return this.bounds;
    const pts = [...on].map((id) => this.chips.get(id)).filter(Boolean);
    if (!pts.length) return this.bounds;
    const [ox, oy] = this.origin;
    return [[ox + Math.min(...pts.map((p) => p.x)) - 60, oy + Math.min(...pts.map((p) => p.y)) - 50],
            [ox + Math.max(...pts.map((p) => p.x)) + CHIP_W + 60, oy + Math.max(...pts.map((p) => p.y)) + CHIP_H + 40]];
  }

  hide() {
    this.shown = null;
    this.g.classed("in", false).selectAll("*").remove();
    document.body.classList.remove("gupdate");
  }

  get active() { return this.shown != null; }
}
