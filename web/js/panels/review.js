// Review (Oct 8 restructure): the human in the loop sits at the end of learning. The server runs a proposal's
// whole learning on a copy of the model (control/stage.py) and this pane shows everything that copy would
// commit, grouped by stage in the stages' colors: intake (the article), working memory (each new or retired item,
// selectable one by one; the ripple at first, second, and third order with the path each takes; what the fold
// settles), and long-term memory (what recall drew on, and its lessons by store), then your decision. Each memory
// opens with what it is. While a proposal is open here the canvas shows the staged graph, with its transmission path
// in a lane above the rest of the model (renderer.setLane): new items in a dashed outline, retired ones in red, moved
// values tinted by order. Approving commits only the selected items.
import { api } from "../api.js";
import { scatter } from "../charts/fan.js";
import { names } from "../names.js";
import { clearStaged, emit, on, refreshGraph, showStaged, store } from "../store.js";
import { errorText, esc, fmt, signed } from "../util.js";

const KIND_LABEL = {
  graph_update: "Graph update", refinement: "Refinement", frontier_promotion: "Frontier promotion",
  superentity_admission: "Collapse", superentity_dissolution: "Expansion", missing_relation: "Missing relation",
};
const KIND_HELP = {
  graph_update: "A graph update event, from news, a data release, or a backend user's edit.",
  refinement: "A graph update event whose fuzzy ends later evidence resolved to concrete values.",
  frontier_promotion: "A co-movement on the correlation frontier, verified often enough to be proposed as a causal interaction.",
  superentity_admission: "A group of entities and the interactions among them, proposed as one superentity.",
  superentity_dissolution: "A superentity proposed to break back into its constituents.",
  missing_relation: "A superentity predicts an interaction the graph does not have yet.",
};
const ORDER = ["The event's own move", "First order", "Second order", "Third order"];
const ACTION_MARK = { add: "+", retire: "−", move: "↕", observe: "◉", collapse: "⊂", expand: "⊃", hedge: "≈" };
const pct = (x) => `${Math.round(100 * x)}%`;
// a value the server names reads "Entity · subentity" (names.js), by its id when it has one, else by its name in prose
const subOr = (id, name) => { const nm = names(); return nm.subs.has(id) ? nm.valueHtml(id) : nm.namedHtml(name ?? id ?? ""); };
const prose = (s) => names().namedHtml(s);

// a hedge's candidates as bars (Oct 8): each candidate's probability, with its value before this event when known
function hedgeBars(cands, { before = false } = {}) {
  return `<ul class="hg-bars">${cands.map((c) => `<li class="${c.id === "__open__" ? "open" : ""}">
    <span class="hg-name">${c.id === "__open__" ? esc(c.name) : subOr(c.id, c.name)}</span>
    <span class="hg-bar"><i style="width:${(100 * c.p).toFixed(1)}%"></i>${before && c.before != null
      ? `<b class="hg-was" style="left:${(100 * c.before).toFixed(1)}%" title="before: ${pct(c.before)}"></b>` : ""}</span>
    <span class="mono hg-p">${before && c.before != null && Math.abs(c.before - c.p) >= 0.005 ? `${pct(c.before)} → ` : ""}<b>${pct(c.p)}</b></span></li>`).join("")}</ul>`;
}
const EVIDENCE_WORD = { narrowed: "is the value the article names:", mention: "names", move: "moved as the interaction predicts:", against: "moved against the interaction:",
                        rejected: "a reviewer rejected", intake: "first read" };
const STAGE_STATE = { done: "✓", waiting: "●", next: "○", skipped: "–" };

// what the fold settles, in words: a value from before to after in its unit, a belief as a probability, an effect per sd
function foldRow(x) {
  const chg = x.before ? ` <span class="muted">(${signed(100 * (x.after - x.before) / Math.abs(x.before), 1)}%)</span>` : "";
  if (x.kind === "existence") {
    return `Belief that <b>${prose(x.name)}</b> exists: ${x.before == null ? "new" : `${(100 * x.before).toFixed(1)}%`} → <b>${(100 * x.after).toFixed(1)}%</b>`;
  }
  if (x.kind === "effect") {
    return `Effect of <b>${prose(x.name)}</b>: ${x.before == null ? "new" : fmt(x.before)} → <b>${fmt(x.after)}</b> sd per sd`;
  }
  return `<b>${subOr(x.ref, x.name)}</b>: ${x.before == null ? "new" : fmt(x.before)} → <b>${fmt(x.after)}</b> ${esc(x.unit ?? "")}${chg}`;
}

// a lesson, under the long-term store it lands in, said plainly (control/stage.py writes them)
const STORES = [
  { re: /^A new kind|^Kind “|^Statistics update along/, name: "Object and interaction generalizations", what: "the kinds of things it has seen" },
  { re: /^Superentity/, name: "Superentities", what: "patterns of entities that recur together" },
  { re: /entity memory/, name: "Entity memories", what: "each actor's decisions, by the context they were made in" },
  { re: /co-movement|correlation frontier/, name: "Correlation frontier", what: "co-movements with no interaction to explain them yet" },
  { re: /prior states/, name: "Prior states", what: "past days that recall can return to" },
];
function lessonText(x) {
  const m = /^Statistics update along (.*)$/.exec(x);
  if (m) {
    return `Refines how often, and how far, these kinds move: ${m[1].split(", ").map((k) => `<span class="rv-kind">${esc(k)}</span>`).join(" ")}`;
  }
  if (/^The explanation of what was learned is stored with the prior states$/.test(x)) {
    return "Keeps today as a prior state, with an explanation of what changed and why, so recall can bring it back when a similar article arrives";
  }
  return prose(x);
}
function keepsList(lessons) {
  const by = new Map();
  for (const x of lessons) {
    const st = STORES.find((s) => s.re.test(x)) ?? { name: "Long-term memory", what: "" };
    if (!by.has(st.name)) by.set(st.name, { st, xs: [] });
    by.get(st.name).xs.push(x);
  }
  return `<dl class="rv-keeps">${[...by.values()].map(({ st, xs }) => `<dt>${esc(st.name)}${st.what ? ` <span class="muted">· ${esc(st.what)}</span>` : ""}</dt>
    ${xs.map((x) => `<dd>${lessonText(x)}</dd>`).join("")}`).join("")}</dl>`;
}

export function initReview({ openModal, toast, onFocusGraph }) {
  const body = document.getElementById("review-body");
  const counts = [document.getElementById("review-count"), document.getElementById("review-count-tab")];
  const st = { focused: null, keep: new Map(), review: null, loading: false, ticket: 0, open: false,
               conf: new Map(), openConf: null, openRip: null };
  // the reviewer's confidence per proposal (Oct 8): {all: the article's (null: as it came), ops: {index: c}}; and
  // ripple (Oct 9): {subentity id: the probability its ripple arrives (null: as the analysis expects)}
  const confOf = (id) => {
    if (!st.conf.has(id)) st.conf.set(id, { all: null, ops: {}, ripple: {} });
    return st.conf.get(id);
  };

  // -- the list of waiting proposals ----------------------------------------------------------------
  function render() {
    const ps = store.proposals ?? [];
    for (const c of counts) {
      c.textContent = String(ps.length);
      c.classList.toggle("hot", ps.length > 0);
    }
    document.getElementById("btn-review")?.classList.toggle("idle", !ps.length);
    if (!ps.length) {
      st.focused = null;
      st.review = null;
      clearStaged();
      body.innerHTML = `<div class="rv-empty"><p><b>Nothing waits for review.</b></p>
        <p class="small muted">Every change to the world model stops here first. Learning runs on a staged copy, and you see
        what it would commit, down to the second- and third-order ripple, before anything changes.</p>
        ${!!store.status?.examples ? `<button class="primary" data-examples>Pick an example event</button>` : ""}</div>`;
      body.querySelector("[data-examples]")?.addEventListener("click", () => emit("open-examples"));
      return;
    }
    if (!ps.some((p) => p.proposal.id === st.focused)) {
      st.focused = ps[0].proposal.id;
      st.review = null;
    }
    const others = ps.length > 1 ? `<nav class="rv-queue" aria-label="Waiting proposals">${ps.map((pv) => `
      <button class="rv-q${pv.proposal.id === st.focused ? " sel" : ""}" data-pr="${esc(pv.proposal.id)}"
        title="${esc(pv.proposal.reason ?? pv.proposal.event.id)}">${esc(KIND_LABEL[pv.proposal.kind] ?? pv.proposal.kind)} · ${esc(pv.proposal.id)}</button>`).join("")}</nav>` : "";
    body.innerHTML = `${others}<div class="rv-card" aria-live="polite"></div>`;
    for (const b of body.querySelectorAll(".rv-q")) b.addEventListener("click", () => focus(b.dataset.pr));
    renderCard();
    if (st.open && (!st.review || st.review.proposal_id !== st.focused)) restage();
  }

  function focus(id) {
    if (id === st.focused) return;
    st.focused = id;
    st.review = null;
    render();
  }

  const pvOf = (id) => (store.proposals ?? []).find((x) => x.proposal.id === id);
  const keepOf = (id) => {
    if (!st.keep.has(id)) {
      const pv = pvOf(id);
      st.keep.set(id, new Set((pv?.proposal.event.ops ?? []).map((_, i) => i)));
    }
    return st.keep.get(id);
  };

  // -- staging ------------------------------------------------------------------------------------------
  let timer = null;
  function restage(delay = 0) {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const id = st.focused;
      if (!id || !st.open || st.deciding === id || !pvOf(id)) return;
      const ticket = ++st.ticket;
      st.loading = true;
      renderCard();
      try {
        const c = confOf(id);
        const r = await api.stage(id, [...keepOf(id)].sort((a, b) => a - b), c.all, c.ops, c.ripple);
        if (ticket !== st.ticket || id !== st.focused || st.deciding === id) return;
        st.review = r;
        st.loading = false;
        showStaged(r);
        onFocusGraph?.(r);
      } catch (err) {
        if (ticket !== st.ticket) return;
        st.loading = false;
        st.review = { error: errorText(err), proposal_id: id };
      }
      renderCard();
    }, delay);
  }

  // -- the focused proposal ---------------------------------------------------------------------------
  function renderCard() {
    const card = body.querySelector(".rv-card");
    if (!card) return;
    const pv = pvOf(st.focused);
    if (!pv) { card.innerHTML = ""; return; }
    const p = pv.proposal;
    const r = st.review && st.review.proposal_id === p.id ? st.review : null;
    const keep = keepOf(p.id);
    const nAll = p.event.ops.length;
    const scroll = card.querySelector(".rv-scroll")?.scrollTop ?? 0;
    card.innerHTML = `
      <header class="rv-head">
        <div class="meta" title="${esc(p.id)}${p.market_event_id ? ` · ${esc(p.market_event_id)}` : ""}"><span class="badge out" title="${esc(KIND_HELP[p.kind] ?? "")}">${esc(KIND_LABEL[p.kind] ?? p.kind)}</span>
          ${p.status === "deferred" ? `<span class="badge">deferred</span>` : ""}</div>
        <div class="rv-title">${esc(r?.headline ?? p.reason ?? p.event.id)}</div>
        ${r?.source ? `<div class="small muted">${esc(r.source)} · synthetic</div>` : ""}
      </header>
      ${flowStrip(r)}
      <div class="rv-scroll">
        ${r?.error && !r.items ? `<p class="error small">${esc(r.error)}</p>` : ""}
        ${!r ? `<p class="small muted">${st.loading || st.open ? "Staging: running learning on a copy of the model…" : "Open this pane to stage it."}</p>` : sections(r, keep)}
      </div>
      <footer class="rv-actions">
        <button class="primary" data-act="approve" title="Commit the selected changes (A)" ${keep.size || !nAll ? "" : "disabled"}>
          ${keep.size === nAll ? "Approve all" : `Approve ${keep.size} of ${nAll}`}</button>
        <button class="danger" data-act="reject" title="Nothing changes (R)">Reject…</button>
        <button data-act="defer" title="Decide later">Defer</button>
        <span class="spacer"></span>
        <button class="ghost small" data-act="edit" title="Edit the graph update event as JSON">Edit JSON</button>
      </footer>`;
    card.querySelector(".rv-scroll").scrollTop = scroll;
    card.querySelector('[data-act="approve"]').addEventListener("click", () => approve(p.id));
    card.querySelector('[data-act="reject"]').addEventListener("click", () => reject(p.id));
    card.querySelector('[data-act="defer"]').addEventListener("click", () => act(() => api.defer(p.id, "backend user"), `Deferred ${p.id}.`, p.id));
    card.querySelector('[data-act="edit"]').addEventListener("click", () => edit(p.id));
    for (const b of card.querySelectorAll("[data-stage]")) {
      b.addEventListener("click", () => {
        const scroller = card.querySelector(".rv-scroll");
        const target = card.querySelector(`#rvg-${CSS.escape(b.dataset.stage)}`);
        if (!target) { card.querySelector(".rv-actions")?.scrollIntoView({ block: "nearest" }); return; }
        scroller.scrollTo({ top: target.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop - 4,
          behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      });
    }
    for (const box of card.querySelectorAll("input[data-item]")) {
      box.addEventListener("change", () => toggle(p.id, +box.dataset.item, box.checked));
    }
    // confidence (Oct 8): the article's slider, and a change's own; each re-stages the event after a pause
    const showVal = (inp) => { const v = inp.parentElement.querySelector(".rv-conf-v"); if (v) v.textContent = `${inp.value}%`; };
    card.querySelector("[data-conf-all]")?.addEventListener("input", (ev) => {
      showVal(ev.target);
      confOf(p.id).all = +ev.target.value / 100;
      restage(450);
    });
    for (const b of card.querySelectorAll("[data-conf-item]")) {
      b.addEventListener("click", (ev) => { ev.preventDefault(); st.openConf = st.openConf === +b.dataset.confItem ? null : +b.dataset.confItem; renderCard(); });
    }
    for (const inp of card.querySelectorAll("[data-conf-op]")) {
      inp.addEventListener("input", () => {
        showVal(inp);
        confOf(p.id).ops[+inp.dataset.confOp] = +inp.value / 100;
        restage(450);
      });
    }
    for (const b of card.querySelectorAll("[data-conf-reset]")) {
      b.addEventListener("click", () => { confOf(p.id).ops[+b.dataset.confReset] = null; restage(0); });
    }
    // the ripple (Oct 9): a value's checkbox (0 or as expected) and its probability
    const setRip = (sid, v) => { confOf(p.id).ripple[sid] = v; };
    for (const box of card.querySelectorAll("input[data-rip]")) {
      box.addEventListener("change", () => { setRip(box.dataset.rip, box.checked ? null : 0); renderCard(); restage(250); });
    }
    for (const b of card.querySelectorAll("[data-rip-conf]")) {
      b.addEventListener("click", (ev) => { ev.preventDefault(); st.openRip = st.openRip === b.dataset.ripConf ? null : b.dataset.ripConf; renderCard(); });
    }
    for (const inp of card.querySelectorAll("[data-rip-p]")) {
      inp.addEventListener("input", () => { showVal(inp); setRip(inp.dataset.ripP, +inp.value / 100); restage(450); });
      inp.addEventListener("change", () => renderCard());
    }
    for (const b of card.querySelectorAll("[data-rip-reset]")) {
      b.addEventListener("click", () => { setRip(b.dataset.ripReset, null); renderCard(); restage(0); });
    }
    card.querySelector("[data-all]")?.addEventListener("click", () => setAll(p.id, true));
    card.querySelector("[data-none]")?.addEventListener("click", () => setAll(p.id, false));
    for (const m of card.querySelectorAll("mark[data-ops]")) {
      const ids = m.dataset.ops.split(" ");
      const rows = ids.map((i) => card.querySelector(`.rv-item[data-index="${i}"]`)).filter(Boolean);
      m.addEventListener("mouseenter", () => { for (const row of rows) row.classList.add("hl"); emit("staged-hover", rows.flatMap((row) => row.dataset.refs.split(" ")).filter(Boolean)); });
      m.addEventListener("mouseleave", () => { for (const row of rows) row.classList.remove("hl"); emit("staged-hover", null); });
    }
    for (const row of card.querySelectorAll(".rv-item[data-index]")) {
      const marks = [...card.querySelectorAll("mark[data-ops]")].filter((m) => m.dataset.ops.split(" ").includes(row.dataset.index));
      row.addEventListener("mouseenter", () => { for (const m of marks) m.classList.add("hl"); });
      row.addEventListener("mouseleave", () => { for (const m of marks) m.classList.remove("hl"); });
    }
    for (const el of card.querySelectorAll("[data-refs]")) {
      el.addEventListener("mouseenter", () => emit("staged-hover", el.dataset.refs.split(" ").filter(Boolean)));
      el.addEventListener("mouseleave", () => emit("staged-hover", null));
    }
    if (p.kind === "frontier_promotion" && p.subject_id) loadSeries(p);
  }

  // the stages as colored chips; each jumps to its group below (the same colors as How it works and the examples)
  function flowStrip(r) {
    const stages = r?.stages ?? [];
    if (!stages.length) return "";
    return `<div class="rv-flow" role="group" aria-label="The stages of learning, for this event">
      <ol class="rv-stages">${stages.map((s, k) => `<li><button data-stage="${esc(s.phase)}" class="rv-stage st-${esc(s.phase)} ${esc(s.status)}"
        title="${esc(`${s.title}. In: ${s.input}. Out: ${s.output}`)}"><span class="mk">${STAGE_STATE[s.status] ?? k + 1}</span>${esc(s.title.replace("Learning · ", ""))}</button></li>`).join("")}</ol></div>`;
  }

  // a group of the review: one stage, in its color, with its input and output
  function group(r, phase, body, empty, said, lede = "") {
    const s = (r.stages ?? []).find((x) => x.phase === phase);
    if (!s) return body;
    return `<section class="rv-group st-${esc(phase)}" id="rvg-${esc(phase)}">
      <header class="rv-gh"><span class="rv-gt">${esc(s.title.replace("Learning · ", ""))}</span>
        <span class="rv-gio" title="${esc(`In: ${s.input}. Out: ${s.output}`)}">${esc(said ?? s.output)}</span></header>
      ${lede ? `<p class="rv-lede">${lede}</p>` : ""}
      ${body.trim() ? body : `<p class="small muted rv-none">${esc(empty)}</p>`}</section>`;
  }

  // a check's progress (Oct 9): the top candidate against the bound, and the articles against the number needed
  function checkMeter(h, bound, needed) {
    const top = (h.candidates ?? []).filter((c) => c.id !== "__open__").reduce((a, c) => (!a || c.p > a.p ? c : a), null);
    if (!top) return "";
    const n = Math.round(h.support ?? 0);
    return `<div class="ck-meter small" title="A fuzzy end resolves when one candidate passes ${pct(bound)} and at least ${needed} articles have borne on it">
      <span class="ck-part ${top.p >= bound ? "met" : ""}"><span class="ck-bar"><i style="width:${Math.min(100, (100 * top.p) / bound).toFixed(0)}%"></i></span>
        ${subOr(top.id, top.name)} ${pct(top.p)} <span class="muted">of ${pct(bound)}</span></span>
      <span class="ck-part ${n >= needed ? "met" : ""}">${Array.from({ length: Math.max(needed, n) }, (_, k) => `<b class="ck-dot${k < n ? " on" : ""}"></b>`).join("")}
        ${n} of ${needed} articles</span></div>`;
  }

  // a co-movement's case: every spaced check it passed, as the article that moved the earlier value and the report of
  // the later one that followed. DECISION: a correlation is learned from many articles, not one; the review shows them all.
  function evidenceSection(ev, article) {
    const n = ev.checks.length;
    const word = ["", "Once", "Twice", "Three times", "Four times", "Five times"][n] ?? `${n} times`;
    const when = ev.lag_days ? `${ev.lag_days} days later` : "within days";
    const card = (a, cur) => `<div class="ev-art${cur ? " cur" : ""}"><div class="eh">${esc(a.headline)}</div>
      <div class="small muted">${esc(a.source)} · ${esc(a.date)}${cur ? " · this article" : ""}</div></div>`;
    return `<section class="rv-sec rv-evidence"><h4>The articles behind it</h4>
      <p class="ev-lede">${esc(word)}, ${prose(ev.earlier)} moved and ${prose(ev.later)} ${ev.sign > 0 ? "followed it" : "moved the other way"} ${esc(when)},
        with nothing in the graph to explain it. <span class="small muted">Correlation ${fmt(ev.corr)} over the checks; a person decides whether it is a cause.</span></p>
      <p class="small muted">Checked at most once every spaced interval: passed ${ev.consistent ?? n}, failed ${ev.inconsistent ?? 0}; it needed ${ev.needed ?? n} more passes than failures.
        ${ev.first_seen ? `First seen ${esc(ev.first_seen.date)} (not a check).` : ""}</p>
      <ol class="ev-checks">${ev.checks.map((c, k) => `<li><span class="ev-n">check ${k + 1}</span>
        <div class="ev-pair">${c.earlier.map((a) => card(a, a.id === article?.id)).join("")}<span class="ev-arrow" aria-hidden="true">→</span>
          ${c.later.map((a) => card(a, a.id === article?.id)).join("")}</div></li>`).join("")}</ol></section>`;
  }

  // a refinement: the fuzzy end it settles, and each article that moved the odds toward the winner
  function resolvesSection(h, bound) {
    const w = h.winner;
    // DECISION (Oct 9): a check is an article; the records one article left (a mention and a move) share its number
    const art = (c) => `${c.date}|${c.headline ?? ""}`;
    const nums = new Map();
    for (const c of h.checks ?? []) if (!["intake", "narrowed", "rejected"].includes(c.kind) && !nums.has(art(c))) nums.set(art(c), nums.size + 1);
    const label = (c) => (c.kind === "intake" ? "start" : c.kind === "narrowed" ? "narrowed" : c.kind === "rejected" ? "rejected" : `check ${nums.get(art(c))}`);
    return `<section class="rv-sec rv-evidence"><h4>The fuzzy end this settles</h4>
      <p class="ev-lede">${prose(h.label)}: <b>${subOr(w?.id, w?.name ?? "")}</b> now holds ${pct(w?.p ?? 0)}, past the ${pct(bound)} bound,
        after ${nums.size} article${nums.size === 1 ? "" : "s"} of evidence. <span class="small muted">Approving keeps it and retires its rivals; rejecting sends half its weight back to the open share.</span></p>
      ${hedgeBars(h.candidates)}
      <ol class="ev-checks">${(h.checks ?? []).map((c) => `<li><span class="ev-n">${label(c)}</span>
        <div class="ev-art"><div class="eh">${esc(c.headline ?? (c.kind === "intake" ? "The first article: the end is hedged" : ""))}</div>
          <div class="small muted">${esc(c.date)}${c.kind !== "intake" ? ` · ${prose(c.candidate ?? "")} ${esc(EVIDENCE_WORD[c.kind] ?? c.kind)}${c.kind === "mention" ? " here" : ""} (+${fmt(c.weight)})` : ""}
            ${c.p != null ? ` · ${subOr(w?.id, w?.name ?? "")} at ${pct(c.p)}` : ""}</div></div></li>`).join("")}</ol></section>`;
  }

  // the article, with each phrase that asked for an operation marked; hovering a phrase lights its items
  function articleSection(a) {
    if (!a) return "";
    const text = a.text ?? a.headline;
    const cuts = [...new Set([0, text.length, ...a.spans.flatMap(([s0, s1]) => [s0, s1])])].sort((x, y) => x - y);
    let html = "";
    for (let k = 0; k < cuts.length - 1; k++) {
      const [s0, s1] = [cuts[k], cuts[k + 1]];
      const ops = a.spans.filter(([b0, b1]) => b0 <= s0 && b1 >= s1).map(([, , i]) => i);
      const piece = esc(text.slice(s0, s1)).replace(/\n/g, "</div><div class=\"ab\">");
      html += ops.length ? `<mark data-ops="${[...new Set(ops)].join(" ")}" title="Asks for item ${[...new Set(ops)].map((i) => i + 1).join(", ")}">${piece}</mark>` : piece;
    }
    // the whole article (Oct 9), with the same phrases marked; it opens on request so the pane stays short
    let full = "";
    if (a.full_text) {
      const phrases = [...new Set(a.spans.map(([s0, s1]) => text.slice(s0, s1)))].filter((x) => x.length > 2);
      full = esc(a.full_text);
      for (const ph of phrases.sort((x, y) => y.length - x.length)) {
        const e = esc(ph);
        const at = full.indexOf(e);
        if (at >= 0) full = `${full.slice(0, at)}<mark>${e}</mark>${full.slice(at + e.length)}`;
      }
      full = full.split(/\n\s*\n/).map((para) => `<p>${para}</p>`).join("");
    }
    return `<section class="rv-sec rv-article"><h4>The article <span class="small muted">${esc(a.source)} · synthetic · hover a marked phrase</span></h4>
      <blockquote><div class="ah">${html}</div></blockquote>
      ${full ? `<details class="rv-full"><summary>Read the full article</summary><div class="rv-full-text">
        <div class="eh">${esc(a.headline)}</div><div class="small muted">${esc(a.source)} · ${esc(String(a.published_at ?? "").slice(0, 10))} · synthetic</div>${full}</div></details>` : ""}
      ${a.rationale ? `<p class="small muted">Read as: ${esc(a.rationale)}</p>` : ""}</section>`;
  }

  // the review, grouped by stage: intake (the article), working memory (the changes, recall, the ripple, the fold),
  // long-term memory (lessons and what they raise), then your decision and what it commits
  function sections(r, keep) {
    const items = r.items ?? [];
    const intake = [], working = [], longTerm = [];
    const c = confOf(r.proposal_id);
    const artConf = c.all ?? r.confidence ?? 1;
    if (r.error) working.push(`<p class="error small">The staged run failed: ${esc(r.error)}</p>`);
    const bound = r.bounds?.commit_posterior ?? 0.75;
    const needed = r.bounds?.recognition ?? 2;
    if (r.evidence?.checks?.length) intake.push(evidenceSection(r.evidence, r.article));
    if (r.resolves) intake.push(resolvesSection(r.resolves, bound));
    if (r.manual) {
      intake.push(`<section class="rv-sec rv-manual"><h4>From a backend user's own knowledge <span class="small muted">no article</span></h4>
        ${r.manual.note ? `<blockquote><div class="ah">“${esc(r.manual.note)}”</div></blockquote>` : ""}
        <p class="small muted">Their reason is kept as the evidence on what this adds, as an article's words would be.</p></section>`);
    }
    intake.push(articleSection(r.article));
    intake.push(`<div class="rv-conf" title="How far this article's changes should move the model: an interaction's existence and evidence, a report's weight, a move's expected size. 100% takes the article as stated; it applies to every change below unless you set one.">
      <label for="rv-conf-all"><b>Your confidence in this ${r.manual ? "addition" : "article"}</b></label>
      <input id="rv-conf-all" type="range" min="0" max="100" step="5" value="${Math.round(100 * artConf)}" data-conf-all aria-valuetext="${pct(artConf)}">
      <span class="mono rv-conf-v">${pct(artConf)}</span></div>`);
    // the items: one checkbox each; an item that needs another sits under it
    const depth = (it) => (it.requires.length ? 1 + Math.max(...it.requires.map((j) => depth(items[j]))) : 0);
    if (items.length || (r.pending ?? []).length) {
      working.push(`<section class="rv-sec"><h4>What the article asks to change <span class="small muted">select what to commit</span>
          ${items.length > 1 ? `<span class="rv-bulk"><button class="linkish" data-all>all</button> · <button class="linkish" data-none>none</button></span>` : ""}</h4>
        <ul class="rv-items">${items.map((it) => `<li class="rv-item ${esc(it.action)}${keep.has(it.index) ? "" : " off"}" data-index="${it.index}" style="--depth:${Math.min(3, depth(it))}"
            data-refs="${esc(it.refs.join(" "))}">
          <div class="rv-row"><label><input type="checkbox" data-item="${it.index}" ${keep.has(it.index) ? "checked" : ""}>
            <span class="mk ${esc(it.action)}" aria-hidden="true">${ACTION_MARK[it.action] ?? "·"}</span>
            <span>${prose(it.label)}</span></label>
            <button class="rv-conf-chip${it.own_confidence ? " own" : ""}" data-conf-item="${it.index}" aria-expanded="${st.openConf === it.index}"
              title="${it.own_confidence ? "Your confidence in this change" : "Follows the article's confidence"}: click to set it for this change alone">${pct(it.confidence)}</button></div>
          ${st.openConf === it.index ? `<div class="rv-conf item"><input type="range" min="0" max="100" step="5" value="${Math.round(100 * it.confidence)}" data-conf-op="${it.index}" aria-label="Confidence in this change">
            <span class="mono rv-conf-v">${pct(it.confidence)}</span>
            ${it.own_confidence ? `<button class="linkish small" data-conf-reset="${it.index}">follow the article</button>` : `<span class="small muted">set for this change alone</span>`}</div>` : ""}</li>`).join("")}</ul>
        ${items.some((it) => it.requires.length) ? `<p class="small muted">Deselecting an item also deselects what needs it; the review is staged again without them.</p>` : ""}
        ${(r.pending ?? []).map((pd) => `<div class="rv-pending"><b>Fuzzy end, hedged:</b> ${prose(pd.label)}
          ${hedgeBars(pd.candidates)}
          <div class="small muted">The article names none of them, so nothing is chosen.${pd.soft ? " Each candidate gets a soft interaction, as strong as it is probable, so forecasts hedge across them." : ""}
            Later articles move the odds; once one passes ${pct(bound)} after ${needed} articles that bear on it, a resolution comes back here for review.</div></div>`).join("")}
      </section>`);
    }
    if (r.hedges?.length) {
      working.push(`<section class="rv-sec"><h4>What the fuzzy ends learn <span class="small muted">this article as evidence for each candidate</span></h4>
        ${r.hedges.map((h) => `<div class="rv-hedge"><div class="hg-label">${prose(h.label)}${h.resolves ? ` <span class="badge real">passes the bound: a resolution goes to review</span>` : ""}</div>
          ${hedgeBars(h.candidates, { before: true })}
          ${checkMeter(h, bound, needed)}
          <ul class="rv-plain small">${(h.evidence ?? []).map((e) => `<li>${prose(e.candidate ?? "")}: ${esc(EVIDENCE_WORD[e.kind] ?? e.kind)} ${e.kind === "mention" ? "in this article" : ""}
            <span class="muted">(+${fmt(e.weight)}${e.confidence < 1 ? ` at your ${pct(e.confidence)}` : ""})</span></li>`).join("")}</ul></div>`).join("")}</section>`);
    }
    // the event's moves and the ripple, by order
    const byOrder = new Map();
    for (const a of [...(r.moves ?? []), ...(r.ripple ?? [])]) {
      const k = Math.min(3, a.order);
      if (!byOrder.has(k)) byOrder.set(k, []);
      byOrder.get(k).push(a);
    }
    // Oct 9: the ripple moves the state too, so each value's ripple can be deselected or weighed (the probability
    // that it arrives); a value downstream of one weighed already scales with it
    const rw = c.ripple ?? {};
    const wOf = (a) => (!a.order ? 1 : a.subentity_id in rw ? (rw[a.subentity_id] ?? 1) : (a.weight ?? 1));
    const upOf = (a) => (a.hops ?? []).slice(0, -1).reduce((t, sid) => {
      const up = (r.ripple ?? []).find((x) => x.subentity_id === sid);
      return t * (up ? wOf(up) : 1);
    }, 1);
    const ripRow = (a) => {
      const w = wOf(a);
      const up = upOf(a);
      const size = a.order ? a.peak : a.effect;
      const arrow = `<span class="${size >= 0 ? "z-up" : "z-down"}">${size >= 0 ? "▲" : "▼"} ${signed(size)} sd</span>`;
      const scaled = a.order && w * up < 0.995 ? ` <span class="small muted rv-scaled">→ ${signed(size * w * up)} expected</span>` : "";
      const path = a.path?.length > 1 ? `<div class="small muted rv-path">${a.path.map(prose).join(" → ")}</div>` : "";
      if (!a.order) {
        return `<li data-refs="${esc([a.subentity_id, ...(a.via ?? [])].join(" "))}">${arrow} <b>${subOr(a.subentity_id, a.name)}</b>${path}</li>`;
      }
      const sid = esc(a.subentity_id);
      return `<li class="rv-rip${w <= 0 ? " off" : ""}" data-refs="${esc([a.subentity_id, ...(a.via ?? [])].join(" "))}">
        <div class="rv-row"><label><input type="checkbox" data-rip="${sid}" ${w > 0 ? "checked" : ""}>
          <span>${arrow} <b>${subOr(a.subentity_id, a.name)}</b> <span class="small muted">peaks ~day ${a.peak_day}</span>${scaled}</span></label>
          <button class="rv-conf-chip${w < 1 ? " own" : ""}" data-rip-conf="${sid}" aria-expanded="${st.openRip === a.subentity_id}"
            title="The probability that this ripple arrives: click to set it">${pct(w)}</button></div>
        ${path}
        ${up < 0.995 ? `<div class="small muted">Scales with what you said upstream: ${pct(up)}.</div>` : ""}
        ${st.openRip === a.subentity_id ? `<div class="rv-conf item rip"><input type="range" min="0" max="100" step="5" value="${Math.round(100 * w)}" data-rip-p="${sid}" aria-label="Probability that this ripple arrives">
          <span class="mono rv-conf-v">${pct(w)}</span>
          ${w < 1 ? `<button class="linkish small" data-rip-reset="${sid}">as the analysis expects</button>` : `<span class="small muted">the probability it arrives</span>`}</div>` : ""}</li>`;
    };
    if (byOrder.size) {
      working.push(`<section class="rv-sec"><h4>What follows from it: the ripple <span class="small muted">the transmission path on the canvas, left to right</span></h4>
        <p class="small muted rv-sub">It is not in the article: it follows from the interactions. Does each order make sense? Deselect a
          value's ripple, or weigh how likely it is to arrive; a value downstream scales with it.</p>
        ${[...byOrder.entries()].sort((a, b) => a[0] - b[0]).map(([k, xs]) => `<div class="rv-order o${k}">
          <div class="rv-oh"><span class="sw o${k}" aria-hidden="true"></span>${esc(ORDER[k] ?? `Order ${k}`)}</div>
          <ul>${xs.map(ripRow).join("")}</ul></div>`).join("")}
      </section>`);
    }
    if (r.learned?.length) {
      working.push(`<section class="rv-sec"><h4>What the fold settles <span class="small muted">each value and belief, before and after this article</span></h4>
        <ul class="rv-fold">${r.learned.map((x) => `<li data-refs="${esc(x.ref)}">${foldRow(x)}</li>`).join("")}</ul></section>`);
    }
    if (r.recalled?.length || r.adjusted?.length) {
      const top = Math.max(...(r.recalled ?? []).map((x) => x.attention), 1e-9);
      longTerm.push(`<section class="rv-sec"><h4>What it recalled to read this article <span class="small muted">the patterns and past days most like it</span></h4>
        <ul class="rv-recall">${(r.recalled ?? []).slice(0, 4).map((x) => `<li><span class="rc-name">${x.kind === "day"
          ? (x.label.startsWith("a past day") ? `${esc(x.label.replace("a past day", "A past day"))} (${esc(x.day)})` : `The day of “${esc(x.label)}” (${esc(x.day)})`)
          : `Superentity “${esc(x.label)}”`}</span>
          <span class="rc-bar" title="attention ${fmt(x.attention)}"><i style="width:${(100 * x.attention / top).toFixed(0)}%"></i></span></li>`).join("")}</ul>
        ${(r.adjusted ?? []).length ? `<p class="small muted rv-sub">What followed those past days adjusts the expected moves:</p><ul class="rv-plain">
          ${r.adjusted.slice(0, 6).map((a) => `<li>${names().linkHtml(a.interaction_id) ?? prose(a.name)} ${signed(a.before)} → <b>${signed(a.after)}</b></li>`).join("")}
          ${r.adjusted.length > 6 ? `<li class="muted">… and ${r.adjusted.length - 6} smaller adjustments</li>` : ""}</ul>` : ""}</section>`);
    }
    if (r.kind === "frontier_promotion") longTerm.push(`<div class="series"></div>`);
    if (r.lessons?.length || r.raises?.length) {
      longTerm.push(`<section class="rv-sec"><h4>What it keeps <span class="small muted">by the store it lands in</span></h4>
        ${keepsList(r.lessons ?? [])}
        ${(r.raises ?? []).length ? `<ul class="rv-plain">${r.raises.map((x) => `<li>Raises a proposal for its own review later: ${esc(KIND_LABEL[x.kind] ?? x.kind)}${x.reason ? ` (${esc(x.reason)})` : ""}</li>`).join("")}</ul>` : ""}</section>`);
    }
    const decision = `<section class="rv-group st-review rv-decide" id="rvg-review">
      <header class="rv-gh"><span class="rv-gt">Your review</span><span class="rv-gio">does every change above make sense?</span></header>
      <p class="small">${!keep.size && !(r.pending ?? []).length ? "Nothing is selected: reject the proposal instead."
        : `Approving commits the ${keep.size === items.length ? "whole event" : `${keep.size} selected change(s)`} to working memory and its lessons to long-term memory. Nothing has changed yet.`}</p>
      <p class="small faint rv-foot">Staged on a copy of version ${r.version}. ${r.world_event
        ? "Approved, it commits on its day: once to working memory, once to long-term memory." : "Approved, it commits once."}</p></section>`;
    const nRip = (r.ripple ?? []).length;
    const wmSaid = [items.length ? `${items.length} change${items.length === 1 ? "" : "s"} asked for` : "",
      nRip ? `a ripple to ${nRip} value${nRip === 1 ? "" : "s"}` : "",
      r.learned?.length ? `${r.learned.length} value${r.learned.length === 1 ? "" : "s"} and belief${r.learned.length === 1 ? "" : "s"} settle` : ""].filter(Boolean).join(" · ");
    return [group(r, "intake", intake.join(""), "A backend user's edit: no article."),
      group(r, "working", working.join(""), "Nothing changes in working memory.", wmSaid || null,
        "The model as it stands today: each entity's values, and the interactions between them with how strongly each is believed. This is what the article would change in it."),
      group(r, "long_term", longTerm.join(""), "Nothing new for long-term memory.",
        r.lessons?.length ? `${r.lessons.length} lesson${r.lessons.length === 1 ? "" : "s"}${r.raises?.length ? `; raises ${r.raises.length} proposal(s)` : ""}` : "",
        "What the model keeps across articles: the kinds of entities and interactions it has seen, the superentities they form, each actor's record of decisions, co-movements it cannot explain yet, and past days it can recall. It shaped how this article was read, and it learns from it."),
      decision].join("");
  }

  // -- selecting ----------------------------------------------------------------------------------------
  function toggle(id, index, on_) {
    const r = st.review;
    const keep = keepOf(id);
    const items = r?.items ?? [];
    if (on_) {
      const add = (i) => { keep.add(i); for (const j of items[i]?.requires ?? []) add(j); };
      add(index);
    } else {
      const drop = (i) => { keep.delete(i); for (const it of items) if (it.requires.includes(i) && keep.has(it.index)) drop(it.index); };
      drop(index);
    }
    renderCard();
    restage(250);
  }
  function setAll(id, on_) {
    const pv = pvOf(id);
    st.keep.set(id, new Set(on_ ? pv.proposal.event.ops.map((_, i) => i) : []));
    renderCard();
    restage(150);
  }

  async function loadSeries(p) {
    const holder = body.querySelector(".rv-card .series");
    if (!holder) return;
    try {
      const s = await api.frontierSeries(p.subject_id);
      holder.innerHTML = `<div class="rv-sec"><h4>The evidence: paired moves <span class="small muted">${s.lag_days ? `${s.lag_days} days apart` : "the same day"}, correlation ${fmt(s.corr)}</span></h4></div>`;
      holder.appendChild(scatter(s.pairs, { xLabel: "earlier move", yLabel: "later innovation" }));
    } catch { /* the entry may have closed */ }
  }

  // -- deciding -----------------------------------------------------------------------------------------
  const busy = new Set();
  async function act(fn, ok, id) {
    if (busy.has(id)) return;
    busy.add(id);
    // a staging still in flight must not redraw the staged graph over what is about to be committed
    clearTimeout(timer);
    st.ticket += 1;
    st.deciding = id;
    for (const b of body.querySelectorAll(".rv-actions button")) b.disabled = true;
    try {
      await fn();
      toast(ok);
      st.keep.delete(id);
      st.conf.delete(id);
      st.openConf = null;
      st.openRip = null;
      st.review = null;
      clearStaged();
      await refreshGraph();
      emit("reviewed", id);
    } catch (err) {
      toast(errorText(err), "err");
    } finally {
      busy.delete(id);
      st.deciding = null;
      for (const b of body.querySelectorAll(".rv-actions button")) b.disabled = false;
    }
  }
  function approve(id) {
    const pv = pvOf(id);
    const keep = [...keepOf(id)].sort((a, b) => a - b);
    const all = keep.length === pv.proposal.event.ops.length;
    if (!keep.length && pv.proposal.event.ops.length) { toast("Nothing is selected: reject it instead.", "err"); return; }
    const c = confOf(id);
    return act(() => api.approve(id, "backend user", null, all ? null : keep, c.all, c.ops, c.ripple),
      all ? `Approved ${id}: it commits now.` : `Approved ${keep.length} of ${pv.proposal.event.ops.length} changes in ${id}.`, id);
  }
  function reject(id) {
    openModal(`<h3>Reject ${esc(id)}</h3><label for="rj-note" class="small">Nothing it proposes changes the model. A note is required, for the log.</label>
      <textarea id="rj-note" rows="3" placeholder="Why?"></textarea><div class="error" id="rj-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="danger" id="rj-go">Reject</button></div>`,
    (root, close) => {
      root.querySelector("#rj-note").focus();
      root.querySelector("#rj-go").addEventListener("click", async () => {
        const note = root.querySelector("#rj-note").value.trim();
        if (!note) { root.querySelector("#rj-err").textContent = "A rejection needs a note."; return; }
        close();
        await act(() => api.reject(id, note, "backend user"), `Rejected ${id}: nothing changed.`, id);
      });
    });
  }
  function edit(id) {
    const pv = pvOf(id);
    if (!pv) return;
    openModal(`<h3>Edit ${esc(id)}</h3>
      <label class="small" for="ed-json">The graph update event (the server checks it against the schema)</label>
      <textarea id="ed-json" rows="16">${esc(JSON.stringify(pv.proposal.event, null, 2))}</textarea><div class="error" id="ed-err"></div>
      <div class="actions"><button data-close>Cancel</button><button class="primary" id="ed-go">Save edit</button></div>`,
    (root, close) => {
      root.querySelector("#ed-go").addEventListener("click", async () => {
        let parsed;
        try { parsed = JSON.parse(root.querySelector("#ed-json").value); } catch (err) { root.querySelector("#ed-err").textContent = `Invalid JSON: ${err.message}`; return; }
        try {
          await api.edit(id, parsed, "backend user");
          close();
          st.keep.delete(id);
          st.review = null;
          toast(`Edited ${id}; it is staged again.`);
          await refreshGraph();
        } catch (err) { root.querySelector("#ed-err").textContent = errorText(err); }
      });
    });
  }

  on("proposals", render);
  on("tab-left", (name) => {
    const was = st.open;
    st.open = name === "review";
    if (st.open) {
      render();
      // reopened on a review already staged: draw its staged graph again (closing the pane cleared it)
      if (!was && st.review && st.review.proposal_id === st.focused && !st.review.error) {
        showStaged(st.review);
        onFocusGraph?.(st.review);
      }
    } else { st.ticket += 1; clearStaged(); }
  });
  on("flash-review", (id) => { if (id) focus(String(id)); });
  render();
  return {
    approveFocused: () => st.focused && st.open && approve(st.focused),
    rejectFocused: () => st.focused && st.open && reject(st.focused),
    focus: (id) => focus(id),
  };
}
