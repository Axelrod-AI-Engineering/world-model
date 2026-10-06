// Client model: the GraphView plus incremental trace application (§13.7). The store only applies
// what the server sends; it never computes model results.
import { api } from "./api.js";

const listeners = new Map();

export function on(topic, fn) {
  if (!listeners.has(topic)) listeners.set(topic, new Set());
  listeners.get(topic).add(fn);
  return () => listeners.get(topic).delete(fn);
}

export function emit(topic, payload) {
  for (const fn of listeners.get(topic) ?? []) {
    try { fn(payload); } catch (err) { console.error(`listener for ${topic}`, err); }
  }
}

export const PHASE_GROUPS = {
  learn: ["update", "collect", "ingest", "translate", "refine", "review", "daily", "parse", "classify", "recall",
          "prefill", "analyze", "fold", "generalize", "frontier", "abduce", "explain", "consolidate"],
  perf: ["isolate", "predict", "couple", "unify", "read_out"],
};

export const store = {
  layout: null,            // figure1_layout.yaml
  graph: null,             // live GraphView
  view: null,              // the GraphView on screen (live, or a read-only version)
  readOnlyVersion: null,
  status: null,
  scenarios: [],
  config: null,
  traces: [],              // trace events received, in seq order
  lastSeq: 0,
  versions: [],            // {version, seq, cause, at}
  marketEvents: new Map(), // id -> card state
  updates: new Map(),      // update run id -> {id, state, first, last, current, days, done, waiting, report, ...}
  activeUpdate: null,
  days: [],                // {date, seq} as update runs reach each day, for the timeline's day axis
  proposals: [],           // pending ProposalViews
  forecasts: [],
  forecast: null,          // ForecastView on screen
  compare: null,           // ForecastView overlaid
  selection: null,         // {kind, id}
  caption: { text: "", step: null, hyp: false },
  liveOps: new Map(),      // "<event id>:<op index>" -> {event_id, op, ends: {end: {level, ref, candidates}}, hyp}
  recentlyCreated: new Set(),
  highlight: null,         // {entities:Set, links:Set, hulls:Set, hot:Set} for dimming
  phaseFilter: null,
  settings: { speed: 1, reducedMotion: false, figure1LinksOnly: false, groupByCategory: false, layout: "figure1",
              draw: false, showCandidates: false },
};

export function nodeIndex() {
  const g = store.view;
  const ents = new Map((g?.entities ?? []).map((e) => [e.id, e]));
  const subs = new Map((g?.subentities ?? []).map((s) => [s.id, s]));
  const links = new Map((g?.links ?? []).map((l) => [l.id, l]));
  const hulls = new Map((g?.hulls ?? []).map((h) => [h.id, h]));
  return { ents, subs, links, hulls };
}

export function entityOf(ref) {
  if (!ref) return null;
  const i = ref.indexOf(".");
  return i > 0 ? ref.slice(0, i) : ref;
}

// -- graph refresh ------------------------------------------------------------------------------
let refreshTimer = null;
let refreshing = false;
export function scheduleRefresh(delay = 150) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refreshGraph, delay);
}

export async function refreshGraph() {
  if (refreshing) { scheduleRefresh(200); return; }
  refreshing = true;
  try {
    const [g, pending] = await Promise.all([api.state(), api.proposals("pending")]);
    store.graph = g;
    store.proposals = pending;
    if (store.readOnlyVersion == null) {
      store.view = g;
      emit("graph", g);
    }
    emit("proposals", pending);
  } catch (err) {
    console.warn("refresh failed", err);
  } finally {
    refreshing = false;
  }
}

export async function openVersion(version) {
  if (version == null || (store.graph && version === store.graph.version)) return backToLive();
  const g = await api.state(version);
  store.readOnlyVersion = version;
  store.view = g;
  emit("graph", g);
  emit("readonly", version);
}

export function backToLive() {
  store.readOnlyVersion = null;
  store.view = store.graph;
  emit("graph", store.graph);
  emit("readonly", null);
}

// -- trace application --------------------------------------------------------------------------
export const LEVEL_NAMES = ["generalization", "entity", "subentity"];

function dropLiveOps(eventId) {
  if (!eventId) return;
  let changed = false;
  for (const [k, o] of store.liveOps) {
    if (o.event_id === eventId) { store.liveOps.delete(k); changed = true; }
  }
  if (changed) emit("fuzzy", null);
}

function marketCard(id) {
  if (!store.marketEvents.has(id)) store.marketEvents.set(id, { id, status: "queued", headline: id });
  return store.marketEvents.get(id);
}

function updateRun(id) {
  if (!store.updates.has(id)) store.updates.set(id, { id, state: "collecting", collected: {}, done: 0, days: 0 });
  return store.updates.get(id);
}

export function applyTrace(ev) {
  if (ev.seq <= store.lastSeq) return false;
  store.lastSeq = ev.seq;
  store.traces.push(ev);
  if (store.traces.length > 60000) store.traces.splice(0, store.traces.length - 60000);
  const p = ev.payload ?? {};
  switch (ev.kind) {
    case "scenario.caption":
      store.caption = { text: p.text, step: p.step_index, hyp: false, seq: ev.seq };
      emit("caption", store.caption);
      break;
    case "scenario.loaded":
      store.marketEvents.clear();
      store.updates.clear();
      store.activeUpdate = null;
      store.days = [];
      store.liveOps.clear();
      store.recentlyCreated.clear();
      store.forecast = null;
      store.compare = null;
      emit("inbox", null);
      emit("update", null);
      emit("forecast", null);
      scheduleRefresh(50);
      break;
    // -- update runs (§7.8) --------------------------------------------------------------------
    case "update.started": {
      const u = updateRun(p.update_id);
      Object.assign(u, { state: "collecting", first: p.first_date, last: p.last_date, until: p.until,
                         requestedBy: p.requested_by, firstDay: p.first_day, lastDay: p.last_day,
                         days: Math.max(0, (p.last_day ?? 0) - (p.first_day ?? 0) + 1),
                         done: 0, current: null, waiting: null, report: null, startedSeq: ev.seq });
      store.activeUpdate = p.update_id;
      emit("update", u);
      break;
    }
    case "scrape.result": {
      const u = updateRun(p.update_id);
      u.collected[p.source] = p.new;
      u.dropped = (u.dropped ?? 0) + (p.duplicates_dropped ?? 0);
      emit("update", u);
      break;
    }
    case "update.collected": {
      const u = updateRun(p.update_id);
      u.state = "running";
      for (const [date, items] of Object.entries(p.by_day ?? {})) {
        for (const it of items) {
          const c = marketCard(it.id);
          Object.assign(c, { headline: it.headline, channel: it.channel, update_id: p.update_id, day: date });
          if (!c.status || c.status === "received") c.status = "queued";
        }
      }
      u.collected = p.collected ?? u.collected;
      u.dropped = p.duplicates_dropped ?? u.dropped;
      emit("inbox", null);
      emit("update", u);
      break;
    }
    case "update.day": {
      const u = updateRun(p.update_id);
      u.state = "running";
      u.current = p.date;
      if (u.firstDay == null) u.firstDay = p.day;
      u.done = Math.max(0, (p.day ?? 0) - u.firstDay);   // days finished before this one
      u.waiting = null;
      if (!store.days.length || store.days[store.days.length - 1].date !== p.date) {
        store.days.push({ date: p.date, seq: ev.seq, update: p.update_id });
      }
      emit("update", u);
      emit("day", p);
      break;
    }
    case "update.awaiting_review": {
      const u = updateRun(p.update_id);
      u.state = "awaiting_review";
      u.waiting = (p.proposal_ids ?? [])[0] ?? null;
      emit("update", u);
      emit("awaiting-review", u);
      break;
    }
    case "update.resumed": {
      const u = updateRun(p.update_id);
      u.state = "running";
      u.waiting = null;
      emit("update", u);
      break;
    }
    case "update.done":
    case "update.failed": {
      const u = updateRun(p.update_id);
      u.state = ev.kind === "update.failed" ? "failed" : (p.state ?? "done");
      u.report = p.report ?? null;
      u.error = p.error ?? null;
      u.done = u.days;
      u.endSeq = ev.seq;
      if (store.activeUpdate === p.update_id) store.activeUpdate = null;
      emit("update", u);
      emit("update-done", u);
      scheduleRefresh(80);
      break;
    }
    case "daily.propagated":
      emit("propagated", p);
      break;
    // -- the shared process ----------------------------------------------------------------------
    case "market_event.received": {
      const c = marketCard(p.id);
      Object.assign(c, { headline: p.headline, source: p.source, synthetic: p.synthetic, kind: p.kind,
                         channel: p.channel ?? c.channel, update_id: p.update_id ?? c.update_id,
                         published_at: p.published_at, status: "received" });
      if (!c.day && p.published_at) c.day = String(p.published_at).slice(0, 10);
      emit("inbox", c);
      break;
    }
    case "translate.result": {
      const c = marketCard(p.market_event_id);
      c.status = p.events?.length ? "translated" : "no translation";
      c.translation = p;
      for (const e of p.events ?? []) {
        for (const o of e.ops ?? []) {
          const ends = {};
          for (const end of o.ends ?? []) ends[end.end] = { level: end.level, ref: end.ref, candidates: end.candidates ?? [] };
          const fuzzy = Object.values(ends).some((x) => x.level !== "subentity");
          if (fuzzy || o.op === "add_interaction") {
            store.liveOps.set(`${e.id}:${o.index}`, { key: `${e.id}:${o.index}`, event_id: e.id, op: o.op,
                                                      label: o.summary, ends, hyp: false });
          }
        }
      }
      emit("inbox", c);
      emit("fuzzy", null);
      break;
    }
    case "translate.missing":
      break;
    case "refine.step": {
      const key = `${p.event_id}:${p.op_index}`;
      const hyp = /^GUE-(T|EVAL)/.test(String(p.event_id ?? ""));
      const op = store.liveOps.get(key) ?? { key, event_id: p.event_id, op: null, label: null, ends: {}, hyp };
      op.ends[p.end] = { level: LEVEL_NAMES[p.to_level] ?? "entity", ref: p.node_id, candidates: p.candidates ?? [],
                         created: !!p.created };
      op.lastStep = p;
      store.liveOps.set(key, op);
      if (p.created) store.recentlyCreated.add(String(p.node_id).replace(/^new:/, ""));
      emit("fuzzy", key);
      break;
    }
    case "refine.pending":
      emit("fuzzy", p.pending_id);
      break;
    case "review.queued": {
      if (p.market_event_id) { marketCard(p.market_event_id).status = "awaiting review"; emit("inbox", null); }
      dropLiveOps(ev.refs?.[1]);
      scheduleRefresh(50);
      break;
    }
    case "review.auto":
    case "review.decided": {
      const status = { auto_applied: "applied", approved: "applied", rejected: "rejected", deferred: "deferred",
                       edited: "awaiting review" }[p.decision] ?? (ev.kind === "review.auto" ? "applied" : null);
      if (p.market_event_id && status) { marketCard(p.market_event_id).status = status; emit("inbox", null); }
      if (p.decision !== "deferred" && p.decision !== "edited") dropLiveOps(ev.refs?.[1]);
      scheduleRefresh(80);
      break;
    }
    case "forecast.ready":
      for (const [k, o] of store.liveOps) if (o.hyp) store.liveOps.delete(k);
      emit("fuzzy", null);
      emit("forecast-ready", p);
      break;
    case "state.version":
      store.versions.push({ version: p.version, seq: ev.seq, cause: p.cause, at: ev.sim_time });
      emit("versions", store.versions);
      scheduleRefresh(250);
      break;
    case "consolidation.done":
      emit("memory", p);
      break;
    case "classify.path":
      emit("classify", p);
      break;
    case "decision.recorded":
    case "decision.resolved":
      emit("decisions", p);
      break;
    case "hypothesis.scored":
      emit("hypotheses", p);
      break;
    default:
      break;
  }
  emit("phase", ev.phase);
  return true;
}

export function setStatus(st) {
  store.status = st;
  emit("status", st);
}
