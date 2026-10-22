// The walkthrough. DECISION: the user asked to step through what the model does, for learning and for
// inference, and to see a market event travel from fuzzy to real. The walkthrough reads one scope's trace
// events (one market event's, or one thesis's) and turns them into steps; each step frames and lights up
// what it touched on the canvas, and ◀ ▶ (or ← →) move between steps. Like the animator, it computes
// nothing: it replays the trace.
import { api } from "../api.js";
import { prettyNode } from "../graph/fuzzy.js";
import { names, OP_WORDS } from "../names.js";
import { emit, store } from "../store.js";
import { esc, fmt, signed } from "../util.js";

const LEVELS = ["generalization", "entity", "subentity"];
const LEVEL_WORDS = { generalization: "a generalization (fuzzy)", entity: "an entity", subentity: "a subentity (real)" };
const METER_WORDS = ["generalization", "entity", "subentity"];
const NET_COLORS = ["#B07CC0", "#5F7AA3", "#A9764B", "#4F8C80", "#A86D80", "#8C7A66", "#958C4F"];
// DECISION (Oct 8): the flowchart is the source of truth. Every step of a walkthrough is one node of a flowchart
// (learning: flows "world-model"; inference: "inference", both from /api/flows), the chips are grouped under the
// flowchart's stages in the stages' colors, and each step says which node it is. A stage whose optional steps did
// not run for this event still shows, dimmed, so the walkthrough always reads as the whole flowchart.
const FLOW_OF = { learn: "world-model", predict: "inference" };
const NODE_OF = {
  learn: {
    received: "event", translated: "translate", refined: "refine", parsed: "parse", classified: "classify",
    recalled: "recall", prefilled: "recall", analyzed: "ripple", folded: "fold", weighed: "hedges", generalized: "kinds",
    noticed: "frontier", reviewed: "check",
  },
  predict: {
    posed: "question", refined: "translate", parsed: "branch", classified: "branch", recalled: "networks",
    prefilled: "networks", isolated: "networks", predicted: "alone", coupled: "couple", unified: "weigh",
    read: "paths", explained: "brief",
  },
};
const LEARN_ORDER = ["received", "translated", "refined", "parsed", "classified", "recalled", "prefilled",
                     "analyzed", "folded", "weighed", "generalized", "noticed", "reviewed"];
const PREDICT_ORDER = ["posed", "refined", "parsed", "classified", "recalled", "prefilled", "isolated", "predicted",
                       "coupled", "unified", "read", "explained"];
// short chip names, in the flowchart's words
const PHASE_LABEL = {
  learn: {
    received: "Event", translated: "Translate", refined: "Refine", parsed: "Parse", classified: "Classify",
    recalled: "Recall", prefilled: "Recall: adjust", analyzed: "Ripple", folded: "Fold", weighed: "Fuzzy ends", generalized: "Concepts",
    noticed: "Frontier & support", reviewed: "Review",
  },
  predict: {
    posed: "Thesis", refined: "Refine", parsed: "Branch", classified: "Branch: classify", recalled: "Recall",
    prefilled: "Recall: adjust", isolated: "Networks", predicted: "Simulate alone", coupled: "Couple",
    unified: "Weigh", read: "Read out", explained: "Brief",
  },
};
let FLOWS = null;           // id -> flow, from /api/flows (loaded once)

function chip(text, cls = "") {
  return `<span class="wchip ${cls}">${esc(text)}</span>`;
}

// how specific an op end is: a generalization (fuzzy) → an entity → a subentity (real)
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
  return `<div class="zlist">${pairs.map(([id, z]) => `<span class="nm" title="${esc(id)}">${(nm.valueHtml(id))}</span>
    <span class="zbar"><i class="${z >= 0 ? "up" : "down"}" style="width:${((Math.abs(z) / m) * 50).toFixed(1)}%"></i></span>
    <span class="mono ${z > 0 ? "z-up" : "z-down"}">${signed(z)} ${unit}</span>`).join("")}</div>`;
}

// recall scores as a short list of bars
function attnList(pats, nm) {
  if (!pats.length) return "<p class='muted'>Nothing recalled.</p>";
  const m = Math.max(...pats.map((x) => x.attention), 1e-9);
  return `<div class="zlist attn">${pats.map((x) => `<span class="nm">${(nm.valueHtml(x.id))}</span>
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
  const opList = () => [...ops.values()].map((o) => `<li>${chip(OP_WORDS[o.op] ?? (o.op ? o.op.replace(/_/g, " ") : "op"))} ${esc(nm.text(o.label))}
      ${Object.entries(o.ends).map(([end, x]) => `<div class="end"><span class="small muted">${esc(end)}</span> ${meter(x.level)}
        <span class="small">${x.ref ? (nm.valueHtml(x.ref)) : ""}</span></div>`).join("")}</li>`).join("");

  const rec = of("market_event.received")[0];
  if (rec) {
    const p = rec.payload;
    steps.push({ phase: "received", title: "A market event arrives",
      body: `<p><b>${esc(p.headline)}</b></p><p class="small muted">${esc(p.source ?? "")} · ${esc(String(p.published_at ?? "").slice(0, 16).replace("T", " "))}
        · ${p.channel === "data_feed" ? "a scheduled data release" : p.channel === "user" ? "entered by a backend user" : "found by the web scraper"} · synthetic</p>
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
    steps.push({ phase: "translated", title: `Translated into ${ops.size} proposed operation${ops.size === 1 ? "" : "s"}`,
      body: `<p>The translator reads the text as ${ops.size} proposed operation${ops.size === 1 ? "" : "s"} on the graph. Nothing is applied yet. Each end is only as specific as the text allows.
        ${fuzzy ? "On the canvas, a wide band is a fuzzy end; it narrows as the end becomes real." : "Here every end is already a subentity: the release names it."}</p>
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
      ${meter(x.level, end === p.end ? from : null)} <span class="small">${(nm.valueHtml(x.ref))}</span></div>`).join("");
    steps.push({ phase: "refined", title: `Fuzzy → real: the ${p.end} end narrows`,
      body: `<ul class="wlist ops"><li>${chip(OP_WORDS[o.op] ?? (o.op ? o.op.replace(/_/g, " ") : "op"))} ${esc(nm.text(o.label ?? ""))}${endsNow}</li></ul>
        <p>The ${esc(p.end)} end becomes <b>${(nm.valueHtml(p.node_id))}</b>${p.created ? " (new, created for this news)" : ""}.</p>
        ${cands.length ? `<p class="small">The refiner scored ${cands.map(([c, s]) => `${chip(nm.value(c))}<span class="mono faint">${fmt(s)}</span>`).join(" ")}</p>` : ""}
        ${p.reason ? `<p class="small muted">${esc(p.reason)}</p>` : ""}`,
      visual: { ribbons: ribbons(), peek: concrete(), candidates: p.candidates ?? [], pulse: [p.node_id] },
      focus: [p.node_id, ...cands.map(([c]) => c)] });
  }
  const candName = (c) => (c === "__open__" ? "one not in the graph yet" : c.split("|").map((x) => nm.value(x)).join(" → "));
  for (const r of of("refine.pending")) {
    const p = r.payload;
    const cands = (p.candidates ?? []).slice(0, 5);
    const real = cands.filter(([c]) => c !== "__open__");
    steps.push({ phase: "refined", title: `The ${p.end} end stays fuzzy: a hedge across ${real.length} candidate${real.length === 1 ? "" : "s"}`,
      body: `<p>${meter(LEVELS[p.level] ?? "generalization")}</p>
        <p>The article describes this end but names none of its candidates, so nothing is chosen. Each keeps a probability, with a share for one
          not in the graph yet${p.soft ? ", and each candidate value gets a soft interaction as strong as it is probable, so forecasts hedge across them" : ""}.
          Later articles move the odds; a resolution needs a person's approval.</p>
        ${cands.length ? `<p class="small">${cands.map(([c, v]) => `${chip(candName(c))}<span class="mono faint">${Math.round(100 * v)}%</span>`).join(" ")}</p>` : ""}`,
      visual: { ribbons: ribbons(), candidates: real }, focus: real.map(([c]) => c.split("|")[0]) });
  }
  const parsed = of("parse.created").filter((e) => !e.payload.transient);
  if (parsed.length) {
    const p = parsed[0].payload;
    const made = [...(p.entities ?? []), ...(p.subentities ?? []), ...(p.interactions ?? [])];
    steps.push({ phase: "parsed", title: made.length ? "Proposes new structure" : "Proposes no new structure",
      body: made.length ? `<p>On a staged copy, it proposes adding ${made.map((m) => chip(nm.value(m), "new")).join(" ")}. They are proposals until a person approves them (dashed on the canvas while they wait).</p>`
        : "<p>Everything it mentions already exists, so it proposes nothing new.</p>",
      visual: { peek: p.subentities ?? [], pulse: made }, focus: made.length ? made : concrete() });
  }
  const cls = of("classify.path");
  if (cls.length) {
    const rows = cls.slice(0, 5).map((e) => `<li>${chip(nm.value(e.payload.item_id))} → ${(e.payload.path ?? []).slice(1).map((g) => esc(prettyNode(g))).join(" → ") || "<span class='muted'>root</span>"}${e.payload.is_new ? " <span class='badge ltm'>new</span>" : ""}</li>`);
    steps.push({ phase: "classified", title: "Proposes where each item belongs",
      body: `<p>Each touched item is sorted down the taxonomies of objects and interactions. Where it would land decides which priors it would inherit.</p>
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
    steps.push({ phase: "prefilled", title: "Proposes adjusted expectations from what it recalled",
      body: `${bound.length ? `<p>A recalled pattern binds to today's entities: ${bound.map((e) => chip(nm.value(e.payload.pattern_id))).join(" ")}.</p>` : ""}
        ${pre.length ? `<p>Before reading the numbers, it proposes new expectations for ${pre.length} link${pre.length === 1 ? "" : "s"}:</p>
          <ul class="wlist">${pre.slice(0, 3).map((e) => `<li>${chip(nm.value(e.payload.interaction_id))} effect ${fmt(e.payload.effect_before)} → <b>${fmt(e.payload.effect_after)}</b></li>`).join("")}</ul>` : ""}`,
      visual: { highlight: hl({ links: pre.map((e) => e.payload.interaction_id), hot: pre.map((e) => e.payload.interaction_id) }) },
      focus: linkEnds.length ? linkEnds : bound.map((e) => e.payload.instance_id ?? e.payload.pattern_id) });
  }
  const frames = of("propagation.frame").filter((e) => String(e.payload.run_id ?? "").startsWith("analyze:"));
  const ad = of("analyze.done")[0];
  if (ad || frames.length) {
    const moves = top(ad?.payload.expected_moves ?? frames[frames.length - 1]?.payload.z, 5);
    // the ripple by order (addition): direct effects, then those that pass through one or two more values
    const orders = ad?.payload.orders ?? [];
    const byOrder = new Map();
    for (const o of orders) { if (!byOrder.has(o.order)) byOrder.set(o.order, []); byOrder.get(o.order).push(o); }
    const ordWord = (n) => (n === 1 ? "First-order" : n === 2 ? "Second-order" : n === 3 ? "Third-order" : `${n}th-order`);
    const orderHtml = byOrder.size ? `<div class="small" style="margin-top:6px">${[...byOrder.entries()].sort((a, b) => a[0] - b[0]).map(([k, l]) =>
      `<div><span class="ord">${esc(ordWord(k))}</span> ${l.slice(0, 4).map((o) => `${(nm.valueHtml(o.id))} <span class="mono ${o.peak > 0 ? "z-up" : "z-down"}">${signed(o.peak)} sd</span>`).join(", ")}${l.length > 4 ? ` <span class="faint">+${l.length - 4} more</span>` : ""}</div>`).join("")}</div>` : "";
    steps.push({ phase: "analyzed", title: "Simulates the ripple it would set off",
      body: `<p>On the staged copy, the model runs the news through the graph to see where it would show up, and when: first, second, and third order. Press ▶ to watch the days.</p>
        ${zList(moves, nm)}${orderHtml}`,
      frames: frames.map((e) => e.payload), visual: {}, focus: moves.map(([sid]) => sid) });
  }
  const post = of("fold.posterior");
  const edges = of("fold.edge");
  if (post.length || edges.length) {
    const rows = post.slice(0, 4).map((e) => {
      const p = e.payload;
      return `<li>${chip(nm.value(p.subentity_id))} ${fmt(p.before?.q50)} → <b>${fmt(p.after?.q50)}</b>
        <span class="small muted">(now ${signed(p.z)} sd from normal)</span></li>`;
    }).join("");
    const erows = edges.slice(0, 3).map((e) => `<li>${chip(nm.value(e.payload.interaction_id))} effect ${fmt(e.payload.effect_before)} → <b>${fmt(e.payload.effect_after)}</b>, exists ${fmt(e.payload.existence_before)} → <b>${fmt(e.payload.existence_after)}</b></li>`).join("");
    const subs = post.map((e) => e.payload.subentity_id);
    steps.push({ phase: "folded", title: "Proposes updated beliefs",
      body: `<p>The observation is weighed against what the model expected. It proposes moving each value as far as the evidence warrants, and updating the links that carried the move:</p>
        ${rows ? `<ul class="wlist">${rows}</ul>` : ""}${erows ? `<ul class="wlist">${erows}</ul>` : ""}`,
      visual: { peek: subs, halos: Object.fromEntries(post.map((e) => [e.payload.subentity_id, e.payload.z])),
                highlight: hl({ entities: subs.map(nm.entityOf), links: edges.map((e) => e.payload.interaction_id), hot: edges.map((e) => e.payload.interaction_id) }) },
      focus: subs });
  }
  // one step per hedge and evidence (a replayed scope can carry the same weighing twice)
  const once = (list, key) => [...new Map(list.map((e) => [key(e.payload), e])).values()];
  for (const r of once(of("refine.weighed"), (p) => `${p.pending_id}:${JSON.stringify(p.checks)}`)) {
    const p = r.payload;
    const post = Object.entries(p.posterior ?? {}).sort((a, b) => (a[0] === "__open__") - (b[0] === "__open__") || b[1] - a[1]);
    const words = { narrowed: "is the value the article names", mention: "names", move: "moved as the interaction predicts:", against: "moved against the interaction:" };
    steps.push({ phase: "weighed", title: "Proposes new odds for a fuzzy end",
      body: `<p>A fuzzy end held from an earlier article weighs this one as evidence:</p>
        <ul class="wlist">${(p.checks ?? []).map((c) => `<li>${chip(candName(c.candidate ?? ""))} ${esc(words[c.kind] ?? c.kind)} <span class="mono faint">+${fmt(c.weight)}</span></li>`).join("")}</ul>
        <p class="small">${post.map(([c, v]) => `${chip(candName(c))}<span class="mono faint">${Math.round(100 * v)}%</span>`).join(" ")}</p>`,
      visual: {}, focus: (p.checks ?? []).map((c) => (c.candidate ?? "").split("|")[0]).filter(Boolean) });
  }
  for (const r of once(of("refine.resolution_proposed"), (p) => p.pending_id)) {
    const p = r.payload;
    steps.push({ phase: "weighed", title: `A fuzzy end passes the bound: ${candName(p.candidate)} at ${Math.round(100 * p.posterior)}%`,
      body: `<p>After ${fmt(p.support, 0)} checks one candidate holds more than the bound, so the model proposes the resolution: keep it and retire
        its rivals' soft interactions. It goes to review like any other change.</p>`, visual: { pulse: [p.candidate] }, focus: [p.candidate] });
  }
  const gen = of("generalize.updated")[0];
  if (gen) {
    const sup = Object.entries(gen.payload.supports ?? {}).slice(0, 6);
    steps.push({ phase: "generalized", title: "Proposes lessons for its concepts",
      body: `<p>Long-term memory proposes that the concepts that classified this news gain support, so the next similar event would be classified with more confidence.</p>
        <p>${sup.map(([g, v]) => `${chip(prettyNode(g))}<span class="mono faint">${fmt(v, 1)}</span>`).join(" ")}</p>`, visual: {} });
  }
  const notice = evs.filter((e) => e.kind.startsWith("frontier.") || e.kind.startsWith("abduce."));
  if (notice.length) {
    const kinds = [...new Set(notice.map((e) => e.kind))];
    steps.push({ phase: "noticed", title: "Proposes patterns and co-movements to track",
      body: `<p>Long-term memory proposes logging the moves the graph does not explain on the correlation frontier, and counting recurring configurations toward new superentities:</p>
        <p>${kinds.slice(0, 6).map((k) => chip(`${k.replace(".", ": ").replace(/_/g, " ")} ×${notice.filter((e) => e.kind === k).length}`)).join(" ")}</p>`,
      visual: { pulse: notice.flatMap((e) => (e.refs ?? []).slice(1, 3)) }, focus: notice.flatMap((e) => (e.refs ?? []).slice(1, 3)).slice(0, 8) });
  }
  // the review comes last: everything above was a proposal on a staged copy, and the person vets all of it at once;
  // what approval commits is stated here, so the walkthrough ends on the decision
  const queued = of("review.queued")[0];
  const auto = of("review.auto")[0];
  const decided = of("review.decided").filter((e) => e.payload.decision !== "edited").slice(-1)[0];
  const edited = of("review.decided").some((e) => e.payload.decision === "edited");
  // one line per version (a replayed scope can carry the same commit twice)
  const commits = [...new Map(of("state.version")
    .filter((e) => ["learn.working", "learn.long_term", "structural", "review"].includes(e.payload.process))
    .map((e) => [e.payload.version, e])).values()];
  const word = { "learn.working": "working memory", "learn.long_term": "long-term memory", structural: "the graph's structure", review: "the review's effects" };
  if (queued || auto || commits.length) {
    const verdict = decided ? String(decided.payload.decision).replace(/_/g, " ") : auto ? "signed off by the review policy" : null;
    const dec = verdict ? `<p>Decision: <b>${esc(verdict)}</b>${decided?.payload.by ? ` by ${esc(decided.payload.by)}` : ""}${edited ? ", with some proposals deselected" : ""}.</p>`
      : "<p>It is waiting for a decision. Nothing above has changed the model.</p>";
    const wrote = commits.length ? `<p>Only what was approved was written, through the same learning that was staged:</p>
        <ul class="wlist">${commits.map((e) => `<li>${chip(`v${e.payload.version}`)} to ${esc(word[e.payload.process] ?? e.payload.process)}
          <span class="small muted">${e.payload.changes} changes</span></li>`).join("")}</ul>
        <p class="small muted">The log (Console) keeps every version; any one can be reopened or compared.</p>` : "";
    steps.push({ phase: "reviewed", title: queued || !auto ? "Review: a person vets every proposal" : "Review: signed off by the review policy",
      body: `${queued || !auto ? `<p>Every step above was a proposal on a staged copy of the model. Before anything was written, a person checked all of it:
          the new or retired structure, the event's own move, the ripple at second and third order, and what long-term memory would learn.</p>`
        : `<p>Every step above was a proposal on a staged copy. This item only reports values, and the review policy in this scenario signs those off; in the demos a person vets every proposal.</p>`}${dec}${wrote}`,
      visual: { ribbons: ribbons().map((x) => ({ ...x, proposed: true })), peek: concrete() }, focus: touched() });
  }
  return steps;
}

// -- inference: one thesis -----------------------------------------------------------------------------
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
        <p class="small muted">Horizon ${p.horizon_days} days${(p.target_groups ?? []).length ? `; also forecast for ${p.target_groups.map((g) => (nm.valueHtml(g.split(":")[1]))).join(", ")}` : ""}.</p>`,
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
      body: `<p>${meter(to, from)}</p><p>To <b>${(nm.valueHtml(p.node_id))}</b>.</p>`,
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
        <p>${nets.map((n, i) => `<span class="wchip" style="border-color:${NET_COLORS[i % NET_COLORS.length]};border-width:2px">${esc(n.kind === "residual" ? "residual" : nm.value(n.pattern_id ?? n.name))}</span><span class="mono faint">${fmt(n.relevance)}</span>`).join(" ")}</p>`,
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
    steps.push({ phase: "predicted", title: `Predicted within ${n?.kind === "residual" ? "the residual" : nm.value(n?.pattern_id ?? p.name)}`,
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
      body: "<p>The networks are joined across the interactions between them, so effects can cross from one superentity into another, for example from the energy shock into credit tightening.</p>",
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
        <ul class="wlist">${paths.slice(0, 3).map((p) => `<li>${(nm.valueHtml(p.shock_id))} → ${(p.interaction_ids ?? []).map((i) => (nm.valueHtml(i))).join(" → ")} → <b>${(nm.valueHtml(p.target_id))}</b> <span class="muted small">${fmt((p.share ?? 0) * 100, 0)}%</span></li>`).join("")}</ul>`,
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
    if (!FLOWS) {
      try { FLOWS = new Map((await api.flows()).map((f) => [f.id, f])); } catch { FLOWS = new Map(); }
    }
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
    if (v.pulse?.length) setTimeout(() => renderer.pulse(v.pulse, kind === "predict" ? "#B07CC0" : "#7C64C4", 500), 180);
    for (const h of v.flashHulls ?? []) setTimeout(() => renderer.flashHull(h, 600), 180);
    if (v.candidates?.length) setTimeout(() => renderer.flashCandidates(v.candidates, 800), 220);
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
    const flow = FLOWS?.get(FLOW_OF[kind]);
    const nodeOf = (ph) => flow?.nodes.find((n) => n.id === NODE_OF[kind][ph]);
    const stageOf = (ph) => nodeOf(ph)?.phase ?? "";
    const cls = (stage) => (kind === "predict" ? "st-inference" : `st-${stage}`);
    const chipFor = (ph) => {
      const idx = steps.findIndex((s) => s.phase === ph);
      const nd = nodeOf(ph);
      if (idx < 0) {
        // DECISION: every walkthrough shows the same steps, in the flowchart's order; one this event did not need is dimmed
        return `<span class="walk-ph ${cls(stageOf(ph))} skip" title="${esc(`${nd?.label ?? ""}: not needed for this event${nd?.when ? ` (runs only if ${nd.when})` : ""}`)}">${esc(PHASE_LABEL[kind][ph] ?? ph)}</span>`;
      }
      const n = steps.filter((s) => s.phase === ph).length;
      const cur = st.phase === ph;
      const done = steps.findIndex((s) => s.phase === st.phase) > idx;
      return `<button role="tab" class="walk-ph ${cls(stageOf(ph))} ${cur ? "cur" : ""} ${done ? "done" : ""}" data-go="${idx}" aria-selected="${cur}"
        title="${esc(nd?.label ?? "")}">${esc(PHASE_LABEL[kind][ph] ?? ph)}${n > 1 ? `<span class="n">${cur ? `${steps.slice(0, i + 1).filter((s) => s.phase === ph).length}/` : ""}${n}</span>` : ""}</button>`;
    };
    // the flowchart's stages, each with its steps; learning ends at the review (what it commits is told there)
    const stages = flow ? flow.phases.filter((sp) => kind === "predict" || sp.id !== "commit") : [{ id: "", title: "" }];
    const all = [...new Set(order.filter((ph) => NODE_OF[kind][ph]))];
    const stageRow = stages.map((sp, k) => {
      const mine = all.filter((ph) => !flow || stageOf(ph) === sp.id);
      const ran = mine.filter((ph) => phases.includes(ph));
      const name = sp.title.replace("Learning · ", "") + (sp.id === "review" ? ", then commit" : "");
      return `<div class="walk-stage ${cls(sp.id)}${ran.length ? "" : " idle"}${mine.includes(st.phase) ? " on" : ""}">
        <span class="walk-st" title="${esc(sp.input ? `In: ${sp.input}. Out: ${sp.output}` : "")}">${flow ? `${k + 1} · ${esc(name)}` : ""}</span>
        <span class="walk-chips">${mine.length ? mine.map(chipFor).join("") : `<span class="walk-none">not needed</span>`}</span></div>`;
    }).join("");
    const node = nodeOf(st.phase);
    const where = node ? `<p class="walk-fc small"><span class="walk-fc-k">Flowchart</span>
      ${esc(flow.phases.find((x) => x.id === node.phase)?.title.replace("Learning · ", "") ?? "")} → “${esc(node.label)}”
      <button class="linkish small" data-walk="flow">see it ▸</button></p>` : "";
    host.innerHTML = `
      <div class="walk-head">
        <span class="badge ${kind === "predict" ? "hyp" : "real"}">${kind === "predict" ? "How it inferred" : "How it learned"}</span>
        <span class="walk-title" title="${esc(title)}">${esc(title)}</span>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button><button class="close" data-walk="close" aria-label="Close the walkthrough (Esc)">✕</button>
      </div>
      <div class="walk-phases" role="tablist">${stageRow}</div>
      <div class="walk-body"><h4>${esc(st.title)}</h4>${where}<div class="text">${st.body}</div></div>
      ${st.frames?.length ? `<div class="walk-frames"><button data-walk="play" aria-label="Play the days">▶</button>
        <input type="range" min="0" max="${st.frames.length - 1}" value="${st.frames.length - 1}" aria-label="Day">
        <span class="day mono small"></span></div>` : ""}
      <div class="walk-nav">
        <button data-walk="prev" ${i === 0 ? "disabled" : ""}>◀ Back</button>
        <span class="mono small muted">${i + 1} / ${steps.length} · ← →</span>
        <button data-walk="next" class="${i === steps.length - 1 ? "" : "primary"}" ${i === steps.length - 1 ? "disabled" : ""}>Next ▶</button>
      </div>`;
    host.querySelector('[data-walk="close"]').addEventListener("click", close);
    host.querySelector('[data-walk="flow"]')?.addEventListener("click", () => emit("open-methods", {
      tab: kind === "predict" ? "inference" : "how", anchor: `stage-${node.phase}` }));
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
      }, store.settings.reducedMotion ? 40 : 140);
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
