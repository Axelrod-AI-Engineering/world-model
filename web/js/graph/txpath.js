// The transmission path on the canvas (Oct 15, second pass: "too busy"). Only the values the path runs through, as
// chips, each under the name of its entity, laid out as the grid lays them out: the input on the left, one column
// per order, the outputs on the right. The world model's own furniture (entity boxes, superentities, badges, other
// values) is hidden while the path is shown; the canvas keeps its paper, grid, pan, and zoom. An output fed by
// another output moves to a column of its own (downstream outputs), and the link between them is dashed.
import { ownOf } from "../names.js";
import { colOf } from "../panels/paths.js";
import { signed } from "../util.js";

const CHIP_W = 240;
const CHIP_H = 38;
const GAP_Y = 8;          // between chips of one entity
const GROUP_GAP = 22;     // between entities in a column
const HEAD_H = 18;        // an entity's name above its chips
const COL_GAP = 120;
const TOP = 0;

const fmtSd = (v) => `${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(2)}`;

// where each value goes: its column (the grid's), its entity group, its place in the column
export function pathPlacement(grid) {
  const vals = grid.values ?? {};
  const outs = new Set(grid.outputs ?? []);
  const cols = grid.columns ?? ["input", "1", "2", "3", "output"];
  const fed = new Map();
  for (const e of grid.edges ?? []) {
    if (!fed.has(e.target)) fed.set(e.target, []);
    fed.get(e.target).push(e.source);
  }
  const colOfVal = (id) => {
    const v = vals[id];
    if (v.column === "output" && outs.has(id) && (fed.get(id) ?? []).some((s) => vals[s]?.column === "output" && outs.has(s))) return "downstream";
    return v.column;
  };
  const keys = [...cols, "downstream"];
  const pos = new Map();               // value id -> its y order, for the barycenter of later columns
  const columns = [];
  let x = 0;
  for (const key of keys) {
    const ids = Object.keys(vals).filter((id) => colOfVal(id) === key);
    if (!ids.length) continue;
    const bary = (id) => {
      const ps = (fed.get(id) ?? []).filter((s) => pos.has(s)).map((s) => pos.get(s));
      return ps.length ? ps.reduce((t, p) => t + p, 0) / ps.length : 1e6;
    };
    // entities, each holding its values, ordered by where what feeds them sits
    const groups = new Map();
    for (const id of ids) {
      const e = vals[id].entity_id;
      if (!groups.has(e)) groups.set(e, { id: e, name: vals[id].entity ?? e, vals: [] });
      groups.get(e).vals.push(id);
    }
    const gl = [...groups.values()];
    for (const g of gl) {
      g.vals.sort((a, b) => bary(a) - bary(b) || Math.abs(vals[b].peak) - Math.abs(vals[a].peak));
      g.key = Math.min(...g.vals.map(bary));
      g.big = Math.max(...g.vals.map((id) => Math.abs(vals[id].peak)));
    }
    gl.sort((a, b) => a.key - b.key || b.big - a.big);
    const meta = key === "downstream" ? { word: "Downstream outputs", cls: "out" } : colOf(key);
    const col = { key, label: meta.word, cls: meta.cls, x, groups: gl, h: 0 };
    let y = 0;
    let k = 0;
    for (const g of gl) {
      g.y = y;
      y += HEAD_H;
      g.chips = g.vals.map((id) => {
        const c = { id, x, y, col: key };
        y += CHIP_H + GAP_Y;
        pos.set(id, k++);
        return c;
      });
      y += GROUP_GAP - GAP_Y;
    }
    col.h = y - GROUP_GAP;
    columns.push(col);
    x += CHIP_W + COL_GAP;
  }
  // columns sit centered on one another
  const H = Math.max(0, ...columns.map((c) => c.h));
  const chips = new Map();
  for (const c of columns) {
    const dy = TOP + (H - c.h) / 2;
    for (const g of c.groups) {
      g.y += dy;
      for (const ch of g.chips) { ch.y += dy; chips.set(ch.id, ch); }
    }
  }
  return { columns, chips, width: Math.max(0, x - COL_GAP), height: H };
}

export class TxPathLayer {
  constructor(renderer, { onSelect } = {}) {
    this.r = renderer;
    this.onSelect = onSelect;
    this.g = renderer.root.append("g").attr("class", "layer-txpath");
    const defs = renderer.defs;
    for (const [id, cls] of [["tx-arr-up", "up"], ["tx-arr-down", "down"], ["tx-arr-out", "out"]]) {
      if (!defs.select(`#${id}`).empty()) continue;
      defs.append("marker").attr("id", id).attr("class", `tx-arrow ${cls}`).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
        .attr("markerWidth", 7).attr("markerHeight", 7).attr("orient", "auto-start-reverse")
        .append("path").attr("d", "M0,0 L10,5 L0,10 z");
    }
    this.shown = null;
  }

  // draw the path; returns its bounds in world units, for framing
  show(grid, key) {
    const reduce = !!this.r.opts.reducedMotion;
    if (this.shown === key) return this.bounds;
    this.shown = key;
    const vals = grid.values ?? {};
    const P = pathPlacement(grid);
    const ox = 600 - P.width / 2;
    const oy = 440 - P.height / 2;
    const outs = new Set(grid.outputs ?? []);
    const colIx = new Map(P.columns.map((c, i) => [c.key, i]));
    this.g.selectAll("*").remove();
    const root = this.g.append("g").attr("class", "tx-root").attr("transform", `translate(${ox},${oy})`);
    root.append("text").attr("class", "tx-title").attr("x", 0).attr("y", -44).text("Transmission path");
    // column headings, with arrows between them
    const heads = root.append("g").attr("class", "tx-heads");
    P.columns.forEach((c, i) => {
      heads.append("text").attr("class", `tx-col ${c.cls}`).attr("x", c.x + CHIP_W / 2).attr("y", -18).attr("text-anchor", "middle").text(c.label);
      if (i) heads.append("text").attr("class", "tx-colarrow").attr("x", c.x - COL_GAP / 2).attr("y", -18).attr("text-anchor", "middle").text("→");
    });
    // links first, under the chips
    const edges = root.append("g").attr("class", "tx-edges");
    for (const e of grid.edges ?? []) {
      const a = P.chips.get(e.source);
      const b = P.chips.get(e.target);
      if (!a || !b) continue;
      const chain = outs.has(e.source) && outs.has(e.target) && b.col === "downstream";
      const x1 = a.x + CHIP_W;
      const y1 = a.y + CHIP_H / 2;
      const x2 = b.x;
      const y2 = b.y + CHIP_H / 2;
      let d;
      if (x2 > x1) {
        const dx = Math.max(30, (x2 - x1) * 0.5);
        d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2 - 2},${y2}`;
      } else {
        // a link within one column (rare): an arc out of the right side and back
        const xr = Math.max(x1, b.x + CHIP_W) + 36;
        d = `M${x1},${y1} C${xr},${y1} ${xr},${y2} ${b.x + CHIP_W + 2},${y2}`;
      }
      const w = (1.2 + 3 * Math.min(1, Math.abs(e.effect) * (e.exists ?? 1))).toFixed(2);
      const cls = chain ? "out" : e.effect >= 0 ? "up" : "down";
      edges.append("path").attr("class", `tx-edge ${cls}${chain ? " chain" : ""}`).attr("d", d).attr("stroke-width", w)
        .attr("marker-end", `url(#tx-arr-${cls})`).attr("data-s", e.source).attr("data-t", e.target)
        .style("--d", `${reduce ? 0 : 120 + 160 * (colIx.get(b.col) ?? 0)}ms`)
        .append("title").text(`${chain ? "Output to output · " : ""}${e.label || "interaction"}: ${signed(e.effect)} sd per sd, `
          + `belief it exists ${Math.round(100 * (e.exists ?? 1))}%, about ${e.delay_days} days`);
    }
    // entities' names and their values' chips
    const nodes = root.append("g").attr("class", "tx-nodes");
    for (const c of P.columns) {
      for (const g of c.groups) {
        const grp = nodes.append("g").attr("class", "tx-ent").style("--d", `${reduce ? 0 : 160 * (colIx.get(c.key) ?? 0)}ms`);
        grp.append("text").attr("class", "tx-entname").attr("x", c.x + 2).attr("y", g.y + 12).text(g.name);
        for (const ch of g.chips) {
          const v = vals[ch.id];
          const own = ownOf(v.name, v.entity);
          const peak = v.peak ?? 0;
          const asked = outs.has(ch.id);
          const chip = grp.append("g").attr("class", `tx-chip o${c.key === "input" ? 0 : c.key === "output" || c.key === "downstream" ? "out" : Math.min(3, +c.key)}${asked ? " asked" : ""}`)
            .attr("transform", `translate(${ch.x},${ch.y})`).attr("data-id", ch.id).attr("tabindex", 0).attr("role", "button")
            .attr("aria-label", `${v.entity ?? ""} ${own}: ${fmtSd(peak)} sd at its peak`);
          chip.append("rect").attr("class", "tx-box").attr("width", CHIP_W).attr("height", CHIP_H).attr("rx", 9);
          chip.append("rect").attr("class", "tx-bar").attr("x", 0).attr("y", 0).attr("width", 5).attr("height", CHIP_H).attr("rx", 2.5);
          chip.append("text").attr("class", "tx-name").attr("x", 14).attr("y", CHIP_H / 2 + 4.5).text(own.length > 25 ? `${own.slice(0, 24)}…` : own);
          chip.append("text").attr("class", `tx-num ${peak > 0.005 ? "up" : peak < -0.005 ? "down" : ""}`).attr("x", CHIP_W - 10).attr("y", CHIP_H / 2 + 4.5)
            .attr("text-anchor", "end").text(c.key === "input" && !v.order ? "shock" : `${fmtSd(peak)} sd`);
          chip.append("title").text(`${v.entity ? `${v.entity} · ` : ""}${own}: ${signed(peak)} sd at its peak on day ${v.peak_day}; `
            + `${signed(v.effect ?? 0)} sd at the horizon${v.order ? `; first reached around day ${v.arrives_day}` : ""}${asked ? "; an output" : ""}`);
        }
      }
    }
    const hover = (id) => {
      this.g.selectAll("path.tx-edge").classed("hot", function () { return !!id && (this.dataset.s === id || this.dataset.t === id); })
        .classed("dim", function () { return !!id && this.dataset.s !== id && this.dataset.t !== id; });
    };
    nodes.selectAll("g.tx-chip")
      .on("mouseenter", function () { hover(this.dataset.id); })
      .on("mouseleave", () => hover(null))
      .on("click", (ev) => { ev.stopPropagation(); this.onSelect?.({ kind: "subentity", id: ev.currentTarget.dataset.id }); })
      .on("keydown", (ev) => { if (ev.key === "Enter") this.onSelect?.({ kind: "subentity", id: ev.currentTarget.dataset.id }); });
    document.body.classList.add("txpath");
    requestAnimationFrame(() => this.g.classed("in", true));
    this.bounds = [[ox - 40, oy - 70], [ox + P.width + 40, oy + P.height + 30]];
    return this.bounds;
  }

  hide() {
    this.shown = null;
    this.g.classed("in", false).selectAll("*").remove();
    document.body.classList.remove("txpath");
  }

  get active() { return this.shown != null; }
}
