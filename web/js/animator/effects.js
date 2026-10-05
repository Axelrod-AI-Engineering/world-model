// Trace kind -> async animation (§13.7). Durations at 1x scale by 1/speed. The animator never computes
// model results: it applies trace payloads to its store and renders them.
import { emit, store } from "../store.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Durations at 1x, in milliseconds.
export const DURATIONS = {
  "market_event.received": 600, "translate.result": 400, "refine.step": 700, "review.queued": 300,
  "parse.created": 500, "classify.path": 450, "recall.result": 600, "induce.bound": 800, "prefill.adjusted": 300,
  "propagation.frame": 120, "fold.posterior": 500, "fold.edge": 400, "generalize.updated": 300, "frontier.*": 500,
  "abduce.*": 900, "isolate.networks": 700, "predict.network": 400, "couple.done": 600, "unify.scenarios": 700,
  "forecast.ready": 800, "explain.stored": 600, "consolidation.done": 900,
};

export const BATCHABLE = new Set(["fold.posterior", "fold.edge", "generalize.updated", "prefill.adjusted",
  "hypothesis.scored", "kernel.updated", "abduce.support", "frontier.logged", "frontier.verified", "frontier.decayed",
  "classify.path", "translate.missing", "predict.network", "explain.stored"]);

function duration(kind, ctx, n = 1) {
  const base = DURATIONS[kind] ?? DURATIONS[`${kind.split(".")[0]}.*`] ?? 0;
  const ms = (base * n) / (ctx.speed || 1);
  return ctx.reduced ? Math.min(ms, 150) : ms;
}

function realOrHyp(ev) {
  return ev.phase && ["isolate", "predict", "couple", "unify", "read_out"].includes(ev.phase) ? "hyp" : "real";
}

const EFFECTS = {
  async "market_event.received"([ev], ctx) {
    const p = ev.payload;
    ctx.toast?.(`${p.source}: ${p.headline}`, "real");
    emit("flash-inbox", p.id);
    await sleep(duration(ev.kind, ctx));
  },
  async "translate.result"([ev], ctx) {
    const nOps = (ev.payload.events ?? []).reduce((a, e) => a + (e.ops?.length ?? 0), 0);
    ctx.refreshRibbons?.(true);
    emit("flash-inbox", ev.payload.market_event_id);
    await sleep(duration(ev.kind, ctx, Math.max(1, nOps)));
  },
  async "refine.step"([ev], ctx) {
    const p = ev.payload;
    ctx.refreshRibbons?.(true);
    ctx.renderer.flashCandidates(p.candidates ?? [], duration(ev.kind, ctx));
    await sleep(duration(ev.kind, ctx));
  },
  async "refine.pending"([ev], ctx) {
    ctx.refreshRibbons?.(true);
    await sleep(duration("refine.step", ctx));
  },
  async "review.queued"([ev], ctx) {
    emit("flash-review", ev.payload.proposal_id);
    await sleep(duration(ev.kind, ctx));
  },
  async "parse.created"([ev], ctx) {
    const p = ev.payload;
    const ids = [...(p.entities ?? []), ...(p.subentities ?? [])];
    await ctx.renderer.pulse(ids.length ? ids : [], p.transient ? css("--hyp-line") : css("--real-line"), duration(ev.kind, ctx));
  },
  async "classify.path"(evs, ctx) {
    const ids = evs.map((e) => e.payload.item_id);
    const levels = Math.max(...evs.map((e) => e.payload.path?.length ?? 1));
    // interaction ids have no position on the canvas, so the renderer skips them
    ctx.renderer.pulse(ids, css("--ltm-line"), duration(evs[0].kind, ctx, Math.min(levels, 4)));
    await sleep(duration(evs[0].kind, ctx, Math.min(levels, 4)));
  },
  async "recall.result"([ev], ctx) {
    const pats = ev.payload.patterns ?? [];
    for (const p of pats.slice(0, 4)) if (p.instance) ctx.renderer.flashHull(p.instance, duration(ev.kind, ctx));
    await sleep(duration(ev.kind, ctx));
  },
  async "induce.bound"([ev], ctx) {
    await ctx.renderer.flashHull(ev.payload.instance_id, duration(ev.kind, ctx));
  },
  async "prefill.adjusted"(evs, ctx) {
    await ctx.renderer.pulseLinks(evs.map((e) => e.payload.interaction_id), css("--wm-ink"), duration(evs[0].kind, ctx));
  },
  async "propagation.frame"([ev], ctx) {
    const z = ev.payload.z ?? {};
    if (ev.payload.step === 0) ctx.renderer.clearHalos();
    await ctx.renderer.halos(z, duration(ev.kind, ctx));
  },
  async "analyze.done"([ev], ctx) {
    await sleep(Math.min(400, duration("fold.posterior", ctx)));
    ctx.renderer.clearHalos();
  },
  async "fold.posterior"(evs, ctx) {
    const ids = evs.map((e) => e.payload.subentity_id);
    await ctx.renderer.pulse(ids, css("--real-line"), duration(evs[0].kind, ctx));
  },
  async "fold.edge"(evs, ctx) {
    await ctx.renderer.pulseLinks(evs.map((e) => e.payload.interaction_id), css("--real-line"), duration(evs[0].kind, ctx));
  },
  async "generalize.updated"(evs, ctx) {
    await sleep(duration(evs[0].kind, ctx));
  },
  async "frontier.logged"(evs, ctx) {
    await sleep(Math.min(duration("frontier.*", ctx), 250));
  },
  async "frontier.verified"(evs, ctx) {
    const ids = evs.flatMap((e) => (e.refs ?? []).slice(1, 3));
    await ctx.renderer.pulse(ids, css("--front-ink"), duration("frontier.*", ctx));
  },
  async "frontier.promotion_proposed"([ev], ctx) {
    await ctx.renderer.pulse((ev.refs ?? []).slice(1, 3), css("--front-ink"), duration("frontier.*", ctx));
  },
  async "frontier.closed"([ev], ctx) {
    ctx.refresh?.();
    await sleep(duration("frontier.*", ctx));
  },
  async "abduce.candidate"([ev], ctx) {
    ctx.refresh?.();
    await ctx.renderer.pulse(ev.payload.members ?? [], css("--ltm-line"), duration("abduce.*", ctx));
  },
  async "abduce.admission_proposed"([ev], ctx) {
    await ctx.renderer.pulse(ev.payload.members ?? [], css("--ltm-ink"), duration("abduce.*", ctx));
  },
  async "abduce.admitted"([ev], ctx) {
    ctx.refresh?.();
    await sleep(duration("abduce.*", ctx));
  },
  async "isolate.networks"([ev], ctx) {
    // dim everything except the isolated networks
    const ents = new Set();
    const links = new Set();
    const hulls = new Set();
    for (const n of ev.payload.networks ?? []) {
      for (const m of n.members ?? []) ents.add(m);
      for (const c of n.channels ?? []) links.add(c);
      if (n.instance_id) hulls.add(n.instance_id);
    }
    store.highlight = { entities: ents, links, hulls, hot: new Set() };
    ctx.renderer.setHighlight(store.highlight);
    emit("highlight", store.highlight);
    await sleep(duration(ev.kind, ctx));
  },
  async "predict.network"(evs, ctx) {
    await sleep(duration(evs[0].kind, ctx, Math.min(evs.length, 3)));
  },
  async "couple.done"([ev], ctx) {
    await sleep(duration(ev.kind, ctx));
  },
  async "unify.scenarios"([ev], ctx) {
    emit("scenarios", ev.payload);
    await sleep(duration(ev.kind, ctx));
  },
  async "explain.stored"(evs, ctx) {
    const ev = evs[evs.length - 1];
    const paths = ev.payload.top_paths ?? [];
    if (paths.length && String(ev.refs?.[1] ?? "").startsWith("FC-")) {
      const hot = new Set(paths.flatMap((p) => p.interaction_ids ?? p));
      const hl = store.highlight ?? { entities: new Set(), links: new Set(), hulls: new Set() };
      store.highlight = { ...hl, hot, links: new Set([...(hl.links ?? []), ...hot]) };
      ctx.renderer.setHighlight(store.highlight);
      emit("highlight", store.highlight);
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "forecast.ready"([ev], ctx) {
    emit("open-forecast", ev.payload.forecast_id);
    await sleep(duration(ev.kind, ctx));
  },
  async "consolidation.done"([ev], ctx) {
    ctx.refresh?.();
    await sleep(Math.min(duration(ev.kind, ctx), 600));
  },
  async "state.version"([ev], ctx) {
    ctx.refresh?.();
  },
  async "scenario.caption"([ev], ctx) {
    store.highlight = null;
    ctx.renderer.setHighlight(null);
    ctx.renderer.clearHalos();
    emit("highlight", null);
  },
  async "scenario.error"([ev], ctx) {
    ctx.toast?.(`Scenario error: ${ev.payload.error}`, "err");
  },
};

export async function play(evs, ctx) {
  const fn = EFFECTS[evs[0].kind];
  if (fn) await fn(evs, ctx);
  else if (realOrHyp(evs[0]) === "hyp") await sleep(Math.min(100, duration("predict.network", ctx)));
}
