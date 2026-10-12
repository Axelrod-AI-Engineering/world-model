// Thesis composer (§13.6): a question; shocks (a subentity picker, the change, its mode, and persistence);
// optional interventions (a decision variable, hold or change, and a window); a horizon; and targets.
// DECISION: the tab opens with the question alone, a few examples, and what to forecast as chips that wrap
// (no scrolling box): any value, actor, idea, sector, superentity, or category, so forecasts come at every
// granularity. The full shock builder sits one click down.
import { api } from "../api.js";
import { CATEGORY_CODES, CATEGORY_NAMES } from "../graph/layouts.js";
import { emit, on, store } from "../store.js";
import { errorText, esc } from "../util.js";

// examples the world's template translator (data/worlds/<world>/templates.yaml) understands
const ECONOMY_EXAMPLES = ["What if oil prices doubled next quarter?", "What if NVIDIA's China sales fall by 30%?",
  "What if OPEC cuts output by 10%?", "What if the Fed raises rates by 100bp?", "What if jet fuel spikes next month?"];
const TUTORIAL_EXAMPLES = ["What if oil rose by 30% next quarter?", "What if oil prices doubled next quarter?",
  "What if the Fed raised rates by 100bp?"];
// an imported model (emily_demo): a PM's questions about policy, the yen, and the names
const BOOK_EXAMPLES = ["What if the BoJ hiked by 0.5 next quarter?", "What if the Fed cut rates by 0.75 next quarter?",
  "What if the yen rose by 5% next month?", "What if oil prices spiked next quarter?"];
const examples = () => (store.status?.imports ? BOOK_EXAMPLES : store.status?.examples ? TUTORIAL_EXAMPLES : ECONOMY_EXAMPLES);
const KIND_LABEL = { sub: "value", actor: "actor", idea: "idea", superentity: "superentity", sector: "sector", category: "category" };
const ACTOR_KINDS = new Set(["agency", "company", "person"]);

export function initThesis({ toast }) {
  const el = document.getElementById("tab-thesis");
  let shocks = [{ sid: "resources_energy.oil_price", delta: 1.0, mode: "relative", persistence: "step" }];
  let interventions = [];
  let picks = [
    { kind: "sub", ref: "inflation.headline_cpi" }, { kind: "sub", ref: "interest_rates.us_policy_rate" },
    { kind: "actor", ref: "delta" }, { kind: "sector", ref: "airlines" }, { kind: "category", ref: "SD" },
  ];
  let busy = false;
  let counter = 1;
  let advanced = false;
  let question = ECONOMY_EXAMPLES[0];
  let horizon = 270;
  let adding = false;
  let ready = [];            // the scenario's ready-made questions (a design partner's), posed whole
  let readyFor = null;
  const loadReady = () => api.scenarioTheses().then((l) => { ready = l.filter((t) => !t.scripted); render(); }).catch(() => {});
  loadReady();
  // another scenario (the Tutorial, or back to the model) has other ready-made questions
  on("status", (st) => {
    if (!st?.scenario_id || st.scenario_id === readyFor) return;
    const first = readyFor == null;
    readyFor = st.scenario_id;
    if (!first) { ready = []; loadReady(); }
  });
  let query = "";

  const view = () => store.graph ?? store.view;

  function catalog() {
    const v = view();
    if (!v) return [];
    const ents = new Map(v.entities.map((e) => [e.id, e]));
    const out = [];
    for (const e of v.entities) out.push({ kind: ACTOR_KINDS.has(e.kind) || e.features?.sector ? "actor" : "idea", ref: e.id, name: e.name });
    for (const s of v.subentities) out.push({ kind: "sub", ref: s.id, name: s.name, sub: ents.get(s.entity_id)?.name });
    const seen = new Set();
    for (const h of v.hulls ?? []) {
      if (h.transient || h.status !== "admitted" || seen.has(h.pattern_id)) continue;
      seen.add(h.pattern_id);
      out.push({ kind: "superentity", ref: h.pattern_id, name: h.label });
    }
    const sectors = [...new Set(v.entities.map((e) => e.features?.sector).filter(Boolean))].sort();
    for (const sct of sectors) out.push({ kind: "sector", ref: sct, name: sct.charAt(0).toUpperCase() + sct.slice(1) });
    for (const c of CATEGORY_CODES) out.push({ kind: "category", ref: c, name: CATEGORY_NAMES[c] });
    return out;
  }

  function labelOf(p) {
    const hit = catalog().find((x) => x.kind === p.kind && x.ref === p.ref);
    return hit ? hit.name : p.ref;
  }

  // what the server needs: subentities as targets, the rest as target groups
  function targetsOf() {
    const targets = picks.filter((p) => p.kind === "sub").map((p) => p.ref);
    const groups = picks.filter((p) => p.kind !== "sub").map((p) => ({
      kind: { actor: "entity", idea: "entity", superentity: "superentity", sector: "sector", category: "category" }[p.kind],
      ref: p.ref }));
    return { targets, target_groups: groups };
  }

  function suggestions() {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const have = new Set(picks.map((p) => `${p.kind}:${p.ref}`));
    return catalog().filter((x) => !have.has(`${x.kind}:${x.ref}`)
      && (x.name.toLowerCase().includes(q) || x.ref.toLowerCase().includes(q) || (x.sub ?? "").toLowerCase().includes(q)))
      .sort((a, b) => (a.name.toLowerCase().startsWith(q) ? 0 : 1) - (b.name.toLowerCase().startsWith(q) ? 0 : 1))
      .slice(0, 10);
  }

  function subOptions() {
    return (view()?.subentities ?? []).map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  }

  function render() {
    const subs = view()?.subentities ?? [];
    // forecast only for what this world has (the tutorial starts empty)
    if (view()?.entities?.length) {
      const known = new Set(catalog().map((x) => `${x.kind}:${x.ref}`));
      picks = picks.filter((p) => known.has(`${p.kind}:${p.ref}`));
      const have = new Set(subs.map((x) => x.id));
      shocks = shocks.filter((x) => !x.sid || have.has(x.sid));
      // an imported model's book: the yen and the names it moves
      if (!picks.length && store.status?.imports) {
        picks = [{ kind: "sub", ref: "dollar_yen.usd_jpy" }, { kind: "actor", ref: "tokio_marine" }, { kind: "actor", ref: "toyota" },
          { kind: "actor", ref: "jpmorgan" }].filter((p) => known.has(`${p.kind}:${p.ref}`));
      }
    }
    const decisions = subs.filter((s) => s.decision_variable);
    const sugg = suggestions();
    el.innerHTML = `
      <div class="group-label">Ask a what-if</div>
      <h3>Pose a thesis</h3>
      <p class="lede">Describe something that has not happened. The model treats it like news, runs it through the graph and
        the superentities it recalls, and forecasts how the economy would respond.</p>
      <div class="ask-row"><input id="th-q" type="text" value="${esc(question)}" aria-label="Question">
        <button class="hyp" id="th-ask">${busy ? "Thinking…" : "Ask"}</button></div>
      <div class="chips" style="margin-top:8px"><span class="faint small">Try</span>
        ${examples().map((q, i) => `<button class="pick ghosted" data-ex="${i}">${esc(q)}</button>`).join("")}</div>
      ${ready.length ? `<div class="section"><h4>Ready-made questions</h4>
        <div class="small muted">${store.status?.imports ? "Your scenarios" : "A design partner's theses"}, each with several shocks and interventions already set.</div>
        <div class="chips" style="margin-top:4px">${ready.map((t) => `<button class="pick ghosted" data-ready="${esc(t.id)}" title="Pose ${esc(t.id)} as written">${esc(t.question)}</button>`).join("")}</div></div>` : ""}
      <div class="section"><h4>Forecast for</h4>
        <div class="chips">${picks.map((p, i) => `<span class="pick ${p.kind}"><span class="k">${esc(KIND_LABEL[p.kind])}</span>${esc(labelOf(p))}
            <button class="x" data-rm="${i}" aria-label="Remove ${esc(labelOf(p))}">✕</button></span>`).join("")}
          ${adding ? `<input id="th-add-q" class="pick-input" type="text" placeholder="a value, actor, idea, sector…" value="${esc(query)}" aria-label="Add a forecast target">`
            : `<button class="pick add" id="th-add-t">+ add</button>`}</div>
        ${adding && sugg.length ? `<div class="chips suggest">${sugg.map((x, i) => `<button class="pick ${x.kind}" data-sg="${i}"><span class="k">${esc(KIND_LABEL[x.kind])}</span>${esc(x.name)}${x.sub ? `<span class="faint"> · ${esc(x.sub)}</span>` : ""}</button>`).join("")}</div>` : ""}
        ${adding && query && !sugg.length ? `<div class="small faint" style="margin-top:4px">No match.</div>` : ""}
      </div>
      <div class="ask-row small"><label for="th-h">Horizon</label><input id="th-h" type="number" value="${horizon}" style="width:76px"> days</div>
      <div class="error" id="th-err"></div>
      <details class="section" ${advanced ? "open" : ""} id="th-adv"><summary class="small" style="cursor:pointer">Build the shocks yourself</summary>
        <datalist id="sub-list">${subOptions()}</datalist>
        <div class="section"><h4>Shocks</h4>
          ${shocks.map((s, i) => `<div class="shock-row" data-i="${i}">
            <input type="text" list="sub-list" data-f="sid" value="${esc(s.sid)}" aria-label="Subentity" class="grow">
            <input type="number" step="0.05" data-f="delta" value="${s.delta}" aria-label="Change" style="width:72px">
            <select data-f="mode" aria-label="Mode">${["relative", "absolute", "standardized"].map((m) => `<option ${m === s.mode ? "selected" : ""}>${m}</option>`).join("")}</select>
            <select data-f="persistence" aria-label="Persistence">${["step", "pulse"].map((m) => `<option ${m === s.persistence ? "selected" : ""}>${m}</option>`).join("")}</select>
            <button class="ghost" data-del="${i}" aria-label="Remove shock">✕</button></div>`).join("")}
          <div class="ask-row"><button id="th-add">+ shock</button>
            <label class="small">starts in <input id="th-start" type="number" value="12" style="width:56px"> weeks</label></div></div>
        <div class="section"><h4>Interventions</h4>
          ${interventions.map((v, i) => `<div class="shock-row" data-v="${i}">
            <select data-f="sid" aria-label="Decision variable" class="grow">${decisions.map((d) => `<option value="${esc(d.id)}" ${d.id === v.sid ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>
            <select data-f="kind" aria-label="Hold or change"><option ${v.kind === "hold" ? "selected" : ""}>hold</option><option ${v.kind === "change" ? "selected" : ""}>change</option></select>
            <input type="number" step="0.25" data-f="delta" value="${v.delta}" ${v.kind === "hold" ? "disabled" : ""} aria-label="Change" style="width:72px">
            <input type="number" data-f="window" value="${v.window}" aria-label="Window (days)" title="window (days)" style="width:72px">
            <button class="ghost" data-vdel="${i}" aria-label="Remove intervention">✕</button></div>`).join("")}
          <button id="th-addv" ${decisions.length ? "" : "disabled"}>+ intervention</button></div>
        <div class="ask-row"><button class="hyp" id="th-run">${busy ? "Running…" : "Run"}</button></div>
      </details>`;
    el.querySelector("#th-adv").addEventListener("toggle", (ev) => { advanced = ev.target.open; });
    el.querySelector("#th-q").addEventListener("input", (ev) => { question = ev.target.value; });
    el.querySelector("#th-q").addEventListener("keydown", (ev) => { if (ev.key === "Enter") ask(); });
    el.querySelector("#th-h").addEventListener("change", (ev) => { horizon = +ev.target.value || 182; });
    for (const b of el.querySelectorAll("[data-ex]")) b.addEventListener("click", () => { question = examples()[+b.dataset.ex]; render(); });
    for (const b of el.querySelectorAll("[data-ready]")) b.addEventListener("click", () => poseReady(b.dataset.ready));
    for (const b of el.querySelectorAll("[data-rm]")) b.addEventListener("click", () => { picks.splice(+b.dataset.rm, 1); render(); });
    el.querySelector("#th-add-t")?.addEventListener("click", () => { adding = true; query = ""; render(); el.querySelector("#th-add-q")?.focus(); });
    const qi = el.querySelector("#th-add-q");
    if (qi) {
      qi.addEventListener("input", () => {
        query = qi.value;
        const pos = qi.selectionStart;
        render();
        const again = el.querySelector("#th-add-q");
        again?.focus();
        again?.setSelectionRange(pos, pos);
      });
      qi.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") { ev.stopPropagation(); adding = false; query = ""; render(); }
        if (ev.key === "Enter") { const s0 = suggestions()[0]; if (s0) addPick(s0); }
      });
    }
    for (const b of el.querySelectorAll("[data-sg]")) b.addEventListener("click", () => addPick(sugg[+b.dataset.sg]));
    for (const row of el.querySelectorAll("[data-i]")) {
      const i = +row.dataset.i;
      for (const inp of row.querySelectorAll("[data-f]")) {
        inp.addEventListener("change", () => { shocks[i][inp.dataset.f] = inp.type === "number" ? +inp.value : inp.value; });
      }
    }
    for (const row of el.querySelectorAll("[data-v]")) {
      const i = +row.dataset.v;
      for (const inp of row.querySelectorAll("[data-f]")) {
        inp.addEventListener("change", () => {
          interventions[i][inp.dataset.f] = inp.type === "number" ? +inp.value : inp.value;
          if (inp.dataset.f === "kind") render();
        });
      }
    }
    for (const b of el.querySelectorAll("[data-del]")) b.addEventListener("click", () => { shocks.splice(+b.dataset.del, 1); render(); });
    for (const b of el.querySelectorAll("[data-vdel]")) b.addEventListener("click", () => { interventions.splice(+b.dataset.vdel, 1); render(); });
    el.querySelector("#th-add").addEventListener("click", () => { shocks.push({ sid: "", delta: 1, mode: "standardized", persistence: "step" }); render(); });
    el.querySelector("#th-addv")?.addEventListener("click", () => {
      interventions.push({ sid: decisions[0]?.id, kind: "hold", delta: 0, window: 270 });
      render();
    });
    el.querySelector("#th-run").addEventListener("click", run);
    el.querySelector("#th-ask").addEventListener("click", ask);
  }

  function addPick(x) {
    if (!x) return;
    picks.push({ kind: x.kind, ref: x.ref });
    query = "";
    adding = false;
    render();
  }

  function nowIso() {
    return store.status?.sim_time ?? store.graph?.sim_time ?? new Date().toISOString();
  }

  async function run() {
    if (busy) return;
    const err = el.querySelector("#th-err");
    const now = new Date(nowIso());
    const start = new Date(now.getTime() + (+el.querySelector("#th-start").value || 0) * 7 * 86400000);
    const ops = shocks.filter((s) => s.sid).map((s) => ({
      op: "change_value", target: { kind: "concrete", subentity_id: s.sid }, delta: +s.delta, mode: s.mode,
      persistence: s.persistence, at: start.toISOString() }));
    for (const v of interventions) {
      if (!v.sid) continue;
      ops.push({ op: "change_value", target: { kind: "concrete", subentity_id: v.sid }, delta: v.kind === "hold" ? 0 : +v.delta,
                 mode: "absolute", persistence: "step", intervention: true, window_days: +v.window || 90, at: now.toISOString() });
    }
    const id = `T-UI${counter++}`;
    const thesis = {
      id, question: question || "Custom thesis", mode: "scaffolded", horizon_days: horizon || 182, ...targetsOf(),
      event: { id: `GUE-${id}`, kind: "hypothetical", event_type: ops.length ? "supply_shock" : null,
               occurred_at: start.toISOString(), recorded_at: now.toISOString(), produced_by: "human", ops },
    };
    busy = true;
    err.textContent = "";
    el.querySelector("#th-run").textContent = "Running…";
    emit("ask-started", { question: thesis.question, thesis_id: id });
    try {
      const fv = await api.poseThesis(thesis);
      emit("asked", fv);
      emit("show-forecast", fv);     // the forecast opens itself: no toast
    } catch (e) {
      err.textContent = errorText(e);
    } finally {
      busy = false;
      const b = el.querySelector("#th-run");
      if (b) b.textContent = "Run";
    }
  }

  async function ask() {
    if (busy) return;
    const err = el.querySelector("#th-err");
    err.textContent = "";
    busy = true;
    el.querySelector("#th-ask").textContent = "Thinking…";
    emit("ask-started", { question });
    try {
      const fv = await api.poseThesis({ question, horizon_days: horizon || 182, ...targetsOf() });
      emit("asked", fv);
      emit("show-forecast", fv);
    } catch (e) {
      err.textContent = `${errorText(e)}\nTry one of the examples, or build the shock yourself below.`;
    } finally {
      busy = false;
      const b = el.querySelector("#th-ask");
      if (b) b.textContent = "Ask";
    }
  }

  async function poseReady(id) {
    if (busy) return;
    const err = el.querySelector("#th-err");
    err.textContent = "";
    busy = true;
    const t = ready.find((x) => x.id === id);
    emit("ask-started", { question: t?.question ?? id });
    try {
      const fv = await api.poseStoredThesis(id);
      emit("asked", fv);
      emit("show-forecast", fv);
    } catch (e) {
      err.textContent = errorText(e);
    } finally {
      busy = false;
    }
  }

  // "What if it moves?" from the canvas: one standardized shock on the entity's first subentity
  function prefill(id) {
    const v = view();
    const sub = (v?.subentities ?? []).find((s) => s.id === id) ?? (v?.subentities ?? []).find((s) => s.entity_id === id);
    if (!sub) return;
    const name = v.entities.find((e) => e.id === sub.entity_id)?.name ?? sub.entity_id;
    shocks = [{ sid: sub.id, delta: 1.0, mode: "standardized", persistence: "step" }];
    interventions = [];
    question = `What if ${name} (${sub.name}) jumps by one standard deviation?`;
    advanced = true;
    render();
  }

  // "Forecast this" from the canvas: add a target chip of the right kind
  function forecastFor(kind, ref) {
    const v = view();
    let k = kind;
    if (kind === "entity") {
      const e = v?.entities.find((x) => x.id === ref);
      k = e && (ACTOR_KINDS.has(e.kind) || e.features?.sector) ? "actor" : "idea";
    }
    if (kind === "subentity") k = "sub";
    if (!picks.some((p) => p.kind === k && p.ref === ref)) picks.push({ kind: k, ref });
    render();
  }

  on("graph", () => { if (!el.contains(document.activeElement)) render(); });
  render();
  // a question from elsewhere (the tutorial's inference example), ready to ask
  function setQuestion(q) {
    question = q;
    advanced = false;
    render();
    el.querySelector("#th-q")?.focus({ preventScroll: true });
  }

  return { render, prefill, forecastFor, setQuestion };
}
