// Timeline (§13.6; redrawn Oct 8). One row per kind of thing, one mark per day: a bar for the articles learned and
// the questions asked (learning in violet, inference in orchid), a dot for each day that committed what learning or
// a review changed (bigger for more; the routine daily commits that every day makes are left out), and a
// playhead for the version on screen. Drag to pan, scroll (or pinch) to zoom, double-click to see everything.
// Hover a day for what happened; click it to open its last version read-only. "Back to live" returns.
// DECISION: the old axis drew a tick per trace event and a diamond per version, hundreds of marks on one line;
// aggregating by day keeps the same information readable at any zoom.
// DECISION (Oct 9): three labelled lanes, so it reads at a glance: news (what was read or asked), checks (each test
// of a fuzzy end, a co-movement, or a group: filled when it passed, hollow when it failed), and commits (a dot per
// day that committed, ringed when a person reviewed something that day).
/* global d3 */
import { api } from "../api.js";
import { backToLive, on, openVersion, store } from "../store.js";

const DAY = 86400000;
// the commits worth a mark: what learning, a review, or a structural edit wrote (not each day's open, record, close)
const MEANINGFUL = new Set(["learn.working", "learn.long_term", "structural", "review"]);
const dayKey = (t) => d3.utcDay.floor(t).getTime();
const CHECKS = { "refine.weighed": "fuzzy end", "frontier.verified": "co-movement", "abduce.support": "group" };
const GUTTER = 50;                                         // the lanes' labels

export function initTimeline() {
  const track = document.getElementById("timeline-track");
  const scrubber = document.getElementById("scrubber");
  const label = document.getElementById("scrub-label");
  const live = document.getElementById("btn-live");
  scrubber.hidden = true;                                   // kept for its value; the playhead replaces it
  const tip = document.createElement("div");
  tip.className = "tl-tip hidden";
  track.parentElement.appendChild(tip);
  const svg = d3.select(track).append("svg");
  const bg = svg.append("rect").attr("class", "tl-bg");
  const clip = svg.append("defs").append("clipPath").attr("id", "tl-clip").append("rect");
  const plot = svg.append("g").attr("clip-path", "url(#tl-clip)");
  const bands = plot.append("g");
  const bars = plot.append("g");
  const ticks = plot.append("g");
  const dots = plot.append("g");
  const lanes = svg.append("g").attr("class", "tl-lanes");
  const hover = plot.append("rect").attr("class", "tl-hover").style("display", "none");
  const head = plot.append("g").attr("class", "tl-head");
  head.append("line");
  head.append("circle").attr("r", 4.5);
  const axis = svg.append("g").attr("class", "axis");
  let base = null;            // the full scale (everything), before zoom
  let x = null;               // the zoomed scale
  let transform = d3.zoomIdentity;
  let scrubbing = false;
  let timer = null;
  let dragged = false;
  let userMoved = false;

  const timeOf = (ev) => new Date(ev.sim_time ?? ev.at);
  const visibleTraces = () => {
    const start = store.traces.findLastIndex((e) => e.kind === "scenario.loaded");
    return start >= 0 ? store.traces.slice(start) : store.traces;
  };
  const W = () => track.clientWidth || 600;
  const H = () => track.clientHeight || 30;

  function fullScale() {
    const evs = visibleTraces();
    const t0 = evs.length ? timeOf(evs[0]) : new Date(store.status?.sim_time ?? Date.now());
    const t1 = new Date(Math.max(+t0 + 30 * DAY, ...(evs.length ? [+timeOf(evs[evs.length - 1])] : []),
                                 +new Date(store.status?.sim_time ?? t0)));
    return d3.scaleUtc().domain([d3.utcDay.floor(t0), d3.utcDay.offset(d3.utcDay.ceil(t1), 1)]).range([GUTTER, W() - 6]);
  }

  // what happened each day: trace counts (learning, inference) and the versions committed
  function days() {
    // DECISION (Oct 9): the pipeline's phase filter no longer empties the strip (news and questions are not phases)
    const evs = visibleTraces();
    const m = new Map();
    const get = (k) => {
      if (!m.has(k)) m.set(k, { t: new Date(k), learn: 0, perf: 0, versions: [], news: [], checks: [], reviews: 0 });
      return m.get(k);
    };
    for (const e of evs) {
      if (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope ?? "")) {
        const d = get(dayKey(timeOf(e)));
        d.learn += 1;
        if (e.payload?.headline && d.news.length < 3) d.news.push(e.payload.headline);
      } else if (e.kind === "thesis.posed") {
        get(dayKey(timeOf(e))).perf += 1;
      } else if (CHECKS[e.kind] && !(e.scope ?? "").startsWith("staged")) {
        get(dayKey(timeOf(e))).checks.push({ what: CHECKS[e.kind], passed: e.kind !== "frontier.verified" || e.payload?.passed !== false });
      } else if (e.kind === "review.decided" && e.payload?.by && e.payload.by !== "policy") {
        get(dayKey(timeOf(e))).reviews += 1;
      }
    }
    // versions without a process (older traces) count as meaningful unless their cause names a day step
    const meaningful = (v) => (v.process ? MEANINGFUL.has(v.process) : !/^(predict|record|distill|close):/.test(v.cause ?? ""));
    for (const v of store.versions) if (v.at && meaningful(v)) get(dayKey(new Date(v.at))).versions.push(v);
    return [...m.values()].sort((a, b) => a.t - b.t);
  }

  function setupZoom() {
    const zoom = d3.zoom().scaleExtent([1, 80]).translateExtent([[0, 0], [W(), H()]]).extent([[0, 0], [W(), H()]])
      .filter((ev) => !ev.button && ev.type !== "dblclick")
      .on("start", () => { dragged = false; })
      .on("zoom", (ev) => {
        if (ev.sourceEvent?.type === "mousemove" || ev.sourceEvent?.type === "touchmove") dragged = true;
        if (ev.sourceEvent) userMoved = true;
        transform = ev.transform;
        render();
      });
    svg.call(zoom).on("dblclick.zoom", null);
    svg.on("dblclick", () => { userMoved = true; svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); });
    return zoom;
  }
  let zoom = null;

  function render() {
    const w = W();
    const h = H();
    svg.attr("viewBox", `0 0 ${w} ${h}`);
    bg.attr("x", 0.5).attr("y", 0.5).attr("width", w - 1).attr("height", h - 11).attr("rx", 7);
    clip.attr("x", 1).attr("y", 0).attr("width", w - 2).attr("height", h);
    base = fullScale();
    if (!zoom) zoom = setupZoom();
    zoom.translateExtent([[0, 0], [w, h]]).extent([[0, 0], [w, h]]);
    // until you pan or zoom, the view follows the latest 60 days (drag right to see earlier ones)
    if (!userMoved) {
      const [d0, d1] = base.domain();
      const k = Math.max(1, (d1 - d0) / DAY / 60);
      const want = d3.zoomIdentity.translate((w - 6) * (1 - k), 0).scale(k);     // the right end stays put
      if (Math.abs(want.k - transform.k) > 1e-6 || Math.abs(want.x - transform.x) > 0.5) {
        transform = want;
        svg.call(zoom.transform, want);
        return;
      }
    }
    x = transform.rescaleX(base);
    // only days inside the run's span (a rewind leaves later versions in the list; they are not this run's)
    const [b0, b1] = base.domain();
    const ds = days().filter((d) => d.t >= b0 && d.t < b1);
    const dayW = Math.max(1, x(new Date(+x.domain()[0] + DAY)) - x(x.domain()[0]));
    const top = 2;
    const barH = 8;
    const checkY = top + barH + 5;
    const dotY = checkY + 9;
    const peak = Math.max(1, ...ds.map((d) => d.learn + d.perf));
    const hgt = (n) => (n ? 1.5 + (barH - 1.5) * Math.log1p(n) / Math.log1p(peak) : 0);
    // the update run in progress, if any: a faint band (finished runs leave no band, so the strip stays quiet)
    const runs = [...store.updates.values()].filter((u) => u.first && u.requestedBy !== "init" && u.id === store.activeUpdate
      && !["done", "failed", "cancelled"].includes(String(u.state)));
    bands.selectAll("rect").data(runs, (u) => u.id).join("rect")
      .attr("class", (u) => `band${u.id === store.activeUpdate ? " cur" : ""}`)
      .attr("x", (u) => x(new Date(`${u.first}T00:00:00Z`)))
      .attr("width", (u) => Math.max(2, x(d3.utcDay.offset(new Date(`${u.first}T00:00:00Z`), 1 + daysBetween(u.first, u.last ?? u.first))) - x(new Date(`${u.first}T00:00:00Z`))))
      .attr("y", 1).attr("height", h - 12).attr("rx", 4);
    // activity: one soft bar per day
    const bw = Math.max(1, Math.min(dayW - 1, 10));
    bars.selectAll("rect").data(ds, (d) => +d.t).join("rect")
      .attr("class", (d) => `tl-bar${d.perf > d.learn ? " perf" : ""}`)
      .attr("x", (d) => x(d.t) + (dayW - bw) / 2).attr("width", bw)
      .attr("y", (d) => top + barH - hgt(d.learn + d.perf)).attr("height", (d) => hgt(d.learn + d.perf)).attr("rx", Math.min(2, bw / 2));
    // checks: one tick per day, filled if every check passed, hollow if any failed
    const cd = ds.filter((d) => d.checks.length);
    ticks.selectAll("rect").data(cd, (d) => +d.t).join("rect")
      .attr("class", (d) => `tl-check${d.checks.every((c) => c.passed) ? "" : " failed"}`)
      .attr("x", (d) => x(d.t) + dayW / 2 - 2).attr("width", 4).attr("y", checkY - 3).attr("height", 6).attr("rx", 1)
      .attr("transform", (d) => `rotate(45 ${x(d.t) + dayW / 2} ${checkY})`);
    // versions: one dot per day that committed any, ringed when a person reviewed something that day
    const vd = ds.filter((d) => d.versions.length);
    dots.selectAll("circle").data(vd, (d) => +d.t).join("circle")
      .attr("class", (d) => `tl-dot${d.reviews ? " reviewed" : ""}`).attr("cx", (d) => x(d.t) + dayW / 2).attr("cy", dotY)
      .attr("r", (d) => Math.min(4.2, 1.8 + Math.sqrt(d.versions.length) * 0.7));
    // the lanes' labels, in the gutter
    lanes.selectAll("text").data([["news", top + barH / 2 + 1], ["checks", checkY + 1], ["commits", dotY + 1]]).join("text")
      .attr("x", 6).attr("y", (l) => l[1]).text((l) => l[0]);
    // the playhead: the version on screen (live: now)
    const cur = scrubbing ? store.traces.find((e) => e.seq >= +scrubber.value) : null;
    const lastDay = ds.length ? +ds[ds.length - 1].t + DAY / 2 : 0;
    const tHead = cur ? timeOf(cur) : new Date(Math.max(+new Date(store.status?.sim_time ?? 0), lastDay) || Date.now());
    const hx = x(tHead);
    head.classed("live", !scrubbing).attr("transform", `translate(${hx},0)`);
    head.select("line").attr("y1", 1).attr("y2", h - 11);
    head.select("circle").attr("cy", dotY);
    // the axis: dates only, spaced to fit
    axis.attr("transform", `translate(0,${h - 10})`)
      .call(d3.axisBottom(x).ticks(Math.max(2, Math.floor(w / 90))).tickSize(0).tickPadding(1)
        .tickFormat((t) => (d3.utcDay.floor(t) < t ? "" : d3.utcFormat(+d3.utcMonth.floor(t) === +t ? "%b" : "%b %-d")(t))))
      .call((g) => g.select(".domain").remove());
    scrubber.min = String(visibleTraces()[0]?.seq ?? 0);
    scrubber.max = String(store.lastSeq);
    if (!scrubbing) scrubber.value = String(store.lastSeq);
    renderDays = ds;
  }
  let renderDays = [];

  function daysBetween(a, b) {
    return Math.round((new Date(`${b}T00:00:00Z`) - new Date(`${a}T00:00:00Z`)) / DAY);
  }

  const dayAt = (px) => {
    if (!x) return null;
    const k = dayKey(x.invert(px));
    return renderDays.find((d) => +d.t === k) ?? { t: new Date(k), learn: 0, perf: 0, versions: [], news: [], checks: [], reviews: 0 };
  };

  svg.on("mousemove", (ev) => {
    const [px] = d3.pointer(ev, svg.node());
    const d = dayAt(px);
    if (!d) return;
    const dayW = Math.max(1, x(new Date(+d.t + DAY)) - x(d.t));
    hover.style("display", null).attr("x", x(d.t)).attr("width", dayW).attr("y", 1).attr("height", H() - 12);
    const vs = d.versions;
    const byWhat = {};
    for (const c of d.checks ?? []) {
      byWhat[c.what] = byWhat[c.what] ?? { n: 0, failed: 0 };
      byWhat[c.what].n += 1;
      if (!c.passed) byWhat[c.what].failed += 1;
    }
    const checkLine = Object.entries(byWhat).map(([w, c]) => `${c.n} ${w} check${c.n > 1 ? "s" : ""}${c.failed ? ` (${c.failed} failed)` : ""}`).join(", ");
    tip.innerHTML = `<b>${d3.utcFormat("%a %-d %b %Y")(d.t)}</b>${vs.length
      ? ` · ${vs.length === 1 ? `v${vs[0].version}` : `v${vs[0].version}–v${vs[vs.length - 1].version}`} (${vs.length} commit${vs.length > 1 ? "s" : ""})`
      : " · no commits"}${d.news.map((n) => `<div class="tl-news">${escapeHtml(n)}</div>`).join("")}
      ${checkLine ? `<div class="tl-news">Checks: ${escapeHtml(checkLine)}</div>` : ""}
      ${d.reviews ? `<div class="tl-news">${d.reviews} reviewed by a person</div>` : ""}
      <div class="tl-hint">${vs.length ? "click to open this day read-only" : "nothing committed this day; click to see the model as it stood"}</div>`;
    tip.classList.remove("hidden");
    const r = track.getBoundingClientRect();
    tip.style.left = `${Math.min(Math.max(0, px - 80), r.width - 230)}px`;
  });
  svg.on("mouseleave", () => { hover.style("display", "none"); tip.classList.add("hidden"); });
  svg.on("click", (ev) => {
    if (dragged) { dragged = false; return; }
    const [px] = d3.pointer(ev, svg.node());
    const d = dayAt(px);
    if (!d) return;
    // the last version committed on or before the end of that day
    const end = +d.t + DAY;
    const v = [...store.versions].reverse().find((vv) => vv.at && +new Date(vv.at) < end);
    // a quiet day opens the model as it stood then: the last commit before it
    if (v) scrubTo(v.seq);
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  }

  const later = () => { if (!timer) timer = setTimeout(() => { timer = null; render(); }, 300); };

  async function scrubTo(seq) {
    scrubbing = seq < store.lastSeq;
    scrubber.value = String(seq);
    const v = [...store.versions].reverse().find((d) => d.seq <= seq);
    const at = store.traces.find((e) => e.seq >= seq);
    label.textContent = scrubbing ? `${at ? String(at.sim_time).slice(0, 10) : `seq ${seq}`}${v ? ` · v${v.version}` : ""}` : "live";
    live.classList.toggle("hidden", !scrubbing);
    render();
    if (!scrubbing) { backToLive(); return; }
    if (v) await openVersion(v.version);
  }

  live.addEventListener("click", () => scrubTo(store.lastSeq));
  on("phase", later);
  on("versions", later);
  on("update", later);
  on("phase-filter", render);
  on("readonly", (v) => {
    if (v == null) { scrubbing = false; label.textContent = "live"; live.classList.add("hidden"); render(); }
  });
  window.addEventListener("resize", later);

  // the version list before this page loaded
  async function backfill() {
    try {
      const evs = await api.trace(Math.max(0, store.lastSeq - 4000));
      for (const ev of evs) {
        if (ev.kind === "state.version" && !store.versions.some((v) => v.seq === ev.seq)) {
          store.versions.push({ version: ev.payload.version, seq: ev.seq, cause: ev.payload.cause, process: ev.payload.process, at: ev.sim_time });
        }
      }
      store.versions.sort((a, b) => a.seq - b.seq);
      render();
    } catch { /* ignore */ }
  }

  return {
    render, backfill,
    stepBack() {
      const cur = +scrubber.value;
      const prev = [...store.versions].reverse().find((d) => d.seq < cur);
      return scrubTo(prev ? prev.seq : (store.traces[0]?.seq ?? 0));
    },
    stepForward() {
      const cur = +scrubber.value;
      const next = store.versions.find((d) => d.seq > cur);
      return scrubTo(next ? next.seq : store.lastSeq);
    },
    scrubTo,
  };
}
