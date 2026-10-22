// The transmission grid (Oct 11): only what is relevant to a shock, as a grid. Columns are the input (the shocked
// values), the first, second, and third (or later) order, and the output; rows are entities, so one entity's values
// line up across the orders they are reached at. Each value moves day by day (the median effect, with its 10–90%
// band), and each interaction lights once the effect has reached its source. Four ways of choosing what is relevant
// sit at the top (inference/paths.py): by order, the largest, toward the outputs, the strongest paths.
// It serves both processes: a staged event under review (learning) and a forecast (generation).
import { api } from "../api.js";
import { ownOf } from "../names.js";
import { on } from "../store.js";
import { errorText, esc, signed } from "../util.js";

// the columns come from the server: input, each order the shock reaches (as deep as its effects matter), output
const ORDINAL = ["", "First", "Second", "Third", "Fourth", "Fifth", "Sixth"];
export const colOf = (id) => (id === "input" ? { id, word: "Input", help: "The values the event or the question moves directly", cls: "o0" }
  : id === "output" ? { id, word: "Output", help: "What the question asks about, or, in a review, where the ripple ends", cls: "out" }
  : { id, word: `${ORDINAL[+id] ?? `${id}th`} order`, help: +id === 1 ? "Moved directly by an input" : `Through ${+id - 1} more interaction${+id > 2 ? "s" : ""}`,
      cls: `o${Math.min(3, +id)}` });
const DEFAULT_COLS = ["input", "1", "2", "3", "output"].map(colOf);
const PLAY_MS = 7000;

export function initPaths({ toast, onSelect, onShow, onHide, onIsolate }) {
  const pane = document.createElement("section");
  pane.id = "paths";
  pane.className = "manual paths hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Transmission grid");
  document.getElementById("stage").appendChild(pane);
  pane.innerHTML = `<header><div class="mtitle">Transmission</div><span class="small muted px-sub"></span><span class="spacer"></span>
      <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button>
      <button class="close" aria-label="Close (Esc)">✕</button></header>
    <div class="mbody">
      <div class="px-top">
        <div class="seg px-methods" role="tablist" aria-label="What is relevant"></div>
        <span class="spacer"></span>
        <button class="px-iso" type="button" aria-pressed="true" title="Show only these entities on the canvas, or the whole graph">Isolated on the canvas</button>
        <button class="px-play" type="button" aria-label="Play">▶</button>
        <input class="px-day" type="range" min="0" max="182" value="0" aria-label="Day">
        <span class="px-daylabel mono small">day 0</span>
      </div>
      <p class="small muted px-help"></p>
      <div class="px-wrap"><svg class="px-edges" aria-hidden="true"></svg><div class="px-grid"></div></div>
      <p class="small muted px-foot"></p>
    </div>`;
  const $ = (s) => pane.querySelector(s);
  pane.querySelector(".close").addEventListener("click", () => close());
  // the canvas shows only the grid's entities while the grid is open (main.js); this switches that off and on
  let isolating = true;
  const isoBtn = pane.querySelector(".px-iso");
  isoBtn.addEventListener("click", () => {
    isolating = !isolating;
    isoBtn.setAttribute("aria-pressed", String(isolating));
    isoBtn.textContent = isolating ? "Isolated on the canvas" : "Isolate on the canvas";
    if (grid?.values) onIsolate?.(isolating ? grid : null, layout);
  });

  let target = null;       // {kind, id, keep, conf, ripple}
  let method = "relevant";
  let grid = null;
  let day = 0;
  let playing = null;
  let ticket = 0;
  let scale = 1;
  let layout = null;      // the grid's rows and columns, for the canvas to mirror

  const isOpen = () => !pane.classList.contains("hidden");
  function close() { stop(); pane.classList.add("hidden"); onHide?.(); }

  function open(t) {
    target = t ?? target;
    if (!target) { toast("Nothing to show yet: open a review's ripple or a forecast first."); return; }
    pane.classList.remove("hidden");
    load();
  }

  async function load() {
    const my = ++ticket;
    stop();
    grid = null;
    loading();
    try {
      const g = target.kind === "proposal"
        ? await api.pathsProposal(target.id, method, target)
        : await api.pathsForecast(target.id, method);
      if (my !== ticket) return;
      grid = g;
      day = 0;
      render();
      play();
    } catch (err) {
      if (my !== ticket) return;
      $(".px-grid").innerHTML = `<p class="error small">${esc(errorText(err))}</p>`;
    }
  }

  // while the server runs the shock through a copy of the model: the grid's frame, with a spinner
  function loading() {
    $(".px-sub").textContent = target.kind === "proposal" ? "staging the event on a copy of the model…" : "reading the forecast…";
    $(".px-grid").innerHTML = `<div class="px-loading"><span class="spinner" aria-hidden="true"></span>
      <span>${target.kind === "proposal" ? "Running the event through a copy of the model" : "Reading the forecast's paths"}</span></div>
      <div class="px-table skeleton" style="grid-template-columns: repeat(${DEFAULT_COLS.length}, minmax(108px, 1fr))">${DEFAULT_COLS.map((c) => `<div class="px-colhead ${c.cls}">${esc(c.word)}</div>`).join("")}</div>`;
    $(".px-edges").innerHTML = "";
    paintMethods();
  }

  function paintMethods() {
    const ms = grid?.methods ?? ["relevant", "orders", "largest", "outputs", "strongest"].map((id) => ({ id, label: "" }));
    const word = { relevant: "Relevant", orders: "By order", largest: "Largest", outputs: "Toward the outputs", strongest: "Strongest paths" };
    $(".px-methods").innerHTML = ms.map((m) => `<button role="tab" data-m="${esc(m.id)}" aria-pressed="${m.id === method}"
      title="${esc(m.label)}">${esc(word[m.id] ?? m.id)}</button>`).join("");
    for (const b of pane.querySelectorAll("[data-m]")) {
      b.addEventListener("click", () => { if (b.dataset.m !== method) { method = b.dataset.m; load(); } });
    }
    $(".px-help").textContent = ms.find((m) => m.id === method)?.label ?? "";
  }

  function render() {
    paintMethods();
    $(".px-sub").textContent = grid.title ?? "";
    if (grid.empty || !Object.keys(grid.values).length) {
      $(".px-grid").innerHTML = `<p class="small muted">This ${target.kind === "proposal" ? "event moves no value with a ripple" : "question reaches no other value"} within the horizon.</p>`;
      $(".px-edges").innerHTML = "";
      $(".px-foot").textContent = "";
      return;
    }
    const vals = grid.values;
    const COLS = (grid.columns ?? DEFAULT_COLS.map((c) => c.id)).map(colOf);
    // rows: entities, in the order they are first reached, then by their largest effect
    const colIx = (c) => COLS.findIndex((x) => x.id === c);
    const rows = new Map();
    for (const [id, v] of Object.entries(vals)) {
      if (!rows.has(v.entity_id)) rows.set(v.entity_id, { id: v.entity_id, name: v.entity, first: 9, big: 0, cells: {} });
      const r = rows.get(v.entity_id);
      r.first = Math.min(r.first, colIx(v.column));
      r.big = Math.max(r.big, Math.abs(v.peak));
      (r.cells[v.column] ??= []).push(id);
    }
    // an output the chain carries on past is also read at the end (Oct 17: outputs sit on the end)
    for (const id of grid.echoes ?? []) {
      const r = rows.get(vals[id]?.entity_id);
      if (r) (r.cells.output ??= []).push(`echo:${id}`);
    }
    // then a few sweeps that move each row toward the rows it is joined to (the barycenter heuristic), so the
    // interactions cross as little as possible and each chain reads straight across
    let ordered = [...rows.values()].sort((a, b) => a.first - b.first || b.big - a.big);
    const entOf = (id) => vals[id]?.entity_id;
    const nbrs = new Map(ordered.map((r) => [r.id, []]));
    for (const e of grid.edges ?? []) {
      const a = entOf(e.source);
      const b = entOf(e.target);
      if (a && b && a !== b) { nbrs.get(a)?.push(b); nbrs.get(b)?.push(a); }
    }
    for (let sweep = 0; sweep < 6; sweep++) {
      const pos = new Map(ordered.map((r, i) => [r.id, i]));
      const bary = (r) => {
        const ns = nbrs.get(r.id) ?? [];
        return ns.length ? ns.reduce((t, n) => t + pos.get(n), 0) / ns.length : pos.get(r.id);
      };
      ordered = ordered.map((r) => ({ r, b: 0.5 * bary(r) + 0.5 * pos.get(r.id) })).sort((x, y) => x.b - y.b).map((x) => x.r);
    }
    scale = Math.max(0.05, ...Object.values(vals).flatMap((v) => [Math.abs(v.q10.reduce((m, x) => Math.max(m, Math.abs(x)), 0)), Math.abs(v.q90.reduce((m, x) => Math.max(m, Math.abs(x)), 0))]));
    const chip = (key) => {
      const echo = key.startsWith("echo:");
      const id = echo ? key.slice(5) : key;
      const v = vals[id];
      // an output the chain carries on past sits at its order (inference/paths._grid), marked as asked
      const asked = !echo && v.column !== "output" && v.order && (grid.outputs ?? []).includes(id);
      // its row names its entity, so the chip names only its own part; the tooltip names both
      const own = ownOf(v.name, v.entity);
      return `<button class="px-chip ${asked ? "asked" : ""}${echo ? " echo" : ""}" data-id="${esc(id)}" type="button" title="${esc(v.entity ? `${v.entity} · ${own}` : v.name)}: ${signed(v.peak)} sd at its peak on day ${v.peak_day}; ${signed(v.effect)} sd at the horizon${v.order ? `; first reached around day ${v.arrives_day}` : ""}${asked ? "; an output, which the grid follows further and also shows at the end" : ""}${echo ? "; an output, shown at the end as well as in its chain" : ""}">
        <span class="px-name">${(v.column === "output" || asked || echo) && v.order ? `<i class="px-ord o${Math.min(3, v.order)}" title="${esc(ORDINAL[v.order] ?? v.order)} order">${v.order}</i>` : ""}${esc(own)}</span>
        <span class="px-meter"><i class="band"></i><i class="bar"></i><i class="zero"></i></span>
        <span class="px-num mono"></span></button>`;
    };
    $(".px-grid").innerHTML = `<div class="px-table" style="grid-template-columns: minmax(84px, 120px) repeat(${COLS.length - 1}, minmax(108px, 1fr)) minmax(128px, 1.25fr); grid-template-rows: auto repeat(${ordered.length}, auto)">
      <div class="px-corner"></div>
      ${COLS.map((c) => `<div class="px-colhead ${c.cls}" title="${esc(c.help)}">${esc(c.word)}</div>`).join("")}
      ${ordered.map((r) => `<div class="px-ent" title="${esc(r.name)}">${esc(r.name)}</div>
        ${COLS.map((c) => `<div class="px-cell ${c.cls}">${(r.cells[c.id] ?? []).sort((a, b) => Math.abs(vals[b.replace(/^echo:/, "")].peak) - Math.abs(vals[a.replace(/^echo:/, "")].peak)).map(chip).join("")}</div>`).join("")}`).join("")}
    </div>`;
    for (const b of pane.querySelectorAll(".px-chip")) {
      b.addEventListener("click", () => onSelect?.({ kind: "subentity", id: b.dataset.id }));
      b.addEventListener("mouseenter", () => hover(b.dataset.id));
      b.addEventListener("mouseleave", () => hover(null));
    }
    const range = $(".px-day");
    range.max = String(grid.horizon);
    const hidden = grid.hidden ? ` ${grid.hidden} smaller value${grid.hidden === 1 ? " is" : "s are"} left out by this view.` : "";
    $(".px-foot").textContent = `Each bar is the median effect, in sd of that value, with its 10–90% band; all bars share one scale. `
      + `An interaction lights once the effect reaches its source.${hidden}`;
    // the canvas mirrors this layout when it isolates the grid's entities: an entity's column is where it is first reached
    layout = { rows: ordered.map((r) => ({ id: r.id, col: Math.max(0, r.first) })), cols: COLS.length };
    requestAnimationFrame(() => { drawEdges(); paint(); if (isolating) onShow?.(grid, layout); });
  }

  // the interactions, as curves from a value's right edge to the next value's left edge
  function drawEdges() {
    const wrap = $(".px-wrap");
    const svg = $(".px-edges");
    const box = wrap.getBoundingClientRect();
    // measured without the layer itself, or it would keep the width of a wider layout and the grid would scroll
    svg.setAttribute("width", "0");
    svg.setAttribute("height", "0");
    svg.setAttribute("width", String(wrap.scrollWidth));
    svg.setAttribute("height", String(wrap.scrollHeight));
    const at = (id) => pane.querySelector(`.px-chip[data-id="${CSS.escape(id)}"]`)?.getBoundingClientRect();
    const outs = new Set(grid.outputs ?? []);
    svg.innerHTML = (grid.edges ?? []).map((e, i) => {
      const a = at(e.source);
      const b = at(e.target);
      if (!a || !b) return "";
      const x1 = a.right - box.left + wrap.scrollLeft;
      const y1 = a.top + a.height / 2 - box.top + wrap.scrollTop;
      let x2 = b.left - box.left + wrap.scrollLeft;
      const y2 = b.top + b.height / 2 - box.top + wrap.scrollTop;
      const w = (1.2 + 3 * Math.min(1, Math.abs(e.effect) * e.exists)).toFixed(1);
      // an output that drives another output (Oct 15): an arc out of the right edge and back into the other output,
      // dashed, rather than a curve doubling back inside the output column
      const chain = outs.has(e.source) && outs.has(e.target) && x2 <= x1 + 8;
      let d;
      if (chain) {
        x2 = b.right - box.left + wrap.scrollLeft;
        const bulge = 26 + Math.min(40, Math.abs(y2 - y1) * 0.25);
        d = `M${x1} ${y1} C${Math.max(x1, x2) + bulge} ${y1} ${Math.max(x1, x2) + bulge} ${y2} ${x2} ${y2}`;
      } else {
        const dx = Math.max(24, (x2 - x1) * 0.5);
        d = `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
      }
      return `<path class="px-edge ${e.effect >= 0 ? "up" : "down"}${chain ? " chain" : ""}" data-i="${i}" data-s="${esc(e.source)}" data-t="${esc(e.target)}"
        d="${d}" stroke-width="${w}">
        <title>${chain ? "Output to output · " : ""}${esc(e.label || "interaction")}: ${signed(e.effect)} sd per sd, belief it exists ${Math.round(100 * e.exists)}%, about ${e.delay_days} days</title></path>`;
    }).join("");
  }

  // a value's series at a (fractional) day, by linear interpolation between the sampled days
  const at = (v, key, d) => {
    const ds = v.days;
    if (!ds.length) return 0;
    if (d <= ds[0]) return v[key][0];
    for (let i = 1; i < ds.length; i++) {
      if (d <= ds[i]) { const f = (d - ds[i - 1]) / Math.max(1, ds[i] - ds[i - 1]); return v[key][i - 1] + f * (v[key][i] - v[key][i - 1]); }
    }
    return v[key][ds.length - 1];
  };

  function paint() {
    if (!grid?.values) return;
    const pct = (x) => `${(50 + 50 * Math.max(-1, Math.min(1, x / scale))).toFixed(2)}%`;
    const live = new Set();
    for (const b of pane.querySelectorAll(".px-chip")) {
      const v = grid.values[b.dataset.id];
      const m = at(v, "q50", day);
      const lo = at(v, "q10", day);
      const hi = at(v, "q90", day);
      const bar = b.querySelector(".bar");
      const band = b.querySelector(".band");
      const l = Math.min(50, parseFloat(pct(m)));
      const r = Math.max(50, parseFloat(pct(m)));
      bar.style.left = `${l}%`;
      bar.style.width = `${r - l}%`;
      bar.classList.toggle("down", m < 0);
      band.style.left = pct(Math.min(lo, hi));
      band.style.width = `${Math.abs(parseFloat(pct(hi)) - parseFloat(pct(lo)))}%`;
      const moved = Math.abs(m) >= 0.02;
      b.classList.toggle("moved", moved);
      if (moved) live.add(b.dataset.id);
      b.querySelector(".px-num").textContent = moved ? `${m >= 0 ? "▲" : "▼"}${Math.abs(m).toFixed(2)}` : "·";
    }
    for (const p of pane.querySelectorAll(".px-edge")) {
      p.classList.toggle("live", live.has(p.dataset.s));
      p.classList.toggle("done", live.has(p.dataset.s) && live.has(p.dataset.t));
    }
    $(".px-day").value = String(Math.round(day));
    $(".px-daylabel").textContent = `day ${Math.round(day)} of ${grid.horizon}`;
  }

  function hover(id) {
    for (const p of pane.querySelectorAll(".px-edge")) {
      const on_ = id && (p.dataset.s === id || p.dataset.t === id);
      p.classList.toggle("hot", !!on_);
      p.classList.toggle("dim", !!id && !on_);
    }
  }

  function play() {
    stop();
    if (!grid?.horizon) return;
    if (day >= grid.horizon) day = 0;
    const t0 = performance.now() - (day / grid.horizon) * PLAY_MS;
    $(".px-play").textContent = "❚❚";
    $(".px-play").setAttribute("aria-label", "Pause");
    const step = (now) => {
      day = Math.min(grid.horizon, ((now - t0) / PLAY_MS) * grid.horizon);
      paint();
      if (day < grid.horizon && isOpen()) playing = requestAnimationFrame(step);
      else stop();
    };
    playing = requestAnimationFrame(step);
  }

  function stop() {
    if (playing) cancelAnimationFrame(playing);
    playing = null;
    $(".px-play").textContent = "▶";
    $(".px-play").setAttribute("aria-label", "Play");
  }

  $(".px-play").addEventListener("click", () => (playing ? stop() : play()));
  $(".px-day").addEventListener("input", (ev) => { stop(); day = +ev.target.value; paint(); });
  new ResizeObserver(() => { if (isOpen() && grid?.values) drawEdges(); }).observe(pane);
  $(".px-wrap").addEventListener("scroll", () => drawEdges());

  on("paths-open", (t) => open(t));
  return { open, close, isOpen, toggle: () => (isOpen() ? close() : open()), hasTarget: () => !!target };
}
