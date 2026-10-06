// The walkthrough. DECISION: the user asked to step through what the model does, for learning and for
// prediction, and to see a market event travel from fuzzy to real. The walkthrough reads one scope's trace
// events (one market event's, or one thesis's) and turns them into steps; each step frames and lights up
// what it touched on the canvas, and ◀ ▶ (or ← →) move between steps. Like the animator, it computes
// nothing: it replays the trace.
import { api } from "../api.js";
import { prettyNode } from "../graph/fuzzy.js";
import { emit, store } from "../store.js";
import { esc, fmt, signed } from "../util.js";

const LEVELS = ["generalization", "entity", "subentity"];
const LEVEL_WORDS = { generalization: "a kind of thing (fuzzy)", entity: "an entity", subentity: "one subentity (real)" };
const METER_WORDS = ["a kind of thing", "an entity", "one value"];
const NET_COLORS = ["#B07CC0", "#5F7AA3", "#A9764B", "#4F8C80", "#A86D80", "#8C7A66", "#958C4F"];
const LEARN_ORDER = ["received", "translated", "refined", "reviewed", "parsed", "classified", "recalled", "prefilled",
                     "analyzed", "folded", "generalized", "noticed"];
const PREDICT_ORDER = ["posed", "refined", "parsed", "classified", "recalled", "prefilled", "isolated", "predicted",
                       "coupled", "unified", "read", "explained"];
const PHASE_LABEL = {
  received: "News", translated: "Translate", refined: "Fuzzy → real", reviewed: "Review", parsed: "Parse",
  classified: "Classify", recalled: "Recall", prefilled: "Prefill", analyzed: "Expect", folded: "Fold",
  generalized: "Generalize", noticed: "Notice", posed: "Question", isolated: "Isolate", predicted: "Predict",
  coupled: "Couple", unified: "Unify", read: "Forecast", explained: "Explain",
};

function names() {
  const v = store.view ?? store.graph;
  const subs = new Map((v?.subentities ?? []).map((s) => [s.id, s]));
  const ents = new Map((v?.entities ?? []).map((e) => [e.id, e]));
  const links = new Map((v?.links ?? []).map((l) => [l.id, l]));
  const hulls = new Map((v?.hulls ?? []).map((h) => [h.id, h]));
  const pats = new Map((v?.hulls ?? []).map((h) => [h.pattern_id, h]));
  const node = (id) => {
    const ref = String(id ?? "").replace(/^new:/, "");
    if (subs.has(ref)) return subs.get(ref).name;
    if (ents.has(ref)) return ents.get(ref).name;
    if (links.has(ref)) return links.get(ref).label;
    if (pats.has(ref)) return `${ref} · ${pats.get(ref).label.replace(/^S\d+\s*·\s*/, "")}`;
    if (hulls.has(ref)) return hulls.get(ref).label;
    return prettyNode(ref);
  };
  // server summaries name things by id ("change federal_reserve.policy_stance +0.52"): use names
  const text = (s) => String(s ?? "").replace(/\b(?:gen:(?:obj|int):[\w.]+|new:[\w.]+|[a-z][\w]*\.[a-z][\w.]*)\b/g, (m) => node(m));
  const entityOf = (id) => subs.get(id)?.entity_id ?? (ents.has(id) ? id : String(id).split(".")[0]);
  return { node, text, subs, ents, links, entityOf };
}

function chip(text, cls = "") {
  return `<span class="wchip ${cls}">${esc(text)}</span>`;
}

// how specific an op end is: a kind of thing (fuzzy) → an entity → one value (real)
function meter(level, from = null) {
  const at = LEVELS.indexOf(level);
  const was = from == null ? -1 : LEVELS.indexOf(from);
  return `<span class="meter" title="${esc(LEVEL_WORDS[level] ?? level)}">${METER_WORDS.map((w, k) =>
    `<span class="stop ${k <= at ? "on" : ""} ${k === at ? "cur" : ""} ${k === was ? "was" : ""}">${esc(w)}</span>`).join("<i></i>")}</span>`;
}

// deviations as a short list of diverging bars
function zList(pairs, nm, unit = "sd") {
  if (!pairs.length) return "";
  const m = Math.max(0.5, ...pairs.map(([, z]) => Math.abs(z)));
  return `<div class="zlist">${pairs.map(([id, z]) => `<span class="nm" title="${esc(id)}">${esc(nm.node(id))}</span>
    <span class="zbar"><i class="${z >= 0 ? "up" : "down"}" style="width:${((Math.abs(z) / m) * 50).toFixed(1)}%"></i></span>
    <span class="mono ${z > 0 ? "z-up" : "z-down"}">${signed(z)} ${unit}</span>`).join("")}</div>`;
}

// recall scores as a short list of bars
function attnList(pats, nm) {
  if (!pats.length) return "<p class='muted'>Nothing recalled.</p>";
  const m = Math.max(...pats.map((x) => x.attention), 1e-9);
  return `<div class="zlist attn">${pats.map((x) => `<span class="nm">${esc(nm.node(x.id))}</span>
    <span class="zbar one"><i class="up" style="width:${((x.attention / m) * 100).toFixed(1)}%"></i></span>
    <span class="mono faint">${fmt(x.attention)}</span>`).join("")}</div>`;
}

const top = (obj, n) => Object.entries(obj ?? {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, n);

// -- learning: one market event ----------------------------------------------------------------------
function learnSteps(evs, nm) {
  const steps = [];
  const of = (k) => evs.filter((e) => e.kind === k);
  const ops = new Map();
  const ribbons = () => [...ops.values()].filter((o) => Object.keys(o.ends).length)
    .map((o) => ({ key: `walk:${o.key}`, ends: structuredClone(o.ends), label: nm.text(o.label), hyp: false }));
  const concrete = () => [...ops.values()].flatMap((o) => Object.values(o.ends).filter((e) => e.level === "subentity").map((e) => e.ref));
  const touched = () => [...ops.values()].flatMap((o) => Object.values(o.ends).flatMap((e) =>
    (e.level === "generalization" ? (e.candidates ?? []).slice(0, 4).map((c) => (Array.isArray(c) ? c[0] : c)) : [e.ref])));
  const opList = () => [...ops.values()].map((o) => `<li>${chip(o.op ? o.op.replace(/_/g, " ") : "op")} ${esc(nm.text(o.label))}
      ${Object.entries(o.ends).map(([end, x]) => `<div class="end"><span class="small muted">${esc(end)}</span> ${meter(x.level)}
        <span class="small">${x.ref ? esc(nm.node(x.ref)) : ""}</span></div>`).join("")}</li>`).join("");

  const rec = of("market_event.received")[0];
  if (rec) {
    const p = rec.payload;
    steps.push({ phase: "received", title: "A market event arrives",
      body: `<p><b>${esc(p.headline)}</b></p><p class="small muted">${esc(p.source ?? "")} · ${esc(String(p.published_at ?? "").slice(0, 16).replace("T", " "))}
        · ${p.channel === "data_feed" ? "a scheduled data release" : p.channel === "user" ? "typed in by you" : "found by the web scraper"} · synthetic</p>
        <p>The model has not touched the graph yet. First it must say what this news is about, in the graph's own terms.</p>`,
      visual: {} });
  }
  const tr = of("translate.result")[0];
  if (tr) {
    for (const e of tr.payload.events ?? []) {
      for (const o of e.ops ?? []) {
        const ends = {};
        for (const x of o.ends ?? []) ends[x.end] = { level: x.level, ref: x.ref, candidates: x.candidates ?? [] };
        ops.set(`${e.id}:${o.index}`, { key: `${e.id}:${o.index}`, label: o.summary, op: o.op, ends });
      }
    }
    const fuzzy = [...ops.values()].some((o) => Object.values(o.ends).some((x) => x.level !== "subentity"));
    steps.push({ phase: "translated", title: "Translated into graph operations",
      body: `<p>The translator turns the text into ${ops.size} operation${ops.size === 1 ? "" : "s"}. Each end is only as specific as the text allows.
        ${fuzzy ? "On the canvas, a wide band is a fuzzy end; it narrows as the end becomes real." : "Here every end is already one value: the release names it."}</p>
        <ul class="wlist ops">${opList()}</ul>`,
      visual: { ribbons: ribbons(), peek: concrete() }, focus: touched() });
  }
  for (const r of of("refine.step")) {
    const p = r.payload;
    const key = `${p.event_id}:${p.op_index}`;
    const o = ops.get(key) ?? { key, label: null, op: null, ends: {} };
    ops.set(key, o);
    const from = LEVELS[p.from_level] ?? "entity";
    const to = LEVELS[p.to_level] ?? "entity";
    o.ends[p.end] = { level: to, ref: p.node_id, candidates: p.candidates ?? [] };
    const cands = (p.candidates ?? []).slice(0, 4);
    const endsNow = Object.entries(o.ends).map(([end, x]) => `<div class="end ${end === p.end ? "changed" : ""}"><span class="small muted">${esc(end)}</span>
      ${meter(x.level, end === p.end ? from : null)} <span class="small">${esc(nm.node(x.ref))}</span></div>`).join("");
    steps.push({ phase: "refined", title: `Fuzzy → real: the ${p.end} end narrows`,
      body: `<ul class="wlist ops"><li>${chip(o.op ? o.op.replace(/_/g, " ") : "op")} ${esc(nm.text(o.label ?? ""))}${endsNow}</li></ul>
        <p>The ${esc(p.end)} end becomes <b>${esc(nm.node(p.node_id))}</b>${p.created ? " (new, created for this news)" : ""}.</p>
        ${cands.length ? `<p class="small">The refiner scored ${cands.map(([c, s]) => `${chip(nm.node(c))}<span class="mono faint">${fmt(s)}</span>`).join(" ")}</p>` : ""}
        ${p.reason ? `<p class="small muted">${esc(p.reason)}</p>` : ""}`,
      visual: { ribbons: ribbons(), peek: concrete(), candidates: p.candidates ?? [], pulse: [p.node_id] },
      focus: [p.node_id, ...cands.map(([c]) => c)] });
  }
  for (const r of of("refine.pending")) {
    const p = r.payload;
    const cands = (p.candidates ?? []).slice(0, 4);
    steps.push({ phase: "refined", title: `The ${p.end} end stays fuzzy for now`,
      body: `<p>${meter(LEVELS[p.level] ?? "generalization")}</p>
        <p>The text is not specific enough to pick one target, so this end waits at <b>${esc(nm.node(p.node_id))}</b> as a pending refinement. Later evidence can bind it.</p>
        ${cands.length ? `<p class="small">Leading candidates: ${cands.map(([c, s]) => `${chip(nm.node(c))}<span class="mono faint">${fmt(s)}</span>`).join(" ")}</p>` : ""}`,
      visual: { ribbons: ribbons(), candidates: p.candidates ?? [] }, focus: cands.map(([c]) => c) });
  }
  const queued = of("review.queued")[0];
  const auto = of("review.auto")[0];
  const decided = of("review.decided").filter((e) => e.payload.decision !== "edited").slice(-1)[0];
  if (queued || auto) {
    const reasons = queued?.payload.reasons ?? [];
    const how = queued ? `It changes what the graph contains, so it waited for you: ${esc(reasons.join("; ") || "structural change")}.`
      : "Routine news that only moves values needs no review, so it was applied automatically.";
    const dec = decided ? ` Decision: <b>${esc(String(decided.payload.decision).replace(/_/g, " "))}</b>${decided.payload.by ? ` by ${esc(decided.payload.by)}` : ""}.` : "";
    steps.push({ phase: "reviewed", title: queued ? "Reviewed by a person" : "Applied without review",
      body: `<p>${how}${dec}</p><p class="small muted">From here on, the operations are graph update events: real changes to the model's state.</p>`,
      visual: { ribbons: ribbons().map((x) => ({ ...x, proposed: true })), peek: concrete() }, focus: touched() });
  }
  const parsed = of("parse.created").filter((e) => !e.payload.transient);
  if (parsed.length) {
    const p = parsed[0].payload;
    const made = [...(p.entities ?? []), ...(p.subentities ?? []), ...(p.interactions ?? [])];
    steps.push({ phase: "parsed", title: "Parsed into the graph",
      body: made.length ? `<p>New things enter the graph: ${made.map((m) => chip(nm.node(m), "new")).join(" ")}.</p>`
        : "<p>Everything it mentions already exists, so nothing new is created.</p>",
      visual: { peek: p.subentities ?? [], pulse: made }, focus: made.length ? made : concrete() });
  }
  const cls = of("classify.path");
  if (cls.length) {
    const rows = cls.slice(0, 5).map((e) => `<li>${chip(nm.node(e.payload.item_id))} → ${(e.payload.path ?? []).slice(1).map((g) => esc(prettyNode(g))).join(" → ") || "<span class='muted'>root</span>"}${e.payload.is_new ? " <span class='badge ltm'>new</span>" : ""}</li>`);
    steps.push({ phase: "classified", title: "Classified in long-term memory",
      body: `<p>Each touched item is sorted down the taxonomies of objects and interactions. Where it lands decides which priors it inherits.</p>
        <ul class="wlist">${rows.slice(0, 3).join("")}${rows.length > 3 ? `<details class="more"><summary>+ ${cls.length - 3} more</summary>${rows.slice(3).join("")}</details>` : ""}</ul>`,
      visual: { pulse: cls.map((e) => e.payload.item_id) }, focus: cls.map((e) => e.payload.item_id) });
  }
  const rc = of("recall.result")[0];
  if (rc) {
    const pats = rc.payload.patterns ?? [];
    const eps = rc.payload.episodes ?? [];
    const insts = pats.map((x) => x.instance).filter(Boolean);
    steps.push({ phase: "recalled", title: "Memory recalls superentities and analogs",
      body: `<p>Long-term memory brings back the patterns this looks like, by how much attention each earns:</p>${attnList(pats.slice(0, 5), nm)}
        ${eps.length ? `<p class="small">And past days that looked similar: ${eps.slice(0, 4).map((x) => chip(`${x.id}${x.tags?.length ? ` (${x.tags.slice(0, 2).join(", ")})` : ""}`)).join(" ")}</p>` : ""}`,
      visual: { flashHulls: insts, highlight: hl({ hulls: insts }) }, focus: insts.slice(0, 3) });
  }
  const pre = of("prefill.adjusted");
  const bound = of("induce.bound").filter((e) => !e.payload.transient);
  if (pre.length || bound.length) {
    const linkEnds = pre.flatMap((e) => { const l = nm.links.get(e.payload.interaction_id); return l ? [l.source, l.target] : []; });
    steps.push({ phase: "prefilled", title: "Recalled patterns adjust expectations",
      body: `${bound.length ? `<p>A recalled pattern binds to today's entities: ${bound.map((e) => chip(nm.node(e.payload.pattern_id))).join(" ")}.</p>` : ""}
        ${pre.length ? `<p>Before reading the numbers, the model updates what it expects of ${pre.length} link${pre.length === 1 ? "" : "s"}:</p>
          <ul class="wlist">${pre.slice(0, 3).map((e) => `<li>${chip(nm.node(e.payload.interaction_id))} effect ${fmt(e.payload.effect_before)} → <b>${fmt(e.payload.effect_after)}</b></li>`).join("")}</ul>` : ""}`,
      visual: { highlight: hl({ links: pre.map((e) => e.payload.interaction_id), hot: pre.map((e) => e.payload.interaction_id) }) },
      focus: linkEnds.length ? linkEnds : bound.map((e) => e.payload.instance_id ?? e.payload.pattern_id) });
  }
  const frames = of("propagation.frame").filter((e) => String(e.payload.run_id ?? "").startsWith("analyze:"));
  const ad = of("analyze.done")[0];
  if (ad || frames.length) {
    const moves = top(ad?.payload.expected_moves ?? frames[frames.length - 1]?.payload.z, 5);
    steps.push({ phase: "analyzed", title: "It predicts the ripple first",
      body: `<p>Before folding the news in, the model runs it through the graph to see where it should show up, and when. Press ▶ to watch the days.</p>
        ${zList(moves, nm)}`,
      frames: frames.map((e) => e.payload), visual: {}, focus: moves.map(([sid]) => sid) });
  }
  const post = of("fold.posterior");
  const edges = of("fold.edge");
  if (post.length || edges.length) {
    const rows = post.slice(0, 4).map((e) => {
      const p = e.payload;
      return `<li>${chip(nm.node(p.subentity_id))} ${fmt(p.before?.q50)} → <b>${fmt(p.after?.q50)}</b>
        <span class="small muted">(now ${signed(p.z)} sd from normal)</span></li>`;
    }).join("");
    const erows = edges.slice(0, 3).map((e) => `<li>${chip(nm.node(e.payload.interaction_id))} effect ${fmt(e.payload.effect_before)} → <b>${fmt(e.payload.effect_after)}</b>, exists ${fmt(e.payload.existence_before)} → <b>${fmt(e.payload.existence_after)}</b></li>`).join("");
    const subs = post.map((e) => e.payload.subentity_id);
    steps.push({ phase: "folded", title: "Folded in: beliefs update",
      body: `<p>The observation is weighed against what the model expected. Values move as far as the evidence warrants, and the links that carried the move learn too.</p>
        ${rows ? `<ul class="wlist">${rows}</ul>` : ""}${erows ? `<ul class="wlist">${erows}</ul>` : ""}`,
      visual: { peek: subs, halos: Object.fromEntries(post.map((e) => [e.payload.subentity_id, e.payload.z])),
                highlight: hl({ entities: subs.map(nm.entityOf), links: edges.map((e) => e.payload.interaction_id), hot: edges.map((e) => e.payload.interaction_id) }) },
      focus: subs });
  }
  const gen = of("generalize.updated")[0];
  if (gen) {
    const sup = Object.entries(gen.payload.supports ?? {}).slice(0, 6);
    steps.push({ phase: "generalized", title: "Generalizations grow",
      body: `<p>The taxonomy nodes that classified this news gain support, so the next similar event is classified with more confidence.</p>
        <p>${sup.map(([g, v]) => `${chip(prettyNode(g))}<span class="mono faint">${fmt(v, 1)}</span>`).join(" ")}</p>`, visual: {} });
  }
  const notice = evs.filter((e) => e.kind.startsWith("frontier.") || e.kind.startsWith("abduce."));
  if (notice.length) {
    const kinds = [...new Set(notice.map((e) => e.kind))];
    steps.push({ phase: "noticed", title: "Patterns and co-movements noticed",
      body: `<p>Moves the graph does not explain are logged on the correlation frontier, and recurring configurations count toward new superentities:</p>
        <p>${kinds.slice(0, 6).map((k) => chip(`${k.replace(".", ": ").replace(/_/g, " ")} ×${notice.filter((e) => e.kind === k).length}`)).join(" ")}</p>`,
      visual: { pulse: notice.flatMap((e) => (e.refs ?? []).slice(1, 3)) }, focus: notice.flatMap((e) => (e.refs ?? []).slice(1, 3)).slice(0, 8) });
  }
  return steps;
}

// -- prediction: one thesis ----------------------------------------------------------------------------
function predictSteps(evs, nm) {
  const steps = [];
  const of = (k) => evs.filter((e) => e.kind === k);
  const ops = new Map();
  const ribbons = () => [...ops.values()].filter((o) => Object.keys(o.ends).length)
    .map((o) => ({ key: `walk:${o.key}`, ends: structuredClone(o.ends), label: nm.text(o.label), hyp: true }));
  const shocked = () => [...ops.values()].flatMap((o) => Object.values(o.ends).map((e) => e.ref)).filter(Boolean);
  const posed = of("thesis.posed")[0];
  if (posed) {
    const p = posed.payload;
    for (const o of p.ops ?? []) {
      const ends = {};
      for (const x of o.ends ?? []) ends[x.end] = { level: x.level, ref: x.ref, candidates: x.candidates ?? [] };
      ops.set(`${p.thesis_id}:${o.index}`, { key: `${p.thesis_id}:${o.index}`, label: o.summary, ends });
    }
    steps.push({ phase: "posed", title: "A question is posed",
      body: `<p><b>${esc(p.question)}</b></p><p>It becomes a hypothetical event the model treats like news that has not happened:</p>
        <ul class="wlist ops">${[...ops.values()].map((o) => `<li>${chip(nm.text(o.label), "hyp")}${Object.entries(o.ends).map(([end, x]) =>
          `<div class="end"><span class="small muted">${esc(end)}</span> ${meter(x.level)}</div>`).join("")}</li>`).join("") || "<li>no shocks: a baseline</li>"}</ul>
        <p class="small muted">Horizon ${p.horizon_days} days${(p.target_groups ?? []).length ? `; also forecast for ${p.target_groups.map((g) => esc(nm.node(g.split(":")[1]))).join(", ")}` : ""}.</p>`,
      visual: { ribbons: ribbons() }, focus: shocked() });
  }
  for (const r of of("refine.step")) {
    const p = r.payload;
    const key = [...ops.keys()].find((k) => k.endsWith(`:${p.op_index}`)) ?? `${p.event_id}:${p.op_index}`;
    const o = ops.get(key) ?? { key, label: null, ends: {} };
    ops.set(key, o);
    const from = LEVELS[p.from_level] ?? "entity";
    const to = LEVELS[p.to_level] ?? "entity";
    o.ends[p.end] = { level: to, ref: p.node_id, candidates: p.candidates ?? [] };
    steps.push({ phase: "refined", title: `Fuzzy → real: the ${p.end} end narrows`,
      body: `<p>${meter(to, from)}</p><p>To <b>${esc(nm.node(p.node_id))}</b>.</p>`,
      visual: { ribbons: ribbons(), candidates: p.candidates ?? [], pulse: [p.node_id] }, focus: [p.node_id] });
  }
  const parsed = of("parse.created")[0];
  if (parsed) {
    steps.push({ phase: "parsed", title: "Parsed as a hypothetical",
      body: "<p>The shock is placed on the graph in a scratch layer: nothing in the model's real state changes while it forecasts.</p>",
      visual: { pulse: [...(parsed.payload.subentities ?? []), ...(parsed.payload.entities ?? [])] }, focus: shocked() });
  }
  const rc = of("recall.result")[0];
  if (rc) {
    const pats = rc.payload.patterns ?? [];
    const insts = pats.map((x) => x.instance).filter(Boolean);
    steps.push({ phase: "recalled", title: "Memory recalls what this resembles",
      body: `<p>Superentities this question touches, by attention:</p>${attnList(pats.slice(0, 6), nm)}`,
      visual: { flashHulls: insts, highlight: hl({ hulls: insts }) }, focus: insts.slice(0, 4) });
  }
  const iso = of("isolate.networks");
  const nets = iso.flatMap((e) => e.payload.networks ?? []);
  const netLabel = (n) => (n.kind === "residual" ? "residual" : (n.pattern_id ?? n.name ?? n.id));
  if (nets.length) {
    const groups = nets.map((n, i) => ({ key: `net:${n.id}`, members: n.members ?? [], color: NET_COLORS[i % NET_COLORS.length], label: netLabel(n) }));
    steps.push({ phase: "isolated", title: "The relevant networks are isolated",
      body: `<p>Rather than run the whole graph at once, the model picks the superentities this question touches and treats each as a network, plus a residual of the other links that matter:</p>
        <p>${nets.map((n, i) => `<span class="wchip" style="border-color:${NET_COLORS[i % NET_COLORS.length]};border-width:2px">${esc(n.kind === "residual" ? "residual" : nm.node(n.pattern_id ?? n.name))}</span><span class="mono faint">${fmt(n.relevance)}</span>`).join(" ")}</p>`,
      visual: { networks: groups, highlight: hl({ entities: nets.flatMap((n) => n.members ?? []), links: nets.flatMap((n) => n.channels ?? []) }) },
      focus: nets.flatMap((n) => n.members ?? []) });
  }
  const preds = of("predict.network");
  for (const pr of preds) {
    const p = pr.payload;
    const n = nets.find((x) => x.id === p.network_id);
    const i = Math.max(0, nets.indexOf(n));
    const frames = evs.filter((e) => e.kind === "propagation.frame" && e.payload.run_id === `predict:${p.network_id}`).map((e) => e.payload);
    const moves = top(p.summaries, 4);
    steps.push({ phase: "predicted", title: `Predicted within ${n?.kind === "residual" ? "the residual" : nm.node(n?.pattern_id ?? p.name)}`,
      body: `<p>The shock propagates through this network alone, day by day, along each link's delay and lag. Press ▶ or scrub the days to watch it spread.</p>
        ${moves.length ? `<p class="small muted">At the horizon:</p>${zList(moves, nm)}` : ""}`,
      frames, visual: { networks: n ? [{ key: `net:${n.id}`, members: n.members ?? [], color: NET_COLORS[i % NET_COLORS.length], label: netLabel(n) }] : [],
                        highlight: hl({ entities: n?.members ?? [], links: n?.channels ?? [] }) },
      focus: n?.members ?? [] });
  }
  const cframes = evs.filter((e) => e.kind === "propagation.frame" && String(e.payload.run_id ?? "").startsWith("couple:")).map((e) => e.payload);
  const cd = of("couple.done");
  if (cd.length || cframes.length) {
    steps.push({ phase: "coupled", title: "Networks are coupled",
      body: "<p>The networks are joined across the links between them, so effects can cross from one superentity into another, for example from the energy shock into credit tightening.</p>",
      frames: cframes, visual: {}, focus: nets.flatMap((x) => x.members ?? []) });
  }
  const un = of("unify.scenarios")[0];
  if (un) {
    const sc = un.payload.scenarios ?? [];
    steps.push({ phase: "unified", title: "Rival structures become weighted scenarios",
      body: `<p>Where memory holds rival explanations of the same moves, each becomes a scenario, weighted by how well it has predicted before:</p>
        <div class="weightbar">${sc.map((s, i) => `<div style="width:${(s.weight * 100).toFixed(1)}%;background:${NET_COLORS[i % NET_COLORS.length]}33" title="${esc(s.name)}">${s.weight > 0.18 ? esc(`${s.name.split(" · ")[0]} ${fmt(s.weight * 100, 0)}%`) : ""}</div>`).join("")}</div>`,
      visual: { highlight: hl({ hot: sc.flatMap((s) => Object.keys(s.forced ?? {})), links: sc.flatMap((s) => Object.keys(s.forced ?? {})) }) } });
  }
  const ready = of("forecast.ready")[0];
  const last = cframes[cframes.length - 1];
  if (ready) {
    const moves = top(last?.z, 6);
    steps.push({ phase: "read", title: "The forecast is read out",
      body: `<p>The scenarios are mixed by weight into one forecast with honest uncertainty, for single values and for whole actors, sectors, and ideas. It is open in the Forecast tab.</p>
        ${zList(moves, nm)}`,
      visual: { halos: last?.z ?? {}, flows: last?.flow ?? {}, openForecast: ready.payload.forecast_id }, focus: moves.map(([sid]) => sid) });
  }
  const ex = of("explain.stored").filter((e) => String(e.refs?.[1] ?? "").startsWith("FC-")).slice(-1)[0];
  if (ex) {
    const paths = ex.payload.top_paths ?? [];
    const hot = paths.flatMap((p) => p.interaction_ids ?? []);
    steps.push({ phase: "explained", title: "Why: the paths that carry the effect",
      body: `<p>${esc(ex.payload.text ?? "")}</p>
        <ul class="wlist">${paths.slice(0, 3).map((p) => `<li>${esc(nm.node(p.shock_id))} → ${(p.interaction_ids ?? []).map((i) => esc(nm.node(i))).join(" → ")} → <b>${esc(nm.node(p.target_id))}</b> <span class="muted small">${fmt((p.share ?? 0) * 100, 0)}%</span></li>`).join("")}</ul>`,
      visual: { highlight: hl({ links: hot, hot, entities: paths.flatMap((p) => [p.shock_id, p.target_id].map(nm.entityOf)) }) },
      focus: paths.slice(0, 3).flatMap((p) => [p.shock_id, p.target_id]) });
  }
  return steps;
}

function hl({ entities = [], links = [], hulls = [], hot = [] } = {}) {
  return { entities: new Set(entities), links: new Set(links), hulls: new Set(hulls), hot: new Set(hot) };
}

// -- the walkthrough card ---------------------------------------------------------------------------------
export function initWalkthrough({ renderer, toast, openForecast }) {
  const host = document.getElementById("walkthrough");
  const caption = document.getElementById("caption");
  const canvas = document.getElementById("canvas");
  let steps = [];
  let i = 0;
  let kind = "learn";
  let scope = null;
  let title = "";
  let frameIdx = 0;
  let playing = null;
  let camera = null;          // the view before the walkthrough, restored when it closes
  let frameTimer = null;

  const isOpen = () => !host.classList.contains("hidden");

  async function open(sc, opts = {}) {
    stopPlay();
    scope = sc;
    kind = opts.kind ?? (/^T-|^FC-/.test(sc) ? "predict" : "learn");
    let evs = store.traces.filter((e) => e.scope === sc);
    try {
      const fromServer = await api.traceScope(sc);
      if (fromServer.length >= evs.length) evs = fromServer;
    } catch { /* the local trace is enough */ }
    const nm = names();
    steps = kind === "predict" ? predictSteps(evs, nm) : learnSteps(evs, nm);
    if (!steps.length) { toast?.(`Nothing to walk through for ${sc} yet.`, "err"); return; }
    title = opts.title ?? (kind === "predict"
      ? (evs.find((e) => e.kind === "thesis.posed")?.payload.question ?? sc)
      : (evs.find((e) => e.kind === "market_event.received")?.payload.headline ?? store.marketEvents.get(sc)?.headline ?? sc));
    i = 0;
    if (!isOpen()) {
      const t = renderer.zoom?.transform();
      camera = t ? { x: t.x, y: t.y, k: t.k } : null;
    }
    host.classList.remove("hidden");
    host.classList.toggle("predict", kind === "predict");
    caption.classList.add("hidden");
    store.walkthrough = { scope: sc, kind };
    emit("walkthrough", store.walkthrough);
    render();
  }

  function close() {
    if (!isOpen()) return;
    stopPlay();
    clearTimeout(frameTimer);
    host.classList.add("hidden");
    caption.classList.remove("hidden");
    store.walkthrough = null;
    renderer.unpeek();
    renderer.setOverlayGroups([]);
    renderer.setFlows({});
    renderer.clearHalos();
    renderer.setHighlight(store.highlight);
    emit("walk-ribbons", null);
    emit("walkthrough", null);
    if (camera) renderer.zoom?.set(camera, store.settings.reducedMotion ? 0 : 450);
    camera = null;
  }

  function go(k) {
    stopPlay();
    i = Math.max(0, Math.min(steps.length - 1, k));
    render();
  }

  function stopPlay() {
    if (playing) { clearInterval(playing); playing = null; }
    const b = host.querySelector('[data-walk="play"]');
    if (b) b.textContent = "▶";
  }

  function applyFrame(st) {
    const f = st.frames?.[frameIdx];
    if (!f) return;
    renderer.clearHalos();
    renderer.halos(f.z ?? {}, 0, { dotted: kind === "learn" });
    renderer.setFlows(f.flow ?? {});
    const lab = host.querySelector(".walk-frames .day");
    if (lab) lab.textContent = `day ${f.day} of ${st.frames[st.frames.length - 1].day}`;
    const rng = host.querySelector(".walk-frames input");
    if (rng) rng.value = String(frameIdx);
  }

  // frame the step's subject below the card, once the nodes it opened have their places
  function frameStep(st) {
    clearTimeout(frameTimer);
    const ids = [...new Set((st.focus ?? []).filter(Boolean))];
    if (!ids.length) return;
    frameTimer = setTimeout(() => {
      // frame inside what the card and any open side panel leave visible
      const c = canvas.getBoundingClientRect();
      const top = host.getBoundingClientRect().bottom - c.top;
      const lp = document.getElementById("left-panel");
      const rp = document.getElementById("right-panel");
      const left = lp && !lp.hidden ? lp.getBoundingClientRect().right - c.left : 0;
      const right = rp && !rp.hidden ? c.right - rp.getBoundingClientRect().left : 0;
      renderer.frame(ids, { top: Math.max(0, top), left: Math.max(0, left), right: Math.max(0, right) });
    }, 60);
  }

  function apply(st) {
    const v = st.visual ?? {};
    renderer.peek(v.peek ?? []);
    renderer.setOverlayGroups(v.networks ?? []);
    renderer.setHighlight(v.highlight ?? null);
    renderer.clearHalos();
    renderer.setFlows(v.flows ?? {});
    if (v.halos && Object.keys(v.halos).length) renderer.halos(v.halos, 0, { dotted: false });
    emit("walk-ribbons", v.ribbons ?? []);
    frameStep(st);
    if (v.pulse?.length) setTimeout(() => renderer.pulse(v.pulse, kind === "predict" ? "#B07CC0" : "#7C64C4", 800), 450);
    for (const h of v.flashHulls ?? []) setTimeout(() => renderer.flashHull(h, 900), 450);
    if (v.candidates?.length) setTimeout(() => renderer.flashCandidates(v.candidates, 1100), 500);
    if (v.openForecast) openForecast?.(v.openForecast);
    if (st.frames?.length) {
      frameIdx = st.frames.length - 1;
      applyFrame(st);
    }
  }

  function render() {
    const st = steps[i];
    const order = kind === "predict" ? PREDICT_ORDER : LEARN_ORDER;
    const phases = order.filter((ph) => steps.some((s) => s.phase === ph));
    host.innerHTML = `
      <div class="walk-head">
        <span class="badge ${kind === "predict" ? "hyp" : "real"}">${kind === "predict" ? "Prediction" : "Learning"}</span>
        <span class="walk-title" title="${esc(title)}">${esc(title)}</span>
        <button class="close" data-walk="close" aria-label="Close the walkthrough (Esc)">✕</button>
      </div>
      <div class="walk-phases" role="tablist">${phases.map((ph) => {
        const idx = steps.findIndex((s) => s.phase === ph);
        const n = steps.filter((s) => s.phase === ph).length;
        const cur = st.phase === ph;
        const done = steps.findIndex((s) => s.phase === st.phase) > idx;
        return `<button role="tab" class="walk-ph ${cur ? "cur" : ""} ${done ? "done" : ""}" data-go="${idx}" aria-selected="${cur}">
          ${esc(PHASE_LABEL[ph] ?? ph)}${n > 1 ? `<span class="n">${cur ? `${steps.slice(0, i + 1).filter((s) => s.phase === ph).length}/` : ""}${n}</span>` : ""}</button>`;
      }).join("")}</div>
      <div class="walk-body"><h4>${esc(st.title)}</h4><div class="text">${st.body}</div></div>
      ${st.frames?.length ? `<div class="walk-frames"><button data-walk="play" aria-label="Play the days">▶</button>
        <input type="range" min="0" max="${st.frames.length - 1}" value="${st.frames.length - 1}" aria-label="Day">
        <span class="day mono small"></span></div>` : ""}
      <div class="walk-nav">
        <button data-walk="prev" ${i === 0 ? "disabled" : ""}>◀ Back</button>
        <span class="mono small muted">${i + 1} / ${steps.length} · ← →</span>
        <button data-walk="next" class="${i === steps.length - 1 ? "" : "primary"}" ${i === steps.length - 1 ? "disabled" : ""}>Next ▶</button>
      </div>`;
    host.querySelector('[data-walk="close"]').addEventListener("click", close);
    host.querySelector('[data-walk="prev"]').addEventListener("click", () => go(i - 1));
    host.querySelector('[data-walk="next"]').addEventListener("click", () => go(i + 1));
    for (const b of host.querySelectorAll("[data-go]")) b.addEventListener("click", () => go(+b.dataset.go));
    const rng = host.querySelector(".walk-frames input");
    rng?.addEventListener("input", () => { stopPlay(); frameIdx = +rng.value; applyFrame(st); });
    host.querySelector('[data-walk="play"]')?.addEventListener("click", (ev) => {
      if (playing) { stopPlay(); return; }
      frameIdx = 0;
      applyFrame(st);
      ev.currentTarget.textContent = "❚❚";
      playing = setInterval(() => {
        frameIdx += 1;
        if (frameIdx >= st.frames.length) { stopPlay(); return; }
        applyFrame(st);
      }, store.settings.reducedMotion ? 60 : 260);
    });
    apply(st);
  }

  // the scopes worth walking through after a scripted step: its news and releases (not the routine daily
  // data, ME-D-*) and its theses
  function scopesSince(seq) {
    const out = [];
    for (const e of store.traces) {
      if (e.seq <= seq || !e.scope || out.includes(e.scope)) continue;
      if (/^T-/.test(e.scope)) out.push(e.scope);
      else if (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope)) out.push(e.scope);
    }
    return out;
  }

  function latestScope() {
    for (let k = store.traces.length - 1; k >= 0; k--) {
      const e = store.traces[k];
      if (!e.scope) continue;
      if (/^T-/.test(e.scope)) return e.scope;
      if (e.kind === "market_event.received" && !/^ME-D-/.test(e.scope)) return e.scope;
    }
    return null;
  }

  return { open, close, isOpen, next: () => go(i + 1), prev: () => go(i - 1), scopesSince, latestScope };
}
