// Timeline (§13.6): a track of trace ticks colored by phase, diamonds for state versions, and a scrubber
// that replays to any trace seq or opens any version read-only.
/* global d3 */
import { api } from "../api.js";
import { backToLive, on, openVersion, store } from "../store.js";

const PHASE_COLOR = {
  ingest: "#7C64C4", translate: "#7C64C4", refine: "#7C64C4", review: "#E0B092", parse: "#7C64C4", classify: "#A9BFD6",
  recall: "#A9BFD6", prefill: "#A9C6A9", analyze: "#A9C6A9", fold: "#7C64C4", generalize: "#A9BFD6", frontier: "#D9A9B8",
  abduce: "#A9BFD6", explain: "#E0B092", consolidate: "#3B5B7C", isolate: "#B07CC0", predict: "#B07CC0", couple: "#B07CC0",
  unify: "#B07CC0", read_out: "#E0B092", evaluate: "#7FB5A9", decide: "#7FB5A9", scenario: "#665E54", init: "#B9ACD8",
};

export function initTimeline() {
  const track = document.getElementById("timeline-track");
  const scrubber = document.getElementById("scrubber");
  const label = document.getElementById("scrub-label");
  const live = document.getElementById("btn-live");
  const svg = d3.select(track).append("svg");
  const ticks = svg.append("g");
  const versions = svg.append("g");
  const scrubLine = svg.append("line").attr("class", "scrub").style("display", "none");
  let scrubbing = false;
  let timer = null;

  function x() {
    const w = track.clientWidth || 600;
    const first = store.traces[0]?.seq ?? 0;
    const last = Math.max(store.lastSeq, first + 1);
    return d3.scaleLinear().domain([first, last]).range([6, w - 6]);
  }

  function render() {
    const h = track.clientHeight || 60;
    const sx = x();
    const evs = store.phaseFilter ? store.traces.filter((e) => e.phase === store.phaseFilter) : store.traces;
    // thin to at most ~1500 ticks
    const step = Math.max(1, Math.ceil(evs.length / 1500));
    const data = evs.filter((_, i) => i % step === 0);
    ticks.selectAll("line").data(data, (d) => d.seq).join("line").attr("class", "tick")
      .attr("x1", (d) => sx(d.seq)).attr("x2", (d) => sx(d.seq)).attr("y1", 6).attr("y2", h * 0.55)
      .attr("stroke", (d) => PHASE_COLOR[d.phase] ?? "#999");
    const vs = store.versions;
    versions.selectAll("path").data(vs, (d) => `${d.version}:${d.seq}`).join("path").attr("class", "version")
      .attr("d", "M0 -5L5 0L0 5L-5 0Z").attr("transform", (d) => `translate(${sx(d.seq)},${h * 0.75})`)
      .on("click", (ev, d) => openVersion(d.version))
      .selectAll("title").data((d) => [d]).join("title").text((d) => `v${d.version} · ${d.cause}`);
    scrubber.min = String(store.traces[0]?.seq ?? 0);
    scrubber.max = String(store.lastSeq);
    if (!scrubbing) scrubber.value = String(store.lastSeq);
    if (scrubbing) scrubLine.style("display", null).attr("x1", sx(+scrubber.value)).attr("x2", sx(+scrubber.value))
      .attr("y1", 0).attr("y2", h);
    else scrubLine.style("display", "none");
  }

  const later = () => { if (!timer) timer = setTimeout(() => { timer = null; render(); }, 250); };

  async function scrubTo(seq) {
    scrubbing = seq < store.lastSeq;
    scrubber.value = String(seq);
    const v = [...store.versions].reverse().find((d) => d.seq <= seq);
    label.textContent = scrubbing ? `seq ${seq}${v ? ` · v${v.version}` : ""}` : "live";
    live.classList.toggle("hidden", !scrubbing);
    render();
    if (!scrubbing) { backToLive(); return; }
    if (v) await openVersion(v.version);
  }

  scrubber.addEventListener("input", () => scrubTo(+scrubber.value));
  live.addEventListener("click", () => scrubTo(store.lastSeq));
  on("phase", later);
  on("versions", later);
  on("phase-filter", render);
  on("readonly", (v) => {
    if (v == null) { scrubbing = false; label.textContent = "live"; live.classList.add("hidden"); render(); }
  });
  window.addEventListener("resize", later);

  // the version list and trace history before this page loaded
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
