// Timeline (§13.6): a day axis with update runs drawn as bands, trace ticks colored by phase, diamonds for
// state versions, and a scrubber that replays to any trace seq or opens any version read-only.
/* global d3 */
import { api } from "../api.js";
import { backToLive, on, openVersion, store } from "../store.js";

const PHASE_COLOR = {
  update: "#B9ACD8", collect: "#B9ACD8", daily: "#A9C6A9", ingest: "#7C64C4", translate: "#7C64C4", refine: "#7C64C4",
  review: "#E0B092", parse: "#7C64C4", classify: "#A9BFD6", recall: "#A9BFD6", prefill: "#A9C6A9", analyze: "#A9C6A9",
  fold: "#7C64C4", generalize: "#A9BFD6", frontier: "#D9A9B8", abduce: "#A9BFD6", explain: "#E0B092",
  consolidate: "#3B5B7C", isolate: "#B07CC0", predict: "#B07CC0", couple: "#B07CC0", unify: "#B07CC0",
  read_out: "#E0B092", evaluate: "#7FB5A9", decide: "#7FB5A9", scenario: "#665E54", init: "#B9ACD8",
};

export function initTimeline() {
  const track = document.getElementById("timeline-track");
  const scrubber = document.getElementById("scrubber");
  const label = document.getElementById("scrub-label");
  const live = document.getElementById("btn-live");
  const svg = d3.select(track).append("svg");
  const bands = svg.append("g");
  const ticks = svg.append("g");
  const versions = svg.append("g");
  const axis = svg.append("g").attr("class", "axis");
  const scrubLine = svg.append("line").attr("class", "scrub").style("display", "none");
  let scrubbing = false;
  let timer = null;

  const timeOf = (ev) => new Date(ev.sim_time ?? ev.at);
  // the run's own traces: everything after the history replay
  const visibleTraces = () => {
    const start = store.traces.findIndex((e) => e.kind === "scenario.loaded");
    return start >= 0 ? store.traces.slice(start) : store.traces;
  };

  function scale() {
    const w = track.clientWidth || 600;
    const evs = visibleTraces();
    const t0 = evs.length ? timeOf(evs[0]) : new Date(store.status?.sim_time ?? Date.now());
    // DECISION: the axis spans at least 30 days, so a fresh session shows days rather than hours
    const t1raw = new Date(Math.max(+t0 + 30 * 86400000, ...(evs.length ? [+timeOf(evs[evs.length - 1])] : []),
                                    +new Date(store.status?.sim_time ?? t0), +new Date(store.status?.next_step_at ?? t0)));
    return d3.scaleUtc().domain([d3.utcDay.floor(t0), d3.utcDay.offset(d3.utcDay.ceil(t1raw), 2)]).range([4, w - 4]);
  }

  function render() {
    const h = track.clientHeight || 22;
    const x = scale();
    const evs0 = visibleTraces();
    const evs = store.phaseFilter ? evs0.filter((e) => e.phase === store.phaseFilter) : evs0;
    const step = Math.max(1, Math.ceil(evs.length / 1500));
    const data = evs.filter((_, i) => i % step === 0);
    // update runs as bands
    const runs = [...store.updates.values()].filter((u) => u.first && u.requestedBy !== "init");
    bands.selectAll("rect").data(runs, (u) => u.id).join("rect")
      .attr("class", (u) => `band${u.id === store.activeUpdate ? " cur" : ""}`)
      .attr("x", (u) => x(new Date(`${u.first}T00:00:00Z`)))
      .attr("width", (u) => Math.max(2, x(d3.utcDay.offset(new Date(`${u.last ?? u.first}T00:00:00Z`), 1)) - x(new Date(`${u.first}T00:00:00Z`))))
      .attr("y", 0).attr("height", 12).attr("rx", 2)
      .selectAll("title").data((u) => [u]).join("title").text((u) => `${u.id}: ${u.first} to ${u.last ?? u.first} (${u.state})`);
    ticks.selectAll("line").data(data, (d) => d.seq).join("line").attr("class", "tick")
      .attr("x1", (d) => x(timeOf(d))).attr("x2", (d) => x(timeOf(d))).attr("y1", 2).attr("y2", 10)
      .attr("stroke", (d) => PHASE_COLOR[d.phase] ?? "#999").attr("stroke-opacity", 0.7);
    const vs = store.versions.filter((v) => v.at);
    versions.selectAll("path").data(vs, (d) => `${d.version}:${d.seq}`).join("path").attr("class", "version")
      .attr("d", "M0 -3.5L3.5 0L0 3.5L-3.5 0Z").attr("transform", (d) => `translate(${x(new Date(d.at))},${h - 6})`)
      .on("click", (ev, d) => scrubTo(d.seq))
      .selectAll("title").data((d) => [d]).join("title").text((d) => `v${d.version} · ${d.cause} · ${String(d.at).slice(0, 10)}`);
    axis.attr("transform", `translate(0,${h - 1})`)
      .call(d3.axisBottom(x).tickValues(x.ticks(Math.max(2, Math.floor((track.clientWidth || 600) / 110)))
        .filter((t) => +t === +d3.utcDay.floor(t))).tickSize(3).tickFormat(d3.utcFormat("%b %-d")))
      .call((g) => g.select(".domain").remove())
      .selectAll("text").attr("dy", "0.9em");
    scrubber.min = String(evs0[0]?.seq ?? 0);
    scrubber.max = String(store.lastSeq);
    if (!scrubbing) scrubber.value = String(store.lastSeq);
    const at = store.traces.find((e) => e.seq >= +scrubber.value);
    if (scrubbing && at) scrubLine.style("display", null).attr("x1", x(timeOf(at))).attr("x2", x(timeOf(at))).attr("y1", 0).attr("y2", h);
    else scrubLine.style("display", "none");
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

  scrubber.addEventListener("input", () => scrubTo(+scrubber.value));
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
          store.versions.push({ version: ev.payload.version, seq: ev.seq, cause: ev.payload.cause, at: ev.sim_time });
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
