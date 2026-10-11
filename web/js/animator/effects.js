// Trace kind -> async animation (§13.7). Durations at 1x scale by 1/speed. The animator never computes
// model results: it applies trace payloads to its store and renders them. A long update plays its
// routine days fast (data releases make no toast and barely pause) and slows down for news, proposals,
// and consolidations that propose something.
import { emit, store } from "../store.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const NET_COLORS = ["#B07CC0", "#5F7AA3", "#A9764B", "#4F8C80", "#A86D80", "#8C7A66", "#958C4F", "#6E9E72", "#B86A84", "#5E9C8F"];

// One forecast being animated, keyed by its trace scope (the thesis id).
const runs = new Map();
const runOf = (ev) => (ev.scope ? runs.get(ev.scope) : null);
const subName = (id) => store.view?.subentities.find((s) => s.id === id)?.name ?? String(id).split(".").pop().replace(/_/g, " ");
const entName = (id) => store.view?.entities.find((e) => e.id === id)?.name ?? id;
const nodeName = (id) => (String(id).includes(".") ? subName(id) : entName(id));
const instOf = (pid) => (store.view?.hulls ?? []).find((h) => h.pattern_id === pid && !h.transient)?.id ?? null;
const hullLabel = (pid) => (store.view?.hulls ?? []).find((h) => h.pattern_id === pid)?.label ?? pid;
const netLabel = (n) => (n.kind === "residual" ? "the residual" : hullLabel(n.pattern_id ?? n.name ?? n.id));
const el = (sel) => ({ el: document.querySelector(sel) });

// Durations at 1x, in milliseconds.
export const DURATIONS = {
  "update.started": 200, "scrape.result": 120, "update.collected": 250, "update.day": 80, "daily.propagated": 90,
  "market_event.received": 350, "translate.result": 240, "refine.step": 380, "review.queued": 200,
  "parse.created": 280, "classify.path": 220, "recall.result": 320, "induce.bound": 400, "prefill.adjusted": 160,
  "propagation.frame": 60, "fold.posterior": 280, "fold.edge": 220, "generalize.updated": 120, "frontier.*": 260,
  "abduce.*": 450, "isolate.networks": 350, "predict.network": 160, "couple.done": 300, "unify.scenarios": 350,
  "forecast.ready": 400, "explain.stored": 300, "consolidation.done": 120, "update.done": 300,
};

export const BATCHABLE = new Set(["fold.posterior", "fold.edge", "generalize.updated", "prefill.adjusted",
  "hypothesis.scored", "kernel.updated", "abduce.support", "frontier.logged", "frontier.verified", "frontier.decayed",
  "classify.path", "translate.missing", "predict.network", "explain.stored", "market_event.received"]);

function duration(kind, ctx, n = 1) {
  const base = DURATIONS[kind] ?? DURATIONS[`${kind.split(".")[0]}.*`] ?? 0;
  const ms = (base * n) / (ctx.speed || 1);
  return ctx.reduced ? Math.min(ms, 150) : ms;
}

function realOrHyp(ev) {
  return ev.phase && ["isolate", "predict", "couple", "unify", "read_out"].includes(ev.phase) ? "hyp" : "real";
}

const isRoutine = (p) => p.channel === "data_feed" || p.kind === "data" || String(p.id ?? "").startsWith("ME-D-");

const EFFECTS = {
  async "update.started"([ev], ctx) {
    // the update strip says what is happening; no toast on top of it
    await sleep(duration(ev.kind, ctx));
  },
  async "scrape.result"([ev], ctx) {
    await sleep(ev.payload.new ? duration(ev.kind, ctx) : 0);
  },
  async "update.collected"([ev], ctx) {
    await sleep(duration(ev.kind, ctx));
  },
  async "update.day"([ev], ctx) {
    await sleep(duration(ev.kind, ctx));
  },
  async "daily.propagated"([ev], ctx) {
    const moved = ev.payload.moved ?? {};
    if (!Object.keys(moved).length) return;
    // a dotted halo: these values moved because the graph carried a move, not because anyone reported them
    ctx.renderer.clearHalos();
    await ctx.renderer.halos(moved, duration(ev.kind, ctx), { dotted: true });
  },
  async "update.done"([ev], ctx) {
    ctx.renderer.clearHalos();
    await sleep(duration(ev.kind, ctx));
  },
  async "market_event.received"(evs, ctx) {
    const news = evs.filter((e) => !isRoutine(e.payload));
    for (const e of news) ctx.toast?.(`${e.payload.source}: ${e.payload.headline}`, "real");
    for (const e of evs) emit("flash-inbox", e.payload.id);
    const first = news[0];
    if (first && ctx.guide?.begin("learn", first.scope)) {
      await ctx.guide.say(`News: “${first.payload.headline}”. Let me show you how the model reads it.`, el("#btn-inbox"));
      return;
    }
    await sleep(news.length ? duration("market_event.received", ctx) : Math.min(40, duration("update.day", ctx)));
  },
  async "translate.result"([ev], ctx) {
    const nOps = (ev.payload.events ?? []).reduce((a, e) => a + (e.ops?.length ?? 0), 0);
    ctx.refreshRibbons?.(true);
    emit("flash-inbox", ev.payload.market_event_id);
    if (ctx.guide?.active(ev.scope) && ctx.guide.run.kind === "learn") {
      const ends = (ev.payload.events ?? []).flatMap((e) => (e.ops ?? []).flatMap((o) => (o.ends ?? []).map((x) => x.ref))).filter(Boolean);
      await ctx.guide.say(`The translator reads it as ${nOps} graph operation${nOps === 1 ? "" : "s"}. A wide band is a fuzzy end (a generalization); it narrows as each end becomes a real subentity.`, ends.slice(0, 6));
      return;
    }
    const routine = String(ev.payload.market_event_id ?? "").startsWith("ME-D-");
    await sleep(routine ? 30 : duration(ev.kind, ctx, Math.min(2, Math.max(1, nOps))));
  },
  async "refine.step"([ev], ctx) {
    const p = ev.payload;
    ctx.refreshRibbons?.(true);
    ctx.renderer.flashCandidates(p.candidates ?? [], duration(ev.kind, ctx));
    if (ctx.guide?.active(ev.scope) && ctx.guide.run.kind === "learn") {
      const g = ctx.guide.run;
      g.refines = (g.refines ?? 0) + 1;
      const text = `Fuzzy → real: the ${p.end} end narrows to ${nodeName(p.node_id)}${p.created ? " (new: created for this news)" : ""}.`;
      if (g.refines <= 3) { await ctx.guide.say(text, [p.node_id]); return; }
      ctx.guide.say(text, [p.node_id], { wait: false });
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "refine.pending"([ev], ctx) {
    ctx.refreshRibbons?.(true);
    await sleep(duration("refine.step", ctx));
  },
  async "review.queued"([ev], ctx) {
    emit("flash-review", ev.payload.proposal_id);
    if (ctx.guide?.active(ev.scope) && ctx.guide.run.kind === "learn") {
      await ctx.guide.end("It changes what the graph contains, so it waits for your review.", el("#btn-review"));
      return;
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "parse.created"([ev], ctx) {
    const p = ev.payload;
    const ids = [...(p.entities ?? []), ...(p.subentities ?? [])];
    await ctx.renderer.pulse(ids, p.transient ? css("--hyp-line") : css("--real-line"), duration(ev.kind, ctx));
  },
  async "classify.path"(evs, ctx) {
    const ids = evs.map((e) => e.payload.item_id);
    const levels = Math.max(...evs.map((e) => e.payload.path?.length ?? 1));
    // interaction ids have no position on the canvas, so the renderer skips them
    ctx.renderer.pulse(ids, css("--ltm-line"), duration(evs[0].kind, ctx, Math.min(levels, 2)));
    await sleep(duration(evs[0].kind, ctx, Math.min(levels, 2)));
  },
  async "recall.result"([ev], ctx) {
    const pats = (ev.payload.patterns ?? []).slice().sort((a, b) => (b.attention ?? 0) - (a.attention ?? 0));
    const run = runOf(ev);
    // the recalled superentities light up one after another
    for (const p of pats.slice(0, 4)) {
      if (p.instance) ctx.renderer.flashHull(p.instance, duration(ev.kind, ctx));
      if (run?.guided) await sleep(90);
    }
    if (run?.guided && pats.length) {
      await ctx.guide.say(`Memory recalls what this resembles: ${pats.slice(0, 3).map((p) => hullLabel(p.id)).join(", ")}.`,
        pats.slice(0, 3).map((p) => p.instance).filter(Boolean));
      return;
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "induce.bound"([ev], ctx) {
    await ctx.renderer.flashHull(ev.payload.instance_id, duration(ev.kind, ctx));
  },
  async "prefill.adjusted"(evs, ctx) {
    await ctx.renderer.pulseLinks(evs.map((e) => e.payload.interaction_id), css("--wm-ink"), duration(evs[0].kind, ctx));
  },
  async "propagation.frame"([ev], ctx) {
    const p = ev.payload;
    const run = runOf(ev);
    if (p.day === 0) ctx.renderer.clearHalos();
    const learn = String(p.run_id ?? "").startsWith("analyze:") && !run;
    ctx.renderer.setFlows(p.flow ?? {});
    if (run?.guided && String(p.run_id ?? "").startsWith("analyze:") && !run.rippled) {
      run.rippled = true;
      run.label = "First look";
      ctx.guide.say("First, a quick look at where the shock ripples through the whole graph, day by day.", run.shocked, { wait: false });
    }
    if (run?.guided) ctx.guide.note(`${run.label} · day ${p.day}`);
    await ctx.renderer.halos(p.z ?? {}, run?.guided ? 55 : duration(ev.kind, ctx), { dotted: learn });
  },
  async "analyze.done"([ev], ctx) {
    await sleep(Math.min(400, duration("fold.posterior", ctx)));
    ctx.renderer.clearHalos();
    ctx.renderer.setFlows({});
  },
  async "fold.posterior"(evs, ctx) {
    const ids = evs.map((e) => e.payload.subentity_id);
    const pulse = ctx.renderer.pulse(ids, css("--real-line"), duration(evs[0].kind, ctx));
    if (ctx.guide?.active(evs[0].scope) && ctx.guide.run.kind === "learn") {
      const top = evs.map((e) => e.payload).sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0))[0];
      await ctx.guide.end(`Beliefs update: ${subName(top.subentity_id)} is now ${top.z > 0 ? "▲" : "▼"} ${Math.abs(top.z ?? 0).toFixed(1)} sd from normal. That is one piece of news, folded in.`, [top.subentity_id]);
      return;
    }
    await pulse;
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
  // -- forecasting (inference), step by step ----------------------------------------------
  async "thesis.posed"([ev], ctx) {
    const p = ev.payload;
    const shocked = [...new Set((p.ops ?? []).flatMap((o) => (o.ends ?? []).map((e) => e.ref)).filter(Boolean))];
    const guided = ctx.guide?.begin("forecast", ev.scope) ?? false;
    runs.set(ev.scope, { scope: ev.scope, question: p.question, shocked, guided, nets: [], byId: new Map(), done: 0, label: "" });
    ctx.renderer.clearHalos();
    ctx.renderer.setFlows({});
    ctx.renderer.setOverlayGroups([]);
    if (guided) {
      ctx.guide.frame(shocked.length ? shocked : null);
      const shock = (p.ops ?? []).map((o) => o.summary).join("; ").replace(/\b([a-z][\w]*\.[a-z][\w.]*)\b/g, (m) => subName(m)) || "no shock: a baseline";
      await ctx.guide.say(`“${p.question}” becomes a hypothetical event: ${shock}. Here is how the model forecasts it.`, shocked);
    }
    await ctx.renderer.pulse(shocked, css("--hyp-line"), duration("parse.created", ctx));
  },
  async "isolate.networks"([ev], ctx) {
    const nets = ev.payload.networks ?? [];
    const run = runOf(ev);
    const ents = new Set();
    const links = new Set();
    const hulls = new Set();
    for (const n of nets) {
      for (const m of n.members ?? []) ents.add(m);
      for (const c of n.channels ?? []) links.add(c);
      if (n.instance_id) hulls.add(n.instance_id);
    }
    // once a person has left the forecast (main.js clearForecastCanvas), its animation stops dimming the canvas
    if (store.forecastDismissed) { await sleep(duration(ev.kind, ctx)); return; }
    store.highlight = { entities: ents, links, hulls, hot: new Set() };
    ctx.renderer.setHighlight(store.highlight);
    emit("highlight", store.highlight);
    if (run) {
      run.nets = nets.map((n, i) => ({ ...n, key: `net:${n.id}`, color: NET_COLORS[i % NET_COLORS.length],
                                      label: n.kind === "residual" ? "residual" : (n.pattern_id ?? n.name ?? n.id) }));
      for (const n of run.nets) run.byId.set(n.id, n);
      if (run.guided) {
        ctx.guide.frame([...ents]);
        ctx.guide.say(`It picks the ${nets.length} networks this question touches and runs each on its own first, so each one's share is clear.`, [...ents], { wait: false });
      }
      // the networks draw themselves in, one after another
      const shown = [];
      for (const n of run.nets) {
        shown.push({ key: n.key, members: n.members ?? [], color: n.color, label: n.label });
        ctx.renderer.setOverlayGroups([...shown]);
        await sleep(run.guided ? 110 : Math.max(30, duration(ev.kind, ctx) / Math.max(4, run.nets.length)));
      }
      if (run.guided) await sleep(900);
      return;
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "predict.network"(evs, ctx) {
    for (const ev of evs) {
      const run = runOf(ev);
      if (!run) { await sleep(duration(ev.kind, ctx)); continue; }
      const n = run.byId.get(ev.payload.network_id);
      run.done += 1;
      run.label = n ? netLabel(n) : ev.payload.name ?? "network";
      ctx.renderer.clearHalos();
      ctx.renderer.setFlows({});
      ctx.renderer.focusOverlay(n?.key ?? null);
      if (run.guided && n) {
        const top = Object.entries(ev.payload.summaries ?? {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
        const lead = top ? ` By the horizon: ${subName(top[0])} ${top[1] > 0 ? "▲" : "▼"} ${Math.abs(top[1]).toFixed(2)} sd.` : "";
        if (run.done === 1) await ctx.guide.say(`Simulating ${run.label}, day by day along each interaction's delay and lag.${lead}`, n.members ?? []);
        else ctx.guide.say(`Simulating ${run.done} of ${run.nets.length}: ${run.label}`, n.members ?? [], { wait: false });
      } else await sleep(duration(ev.kind, ctx));
    }
  },
  async "unify.scenarios"([ev], ctx) {
    emit("scenarios", ev.payload);
    const run = runOf(ev);
    ctx.renderer.clearHalos();
    ctx.renderer.setFlows({});
    ctx.renderer.focusOverlay(null);
    const sc = ev.payload.scenarios ?? [];
    const pids = sc.flatMap((x) => String(x.name ?? "").match(/S\d+|HP\d+/g) ?? []);
    const insts = [...new Set(pids.map(instOf).filter(Boolean))];
    for (const h of insts) ctx.renderer.flashHull(h, 900);
    if (run?.guided && sc.length > 1) {
      await ctx.guide.say(`Rival explanations become weighted scenarios: ${sc.map((x) => `${String(x.name).split(" · ")[0]} ${Math.round(x.weight * 100)}%`).join(" vs ")}. Both are kept.`, insts);
    } else await sleep(duration(ev.kind, ctx));
  },
  async "couple.done"(evs, ctx) {
    const run = runOf(evs[0]);
    if (run && !run.coupled) {
      run.coupled = true;
      run.label = "Coupled";
      ctx.renderer.setOverlayGroups([]);
      if (run.guided) {
        await ctx.guide.say("Now the networks are joined, so effects can cross from one superentity into another.", run.nets.flatMap((n) => n.members ?? []).slice(0, 12));
        return;
      }
    }
    await sleep(duration(evs[0].kind, ctx));
  },
  async "explain.stored"(evs, ctx) {
    const ev = evs[evs.length - 1];
    const paths = ev.payload.top_paths ?? [];
    const run = runOf(ev);
    if (paths.length && String(ev.refs?.[1] ?? "").startsWith("FC-") && !store.forecastDismissed) {
      ctx.renderer.clearHalos();
      ctx.renderer.setFlows({});
      const hot = new Set(paths.flatMap((p) => p.interaction_ids ?? p));
      const hl = store.highlight ?? { entities: new Set(), links: new Set(), hulls: new Set() };
      store.highlight = { ...hl, hot, links: new Set([...(hl.links ?? []), ...hot]) };
      ctx.renderer.setHighlight(store.highlight);
      emit("highlight", store.highlight);
      const first = paths.slice().sort((a, b) => (b.interaction_ids?.length ?? 0) - (a.interaction_ids?.length ?? 0))[0];
      if (run?.guided && first) {
        // the chain in names: the shock, then the value each link on the path moves
        const links = new Map((store.view?.links ?? []).map((l) => [l.id, l]));
        const steps = [nodeName(first.shock_id), ...(first.interaction_ids ?? []).map((i) => nodeName(links.get(i)?.target ?? i))];
        ctx.guide.say(`Why: ${steps.join(" → ")}. A comet runs along each interaction of the main paths.`,
          [first.shock_id, first.target_id], { wait: false });
      }
      // a comet runs along each of the top paths, link by link
      for (const p of paths.slice(0, 3)) {
        for (const iid of p.interaction_ids ?? []) await ctx.renderer.pulseLinks([iid], css("--hyp-ink"), run?.guided ? 180 : 140);
      }
      if (run?.guided) await sleep(300);
      return;
    }
    await sleep(duration(ev.kind, ctx));
  },
  async "forecast.ready"([ev], ctx) {
    emit("open-forecast", ev.payload.forecast_id);
    emit("brief-ready", ev.payload);
    const run = runOf(ev);
    await sleep(duration(ev.kind, ctx));
    if (run) {
      if (run.guided) {
        await ctx.guide.end("Ready: fan charts on the right, and a written brief with the news behind it on the left.",
          el('#right-tabs [data-tab="forecast"]'));
      }
      setTimeout(() => ctx.renderer.setOverlayGroups([]), 400);
      runs.delete(ev.scope);
    }
  },
  async "consolidation.done"([ev], ctx) {
    const r = ev.payload.report ?? {};
    const proposes = (r.proposal_events?.length ?? r.proposals ?? 0) > 0 || (r.candidates?.length ?? 0) > 0;
    if (proposes) ctx.refresh?.();
    await sleep(duration(ev.kind, ctx, proposes ? 900 / 250 : 1));
  },
  async "state.version"(_evs, ctx) {
    ctx.refresh?.();
  },
  async "scenario.caption"(_evs, ctx) {
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
