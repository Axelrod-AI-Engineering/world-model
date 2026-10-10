// Add from your own knowledge (Oct 9): a backend user adds what they know from experience, with no article behind it:
// a new entity, its values (a typical level and a spread give the prior), interactions between any values (sign,
// size, timing), why they believe it, and how sure they are. It is staged and reviewed like any article. A manual
// example opens the form prefilled, so the example shows how it is done; the person can change anything first.
import { api } from "../api.js";
import { store } from "../store.js";
import { errorText, esc } from "../util.js";

const MAX_WIDTH = "min(860px, calc(100vw - 32px))";

export function initManual({ toast, onProposal }) {
  const pane = document.createElement("section");
  pane.id = "manual";
  pane.className = "manual hidden";
  pane.setAttribute("role", "dialog");
  pane.setAttribute("aria-label", "Add from your own knowledge");
  pane.style.maxWidth = MAX_WIDTH;
  document.getElementById("stage").appendChild(pane);
  let vocab = null;
  let spec = null;          // the form's state, in the shape sim/examples/catalog.manual_ops reads
  let exampleId = null;     // set when a manual example opened the form
  let busy = false;

  const blank = () => ({ entity: null, values: [], interactions: [], confidence: 0.8, note: "" });
  const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "value";

  // the values an interaction can connect: every value in the graph, and the new ones in this form
  function valueOptions(selected) {
    const view = store.view;
    const ents = new Map((view?.entities ?? []).map((e) => [e.id, e.name]));
    const existing = (view?.subentities ?? []).map((s) => [s.id, `${ents.get(s.entity_id) ?? s.entity_id} · ${s.name}`])
      .sort((a, b) => a[1].localeCompare(b[1]));
    const fresh = spec.values.map((v) => [`new:${v.slug}`, `${spec.entity?.name || ents.get(v.entity) || "new"} · ${v.name || "(new value)"} (new)`]);
    // a prefilled value the graph does not have yet: the earlier examples add it when they play
    const later = selected && !selected.startsWith("new:") && !existing.some(([id]) => id === selected)
      ? [[selected, `${selected.replace(/[._]/g, " ")} (added when the earlier examples play)`]] : [];
    return [...later, ...fresh, ...existing].map(([id, label]) => `<option value="${esc(id)}" ${id === selected ? "selected" : ""}>${esc(label)}</option>`).join("");
  }

  function render() {
    const kinds = vocab?.attribute_kinds ?? [];
    const ents = (store.view?.entities ?? []).slice().sort((a, b) => a.name.localeCompare(b.name));
    const e = spec.entity;
    pane.innerHTML = `
      <header><div class="mtitle">Add from your own knowledge</div><span class="spacer"></span>
        <button class="ghost win-max-btn" data-max type="button" aria-label="Full screen" title="Full screen (or back)">⤢</button>
        <button class="close" aria-label="Close (Esc)">✕</button></header>
      <div class="mbody">
        <p class="small muted">What you know from experience, with no article behind it. It is staged and reviewed like any article;
          ${exampleId ? "<b>this example prefilled the form</b>: change anything, then stage it." : "fill in what you need and stage it."}</p>
        <section class="mf-sec"><h4><label><input type="checkbox" data-ent-on ${e ? "checked" : ""}> A new entity</label></h4>
          ${e ? `<div class="mf-grid">
            <label>Name<input data-f="entity.name" value="${esc(e.name)}"></label>
            <label>Kind<select data-f="entity.kind">${(vocab?.entity_kinds ?? []).map((k) => `<option ${k === e.kind ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
            <label>Category<select data-f="entity.tag">${(vocab?.category_tags ?? []).map((t) => `<option ${t === (e.tags ?? [])[0] ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
            <label>Other names<input data-f="entity.aliases" value="${esc((e.aliases ?? []).join(", "))}" placeholder="comma-separated"></label></div>` : ""}</section>
        <section class="mf-sec"><h4>New values <button class="linkish small" data-add-value>+ add a value</button></h4>
          ${spec.values.map((v, i) => `<div class="mf-row">
            <label>Name<input data-v="${i}" data-k="name" value="${esc(v.name)}"></label>
            <label>On<select data-v="${i}" data-k="entity">${e ? `<option value="" ${!v.entity ? "selected" : ""}>${esc(e.name || "the new entity")}</option>` : ""}
              ${ents.map((x) => `<option value="${esc(x.id)}" ${x.id === v.entity ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
            <label>Kind<select data-v="${i}" data-k="attribute_kind">${kinds.map((k) => `<option ${k.id === v.attribute_kind ? "selected" : ""}>${esc(k.id)}</option>`).join("")}</select></label>
            <label>Unit<input data-v="${i}" data-k="unit" value="${esc(v.unit ?? "")}" size="7"></label>
            <label title="Its usual level, in its unit">Typical<input data-v="${i}" data-k="typical" type="number" step="any" value="${v.typical ?? ""}" size="7"></label>
            <label title="How much it varies: a fraction for prices and flows (0.06 = ±6%), units for rates">Spread<input data-v="${i}" data-k="spread" type="number" step="any" value="${v.spread ?? ""}" size="6"></label>
            <button class="ghost small" data-del-value="${i}" aria-label="Remove">✕</button></div>`).join("") || `<p class="small muted">None: interactions can connect values already in the model.</p>`}</section>
        <section class="mf-sec"><h4>Interactions <button class="linkish small" data-add-int>+ add an interaction</button></h4>
          ${spec.interactions.map((it, i) => `<div class="mf-row">
            <label>From<select data-i="${i}" data-k="source">${valueOptions(it.source)}</select></label>
            <label>To<select data-i="${i}" data-k="target">${valueOptions(it.target)}</select></label>
            <label>It<select data-i="${i}" data-k="polarity"><option value="1" ${it.polarity > 0 ? "selected" : ""}>raises</option><option value="-1" ${it.polarity < 0 ? "selected" : ""}>lowers</option></select></label>
            <label title="Standard units of the target per standard unit of the source">Size<input data-i="${i}" data-k="effect" type="number" step="0.05" min="0" max="2" value="${Math.abs(it.effect ?? 0.3)}" size="5"></label>
            <label title="Days before the effect starts">After (days)<input data-i="${i}" data-k="delay_days" type="number" min="0" value="${it.delay_days ?? 14}" size="4"></label>
            <label>Called<input data-i="${i}" data-k="label" value="${esc(it.label ?? "")}" size="12"></label>
            <button class="ghost small" data-del-int="${i}" aria-label="Remove">✕</button></div>`).join("") || `<p class="small muted">None yet.</p>`}</section>
        <section class="mf-sec"><h4>Why you believe it</h4>
          <textarea data-f="note" rows="2" placeholder="Kept with what you add, as an article's words would be">${esc(spec.note ?? "")}</textarea></section>
        <div class="rv-conf"><label for="mf-conf"><b>Your confidence</b></label>
          <input id="mf-conf" type="range" min="0" max="100" step="5" value="${Math.round(100 * spec.confidence)}" data-conf>
          <span class="mono rv-conf-v">${Math.round(100 * spec.confidence)}%</span>
          <span class="small muted">how far it should move the model; you can still change it, and each change's own, in the review</span></div>
        <p class="error small" data-err></p>
      </div>
      <footer class="mf-actions"><button class="primary" data-stage ${busy ? "disabled" : ""}>${busy ? "Staging…" : "Stage it for review"}</button>
        <button data-cancel>Cancel</button></footer>`;
    wire();
  }

  function setPath(path, val) {
    if (path === "note") spec.note = val;
    else if (path === "entity.aliases") spec.entity.aliases = val.split(",").map((x) => x.trim()).filter(Boolean);
    else if (path === "entity.tag") spec.entity.tags = [val];
    else if (path.startsWith("entity.")) {
      spec.entity[path.slice(7)] = val;
      if (path === "entity.name") spec.entity.id = slug(val);
    }
  }

  function wire() {
    pane.querySelector(".close").addEventListener("click", close);
    pane.querySelector("[data-cancel]").addEventListener("click", close);
    pane.querySelector("[data-ent-on]").addEventListener("change", (ev) => {
      spec.entity = ev.target.checked ? { id: "new_entity", name: "", kind: "other", tags: ["SD"], aliases: [] } : null;
      render();
    });
    for (const el of pane.querySelectorAll("[data-f]")) el.addEventListener("input", () => setPath(el.dataset.f, el.value));
    for (const el of pane.querySelectorAll("[data-v]")) {
      el.addEventListener("change", () => {
        const v = spec.values[+el.dataset.v];
        const k = el.dataset.k;
        v[k] = ["typical", "spread"].includes(k) ? (el.value === "" ? null : +el.value) : el.value || null;
        if (k === "name") v.slug = slug(el.value);
        if (k === "attribute_kind") v.family = (vocab?.attribute_kinds ?? []).find((x) => x.id === el.value)?.family;
        render();
      });
    }
    for (const el of pane.querySelectorAll("[data-i]")) {
      el.addEventListener("change", () => {
        const it = spec.interactions[+el.dataset.i];
        const k = el.dataset.k;
        if (k === "polarity") { it.polarity = +el.value; it.effect = Math.abs(it.effect ?? 0.3) * it.polarity; }
        else if (k === "effect") it.effect = Math.abs(+el.value) * (it.polarity ?? 1);
        else if (k === "delay_days") it.delay_days = +el.value;
        else it[k] = el.value;
      });
    }
    pane.querySelector("[data-add-value]").addEventListener("click", () => {
      spec.values.push({ slug: `value_${spec.values.length + 1}`, name: "", attribute_kind: "condition_index", unit: "index",
                         family: "gaussian", typical: null, spread: null, entity: spec.entity ? null : store.view?.entities?.[0]?.id });
      render();
    });
    pane.querySelector("[data-add-int]").addEventListener("click", () => {
      const ids = (store.view?.subentities ?? []).map((s) => s.id);
      spec.interactions.push({ source: spec.values[0] ? `new:${spec.values[0].slug}` : ids[0], target: ids[0], label: "affects",
                               polarity: 1, effect: 0.3, delay_days: 14, lag_days: 30 });
      render();
    });
    for (const b of pane.querySelectorAll("[data-del-value]")) b.addEventListener("click", () => { spec.values.splice(+b.dataset.delValue, 1); render(); });
    for (const b of pane.querySelectorAll("[data-del-int]")) b.addEventListener("click", () => { spec.interactions.splice(+b.dataset.delInt, 1); render(); });
    const conf = pane.querySelector("[data-conf]");
    conf.addEventListener("input", () => { spec.confidence = +conf.value / 100; pane.querySelector(".rv-conf-v").textContent = `${conf.value}%`; });
    pane.querySelector("[data-stage]").addEventListener("click", submit);
  }

  async function submit() {
    const err = pane.querySelector("[data-err]");
    if (spec.entity && !spec.entity.name) { err.textContent = "Name the new entity, or untick it."; return; }
    if (spec.values.some((v) => !v.name)) { err.textContent = "Every new value needs a name."; return; }
    if (!spec.values.length && !spec.interactions.length && !spec.entity) { err.textContent = "There is nothing to add yet."; return; }
    busy = true;
    render();
    try {
      const out = exampleId ? await api.runExample(exampleId, spec) : await api.manual(spec);
      const pid = out.proposal_id ?? out.proposal?.id;
      close();
      toast(exampleId ? "Staged: check the review, then approve all, some, or none." : "Staged for your review.");
      if (pid) onProposal?.(pid);
    } catch (e) {
      busy = false;
      render();
      pane.querySelector("[data-err]").textContent = errorText(e);
    }
  }

  async function open(prefill = null, { example = null } = {}) {
    if (!vocab) { try { vocab = await api.vocabulary(); } catch { vocab = { attribute_kinds: [], entity_kinds: ["other"], category_tags: ["SD"] }; } }
    spec = prefill ? structuredClone(prefill) : blank();
    exampleId = example;
    busy = false;
    pane.classList.remove("hidden");
    render();
  }
  function close() { pane.classList.add("hidden"); exampleId = null; }
  const isOpen = () => !pane.classList.contains("hidden");
  return { open, close, isOpen };
}
